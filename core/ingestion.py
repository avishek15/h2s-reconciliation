"""
Ingestion pipeline: extract raw text from uploaded files, then normalize
to structured transaction records using Gemini.
"""
import asyncio
import base64
import io
import json
import re

from google.genai import types as genai_types

from core.gemini_client import get_gemini_client, get_gemini_model_id


model_id = get_gemini_model_id()


# ── Phase 1: Extract raw text ──────────────────────────────────────────────

async def extract_text(filename: str, mime_type: str, content_b64: str) -> str:
    """
    Extract raw text from an uploaded file.
    CSV/text: decode directly.
    Excel: convert via pandas.
    PDF / image: call Gemini vision to extract text content.
    """
    raw = base64.b64decode(content_b64)

    # Plain text / CSV — decode directly
    if mime_type in ("text/csv", "text/plain"):
        return raw.decode("utf-8", errors="replace")

    # Excel — pandas → CSV string
    if mime_type in (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.ms-excel",
    ):
        try:
            import pandas as pd
            df = pd.read_excel(io.BytesIO(raw))
            return df.to_csv(index=False)
        except Exception as exc:
            return f"[Excel read error for {filename}: {exc}]"

    # PDF — Gemini vision
    if mime_type == "application/pdf":
        def _call():
            return get_gemini_client().models.generate_content(
                model=model_id,
                contents=[
                    genai_types.Part(
                        inline_data=genai_types.Blob(mime_type="application/pdf", data=raw)
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
            return resp.text or ""
        except Exception as exc:
            print(f"[Ingestion] PDF extraction error for {filename}: {exc}")
            return ""

    # Image — Gemini vision
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
            return resp.text or ""
        except Exception as exc:
            print(f"[Ingestion] Image extraction error for {filename}: {exc}")
            return ""

    return ""


# ── Phase 2: Normalize extracted text → structured transactions ───────────

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


async def normalize_to_transactions(filename: str, text: str) -> list[dict]:
    """
    Call Gemini to parse extracted text into a list of structured transaction dicts.
    Returns empty list if the document is not a bank statement or parsing fails.
    """
    if not text.strip():
        return []

    prompt = _NORMALIZE_PROMPT.format(text=text[:120_000])  # stay within token budget

    def _call():
        return get_gemini_client().models.generate_content(
            model=model_id,
            contents=[genai_types.Part(text=prompt)],
        )

    try:
        resp = await asyncio.to_thread(_call)
        raw = resp.text or ""
    except Exception as exc:
        print(f"[Ingestion] Transaction normalization error for {filename}: {exc}")
        return []

    # Direct JSON parse
    try:
        result = json.loads(raw)
        if isinstance(result, list):
            return result
    except json.JSONDecodeError:
        pass

    # Regex fallback — find first [...] block
    match = re.search(r"\[.*\]", raw, re.DOTALL)
    if match:
        try:
            result = json.loads(match.group())
            if isinstance(result, list):
                return result
        except json.JSONDecodeError:
            pass

    return []
