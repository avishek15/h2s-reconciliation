# Finance Productivity Agents Design

## Summary

This project will evolve from a finance reconciliation app into a finance productivity copilot for freelancers and solopreneurs operating across multiple banks, currencies, and accounts.

The core differentiator remains:

- multi-bank statement consolidation
- multi-currency normalization
- recurring payment and anomaly detection
- profile-based financial context

The new product direction adds agent coordination, durable memory, and MCP-connected execution so the system can not only analyze finances, but also help users act on them.

## Objective

Build an API-based, multi-agent finance workflow system that:

- consolidates financial data across banks and currencies
- understands budgets, goals, recurring obligations, and categorized spend
- stores persistent financial memory and user preferences
- coordinates sub-agents to answer questions and perform multi-step workflows
- uses MCP tools to connect analysis to real user systems such as calendar, notes, and drive

This aligns with the broader submission goal of demonstrating agent coordination, tool usage, structured persistence, and multi-step workflow execution, while staying grounded in a finance-specific domain.

## Target User

Primary target user:

- freelancers and solopreneurs with cross-border income, spending, and business operations

Secondary target user:

- personal finance users with multiple accounts and currencies

Typical user characteristics:

- receives or spends in more than one currency
- uses more than one bank or wallet
- wants clearer visibility into obligations, subscriptions, and cash flow
- needs follow-ups, reminders, and decision support rather than static reports

## Product Thesis

The product should not become a generic productivity assistant.

It should become a finance operations copilot:

- reconcile and understand my money
- remember how I classify and interpret spending
- turn findings into actions, reminders, and notes
- help me plan new financial commitments within real budget constraints

## Example User Requests

Representative use cases include:

- "I only have a budget of 2000 INR for subscriptions. Which subscriptions am I paying for now?"
- "I want to start an SIP of 100 HKD every month. Where can I fit this in my budget?"
- "Track this 200 HKD cash spend as weekly groceries."
- "This 500 HKD cash withdrawal went to groceries and other knick knacks."
- "Octopus expenses should be categorized as transportation."

These examples imply three capabilities beyond statement parsing:

- durable memory
- financial planning and constraint reasoning
- workflow execution via connected tools

## Core Capabilities

### 1. Financial Consolidation

The existing foundation remains central:

- ingest statements from multiple banks
- normalize transactions into a shared schema
- convert values into common reporting currencies while preserving original amounts
- detect recurring spend and anomalies

### 2. Memory-Driven Finance Understanding

The system should remember user-specific facts and rules, such as:

- category mappings
- budget constraints
- cash withdrawal allocations
- user goals and commitments
- merchant interpretations

This memory should be durable, queryable, and revisable.

### 3. Actionable Productivity Layer

Financial insights should lead to action:

- create reminders for bills, reviews, renewals, and SIPs
- store review summaries and manual corrections in notes
- use drive-based ingestion and archival flows

## Agent Architecture

The recommended v1 agent architecture is:

### Primary Coordinator Agent

Responsibilities:

- interpret user intent
- decide which sub-agents to invoke
- sequence multi-step workflows
- assemble final answers and actions

Example:

- user asks about subscription budget
- coordinator invokes reconciliation context, planning logic, and memory retrieval
- coordinator returns answer plus next actions

### Reconciliation Agent

Responsibilities:

- analyze statements and normalized transactions
- identify recurring payments, subscriptions, anomalies, and cash-flow patterns
- provide structured financial context to other agents

### Planning Agent

Responsibilities:

- evaluate affordability and budget fit
- reason about goals such as SIPs or spending caps
- propose changes, tradeoffs, and action plans

### Memory Management Agent

Responsibilities:

- store and retrieve financial memory facts
- maintain categorization rules
- attach annotations to cash withdrawals, merchants, and account behavior
- keep user-specific context available for future workflows

## MCP Integrations

The first MCP tools should be:

### Calendar MCP

Use for:

- bill reminders
- subscription review dates
- monthly financial review events
- planned SIP reminders

### Notes MCP

Use for:

- storing finance review summaries
- writing manual annotations and user corrections
- persisting context such as category rules and spending notes

### Drive MCP

Use for:

- ingesting statements from user folders
- maintaining a profile-to-folder ingestion workflow
- optionally storing generated review artifacts

## V1 Hero Workflow

Recommended hero workflow:

### Monthly Finance Review

Workflow:

1. Pull statements from Drive or manual upload
2. Reconcile transactions across banks and currencies
3. Identify subscriptions, anomalies, and major category spend
4. Retrieve relevant memory such as custom category rules and budget caps
5. Produce a review summary
6. Create follow-up notes and calendar reminders where needed

Why this should be v1:

- it uses the existing reconciliation core
- it naturally exercises multiple agents
- it demonstrates multi-step coordination
- it uses MCP tools in a meaningful way

## V1 Supported Finance Tasks

The first product version should support:

- subscription budget review
- goal-fit questions such as SIP affordability
- cash withdrawal tagging and later allocation
- merchant/category correction memory
- recurring bill and reminder scheduling

## Data Model Direction

The persistence layer should evolve toward the following entities:

- `users`
- `profiles`
- `accounts`
- `transactions`
- `recurring_commitments`
- `budgets`
- `financial_goals`
- `memory_facts`
- `categorization_rules`
- `cash_allocations`
- `workflow_runs`
- `tool_sync_state`

This structure supports both analysis and productivity execution.

## AlloyDB Direction

AlloyDB should be treated as a planned persistence upgrade, not a blocker to product direction.

Recommended approach:

1. abstract persistence boundaries now
2. move schema toward workflow and memory entities
3. keep route and agent logic storage-agnostic where possible
4. replace SQLite with AlloyDB once the domain model stabilizes

The near-term goal is to make the current app logically ready for AlloyDB even if the first implementation still uses SQLite.

## Non-Goals

The product should not try to become:

- a generic productivity assistant
- a generic accounting platform
- a broad consumer fintech dashboard with every possible feature

The focus is financial understanding plus action orchestration.

## Recommended Near-Term Build Order

1. Refine the domain model around goals, budgets, memory, and workflow state
2. Introduce the coordinator plus sub-agent boundaries
3. Add a memory layer and category-rule persistence
4. Add MCP integrations for calendar, notes, and drive
5. Implement the monthly finance review workflow end-to-end
6. Prepare the persistence layer for AlloyDB migration

## Success Criteria

The project is on track when it can:

- ingest and reconcile multi-bank, multi-currency statements
- answer finance questions using both transactions and stored memory
- remember and reuse user-specific categorization and budget constraints
- create follow-up notes and reminders through MCP tools
- demonstrate a coordinator agent orchestrating specialized finance sub-agents

## Recommendation

Proceed with a finance productivity architecture rather than a generic multi-agent productivity app.

This keeps the strongest existing advantage of the project while making the multi-agent and MCP story more compelling, domain-specific, and demonstrably useful.
