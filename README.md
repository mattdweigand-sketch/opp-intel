# opp-intel

`opp-intel` is the shared-core migration home for `deal-read` and `pipeline-read`.

## Structure

```text
opp-intel/
├── core/
│   ├── adapters/
│   ├── config/
│   ├── schemas/
│   ├── scripts/
│   ├── validators/
│   └── tests/
├── deal-read/
└── pipeline-read/
```

## Boundaries

`core/` is the shared evidence engine: shared config, source contracts, schemas, deterministic metrics, and future shared validators.

`deal-read/` remains the deepest one-opportunity read. It keeps the coaching workflow and any write policy. Gmail drafts require explicit confirmation.

`pipeline-read/` remains the breadth-oriented multi-opportunity read. It keeps triage, forecast, and hygiene routing. Hygiene remains Salesforce-only.

## Migration Status

The migration is phased and not complete yet. Phases 0 to 2 establish baseline fixtures, repo shape, shared config, depth profiles, source contracts, and schemas. Later phases move scripts, planning adapters, rollup, validators, and finally thin the surface docs.
