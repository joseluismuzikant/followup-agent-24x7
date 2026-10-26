# Architecture

Monorepo with a shared engine and two products. All code, names, comments, and
documentation are in English; product UI copy is in Spanish.

## Layers

Each context has three folders:

- `domain/`: entities, value objects, and repository contracts. Pure Python.
- `application/`: use cases.
- `infrastructure/`: SQLAlchemy, WhatsApp, LangGraph, FastAPI, and other adapters.

`domain` never imports from `application` or `infrastructure`. If both products
need a piece, it belongs in `packages/core`; otherwise, it stays in the product.

## Contexts

In `packages/core`:

- **Tenancy**: customers, plans, onboarding, notifications, and audit log.
- **Identity**: profiles, roles, and global administration.
- **Messaging**: WhatsApp Cloud API and Embedded Signup.
- **Conversation**: follow-up threads, agent runtime, and human handoff.

In `apps/inmo24x7/api`:

- **Leads**: qualification and property visit coordination.
- **Properties**: property import and validation.

Milestone 1 implements Tenancy, its endpoints, and both panels. The remaining
contexts are added in milestones 2 and 3.

## Current boundaries

- No authentication yet: Supabase arrives with onboarding.
- No LangGraph or WhatsApp yet: they arrive with the agent and connection flows.
- API tests use in-memory SQLite; development and production use Postgres.

## Agent

When added, conversation state will live in LangGraph with the Postgres
checkpointer and `thread_id = tenant_id:channel:visitor_id`. Tools will be
declared once and each will have a tested handler. The graph will control the
flow; the LLM will not decide it through prompt rules. The same agent will serve
WhatsApp and the simulator.
