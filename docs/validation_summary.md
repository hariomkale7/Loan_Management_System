# Validation report guide

`validation_report.json` is calculated during generation. Row counts come from records. Anomaly evaluation uses `(issue_type, first affected record ID)` as its evaluation unit and reports true/false positives and negatives, precision and recall against separate labels. This evaluates the injected cases, not future-world model performance. The deliberate wrong-installment fixture is an exception and isolated from normal balance calculation.

The validator checks primary-key uniqueness, entity foreign keys, ID patterns, core enums, preference dates/windows, payment parent and amount constraints, payment-to-installment reconciliation, installment lifecycle consistency, derived case arrears and DPD, score derivation, ordinary contact compliance, and promise-to-payment reconciliation. It is still a challenge-focused validator rather than a complete production data-quality framework.
