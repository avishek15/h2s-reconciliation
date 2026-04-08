# Finance Productivity Agents Roadmap

## Purpose

This roadmap turns the finance productivity agent design into milestone-based next steps for the `feature/finance-productivity-agents` branch.

The recommended build strategy is:

- keep the existing multi-currency, multi-bank reconciliation core
- reshape the domain around finance workflows, memory, and action orchestration
- add MCP integrations where they enable real user action
- defer AlloyDB until the data model and persistence boundaries are stable

## Milestone 1: Product Contract and Workflow Definition

### Goal

Lock the first version of the product around a small number of concrete workflows.

### Scope

- define the v1 hero workflow: `Monthly Finance Review`
- define 2 secondary workflows:
  - `Subscription Budget Control`
  - `Cash Tagging and Memory Capture`
- define the user intent categories the coordinator agent must recognize
- define the MCP responsibilities for calendar, notes, and drive

### Deliverables

- workflow specs with inputs, outputs, and agent/tool involvement
- coordinator decision map for routing requests
- API-level description of the main workflow endpoints

### Exit Criteria

- every example user request maps to a clear workflow
- the v1 surface area is intentionally limited
- there is agreement on what is in v1 versus deferred

## Milestone 2: Domain Model and Persistence Refactor

### Goal

Refactor the backend data model from finance-reporting only into finance workflow infrastructure.

### Scope

- review current schema and keep reusable entities
- introduce or plan entities for:
  - `accounts`
  - `budgets`
  - `financial_goals`
  - `memory_facts`
  - `categorization_rules`
  - `cash_allocations`
  - `workflow_runs`
  - `tool_sync_state`
- introduce a storage boundary so the app is not tightly coupled to SQLite

### Deliverables

- updated schema design
- repository/service layer for persistence access
- migration strategy from current SQLite state

### Exit Criteria

- the new entities support goals, memory, workflow state, and MCP sync state
- agent logic can depend on services instead of raw tables
- the codebase is structurally ready for AlloyDB later

## Milestone 3: Memory Layer

### Goal

Add durable financial memory so the system can remember user-specific rules, annotations, and decisions.

### Scope

- support stored facts such as:
  - `Octopus = Transportation`
  - subscription budget caps by currency
  - cash withdrawal allocations
  - personal finance goals like monthly SIPs
- support retrieval of relevant memory during user workflows
- support updates, corrections, and overwrites

### Deliverables

- memory storage schema and service
- API endpoints or internal service methods for writing and retrieving memory
- rule-application logic for categorization and transaction interpretation

### Exit Criteria

- the system can store and reapply user-defined rules
- cash tagging and merchant/category correction work durably across sessions
- planning and reconciliation logic can consume stored memory

## Milestone 4: Agent Architecture Refactor

### Goal

Move from a single finance narrative agent into a coordinator plus specialized finance sub-agents.

### Scope

- define the `Coordinator/Objectives Agent`
- define the `Reconciliation Agent`
- define the `Planning Agent`
- define the `Memory Management Agent`
- create the contracts between them

### Deliverables

- agent orchestration flow
- shared structured payloads between agents
- routing logic for user intents and workflow steps

### Exit Criteria

- the coordinator can delegate work to the correct finance sub-agent
- the system supports multi-step workflows without hardcoded endpoint chaining
- agent responsibilities are narrow enough to evolve independently

## Milestone 5: MCP Integration Layer

### Goal

Add MCP-connected tools that turn financial insights into action.

### Scope

- Drive MCP for statement ingestion and document workflows
- Notes MCP for summaries, annotations, and user context capture
- Calendar MCP for reminders, review cadences, and planned commitments

### Deliverables

- MCP adapter layer with tool wrappers
- normalized internal interface for tool invocation and error handling
- persisted tool sync state

### Exit Criteria

- the system can ingest from drive, write review notes, and create calendar reminders
- MCP tool failures are captured and recoverable
- tool usage is visible at the workflow level

## Milestone 6: Monthly Finance Review End-to-End

### Goal

Ship one strong, demonstrable workflow that uses agents, memory, persistence, and MCP tools together.

### Scope

- pull or upload statements
- reconcile across currencies and banks
- detect subscriptions, anomalies, and cash-flow issues
- apply user memory and categorization rules
- generate a review summary
- write a note artifact
- create calendar follow-ups where appropriate

### Deliverables

- end-to-end API flow
- representative demo data and test scenario
- user-facing result payload for the monthly review

### Exit Criteria

- a user can complete the monthly review flow from ingestion to action
- the workflow uses more than one agent and more than one tool
- the system demonstrates real coordination rather than isolated analysis

## Milestone 7: Planning and Goal Support

### Goal

Support budget-aware and goal-aware questions that use financial memory plus transaction context.

### Scope

- subscription budget checks in user-selected currency
- affordability checks for new commitments such as SIPs
- budget-fit explanations such as "where can I find this in my budget?"

### Deliverables

- budget and goal query logic
- currency-aware planning responses
- persisted goal definitions

### Exit Criteria

- the system can answer the budget and SIP examples accurately
- planning logic works across multiple currencies and stored constraints

## Milestone 8: AlloyDB Migration

### Goal

Replace SQLite persistence with AlloyDB once the domain model and workflow interfaces are stable.

### Scope

- prepare production-grade database configuration
- migrate schema and connection management
- validate transactional behavior for workflow and memory updates

### Deliverables

- AlloyDB-ready configuration and deployment setup
- migration scripts
- compatibility validation across the main workflows

### Exit Criteria

- the core workflows work against AlloyDB without application-level redesign
- persistence and agent logic remain cleanly separated

## Milestone 9: Hardening and Demonstration Readiness

### Goal

Prepare the system for demonstration and evaluation.

### Scope

- add tests for key workflow paths
- add observability around workflows and tool calls
- tighten auth and profile isolation
- refine demo scripts and setup instructions

### Deliverables

- smoke tests for core flows
- workflow-level logging
- updated README and demo instructions

### Exit Criteria

- the happy-path workflows are reproducible
- the failure modes are understandable
- the system is ready to present as an MCP-enabled multi-agent finance workflow platform

## Recommended Immediate Next Steps

The next work should happen in this order:

1. finalize Milestone 1 workflow definitions
2. implement Milestone 2 persistence and domain refactor
3. add Milestone 3 memory support
4. refactor into the Milestone 4 coordinator/sub-agent model
5. wire Milestone 5 MCP tools
6. ship Milestone 6 monthly review

## Suggested First Cut for Implementation

If we want the shortest path to something demonstrable, the first implementation slice should be:

1. define memory facts and categorization rules
2. add a basic coordinator that routes to reconciliation, planning, or memory actions
3. support note creation and calendar reminder creation through MCP
4. ship one monthly finance review endpoint that uses all of the above

That gives the project a real agent-and-tools story quickly, without waiting for the full AlloyDB migration.
