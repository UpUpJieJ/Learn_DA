# Refactor closeout implementation plan

> **For agentic workers:** Use superpowers:executing-plans for integration and dispatching-parallel-agents for independent fixes. Preserve the existing uncommitted refactor; no commits or deployment until validation completes.

**Goal:** Complete the agreed high-priority closeout in refactor-review-2026-10-26.md §8 and Appendix A.4.
**Architecture:** Backend owns trusted comparisons and refs; Runner returns bounded serialized observations. Structured assertions replace data-course expressions and fixed-input Python contracts replace free comparisons. Preserve anonymous identity, historical attempts and server authority.
**Tech Stack:** FastAPI/Python 3.12, Docker Runner, Vue 3/TypeScript/Pinia.
**Spec:** ../../refactor-review-2026-10-26.md

## Global constraints
- Preserve user changes and existing UI tokens; no unrelated formatting.
- TaskAttempt remains teaching evidence; LearningRecord updates must reuse the authoritative learner-state service and idempotent events.
- No production deployment or unrelated container changes; Hermes may be paused only if resources require it.
- Fail closed for malformed observations, missing refs, unsupported types and replay collisions.

## Review focus
- Forged child events and custom equality objects cannot manufacture a pass.
- Reused request IDs cannot cross sessions, operations or targets; concurrent retries do not double-write.
- Partial SSE and cancellation retain text; stale responses do not mutate a new lesson.
- Generated references remain reproducible; starters fail and reference solutions pass all 13 courses.
- Timeouts, oversize output, Windows paths, SQL column count and production-local execution fail safely.

## Tasks
- [x] 1. Data content: migrate remaining data-course expr_true to frame/schema/value contracts, generate refs and verify starter/solution behavior. Owner: content worker; coordinate new value contract with integrator.
- [x] 2. Runtime/Runner: move trusted comparison into API backend, implement strict JSON value/call observations, remove Python expr_true, fix path and production configuration boundaries. Owner: integrator.
- [x] 3. Workspace: scoped idempotency, concurrency recovery, hint requestId, run/submit/hint limits and authoritative learning events. Owner: backend worker.
- [x] 4. Streaming/UI: retain cross-round partial text, cancel safely, abort on dispose and isolate workspace requests by generation. Owner: conversation worker.
- [x] 5. Integration: read all diffs, fix contracts, run backend/Runner/frontend suites, content lint, dataset/ref checks, type-check/UI lint and real Docker verification.
- [x] 6. Reconcile report and AGENTS facts with verified results and explicitly list any remaining lower-priority findings.

Each implementation task uses a failing regression before fixes, then targeted tests. Integration runs all checks once combined; no unrelated UI redesign or dependency upgrades.

## Execution rulings and evidence
- 2026-10-31 user continuation extends scope to the report's remaining third batch and verified P1/P2/P3 findings; the following tasks supersede the earlier deferral.
- Continued in the existing dirty workspace because the approved Part 2 implementation was already there; preserved all starting changes and made no commits.
- Independent content/workspace/conversation tasks used dispatching-parallel-agents; independent reviews caught and resolved malformed observations, native decoder amplification, SQL tags, spoofed dtype, cell shape and leave-during-save races.
- JSON tables replace Arrow IPC for observations to bound host allocations. Legacy Runner judgement remains internal compatibility only; API always strips expectations and judges on host.
- Initial third-batch deferral was superseded by the user continuation; all actionable report items were implemented or reconciled (supported documented catalog/categories/recommendations retained; historical N16 already deleted).
- Evidence: backend 567 passed, Runner 56 passed, frontend 155 passed; content/dataset/ref/type/UI checks passed. Real HTTP/Docker contracts rerun for all 76 starter/solution cases.

## Remaining report closeout
- [x] 7. UI infrastructure and lint: accessible components, clipboard fallback, token contrast, zero baseline loopholes and regression tests.
- [x] 8. Pages and dead frontend code: unified metrics, Lab output/races, honest reporting, deep links, useful Navbar and removal of unused controls/modules.
- [x] 9. Backend evidence/metrics/performance: current-task evidence, prompt boundaries, consistent recommendations, unexpected SSE audit, stale-aware reports, aggregate hint queries and releasing read transactions during execution.
- [x] 10. Core/Runner: metadata removal, deterministic/orphan reference checks, relative content lint paths, log stream separation, child reaping, numeric edge cases, immutable image guidance, CRLF/global fetch cancellation.
- [x] 11. Whole-suite regression, final independent review and reconciliation of every report finding with fixed/not-applicable evidence.

## Final evidence
- Backend604, Runner59, frontend172, Node lint rule tests4: all passed. UI baseline0; content/dataset/refs/type checks passed.
- Real Docker76/76; full acceptance with real LLM29/29, rerun after d8 marker migration29/29; original PoCs5/5 safe. Linux frontend npm production build passed.
- Added persistent task_verified and guarded late cross-worker completions; no historical attempts rewritten. Migrations c7 and d8 tested and applied to isolated QA database only.
- Fresh final review found no new important regressions. Existing code remains uncommitted, production untouched, Hermes left running because memory was sufficient.

## Authorized release follow-up
- User authorized committing the full refactor, stopping Hermes, removing old Learn DA history and deploying a fresh database. This supersedes the earlier no-deployment constraint for this follow-up only; unrelated services remain out of scope.
- Release scripts require an explicit SSH target and a clean main checkout, upload an exact-commit bundle and the new updater, back up only labelled project volumes, then start Runner/migration/Backend/Web in sequence and run acceptance.
- Backend and Runner Compose timeout interpolation now use separate names; combined env files previously shortened the backend's session budget to 20 seconds.
- Fresh verification: backend604, Runner59, frontend172, UI rules4 and content/dataset/refs/type/UI gates passed again. Release flow checks6 passed.
- Independent release review found the same-revision retry could reuse an old sandbox tag after a failed update. The regression failed before the fix and passed after switching to unconditional content-cached sandbox builds.
- Target discovery: configured SSH alias contains Hermes as a user service, but no existing Learn DA checkout. Legacy script default failed SSH host-key verification. Await explicit target confirmation before stopping services or clearing data.
- User confirmed the address belonging to the configured alias. No Learn DA checkout, containers or data volumes were found; fresh installation proceeds on that machine. Hermes user service is now inactive and project secrets were generated into ignored env files.
- First deployment exposed the existing frontend base tag `nginx:1.27-slim` failing manifest resolution (403 from configured mirror). The same-version Debian tag `nginx:1.27` resolves and pulls; use that published tag while retaining the existing Debian setup.
