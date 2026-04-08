# Milestone 2 Domain Model and Persistence Plan

## Purpose

This document locks the Milestone 2 domain model direction for the finance productivity agent system.

Milestone 2 prepares the backend for finance workflows, memory, MCP tool state, and eventual AlloyDB migration. It keeps the v1 model intentionally simple while adding the entities needed for the agreed Milestone 1 workflows.

## Design Principles

### Keep V1 Simple

The model should support the first product workflows without becoming a full accounting, budgeting, or knowledge-graph system.

### Profile-Scoped by Default

Users own profiles. Profiles own operational finance state.

This prevents cross-profile leakage and lets one user maintain separate contexts such as personal finance, business finance, or country-specific banking.

### Database as Source of Truth

The database remains the canonical operational memory store.

Google Drive and Google-native artifacts may store human-readable notes and prompt-loadable instruction assets, but the DB should hold structured references and operational state.

### AlloyDB Later

The schema should be structured enough to migrate to AlloyDB later, but v1 does not need AlloyDB before the domain model stabilizes.

## Ownership Model

### User

Owns authentication identity and profiles.

### Profile

Owns all operational finance state:

- accounts
- transactions
- budgets
- financial goals
- memory facts
- categorization rules
- cash allocations
- recurring commitments
- workflow runs
- tool sync state
- agent instruction assets

## V1 Entities

### `accounts`

First-class in v1.

Purpose:

- represent bank accounts, cards, wallets, or other transaction sources
- support cross-bank grouping and account-level analysis
- store default account currency and labels

V1 behavior:

- accounts are auto-created from ingestion where possible
- users may later edit metadata, aliases, and labels
- manual account creation is not the main onboarding path

Suggested fields:

- `id`
- `profile_id`
- `account_name`
- `institution_name`
- `account_type`
- `currency`
- `external_ref`
- `created_at`
- `updated_at`

### `transactions`

Canonical first-class financial ledger.

Purpose:

- store normalized transaction records from Drive-ingested statements
- preserve original currency and USD/reporting currency values
- support analysis, budgeting, goals, and cash allocation

V1 correction policy:

- keep corrections simple
- editable fields:
  - `category`
  - `clean_name`
  - optional short user note
- not editable in v1:
  - amount
  - date
  - account linkage

Cash withdrawal breakdowns belong in `cash_allocations`, not in transaction mutation logic.

Suggested additional fields beyond current model:

- `profile_id`
- `account_id`
- `user_note`

### `budgets`

First-class in v1.

Purpose:

- support structured budget constraints for planning and review workflows
- avoid burying budget math in generic memory

V1 scope:

- simple recurring budget limits

Example:

- subscriptions <= 2000 INR monthly

Suggested fields:

- `id`
- `profile_id`
- `name`
- `scope`
- `category`
- `amount`
- `currency`
- `cadence`
- `status`
- `created_at`
- `updated_at`

### `financial_goals`

First-class in v1.

Purpose:

- store explicit user commitments and goals
- support planning questions and reminders

V1 scope:

- recurring or target-based commitments only
- no complex portfolio modeling

Examples:

- monthly SIP of 100 HKD
- monthly savings target
- recurring transfer plan

Suggested fields:

- `id`
- `profile_id`
- `goal_type`
- `title`
- `target_amount`
- `currency`
- `cadence`
- `start_date`
- `status`
- `created_at`
- `updated_at`

### `memory_facts`

Generic explicit-memory table.

Purpose:

- store user-provided finance facts and instructions
- keep generic memory separate from structured budgets and goals

V1 policy:

- memory is written only from explicit user instructions
- the system should not automatically store inferred facts in v1

Examples:

- "Octopus expenses are transportation"
- "I prefer to track cash groceries separately"
- "This withdrawal was for groceries and knick knacks"

Suggested fields:

- `id`
- `profile_id`
- `fact_type`
- `content`
- `currency`
- `effective_date`
- `linked_transaction_id`
- `status`
- `created_at`
- `updated_at`

### `categorization_rules`

Dedicated table separate from generic memory.

Purpose:

- store category and merchant rules that can be applied to transaction interpretation

V1 scope:

- example-first rather than a full rule engine

Examples:

- Octopus -> Transportation
- merchant pattern -> category

Suggested fields:

- `id`
- `profile_id`
- `match_type`
- `match_value`
- `category`
- `clean_name`
- `confidence`
- `source_memory_fact_id`
- `status`
- `created_at`
- `updated_at`

### `cash_allocations`

Dedicated table in v1.

Purpose:

- split a cash withdrawal into tagged uses without overcomplicating transaction correction

Example:

- 500 HKD withdrawal:
  - groceries
  - knick knacks

Suggested fields:

- `id`
- `profile_id`
- `transaction_id`
- `category`
- `amount`
- `currency`
- `description`
- `created_at`
- `updated_at`

### `recurring_commitments`

Dedicated table in v1.

Purpose:

- distinguish detected recurring patterns from confirmed obligations or subscriptions
- support planning, budget checks, and calendar reminders

Suggested fields:

- `id`
- `profile_id`
- `name`
- `merchant_pattern`
- `amount`
- `currency`
- `cadence`
- `next_expected_date`
- `status`
- `source`
- `created_at`
- `updated_at`

### `workflow_runs`

Generic workflow execution table.

Purpose:

- track multi-step agent workflows
- attach artifacts, statuses, and tool actions to a run
- support debugging and later observability

V1 workflow types:

- `monthly_review`
- `goal_planning`
- `memory_capture`
- `general_finance_query`

Suggested fields:

- `id`
- `profile_id`
- `workflow_type`
- `status`
- `user_request`
- `result_summary`
- `started_at`
- `completed_at`
- `metadata`

### `tool_sync_state`

Generic MCP/tool sync state table.

Purpose:

- keep external tool state out of profile fields
- support Drive, Calendar, and Google-native note artifact references

V1 scope:

- one generic table keyed by profile and tool

Suggested fields:

- `id`
- `profile_id`
- `tool_name`
- `connection_status`
- `external_account_ref`
- `resource_ref`
- `last_synced_at`
- `sync_cursor`
- `metadata`
- `created_at`
- `updated_at`

### `agent_instruction_assets`

First-class v1 metadata table for prompt-loadable instruction memory.

Purpose:

- store and index richer guidance that agents can load on demand
- separate operational memory from longer instruction-like artifacts

Storage policy:

- actual long-form content may live as a Google-native artifact
- DB stores metadata and references
- DB remains the index and source of structured state

Suggested fields:

- `id`
- `profile_id`
- `asset_type`
- `title`
- `google_file_id`
- `summary`
- `topics`
- `version`
- `is_active`
- `created_at`
- `updated_at`

## Instructional Memory Layer

Instructional memory is separate from canonical operational memory.

It can contain:

- richer agent-controlled guidance
- user-specific finance heuristics
- prompt-loadable domain context
- longer-form instructions stored as Google-native artifacts

Agents can load these assets on demand as prompt context.

The DB should still store the searchable index and references.

## V1 Simplifications

The following are intentionally deferred:

- full transaction overlay/audit system
- complex budget plans with many line items
- portfolio modeling
- automatic memory writes from inferred behavior
- full rule-engine categorization
- multiple Drive folders per profile
- manual upload UX

## Required V1 Tables

Milestone 2 locks these as first-class v1 entities:

- `accounts`
- `transactions`
- `budgets`
- `financial_goals`
- `memory_facts`
- `categorization_rules`
- `cash_allocations`
- `recurring_commitments`
- `workflow_runs`
- `tool_sync_state`
- `agent_instruction_assets`

## Recommended Implementation Order

1. Add profile-scoped model classes for new entities
2. Add service/repository boundaries for profile-owned state
3. Move Google Drive OAuth/tool state out of `profiles` toward `tool_sync_state`
4. Add memory and categorization services
5. Add goal and budget services
6. Add workflow run tracking
7. Prepare the persistence layer for AlloyDB migration

## Exit Criteria

Milestone 2 is complete when:

- the v1 entities are represented in the backend schema
- profile ownership is consistent across operational entities
- budgets and goals are structured, not free-form memory only
- memory facts and categorization rules are separate
- cash allocations can represent withdrawal breakdowns
- workflow runs can track agent workflows
- MCP/tool state has a dedicated persistence home
- instruction assets can be indexed and loaded by agents
