# deal-read Surface

`deal-read/` is the one-opportunity deep-read surface inside `opp-intel`.

The shared mechanics live in `../core/`:
- shared config: `../core/config/`
- shared scripts: `../core/scripts/`
- validators: `../core/validators/`
- source contracts and adapters: `../core/config/source-contracts.json`, `../core/adapters/`

This surface owns orchestration, coaching output, prep/review mode, and the Gmail draft policy. It may create a Gmail draft only after explicit user confirmation. It does not own shared Salesforce fields, risk thresholds, source contracts, date math, call statistics, account-history parsing, or validation logic.

Use the wrapper scripts in `scripts/` for compatibility. They delegate to `../core/`.
