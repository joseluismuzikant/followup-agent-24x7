# Hybrid lead agent: a bounded tool-calling step (design, for later)

Status: **not built**. The supported design today is the hardened planner: `plan_turn`
decides, the model words each step, and `ANSWER_QUESTION` answers from the options already
shown ([`go-live.md`](go-live.md), 12c). This file keeps the design of the next step so it
is not lost. When to build it is in [`roadmap-mvp.md`](roadmap-mvp.md), section 4, "Agente
con herramientas (híbrido), para más adelante".

The governing rule stays the same: **the model proposes, the application authorizes.** No
limit, counter or termination is ever in a prompt, a model output, or changed by one.

## Architecture

```
START → guard_input → extract → [router] → assist? → reconcile → respond → guard_output → END
```

### The router (deterministic)

The `assist` node runs only when every one of these holds:

- `LEAD_AGENT_MODE` is `hybrid` (or `shadow`), and the tenant is on the allowlist;
- the turn has no opt-out and the thread has no hand-off;
- `needs_answer` is set, but the `ANSWER_QUESTION` data cannot answer it (the topic is a
  comparison or a search beyond the shown options, or the simple answer would be deferred);
- the per-conversation caps are not spent (assist turns per conversation, per day).

### One agent, read-only tools

There is one tool-calling agent: no multi-agent setup, and no tool that writes anything.

| Tool | What it returns |
| --- | --- |
| `get_offered_property(card_id)` | One shown card: its fields, effective conditions and `condiciones` text |
| `compare_offered(card_ids, by)` | The shown cards ordered by price, rooms or fit |
| `check_requirements(card_id)` | What the card asks, and what the lead's answers meet |
| `search_preview(changes)` | Published listings for a changed search; titles and prices only, nothing is offered yet |
| `agency_info()` | Business name, team hours, whether the team is in now |

### The ToolGateway

Every tool call goes through it, in this order:

1. **Allowlist:** only the five tools above, and only the ones the mode allows.
2. **Execution Guard** (phase 1's, plus the assist limits below):
   - iterations;
   - tool calls per turn and per tool;
   - identical-call detection;
   - retries;
   - the deadline and the tokens.
3. **Arguments:** Pydantic models with `extra="forbid"` and `strict=True`. Anything else is a
   denied call.
4. **Scope checks:**
   - card ids must belong to this thread's `offered_cards`;
   - `tenant_id` comes only from a `TrustedContext` the runtime builds, never from the
     model.
5. **Result sanitising:** `sanitize_untrusted` on every imported string, with caps, and the
   results go inside the DATA envelope.
6. **Audit:** tool name, outcome code (allowed, denied: reason) and latency. Never
   arguments with lead text.

### Proposals, authorized by code

- The agent returns an answer text plus **at most one proposal** from a closed set:
  `choose_property(card_id)`, `change_search(changes)`, `request_human` or `none`.
- A deterministic **`reconcile`** node authorizes the proposal and maps it to state keys
  that `plan_turn` already understands:
  - `turn_choice`;
  - `turn_refine_search` with the validated answers;
  - `turn_wants_human`.
- These are **never** agent actions: visit slots, visit confirmation, the hand-off itself,
  opt-out, and contact data. They stay with the planner and the existing tools.
- The answer text goes through `guard_output` like any reply. Grounding is checked against
  the tool results the gateway returned in this turn.

### State

- No agent messages are persisted in the checkpoint. The agent's conversation (tool calls
  and results) lives only inside the node, for one turn.
- What persists is what `reconcile` mapped, plus counters computed by code (`assist_turns`,
  `assist_denials`).

## Modes and providers

- **`shadow`:** the assist runs and is logged (the proposal, the gateway's decisions, the
  answer it would have sent), but the lead gets the planner's turn as today.
- **`hybrid`:** the assist's answer and authorized proposal go out, per tenant on the
  allowlist.
- **`AGENT_LLM_MODEL`:** the assist may use a stronger model than extract and reply, priced
  in `llm_prices.toml` and recorded in `llm_usage` with its own operation.
- **Provider support:** confirm tool calling for each provider before allowing it. OpenAI
  and Anthropic support it. DeepSeek, Kimi and MiMo are still to be verified (their
  OpenAI-compatible endpoints, parallel calls, and strict JSON arguments).

## Assist limits (on top of phase 1's guard)

| Limit | Value |
| --- | --- |
| Iterations (model calls inside the assist) | 3 |
| Tool calls per turn | 4 |
| Calls per tool | 2 |
| Retries of a failed tool call | 1 |
| Assist deadline | 8 s |

When any of these stops the assist, its partial work is dropped and the planner's turn goes
out as today. The turn is never left without a reply.

## Phases

1. **(2) Core:** the `ToolGateway`, a tool-calling port next to `LanguageModel`, and a
   scripted fake model for tests (tool calls, loops, bad arguments, out-of-scope ids).
2. **(3) inmo24x7:** the assist node and `reconcile` behind `LEAD_AGENT_MODE`, with the
   five tools.
3. **(4) Rollout:**
   - the adversarial suite (injection in titles, `condiciones`, lead text and tool
     results);
   - then `shadow` for a few weeks;
   - then `hybrid` per tenant.

   Grafana alerts on gateway denials, guard blocks and terminations.
