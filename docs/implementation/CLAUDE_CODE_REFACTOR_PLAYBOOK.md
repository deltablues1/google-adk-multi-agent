# Claude Code Refactor Playbook

Ovaj dokument je radni playbook za Claude Code ili sličan coding agent.
Cilj nije "veliki rewrite", nego kontrolirano poliranje postojećeg sustava u fazama.

## Način rada

Koristi ove promptove redom.
Ne preskači faze.
Nakon svake faze traži:

1. pregled postojećeg stanja
2. implementaciju najmanjeg sigurnog skupa promjena
3. testove ili barem smoke provjere
4. kratak changelog
5. popis otvorenih rizika

## Global Rules Prompt

Ovo zalijepi na početku svake veće sesije:

```text
You are working in an existing Python multi-agent system repository built around Google ADK, FastAPI, APScheduler, Firestore, Google Workspace APIs, and a Croatian fiscalization workflow.

Your job is to improve the current system incrementally, not rewrite it.

Important constraints:
- Preserve working behavior unless there is a clear bug, security issue, or architectural inconsistency.
- Prefer small, well-scoped changes over large refactors.
- Before editing code, inspect the current implementation and identify the true runtime path.
- Treat source code as the source of truth over README/docs if they conflict.
- When you find legacy/dead code, do not delete aggressively unless you confirm it is unused.
- Keep all changes production-oriented: security, operability, testability, and maintainability matter more than adding new features.
- If a task is too large, split it into phases and implement only the first safe phase.
- After every change, run the narrowest useful verification and summarize risks that remain.

Architecture notes discovered in this repo:
- The system currently mixes ADK runtime paths with older legacy abstractions.
- Web/API, CLI, Telegram, and Scheduler entry points are not fully aligned.
- Some docs describe older architecture and model choices.
- Web deployment security and identity handling are weak and should be treated as high priority.
- Fiscalization is business-critical and must remain deterministic on the critical execution path.
- HITL should move away from terminal-only input toward channel-aware approval flows.

When you respond:
- Start by summarizing what you found in the current code.
- Then propose the smallest safe implementation plan.
- Then implement.
- End with what was changed, how it was verified, and what still needs follow-up.
```

## Phase 1 Prompt

Koristi ovo za prvi ozbiljan radni paket.
Fokus je stabilizacija i smanjenje rizika bez velikog refaktora.

```text
Task: Phase 1 stabilization and security hardening.

Work inside this repository and implement only Phase 1 changes.

Goals:
- Remove the most immediate security and runtime risks.
- Align the real runtime paths across interfaces.
- Avoid large architectural rewrites.

Priority issues to address:
1. Web security hardening
   - Inspect FastAPI routes, deployment config, and frontend user identity handling.
   - Remove obviously unsafe defaults for production-oriented deployment.
   - Introduce the smallest viable authentication or at least a secure gating mechanism if full auth is too large for one step.

2. Runtime path alignment
   - Inspect CLI, web non-streaming, web streaming, Telegram, and scheduler execution paths.
   - Eliminate broken or stale references such as legacy routing objects if they are still in active paths.
   - Make sure all user-facing interfaces use the same orchestrator execution path where practical.

3. Scheduler isolation
   - Inspect how the scheduler is initialized.
   - Prevent scheduler startup as an accidental side effect of unrelated app startup paths if this is happening now.
   - Keep existing scheduler functionality intact.

4. Secret and credential hygiene
   - Remove hardcoded fallback secrets/passwords from active runtime code.
   - Prefer environment-variable-only behavior if secret manager integration is too large for this phase.
   - Do not break local development unnecessarily; if needed, fail clearly instead of silently using insecure defaults.

Implementation rules:
- First inspect the relevant files and explain the current behavior.
- Then implement the smallest safe set of changes.
- Add or update tests where reasonable.
- If existing tests are outdated, note that clearly and add focused smoke coverage for the actual runtime path.

Expected output:
- A concise analysis of the current active runtime path.
- The implemented Phase 1 changes.
- Verification steps performed.
- A short list of remaining Phase 2 issues.
```

## Phase 2 Prompt

Ovo koristi nakon što je Phase 1 stabilan.
Ovdje je cilj konsolidacija, ne novi feature set.

```text
Task: Phase 2 runtime consolidation.

Now that the immediate security and startup risks are reduced, improve architectural coherence without rewriting the project.

Goals:
1. Session and memory coherence
   - Inspect how UI history, Firestore persistence, and ADK session memory currently interact.
   - Design and implement a coherent session strategy so that the system has one clear source of truth for conversational continuity.
   - Preserve existing user-visible history behavior where possible.

2. HITL redesign foundation
   - Inspect the current human-in-the-loop flow, especially for fiscalization.
   - Remove terminal-only assumptions from the approval mechanism.
   - Implement a channel-aware approval model foundation that can work with web and messaging interfaces.
   - Do not fully build every UI; focus on backend flow and persistence model first.

3. Legacy boundary cleanup
   - Identify which legacy abstractions are still active and which are compatibility leftovers.
   - Reduce coupling between legacy code paths and current ADK paths.
   - Add comments or small structural cleanup to clarify what is active, deprecated, or transitional.

Rules:
- Do not attempt a full rewrite.
- Preserve business-critical fiscalization behavior.
- Favor explicit, documented boundaries over broad cleanup.
- Where code cannot yet be removed safely, mark the boundary clearly and reduce accidental usage.

Expected output:
- A short architecture note describing the new runtime boundaries.
- The implemented consolidation changes.
- Verification and residual risks.
```

## Phase 3 Prompt

Ovo je trenutak za pripremu pravih novih capabilityja i integracija.

```text
Task: Phase 3 foundation for business integrations.

Prepare the system for future integrations without implementing every external connector yet.

Goals:
1. Introduce an integration architecture
   - Create a clear pattern for external business system connectors.
   - Separate connector configuration, authentication, domain mapping, and orchestration.
   - Avoid provider-specific spaghetti logic inside agent code.

2. Define domain events / audit shape
   - Introduce a minimal event model for important business actions:
     request_received, approval_requested, approval_completed, invoice_fiscalized, job_executed, integration_sync_started, integration_sync_completed, integration_sync_failed.
   - Reuse existing audit/persistence patterns when possible.

3. Prepare adapter points for:
   - ERP/accounting
   - Slack/Teams approvals
   - Banking/PSD2 reconciliation
   - Peppol/e-invoice delivery
   - Analytics export to BigQuery

4. Keep implementation lightweight
   - Build interfaces, models, and at most one thin example adapter if helpful.
   - Do not attempt to fully implement all third-party integrations in one pass.

Expected output:
- Proposed integration architecture based on current code.
- Minimal implementation establishing extension points.
- Notes on which provider should be implemented first and why.
```

## Dedicated Prompt: Web Security

Ako želiš posebno riješiti web bez distrakcija:

```text
Audit and harden the web interface in this repository.

Focus areas:
- FastAPI route exposure
- deployment defaults
- frontend identity assumptions
- file upload and media serving
- session isolation
- unsafe production defaults

Your process:
1. Inspect the current web app, frontend, and deployment path.
2. Identify the actual active risks in the current code.
3. Implement the smallest viable hardening changes first.
4. Add focused verification for login/session/access behavior.

Do not redesign the whole frontend.
Do not add speculative features.
Prioritize real risk reduction.
```

## Dedicated Prompt: HITL and Fiscalization

Ako želiš fokus samo na fiskalizaciju i approval workflow:

```text
Audit and improve the fiscalization workflow in this repository, especially the human-in-the-loop path.

Goals:
- Keep deterministic execution for the critical path.
- Preserve current working fiscalization behavior.
- Remove terminal-only approval assumptions.
- Establish a persistent approval model suitable for web and messaging interfaces.

Inspect carefully:
- the fiscalization agent wrapper
- the orchestrator
- approval/HITL functions
- persistence model
- where skip_llm, approval flags, and environment variables affect behavior

Then implement:
- a safer approval state flow
- explicit approval statuses
- persistence for pending approvals
- the smallest channel-neutral API/service layer for approve/reject actions

Do not overbuild UI.
Do not replace deterministic execution with LLM logic.
```

## Dedicated Prompt: Session and Memory Cleanup

Ako želiš srediti continuity i state:

```text
Inspect how conversation state works across CLI, web, scheduler, Telegram, Firestore persistence, and ADK runner sessions.

I want a coherent design for session identity, message history, trace events, and LLM memory continuity.

Your task:
1. Map the current state flow from each interface to the runner/session layer.
2. Identify mismatches between displayed history and actual model memory.
3. Propose the smallest safe target design.
4. Implement the first practical consolidation step.

Constraints:
- Preserve existing user-visible history where possible.
- Avoid a big migration if a bridge layer is enough.
- Explain exactly which component becomes the source of truth.
```

## Dedicated Prompt: Integration Foundations

Ako želiš odmah otvoriti put za ERP/Slack/banking bez da ih sve odmah spojiš:

```text
Prepare this repository for business-system integrations.

I do not want all providers implemented immediately.
I want a clean integration foundation.

Design and implement:
- a connector/adaptor pattern
- integration configuration models
- shared sync result / audit models
- provider registration or discovery
- one example integration boundary end-to-end

Target future connectors:
- ERP/accounting systems
- Slack/Teams approvals
- banking/PSD2 reconciliation
- Peppol/e-invoice gateways
- BigQuery analytics export

Keep the implementation grounded in the current codebase.
Do not create an abstract framework disconnected from actual runtime paths.
```

## Moj preporučeni redoslijed

Ako želiš raditi racionalno, idi ovako:

1. `Phase 1 Prompt`
2. `Dedicated Prompt: Web Security`
3. `Dedicated Prompt: HITL and Fiscalization`
4. `Phase 2 Prompt`
5. `Dedicated Prompt: Session and Memory Cleanup`
6. `Phase 3 Prompt`
7. `Dedicated Prompt: Integration Foundations`

## Što očekivati od prve 3 faze

Ako agent odradi posao dobro, nakon toga bi trebao dobiti:

- sigurniji web i deployment
- jasniji i stabilniji runtime
- konzistentniji session/memory model
- fiskalizaciju koja nije vezana za terminal approval
- čišći put za ERP, Slack/Teams, banking i BI integracije

## Kratka verzija ako želiš samo jedan prompt

```text
Work in this repository as a senior engineering agent.

Your mission is to polish and harden the existing multi-agent system incrementally.
Do not rewrite it.
Treat code as the source of truth.

Do the work in phases:
1. Stabilize and secure the active runtime paths.
2. Align all user-facing interfaces onto coherent orchestration behavior.
3. Isolate scheduler behavior from unrelated app startup.
4. Remove insecure secret fallbacks and clarify credential handling.
5. Redesign the HITL foundation so approvals are not terminal-only.
6. Consolidate session and memory behavior across interfaces and persistence.
7. Prepare integration boundaries for ERP/accounting, Slack/Teams approvals, banking/PSD2, Peppol, and BigQuery analytics.

Rules:
- Make only the smallest safe changes in each phase.
- Explain the current behavior before editing.
- Prefer production-safety over feature expansion.
- Preserve deterministic fiscalization critical paths.
- Add focused verification after each change.
- End each phase with:
  - what changed
  - what was verified
  - what remains risky

Start with Phase 1 only. Inspect current runtime paths first, then implement the smallest safe stabilization batch.
```
