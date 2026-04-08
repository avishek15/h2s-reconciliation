# Milestone 1 Workflow Definition

## Purpose

This document locks the Milestone 1 product contract for the finance productivity agent system.

Milestone 1 is not implementation work. It defines the v1 workflow boundaries, intent taxonomy, tool usage, and memory behavior that later schema and agent architecture work must follow.

## V1 Product Shape

The product is a finance productivity copilot for freelancers and solopreneurs with cross-border accounts and currencies.

It is built around:

- Drive-only statement ingestion
- multi-bank and multi-currency consolidation
- agent-driven workflow orchestration
- persistent financial memory
- Google OAuth-based external tool access

## Authentication Model

### App Authentication

- username/password login remains the app authentication model for v1

### External Tool Authentication

- all external tool access is OAuth-based
- end users should not manage API keys
- Google OAuth should be the user-facing connection model for:
  - Drive access
  - Calendar access
  - Google-native notes artifact creation

## Data Ingestion Contract

### Ingestion Policy

- v1 is Drive-only
- manual uploads are no longer part of the product direction

### Drive Organization

- one Drive folder per profile
- one connected Google account per profile
- users place statements into the connected folder

This keeps ingestion predictable and simplifies profile-level workflow execution.

## V1 Workflows

Milestone 1 locks three v1 workflows.

### 1. Monthly Finance Review

This is the v1 hero workflow.

#### Trigger

- manual trigger by the user
- the workflow pulls the latest statements from the profile’s connected Drive folder

#### Output Contract

Every monthly finance review must produce:

- a cross-account, cross-currency summary
- a list of subscriptions and recurring obligations
- a list of anomalies or items needing review
- a review artifact written as a Google-native note artifact
- automatic calendar reminders for high-confidence follow-ups

#### Anomaly Scope

The review should focus on:

- recurring charges
- new recurring charges
- unusual transactions
- amount spikes
- uncategorized or ambiguous cash spending
- items that threaten budgets or goals

This keeps the review useful without making it noisy.

#### Notes Behavior

- one note artifact per review run
- the note acts as a durable review record and audit trail

#### Calendar Behavior

- reminders should be created automatically for high-confidence follow-ups
- examples include renewals, bill dates, and scheduled review checkpoints

### 2. Goal Planning

This workflow supports questions about financial commitments and budget fit.

#### Example Questions

- "I want to start an SIP of 100 HKD every month. Where can I fit this in my budget?"
- "Can I afford this new recurring commitment?"

#### Behavior

- answer planning and affordability questions using transactions, budgets, and memory
- persist goals when the user explicitly commits to them
- create reminders when appropriate after commitment

### 3. Cash Tagging and Memory Capture

This workflow captures explicit corrections and financial memory.

#### Example Actions

- "Track this 200 HKD cash spend as weekly groceries."
- "This 500 HKD cash withdrawal went to groceries and other knick knacks."
- "Octopus expenses are transportation."

#### Behavior

- operate as a standalone workflow
- also be reusable internally by other workflows
- store durable financial memory facts and categorization rules

## Memory Write Policy

### Policy

- persistent memory is written only from explicit user instructions

### Implications

- the system should not automatically store inferred finance facts in v1
- explicit instructions have priority over existing memory
- memory must remain editable and overridable later

This keeps trust high in the first version.

## Google-Native Notes Artifact Policy

The v1 notes artifact will be Google-native rather than a separate notes provider.

### Rationale

- cleaner OAuth story
- fewer external providers
- lower user friction
- easier alignment with Drive-based ingestion

### Expected Usage

- monthly review artifact creation
- durable finance review records
- future extension point for summaries and annotations

## Coordinator Intent Taxonomy

The coordinator agent should initially route requests into four intent classes:

1. `monthly_review`
2. `goal_planning`
3. `memory_capture`
4. `general_finance_query`

### Intent Meanings

#### `monthly_review`

Used when the user wants a consolidated review of recent financial activity.

#### `goal_planning`

Used when the user wants planning support, affordability analysis, or commitment evaluation.

#### `memory_capture`

Used when the user is explicitly tagging, correcting, or storing financial context.

#### `general_finance_query`

Used for standard finance Q&A that does not clearly require a workflow write action.

## Agent Roles Implied by Milestone 1

Milestone 1 decisions imply the following eventual routing model:

- coordinator agent selects workflow/intent
- reconciliation agent powers review understanding
- planning agent powers affordability and commitment reasoning
- memory management agent stores and retrieves durable rules and facts

This milestone does not require the full implementation yet, but later milestones must preserve this separation.

## Non-Goals for Milestone 1

The following are explicitly out of scope for this milestone definition:

- manual upload flows
- non-OAuth user-managed tool keys
- multiple Drive folders per profile
- automatic memory writes from inferred behavior
- generic productivity workflows outside the finance domain

## Exit Criteria

Milestone 1 is complete when the team has a stable contract for:

- Drive-only ingestion
- Google OAuth tool access
- the three v1 workflows
- explicit-only memory writes
- one-note-per-review artifact creation
- automatic reminder creation for high-confidence follow-ups
- the four coordinator intent classes

## Result

Milestone 1 now defines a focused finance workflow platform rather than a generic assistant:

- reviews are triggered manually
- data comes from Drive
- findings create notes and reminders
- planning persists goals on commitment
- explicit user instructions create durable financial memory
