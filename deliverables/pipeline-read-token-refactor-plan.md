# Pipeline-read token and cost refactor plan

## Call

Proceed with the refactor, with one correction: Haiku is primarily a cost-control change. The token reduction comes from bounding Gmail thread expansion.

## Changes

1. Use Haiku for per-deal gather subagents in `pipeline-read/SKILL.md`.
   - Scope: pipeline-read read/forecast gather only.
   - Keep the orchestrator, rollup, and brief-writing step on the default model.
   - Do not change `deal-read`; it remains the deeper single-opportunity workflow.

2. Emit `gmail.max_threads` from `core/scripts/plan.py`.
   - Pipeline profile: `max_threads = 3`.
   - Deal profile: `max_threads = 10`.
   - Source of truth: `core/config/depth-profiles.json`.

3. Preserve the snippet-trap fix while bounding expansion.
   - Expand every thread in the capped set via `get_thread`.
   - Derive freshness from the max message date across expanded threads, never from snippets.
   - If result metadata exposes latest thread dates, use the newest capped set; otherwise use the connector's returned order.
   - Do not claim a hard newest-first guarantee unless the connector contract is verified.

4. Pin the behavior in tests and fixtures.
   - Assert pipeline per-deal plans emit `gmail.max_threads == 3`.
   - Assert deal-read plans emit `gmail.max_threads == 10`.
   - Assert `_freshness_rule` still requires `get_thread` and blocks snippet-derived freshness.
   - Update baseline fixtures for the changed planner contract.

## Expected impact

- Large cost reduction from Haiku per-deal gather subagents.
- Meaningful token reduction from capping expanded Gmail threads.
- Faster wall-clock runs from existing parallel subagent fan-out, but parallelism is a speed improvement rather than the main token lever.

## Verification

Run `bash scripts/test.sh`.
