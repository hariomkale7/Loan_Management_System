# Requirement to test matrix

| Requirement | Implementation | Check |
|---|---|---|
| Ten entities, ID formats, joins | `app/generator.py` | entity/count and FK tests |
| Seeded generation, 10k/30k, manifest | CLI/generator | reproducibility test; full command in README |
| Derived arrears, DPD, score | `app/rules.py` | calculation tests |
| Contact compliance | rules and API | boundary/restriction test |
| Promise reconciliation | `app/reconciliation.py` | reconciliation test |
| Five labeled anomalies | generator detector | anomaly evaluation test |
| API and dashboard use actual data | `app/api.py`, `app/dashboard.py` | shared CSV source; API docs |
| Fresh setup | README | follow quick start in clean venv |

These tests are focused acceptance checks, not production certification.
