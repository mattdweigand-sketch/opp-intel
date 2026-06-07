# ACV Added ARR Audit

## Finding

ACV was not source-locked.

The repo already mapped `amount_basis.acv` to Salesforce `Added_ARR__c`, but the rest of the system still allowed non-Added-ARR money fields to leak into ACV:

- `core/config/sf-fields.json` selected legacy non-Added-ARR money fields alongside `Added_ARR__c` in the default opportunity query.
- `core/config/sf-fields.json` selected legacy non-Added-ARR money fields in the default pipeline portfolio query.
- `core/scripts/rollup.py` treated normalized `acv`, generic `amount`, and non-Added-ARR money fields as valid ACV fallbacks.
- `pipeline-read/SKILL.md` told the orchestrator to list ACV but did not make the large-run ACV source explicit enough.
- Tests still expected non-Added-ARR money fields in pipeline and per-deal queries, which preserved the wrong behavior.

That created the exact failure mode in the screenshot: the table could show an ACV-looking value that was not Salesforce `Added_ARR__c`.

## Fix Design

ACV has one source: Salesforce `Added_ARR__c`.

The enforcement points are:

1. Query planning: default opportunity and pipeline queries select `Added_ARR__c` for ACV and do not select non-Added-ARR Salesforce money fields.
2. Rollup: `amount_basis == "acv"` reads only `Added_ARR__c`.
3. Display: row `acv`, portfolio `total_acv`, `acv_at_risk`, large-run list ACV, and ACV tie-breaks derive from `Added_ARR__c`.
4. No alternate amount basis: `crm_primary_amount` was removed and is now rejected. The only legal configured basis is `acv -> Added_ARR__c`.
5. Tests: regression fixtures include wrong `acv`, `amount`, and non-Added-ARR Salesforce money values to prove they cannot win over `Added_ARR__c`.

## Changes Made

- Removed non-Added-ARR money fields from default Salesforce opportunity and pipeline-scope field lists.
- Added `ADDED_ARR_FIELD = "Added_ARR__c"` in `core/scripts/rollup.py`.
- Changed rollup ACV computation to read only `Added_ARR__c`.
- Changed default ACV amount-basis computation to read only `Added_ARR__c`.
- Removed `crm_primary_amount` as a legal amount basis.
- Updated `pipeline-read/SKILL.md` large-run and rollup-bundle instructions to require `Added_ARR__c`.
- Updated README wording so ACV rows and totals are explicitly source-locked.
- Updated plan, forecast config, rollup, hygiene, compare, and fixture tests.

## Verification

Command:

```bash
bash scripts/test.sh
```

Result:

```text
All tests passed.
```
