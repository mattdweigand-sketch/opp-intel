# Opp-Intel Repo Audit

Date: 2026-06-06

Repo: `/Users/matthewweigand/Code/opp-intel`

Branch: `main`

Baseline: `bash scripts/test.sh` passes.

## Audit Method

I acted as the orchestrator and dispatched independent audit agents across four lanes:

- Shared core architecture and contracts
- `deal-read` surface
- `pipeline-read` surface
- Tests, setup, docs, and repo hygiene

A final verifier agent reviewed the consolidated findings for severity, duplicates, and missing evidence. I also reproduced the material findings locally with deterministic script inputs. No live Salesforce, Gmail, Calendar, Zoom, Slack, or Drive connectors were called.

## Executive Summary

The repo is green on its canonical local gate, but the gate misses several contract failures. The main pattern is that source gaps are documented correctly, but not always carried through the computed audit trail. That creates exactly the failure mode this repo is meant to prevent: absence of retrieved data can disappear before the final brief and validator see it.

No critical issue was found. I found three P1 issues, four P2 issues, and three P3 issues.

## P1 Findings

### 1. Pipeline rollup drops Calendar and internal-evidence gaps from computed inputs

Impact: `/pipeline-read` can lose source gaps before the final brief and validator see them. Calendar unavailable, missing Slack rooms, checked-no-match Slack fallback, and unavailable linked docs can disappear from top-level `source_gaps`. In read mode, Slack/Drive gaps can disappear entirely from the computed artifact.

Evidence:

- `core/scripts/rollup.py:83` reads only `deal_metrics.coverage_gaps`.
- `core/scripts/rollup.py:244` aggregates only `coverage_gaps_for()`.
- `core/scripts/rollup.py:170` has `source_gaps_for()` for internal gaps, but it is not used in read-mode top-level gaps.
- `core/scripts/rollup.py:725` emits top-level `source_gaps` from connector coverage gaps only.
- `core/scripts/compute.py:372` preserves Calendar gaps under `deal_metrics.calendar.source_gaps`, but rollup does not aggregate that field.
- `pipeline-read/SKILL.md:304` says unavailable Calendar is an evidence gap, not a risk flag.
- `pipeline-read/SKILL.md:183` says Slack/Drive can affect confidence and source gaps.

Local reproduction:

- A read-mode rollup with `internal_evidence.deal_room.coverage = "deal_room_missing"` produced `run.internal_evidence: "off"`, no `internal_evidence` block, empty row `coverage_gaps`, and top-level `source_gaps: []`.
- A read-mode rollup with `deal_metrics.calendar.source_gaps = ["calendar_unavailable"]` produced top-level `source_gaps: []`.

Recommended fix:

- Add a single rollup source-gap aggregator that includes:
  - `deal_metrics.coverage_gaps`
  - `deal_metrics.calendar.source_gaps`
  - internal evidence gaps from `source_gaps_for(deal)`
- Use it for read and forecast.
- Include per-row gaps so validators can force "Where you're blind" when relevant.
- Add tests for read and forecast modes with Calendar unavailable and Slack/Drive missing/unavailable.

### 2. Pipeline internal evidence defaults conflict with the source boundary and depth profile

Impact: The root source boundary says Slack/Drive fallback should happen only when explicitly requested. The live config defaults pipeline internal evidence to `force`, which emits bounded fallback Slack lookup by default. It also uses larger caps than the pipeline depth profile.

Evidence:

- `README.md:90` says Slack and Drive stay bounded to mapped rooms and linked docs unless pipeline mode explicitly asks for fallback lookup.
- `core/config/depth-profiles.json:51` sets pipeline Slack to `mapped_room_default` with `max_messages: 40`.
- `core/config/depth-profiles.json:56` sets pipeline Drive `max_docs: 3`.
- `core/config/risk-model.json:87` starts the internal evidence config.
- `core/config/risk-model.json:89` sets global default to `force`.
- `core/config/risk-model.json:90` sets `default_by_profile.pipeline` to `force`.
- `core/config/risk-model.json:96` sets `max_messages_per_room: 80`.
- `core/config/risk-model.json:97` sets `max_linked_docs_per_room: 5`.
- `core/scripts/plan.py:140` resolves default internal mode from config.
- `core/scripts/plan.py:209` emits bounded fallback Slack lookup when mode is `force`.
- `pipeline-read/tests/test_plan.py:39` locks in that default pipeline reads include Slack/Drive.

Local reproduction:

`python3 pipeline-read/scripts/plan.py` with `mode:"pipeline"` and an owner emitted:

- `internal_evidence.mode: "force"`
- `broad_search_allowed: true`
- `query_type: "bounded_fallback_lookup"`
- `max_messages: 80`
- `max_linked_docs: 5`

Recommended fix:

- Decide the intended default. If the root boundary is right, set pipeline default to `auto`, keep `force` as explicit only, and align caps to the pipeline depth profile.
- If `force` is intentional, update root README, depth profile, and tests so the broader behavior is explicit and not contradictory.

### 3. Calendar buyer-attendee data is dropped before scoring

Impact: A Calendar meeting with buyer attendees can be scored as `calendar_next_meeting_no_buyer_attendees`. That is a false risk flag.

Evidence:

- `core/scripts/compute.py:251` checks `buyer_attendees`.
- `core/scripts/analyze.py:143` starts `compact_event()`.
- `core/scripts/analyze.py:144` returns a compact event without `buyer_attendees`, `is_buyer`, `external`, or `is_internal`.
- `core/scripts/compute.py:295` computes `calendar_next_meeting_no_buyer_attendees`.

Local reproduction:

A bundle with:

```json
{
  "calendar_evidence": {
    "coverage": "available",
    "upcoming_meetings": [
      {"title": "Buyer call", "start": "2026-06-10", "buyer_attendees": ["buyer@example.com"]}
    ]
  }
}
```

produced `calendar_next_meeting_no_buyer_attendees: true` after `analyze.py`, because the compacted event kept `attendees: []` and dropped `buyer_attendees`.

Recommended fix:

- Preserve `buyer_attendees` and attendee classification fields in `compact_event()`.
- Add a regression test under core and both surfaces for Calendar buyer-attendee preservation.

## P2 Findings

### 4. `deal-read/scripts/plan.py` can emit a pipeline portfolio plan

Impact: The deal surface is supposed to stay one-opportunity only. Passing `{"mode":"pipeline"}` through the deal wrapper emits a many-opportunity portfolio plan.

Evidence:

- `deal-read/SKILL.md:340` says one deal per run.
- `deal-read/scripts/plan.py:8` delegates to core.
- `deal-read/scripts/plan.py:10` sets `OPP_INTEL_SURFACE = "deal-read"`.
- `core/scripts/plan.py:473` reads the context.
- `core/scripts/plan.py:478` routes `ctx.get("mode") == "pipeline"` to `pipeline_plan()` before surface restrictions are enforced.

Local reproduction:

`printf '{"mode":"pipeline","today":"2026-06-06","owner_id":"005X"}' | python3 deal-read/scripts/plan.py` emitted a Salesforce portfolio query and pipeline connector plan.

Recommended fix:

- Have the deal wrapper reject `mode:"pipeline"`.
- Or have `core/scripts/plan.py` reject pipeline mode when `OPP_INTEL_SURFACE == "deal-read"`.
- Add a deal-read test for this boundary.

### 5. Connector status is optional and common source-name aliases are ignored

Impact: The repo requires failed connectors to become coverage gaps, but `connector_status` is optional and key-sensitive. A harness that reports `gmail` or `google_calendar` instead of `email` or `calendar` gets no degraded gap.

Evidence:

- `core/config/source-contracts.json:23` defines clean-negative rules.
- `core/config/source-contracts.json:26` requires retry and final status reporting.
- `core/config/source-contracts.json:27` says absent/unrecognized status is treated as not degraded.
- `core/scripts/compute.py:63` reads optional `connector_status`.
- `core/scripts/compute.py:64` checks only `email`, `zoom`, `calendar`, and `salesforce`.
- `core/schemas/evidence-bundle.schema.json:5` requires only `profile`, `opportunity`, and `source_gaps`.
- `pipeline-read/SKILL.md:205` requires per-deal `connector_status`, but that is prose/orchestration, not a schema gate.

Local reproduction:

`connector_status: {"gmail":"timeout","google_calendar":"timeout"}` produced `coverage_gaps: []`.

Recommended fix:

- Normalize source aliases such as `gmail -> email`, `google_calendar -> calendar`, `calls_zoom -> zoom`.
- Add schema/validator coverage for required statuses when a source is expected to run.
- Add tests for canonical keys and alias keys.

### 6. Deal brief validator allows High confidence with coverage gaps

Impact: A deal brief can pass validation with `Confidence: High` even when degraded connector gaps are present.

Evidence:

- `core/validators/validate_deal_brief.py:89` only checks High confidence against `email_data_stale`.
- `core/scripts/compute.py:183` emits degraded connectors as coverage gaps.

Local reproduction:

A deal brief with `Confidence: High` and computed `coverage_gaps: ["email_connector_degraded"]` exited `0` and rendered the pass stamp.

Recommended fix:

- Reject High confidence when `deal_metrics.coverage_gaps` is non-empty.
- Consider also checking `calendar.source_gaps` and `internal_evidence.source_gaps`.

### 7. Setup and registration behavior is outside the canonical test gate

Impact: Team-facing setup can drift while `scripts/test.sh` stays green. The most relevant untested behavior is `CLAUDE_SKILLS_DIR`, `--force`, non-symlink skip behavior, and stale alias cleanup.

Evidence:

- `scripts/test.sh:17` starts the core test loop only.
- `scripts/test.sh:25` runs core, deal-read, and pipeline-read Python tests.
- `scripts/register-claude-skills.sh:14` implements registration behavior.
- `scripts/register-claude-skills.sh:19` skips existing non-symlink folders unless forced.
- `scripts/register-claude-skills.sh:34` removes only one exact old `pipeline-triage` symlink target.
- `SETUP.md:50` documents `CLAUDE_SKILLS_DIR`.
- `pipeline-read/tests/test_command_frontends.py:20` checks text/folders, not setup script execution.

Recommended fix:

- Add a shell test or Python subprocess test that runs registration against a temp `CLAUDE_SKILLS_DIR`.
- Cover normal install, non-symlink skip, `--force`, and stale `pipeline-triage` cleanup.

## P3 Findings

### 8. Pipeline README computed-input schema omits hygiene

Impact: Docs understate the supported computed-input shape. A teammate using the README as the contract may treat hygiene output as out of schema.

Evidence:

- `pipeline-read/README.md:155` lists `run.mode` as `read|forecast`.
- `pipeline-read/SKILL.md:266` lists `read|forecast|hygiene`.
- `core/scripts/rollup.py:679` emits a hygiene output block.

Recommended fix:

- Update README schema to include `hygiene`.
- Mention the hygiene block and when forecast/internal/movement blocks appear.

### 9. Pipeline README still points at the old standalone `deal-read` relationship

Impact: The repo-level README says old standalone repos are archived and this repo is the active home. The pipeline README still links the old GitHub repo and says Pipeline Read "reuses" Deal Read's core, which muddies the current `core/` ownership boundary.

Evidence:

- `README.md:172` says the old standalone GitHub repos are archived.
- `pipeline-read/README.md:172` starts the relationship section.
- `pipeline-read/README.md:174` links to `https://github.com/mattdweigand-sketch/deal-read`.
- `pipeline-read/README.md:175` says Pipeline Read reuses Deal Read's deterministic core.

Recommended fix:

- Update the relationship section to point to `../deal-read` and `../core`.
- Say both surfaces use the shared `core/`, not that pipeline reuses deal-read.

### 10. Historical PRD is stale relative to active command surface

Impact: Low runtime risk, but it is a tracked deliverable inside `deal-read/deliverables/` that contradicts active tests and docs.

Evidence:

- `deal-read/deliverables/opp-intel-prd.md:183` still lists `pipeline-triage`.
- Active tests assert old `/pipeline-triage` is absent in `pipeline-read/tests/test_command_frontends.py:25`.

Recommended fix:

- Move the PRD to a clearly historical location or add a header that it is pre-migration history.
- If it remains in-tree, update stale command references or mark them explicitly as superseded.

## Verification Run

Commands run:

```bash
git status --short --branch
bash scripts/test.sh
printf '{"mode":"pipeline","today":"2026-06-06","owner_id":"005X"}' | python3 deal-read/scripts/plan.py
python3 deal-read/scripts/validate_brief.py < high-confidence-coverage-gap-brief.md
python3 deal-read/scripts/analyze.py < buyer-attendee-calendar-bundle.json
python3 core/scripts/compute.py < alias-connector-status-bundle.json
python3 core/scripts/rollup.py < read-mode-internal-gap-bundle.json
python3 core/scripts/rollup.py < read-mode-calendar-gap-bundle.json
python3 pipeline-read/scripts/plan.py < pipeline-default-internal-bundle.json
```

Baseline tests passed. Targeted repros confirmed the findings above.

## Suggested Fix Order

1. Fix rollup source-gap propagation and add tests for Calendar/internal gaps in read and forecast.
2. Preserve Calendar buyer-attendee fields through `analyze.py`.
3. Decide the pipeline internal-evidence default and align README, depth profiles, config, and tests.
4. Enforce the deal-read one-opportunity boundary at the script layer.
5. Normalize/enforce connector status and strengthen deal validation against coverage gaps.
6. Add setup registration tests.
7. Clean stale docs and historical deliverable references.

## Residual Risk

This was a repo/static and deterministic-script audit. I did not run live connectors, inspect sibling repos outside this checkout, or inspect installed `~/.claude/skills` state. The Gmail draft policy is documented correctly, but actual enforcement still depends on the agent or harness honoring the `deal-read` skill before calling `create_draft`.
