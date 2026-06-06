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

The shared-core migration is complete through the planned Phase 6 extraction. Surface scripts remain as compatibility wrappers; shared mechanics now live under `core/`.
