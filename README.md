# Loan Management System

A synthetic-data reference implementation for prioritizing overdue loan accounts while enforcing contact rules, tracking promises, reconciling payments, and preserving audit history. It uses transparent business rules; the score is **not** a probability of repayment.

## Quick start (Windows / PyCharm)

Python 3.11 or newer is recommended.

```powershell
cd C:\Yottaflex_ai
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m app.cli generate --loans 100 --seed 20261022 --output data\samples
python -m app.cli validate --input data\samples
python -m pytest
```

PowerShell may block activation; use `Set-ExecutionPolicy -Scope Process Bypass` for that terminal only, or invoke `.\.venv\Scripts\python.exe` directly. The dashboard and API read the same generated CSV records.

```powershell
python -m app.cli generate --loans 10000 --seed 20261022 --reporting-date 2026-10-26 --output data\full
uvicorn app.api:app --reload
streamlit run app/dashboard.py
```

All generated data is fictional. A fixed seed plus fixed reporting date gives stable files and checksums. Anomalies are separately labeled in `ground_truth.csv`; the detector operates on operational records alone. `--no-anomalies` omits the deliberate anomaly fixtures. The generator uses exactly three monthly installments per loan over the 12-month reporting horizon (a 3-installment schedule is a simplified challenge fixture, not a claim about real lending products).

## Business rules

- Amounts are integer paise. Interest is not accrued; installment principal is equal-share with any remainder assigned to the final installment. Payments allocate oldest due installment first. Normal allocations never exceed payment amount or installment due amount.
- Arrears are unpaid installment amounts with due date strictly before the reporting date. Days past due are reporting date minus the earliest overdue installment's due date, floored at zero; accounts with no overdue balance have zero DPD.
- Case score is deterministic: `min(100, 2*min(DPD,30) + min(arrears_rupees/1000,40) + risk_points)`, where hardship contributes 0, disputed status blocks contact, and risk points are 10 for a prior missed promise, 8 for hardship, and 5 for a restriction. Bands: low <30, medium <60, high otherwise. The score ranks work, never authorizes contact. Ties sort by score descending then case ID.
- Local contact window is `[09:00, 18:00)` in the preference's IANA timezone. Effective dates are inclusive. Restriction blocks contact; allowed channels must match. Boundary at 09:00 passes, at 18:00 blocks. Blocked requests return a reason and safe next step.
- Promise state at/after its due date: fulfilled when eligible payment allocated to the loan on or before due date covers promised amount; partially_fulfilled when some but less than promised amount is allocated; missed when none is allocated; pending before due date. Reconciliation is loan-scoped and excludes payments after the promise due date.
- The five fixtures are narrowly injected and labeled. The wrong-allocation fixture is marked as an exception and excluded from normal loan balance derivation, so it cannot distort a different loan. Detection uses no ground-truth labels.

## Data and commands

`python -m app.cli generate --help` lists generator options. Output includes ten entity CSVs, separate ground truth and detected anomalies, append-only event history, validation report, metadata/provenance, and a SHA-256 manifest. Generated files are reproducible for identical options. Use a dedicated output directory; generation replaces files with matching output names.

The SQLite database is optional and can be built from the generated CSVs with `python -m app.cli load-db --input data\sample --database data\sample\collections.sqlite`. SQLite foreign keys and unique constraints are enabled. CSV remains the generator's canonical export.

## API

Start with `uvicorn app.api:app --reload`; interactive docs are at `/docs`.

- `GET /health`, `/metrics`, `/cases`, `/cases/{case_id}`, `/anomalies`
- `POST /validate`
- `POST /cases/{case_id}/contact-attempts`
- `POST /cases/{case_id}/promises`
- `POST /payments`
- `POST /promises/{promise_id}/reconcile`

Set `YOTTAFLEX_DATA_DIR` to select an input directory (default `data/samples`). Mutation endpoints append records to the selected directory and preserve prior event rows. Contact attempts are checked against preferences before append. This local demo API has no authentication and is not production-ready.

## Quality and coverage

Run `python -m pytest`. See [docs/requirement_test_matrix.md](docs/requirement_test_matrix.md), [docs/schema.md](docs/schema.md), [docs/data_dictionary.md](docs/data_dictionary.md), [docs/architecture.md](docs/architecture.md), and [docs/validation_summary.md](docs/validation_summary.md). Validation metrics are computed from the generated records; no pass counts are hardcoded. For a full-volume artifact, run the command above and retain the resulting `manifest.json` and `validation_report.json` with the submission if desired; generated data is not committed by default.

## GitHub

Initialize and commit locally after reviewing `git status`:

```powershell
git init
git add .
git commit -m "Build explainable collections compliance system"
```

Create a **public** empty repository on GitHub, then connect and push using the URL GitHub gives you:

```powershell
git branch -M main
git remote add origin https://github.com/<your-user>/<your-repository>.git
git push -u origin main
```

Never put credentials in the remote URL or commit secrets. Verify the repo opens in a signed-out/private browser before submitting; submission is final once sent.
