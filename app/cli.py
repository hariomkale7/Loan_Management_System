import argparse, csv, json, sqlite3
from pathlib import Path
from .generator import generate_dataset, ENTITY_FILES, CSV_FIELDS, validate_tables, detect
from datetime import date

def read_tables(folder):
    p=Path(folder)
    return {name:list(csv.DictReader((p/f'{name}.csv').open(encoding='utf-8',newline=''))) for name in ENTITY_FILES}

def main():
    parser=argparse.ArgumentParser(prog='yottaflex')
    sub=parser.add_subparsers(dest='command',required=True)
    g=sub.add_parser('generate')
    g.add_argument('--loans',type=int,default=100);g.add_argument('--seed',type=int,default=20261022)
    g.add_argument('--reporting-date',default='2026-10-26')
    g.add_argument('--output',default='data/samples')
    g.add_argument('--no-anomalies',action='store_true')

    v=sub.add_parser('validate');v.add_argument('--input',default='data/samples')
    db=sub.add_parser('load-db');db.add_argument('--input',default='data/samples')
    db.add_argument('--database',default='data/samples/collections.sqlite')
    a=parser.parse_args()
    if a.command=='generate':
        report=generate_dataset(a.output,a.loans,a.seed,a.reporting_date,not a.no_anomalies)
        print(json.dumps(report,indent=2))
        return
    if a.command=='validate':
        t=read_tables(a.input)
        gt=list(csv.DictReader(open(Path(a.input)/'ground_truth.csv',encoding='utf-8')))
        det=detect(t,date.fromisoformat(json.load(open(Path(a.input)/'metadata.json'))['reporting_date']))
        report=validate_tables(t,date.today(),gt,det); print(json.dumps(report,indent=2))
        raise SystemExit(0 if report['valid'] else 1)
    load_sqlite(a.input,a.database)

def load_sqlite(folder,database):

    t=read_tables(folder)
    db=Path(database)
    db.parent.mkdir(parents=True,exist_ok=True)
    con=sqlite3.connect(db)
    con.execute('PRAGMA foreign_keys=ON')
    # Rebuild tables atomically from canonical generated CSV rows.
    con.execute('BEGIN')
    try:
        drop_order=['payments','contact_attempts','promises_to_pay','collection_cases','contact_preferences','delinquency_snapshots','installments','loans','accounts','customers']
        for name in drop_order:
            con.execute(f'DROP TABLE IF EXISTS {name}')
        # Explicit parent order, with key relationships enforced.
        fk={'accounts':['customer_id REFERENCES customers(customer_id)'],'loans':['account_id REFERENCES accounts(account_id)'],'installments':['loan_id REFERENCES loans(loan_id)'],'delinquency_snapshots':['loan_id REFERENCES loans(loan_id)'],'contact_preferences':['customer_id REFERENCES customers(customer_id)'],'collection_cases':['loan_id REFERENCES loans(loan_id)','customer_id REFERENCES customers(customer_id)'],'contact_attempts':['case_id REFERENCES collection_cases(case_id)'],'promises_to_pay':['case_id REFERENCES collection_cases(case_id)','loan_id REFERENCES loans(loan_id)'],'payments':['loan_id REFERENCES loans(loan_id)','customer_id REFERENCES customers(customer_id)','allocation_installment_id REFERENCES installments(installment_id)']}
        for name in ENTITY_FILES:
            fields=CSV_FIELDS[name]
            cols=[]
            for i,f in enumerate(fields):
                typ='INTEGER' if f.endswith('_paise') or f in ('sequence','term_months','days_past_due') else ('REAL' if f=='priority_score' else 'TEXT')
                decl=f'{f} {typ}'+(' PRIMARY KEY' if i==0 else '')
                if f in fk.get(name,''):
                    pass
                cols.append(decl)
            if name in fk:
                for relation in fk[name]:
                    rel,ref=relation.split(' REFERENCES ')
                    cols.append(f'FOREIGN KEY({rel}) REFERENCES {ref}')
            con.execute(f'CREATE TABLE {name} ({", ".join(cols)})')

        insert_order=['customers','accounts','loans','installments','delinquency_snapshots','contact_preferences','collection_cases','contact_attempts','promises_to_pay','payments']

        for name in insert_order:
            fields=CSV_FIELDS[name]
            if t[name]:
                marks=','.join('?' for _ in fields)
                con.executemany(f'INSERT INTO {name} VALUES ({marks})',[[r.get(f,'') for f in fields] for r in t[name]])
        con.commit()

    except Exception:
        con.rollback()
        raise
    finally: con.close()
if __name__=='__main__': main()
