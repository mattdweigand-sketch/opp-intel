# pipeline-read Surface

`pipeline-read/` is the many-opportunity pipeline surface inside `opp-intel`.

The shared mechanics live in `../core/`:
- shared config: `../core/config/`
- shared scripts: `../core/scripts/`
- validators: `../core/validators/`
- source contracts and adapters: `../core/config/source-contracts.json`, `../core/adapters/`

This surface owns command routing, triage/forecast/hygiene modes, portfolio output shape, and read-only policy. Hygiene remains Salesforce-only. `pipeline-read` makes no writes.

Use the wrapper scripts in `scripts/` for compatibility. They delegate to `../core/`.
