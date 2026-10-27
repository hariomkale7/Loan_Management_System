# Data dictionary

Required unless stated optional. Dates are ISO dates; timestamps are ISO-8601; money is integer paise.

| Entity | Fields and validation |
|---|---|
| Customer | customer_id unique; first_name, last_name synthetic text; created_date. |
| Account | account_id PK; customer_id FK; account_type (`installment_loan`); opened_date; status (`active`, `closed`). |
| Loan | loan_id (`LOAN-2026-` + six digits); account_id FK; principal_paise >0; origination_date; term_months >0; annual_rate_pct (0, no accrual); status (`active`, `closed`). |
| Installment | installment_id (`INS-<loan-id>-NNN`); loan_id FK; sequence >0; due_date; amount_paise >0; paid_paise 0..amount; status (`due`, `partial`, `paid`). |
| DelinquencySnapshot | snapshot_id unique; loan_id FK; as_of_date; arrears_paise >=0; days_past_due >=0 days; risk_band (`current`, `low`, `medium`, `high`). |
| ContactPreference | preference_id; customer_id FK; timezone IANA; allowed_channels pipe-separated `phone`, `sms`, `email`, `letter`; local window HH:MM; restricted boolean text; inclusive effective dates. |
| ContactAttempt | contact_attempt_id (`CTP-<case-id>-NNN` normal); case_id FK; attempted_at; channel; outcome; compliance_status (`allowed`, injected exception). |
| PromiseToPay | promise_id; case_id and loan_id FKs; promised_amount_paise >0; due_date; created_at; status (`pending`, `fulfilled`, `partially_fulfilled`, `missed`); paid_by_due_paise >=0. |
| Payment | payment_id (`PMT-2026-...`); loan_id/customer_id/installment FKs; paid_at; amount_paise >0; allocation_paise 0..amount; allocation_status (`allocated`, `injected_wrong_installment`). |
| CollectionCase | case_id (`COL-2026-` + six digits); loan_id/customer_id FKs; opened_date; status (`open`, `disputed`, `closed`); arrears_paise >=0; days_past_due >=0; score [0,100]; category (`low`, `medium`, `high`); risk_factors; score_explanation (human-readable formula contributions); recommended_action. |

Ground truth contains unique anomaly_id, issue_type, description, affected_record_ids, expected_decision, and `ground_truth=anomaly`. No real personal or financial data is used.

`event_history.csv` fields: event_id (unique sequential ID); entity_type; entity_id; event_type; event_at timestamp; details (stable JSON text). It preserves operational change history separately from current derived lifecycle states.
