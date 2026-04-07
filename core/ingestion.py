"""
Ingestion pipeline: extract raw text from uploaded files, then normalize
to structured transaction records using Gemini.

PDF strategy:
  1. pdfplumber (local, fast, deterministic) — primary path
  2. Gemini vision — fallback for scanned/image-based PDFs
  3. Normalize page-by-page concurrently for large PDFs
"""
import asyncio
import base64
import io
import json
import re
import logging
import time

from google.genai import types as genai_types

from core.gemini_client import get_gemini_client, get_gemini_model_id

logger = logging.getLogger(__name__)

model_id = get_gemini_model_id()

PDF_MIN_CHARS_PER_PAGE = 30
PDF_GEMINI_CHUNK_SIZE = 4
PDF_GEMINI_MAX_CONCURRENT_CHUNKS = 3
NORMALIZE_MAX_CONCURRENT = 2
NORMALIZE_CHARS_PER_CHUNK = 3000


def _extract_pdf_pages_local(pdf_bytes: bytes) -> list[str]:
    try:
        import pdfplumber
    except ImportError:
        logger.warning("pdfplumber not installed")
        return []

    t0 = time.time()
    pages = []
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            logger.info(f"[PDF-LOCAL] Opened PDF: {len(pdf.pages)} pages, {len(pdf_bytes)} bytes")
            for i, page in enumerate(pdf.pages):
                text = page.extract_text() or ""
                pages.append(text)
                logger.info(f"[PDF-LOCAL] Page {i+1}: {len(text)} chars")
    except Exception as exc:
        logger.warning(f"[PDF-LOCAL] pdfplumber failed: {exc}")
        return []

    elapsed = time.time() - t0
    logger.info(f"[PDF-LOCAL] Done in {elapsed:.2f}s — {len(pages)} pages, {sum(len(p) for p in pages)} total chars")
    return pages


def _extract_pdf_local(pdf_bytes: bytes) -> str:
    pages = _extract_pdf_pages_local(pdf_bytes)
    return "\n\n".join(pages) if pages else ""


def _pdf_needs_ocr(pdf_bytes: bytes, extracted_text: str) -> bool:
    try:
        import pdfplumber
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            page_count = len(pdf.pages)
    except Exception:
        page_count = max(1, len(pdf_bytes) // 50000)

    if page_count == 0:
        return False
    chars_per_page = len(extracted_text.strip()) / page_count
    needs_ocr = chars_per_page < PDF_MIN_CHARS_PER_PAGE
    logger.info(f"[PDF-OCR-CHECK] {page_count} pages, {chars_per_page:.0f} chars/page, needs_ocr={needs_ocr}")
    return needs_ocr


def _split_pdf_bytes(pdf_bytes: bytes, chunk_size: int = PDF_GEMINI_CHUNK_SIZE) -> list[tuple[int, bytes]]:
    try:
        import pdfplumber
    except ImportError:
        return [(0, pdf_bytes)]

    chunks = []
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            total = len(pdf.pages)
            if total <= chunk_size:
                return [(0, pdf_bytes)]
            for start in range(0, total, chunk_size):
                end = min(start + chunk_size, total)
                try:
                    import pypdfium2 as pdfium
                    src = pdfium.PdfDocument(pdf_bytes)
                    chunk_doc = pdfium.PdfDocument.new()
                    for i in range(start, end):
                        chunk_doc.import_pages(src, [i])
                    import tempfile
                    with tempfile.NamedTemporaryFile(suffix=".pdf") as tmp:
                        chunk_doc.save(tmp.name)
                        chunk_bytes = open(tmp.name, "rb").read()
                    chunks.append((start, chunk_bytes))
                    logger.info(f"[PDF-SPLIT] Chunk pages {start}-{end-1}: {len(chunk_bytes)} bytes")
                except Exception as e:
                    logger.warning(f"[PDF-SPLIT] Failed at page {start}: {e}")
                    chunks.append((start, pdf_bytes))
                    break
    except Exception as exc:
        logger.warning(f"[PDF-SPLIT] Failed: {exc}")
        chunks = [(0, pdf_bytes)]

    return chunks if chunks else [(0, pdf_bytes)]


async def _extract_pdf_via_gemini(filename: str, pdf_bytes: bytes) -> str:
    t0 = time.time()
    logger.info(f"[GEMINI-EXTRACT] Starting for {filename}, {len(pdf_bytes)} bytes")

    def _call():
        return get_gemini_client().models.generate_content(
            model=model_id,
            contents=[
                genai_types.Part(
                    inline_data=genai_types.Blob(mime_type="application/pdf", data=pdf_bytes)
                ),
                genai_types.Part(text=(
                    "Extract all text from this bank statement PDF. "
                    "Preserve table structure, column headers, and row alignment. "
                    "Output only the raw text — no commentary."
                )),
            ],
        )
    try:
        resp = await asyncio.to_thread(_call)
        elapsed = time.time() - t0
        text = resp.text or ""
        logger.info(f"[GEMINI-EXTRACT] Done for {filename} in {elapsed:.2f}s — {len(text)} chars")
        return text
    except Exception as exc:
        elapsed = time.time() - t0
        logger.error(f"[GEMINI-EXTRACT] FAILED for {filename} after {elapsed:.2f}s: {exc}")
        return ""


async def _extract_pdf_text(filename: str, pdf_bytes: bytes) -> str:
    t0 = time.time()
    logger.info(f"[EXTRACT-PDF] Starting for {filename}, {len(pdf_bytes)} bytes")

    local_text = await asyncio.to_thread(_extract_pdf_local, pdf_bytes)

    if local_text.strip() and not _pdf_needs_ocr(pdf_bytes, local_text):
        elapsed = time.time() - t0
        logger.info(f"[EXTRACT-PDF] Local extraction sufficient for {filename} in {elapsed:.2f}s")
        return local_text

    logger.info(f"[EXTRACT-PDF] Falling back to Gemini for {filename}")

    chunks = await asyncio.to_thread(_split_pdf_bytes, pdf_bytes)
    if len(chunks) <= 1:
        result = await _extract_pdf_via_gemini(filename, pdf_bytes)
        elapsed = time.time() - t0
        logger.info(f"[EXTRACT-PDF] Gemini single-chunk done for {filename} in {elapsed:.2f}s")
        return result

    semaphore = asyncio.Semaphore(PDF_GEMINI_MAX_CONCURRENT_CHUNKS)

    async def _process_chunk(args: tuple[int, bytes]) -> str:
        idx, chunk = args
        async with semaphore:
            return await _extract_pdf_via_gemini(filename, chunk)

    results = await asyncio.gather(*[_process_chunk(c) for c in chunks])
    merged = "\n\n".join(r for r in results if r)
    elapsed = time.time() - t0
    logger.info(f"[EXTRACT-PDF] Gemini multi-chunk done for {filename} in {elapsed:.2f}s — {len(merged)} chars")
    return merged


async def extract_text(filename: str, mime_type: str, content_b64: str) -> str:
    t0 = time.time()
    logger.info(f"[EXTRACT] Starting for {filename} (mime={mime_type})")

    raw = base64.b64decode(content_b64)
    logger.info(f"[EXTRACT] Decoded {len(raw)} bytes for {filename}")

    if mime_type in ("text/csv", "text/plain"):
        result = raw.decode("utf-8", errors="replace")
        elapsed = time.time() - t0
        logger.info(f"[EXTRACT] Text/CSV done for {filename} in {elapsed:.2f}s — {len(result)} chars")
        return result

    if mime_type in (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.ms-excel",
    ):
        try:
            import pandas as pd
            df = pd.read_excel(io.BytesIO(raw))
            result = df.to_csv(index=False)
            elapsed = time.time() - t0
            logger.info(f"[EXTRACT] Excel done for {filename} in {elapsed:.2f}s — {len(result)} chars")
            return result
        except Exception as exc:
            logger.error(f"[EXTRACT] Excel read error for {filename}: {exc}")
            return f"[Excel read error for {filename}: {exc}]"

    if mime_type == "application/pdf":
        try:
            result = await _extract_pdf_text(filename, raw)
            elapsed = time.time() - t0
            logger.info(f"[EXTRACT] PDF done for {filename} in {elapsed:.2f}s — {len(result)} chars")
            return result
        except Exception as exc:
            elapsed = time.time() - t0
            logger.error(f"[EXTRACT] PDF failed for {filename} after {elapsed:.2f}s: {exc}")
            return ""

    if mime_type.startswith("image/"):
        def _call():
            return get_gemini_client().models.generate_content(
                model=model_id,
                contents=[
                    genai_types.Part(
                        inline_data=genai_types.Blob(mime_type=mime_type, data=raw)
                    ),
                    genai_types.Part(text=(
                        "Extract all text from this bank statement image. "
                        "Preserve table structure, column headers, and row alignment. "
                        "Output only the raw text — no commentary."
                    )),
                ],
            )
        try:
            resp = await asyncio.to_thread(_call)
            result = resp.text or ""
            elapsed = time.time() - t0
            logger.info(f"[EXTRACT] Image done for {filename} in {elapsed:.2f}s — {len(result)} chars")
            return result
        except Exception as exc:
            elapsed = time.time() - t0
            logger.error(f"[EXTRACT] Image failed for {filename} after {elapsed:.2f}s: {exc}")
            return ""

    logger.warning(f"[EXTRACT] Unsupported mime type {mime_type} for {filename}")
    return ""


_NORMALIZE_PROMPT = """\
You are a financial data parser.

The text below was extracted from a document. If it looks like a bank statement \
or transaction record, extract every transaction and return a JSON array.
If it is NOT a financial document, return an empty array [].

Each transaction object MUST have exactly these fields:
  "date"        — "YYYY-MM-DD" (convert any date format you find)
  "description" — merchant name or transaction memo as-is from the statement
  "clean_name"  — human-readable merchant/payee name, max 40 chars.
                  Strip UPI refs (UPI/P2M/...), bank codes, account numbers, reference IDs.
                  Examples: "UPI/P2M/102972018264/NETFLIX/HDFC BANK/Executio//P2V/" → "Netflix"
                            "NBSM/135866103/HDFCBANK - BILLDESK/" → "HDFC Bill Payment"
                            "ACH-CR-AartiDrug Int2025 26-NACH-138026" → "Aarti Drug Income"
                            "ATM Cash ATM" → "ATM Withdrawal"
                            "MS MCKEAN ANNA REBECCA" → "Anna Rebecca McKean"
  "amount"      — a NUMBER in the ORIGINAL currency: negative for debit/withdrawal, positive for credit/deposit
  "currency"    — ISO 4217 currency code of the account (e.g. "USD", "HKD", "INR", "EUR", "GBP").
                  Infer from: account header, currency symbols, country codes (HKG=HKD, IN=INR),
                  bank names (HDFC/ICICI/SBI=INR, HangSeng/BOC HK=HKD), or explicit labels.
                  If truly unknown, use "USD".
  "type"        — "debit" or "credit"
  "category"    — a short label you assign (e.g. Groceries, Dining, Transport,
                  Housing, Income, Subscriptions, Utilities, Shopping, Health,
                  Entertainment, Cash, Transfer, ATM, Tax, Other)

Rules:
- amount must be a NUMBER in the original account currency, never a string
- If separate debit/credit columns exist, combine into one signed amount
- Include ALL transactions — do not skip or summarise
- Assign consistent category labels within the document
- Return ONLY the raw JSON array. No markdown fences. No explanation.

Document text:
{text}
"""


def _parse_json_transactions(raw: str) -> list[dict]:
    try:
        result = json.loads(raw)
        if isinstance(result, list):
            return result
    except json.JSONDecodeError:
        pass

    match = re.search(r"\[.*\]", raw, re.DOTALL)
    if match:
        try:
            result = json.loads(match.group())
            if isinstance(result, list):
                return result
        except json.JSONDecodeError:
            pass

    return []


async def _normalize_chunk(filename: str, chunk_idx: int, text: str) -> list[dict]:
    if not text.strip():
        return []

    t0 = time.time()
    logger.info(f"[NORMALIZE-CHUNK] Starting chunk {chunk_idx} for {filename} — {len(text)} chars")

    prompt = _NORMALIZE_PROMPT.format(text=text[:30_000])

    max_retries = 3
    for attempt in range(max_retries + 1):
        def _call():
            return get_gemini_client().models.generate_content(
                model=model_id,
                contents=[genai_types.Part(text=prompt)],
                config=genai_types.GenerateContentConfig(
                    thinking_config=genai_types.ThinkingConfig(thinking_budget=0),
                ),
            )

        try:
            resp = await asyncio.to_thread(_call)
            raw_resp = resp.text or ""
            txns = _parse_json_transactions(raw_resp)
            elapsed = time.time() - t0
            logger.info(f"[NORMALIZE-CHUNK] Chunk {chunk_idx} for {filename} done in {elapsed:.2f}s — {len(txns)} transactions (response: {len(raw_resp)} chars)")
            return txns
        except Exception as exc:
            exc_str = str(exc)
            is_429 = "429" in exc_str or "RESOURCE_EXHAUSTED" in exc_str
            if is_429 and attempt < max_retries:
                wait = 2 ** (attempt + 1)
                elapsed = time.time() - t0
                logger.warning(f"[NORMALIZE-CHUNK] Chunk {chunk_idx} for {filename} got 429, retrying in {wait}s (attempt {attempt+1}/{max_retries}, elapsed {elapsed:.1f}s)")
                await asyncio.sleep(wait)
                continue
            elapsed = time.time() - t0
            logger.error(f"[NORMALIZE-CHUNK] Chunk {chunk_idx} for {filename} FAILED after {elapsed:.2f}s: {exc}")
            return []

    return []


async def normalize_to_transactions(filename: str, text: str) -> list[dict]:
    t0 = time.time()
    logger.info(f"[NORMALIZE] Starting for {filename} — {len(text)} chars")

    if not text.strip():
        logger.info(f"[NORMALIZE] Empty text for {filename}, skipping")
        return []

    if len(text) <= NORMALIZE_CHARS_PER_CHUNK:
        logger.info(f"[NORMALIZE] Small text ({len(text)} chars), single call for {filename}")
        result = await _normalize_chunk(filename, 0, text)
        elapsed = time.time() - t0
        logger.info(f"[NORMALIZE] Single-chunk done for {filename} in {elapsed:.2f}s — {len(result)} transactions")
        return result

    chunks: list[str] = []
    current_chunk: list[str] = []
    current_len = 0

    for line in text.split("\n"):
        line_len = len(line) + 1
        if current_len + line_len > NORMALIZE_CHARS_PER_CHUNK and current_chunk:
            chunks.append("\n".join(current_chunk))
            current_chunk = []
            current_len = 0
        current_chunk.append(line)
        current_len += line_len

    if current_chunk:
        chunks.append("\n".join(current_chunk))

    logger.info(f"[NORMALIZE] Split {filename} into {len(chunks)} chunks (sizes: {[len(c) for c in chunks]})")

    semaphore = asyncio.Semaphore(NORMALIZE_MAX_CONCURRENT)

    async def _limited(idx: int, chunk: str) -> list[dict]:
        async with semaphore:
            return await _normalize_chunk(filename, idx, chunk)

    results = await asyncio.gather(*[_limited(i, c) for i, c in enumerate(chunks)])
    merged: list[dict] = []
    for batch in results:
        merged.extend(batch)
    elapsed = time.time() - t0
    logger.info(f"[NORMALIZE] ALL chunks done for {filename} in {elapsed:.2f}s — {len(merged)} total transactions from {len(chunks)} chunks")
    return merged


async def process_file(filename: str, mime_type: str, content_b64: str) -> list[dict]:
    t0 = time.time()
    logger.info(f"[PROCESS-FILE] === START {filename} (mime={mime_type}) ===")

    text = await extract_text(filename, mime_type, content_b64)
    if not text.strip():
        logger.warning(f"[PROCESS-FILE] No text extracted from {filename}, skipping")
        return []

    txns = await normalize_to_transactions(filename, text)
    elapsed = time.time() - t0
    logger.info(f"[PROCESS-FILE] === DONE {filename} in {elapsed:.2f}s — {len(txns)} transactions ===")
    return txns


async def process_files_concurrently(
    files: list[tuple[str, str, str]],
    max_concurrent: int = 3,
) -> list[list[dict]]:
    t0 = time.time()
    logger.info(f"[BATCH] Processing {len(files)} files concurrently (max_concurrent={max_concurrent})")

    semaphore = asyncio.Semaphore(max_concurrent)

    async def _process_with_semaphore(args):
        filename, mime_type, content_b64 = args
        async with semaphore:
            try:
                return await process_file(filename, mime_type, content_b64)
            except Exception as e:
                logger.error(f"[BATCH] Failed to process {filename}: {e}")
                return []

    tasks = [_process_with_semaphore(f) for f in files]
    results = await asyncio.gather(*tasks)
    elapsed = time.time() - t0
    total_txns = sum(len(r) for r in results)
    logger.info(f"[BATCH] ALL {len(files)} files done in {elapsed:.2f}s — {total_txns} total transactions")
    return results
