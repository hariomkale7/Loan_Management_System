"""FastAPI interface over the canonical generated CSV dataset."""
import csv, os
from datetime import date, datetime, timezone
from pathlib import Path
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from .cli import read_tables
from .generator import generate_dataset, detect, validate_tables
from .rules import contact_decision
from .rules import arrears_for, dpd_for, priority
from .reconciliation import reconcile_promise

app=FastAPI(title='YottaFlex Collections Intelligence',version='1.0.0')

def folder():
    return Path(os.getenv('YOTTAFLEX_DATA_DIR','data/samples'))

def rows(name):
    p=folder()/f'{name}.csv'
    if not p.exists():
        raise HTTPException(503,f'Dataset not found: {p}. Run the generate command first.')
    with p.open(encoding='utf-8',newline='') as f:
        return list(csv.DictReader(f))

def append(name,row):
    path=folder()/f'{name}.csv'
    path.parent.mkdir(parents=True,exist_ok=True)
    exists=path.exists()
    fields=list(row)
    with path.open('a',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields)
        if not exists:
            w.writeheader()
        w.writerow(row)

def append_event(entity_type,entity_id,event_type,at,details):
    event_path=folder()/'event_history.csv'
    event_id='EVT-00000001'
    if event_path.exists():
        with event_path.open(encoding='utf-8',newline='') as f:
            existing=list(csv.DictReader(f))
        event_id=f'EVT-{len(existing)+1:08d}'
    append('event_history',{'event_id':event_id,'entity_type':entity_type,'entity_id':entity_id,'event_type':event_type,'event_at':at,'details':__import__('json').dumps(details,sort_keys=True,separators=(',',':'))})

def replace_rows(name,items):
    path=folder()/f'{name}.csv';temp=path.with_suffix('.tmp')
    if not items:
        return
    with temp.open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(items[0]));w.writeheader();w.writerows(items)
    temp.replace(path)


class ContactIn(BaseModel):
    attempted_at: datetime
    channel: str
    outcome: str=Field(min_length=2)

class PromiseIn(BaseModel):
    promised_amount_paise: int=Field(gt=0)
    due_date: date

class PaymentIn(BaseModel):
    loan_id: str
    customer_id: str
    paid_at: datetime
    amount_paise: int=Field(gt=0)
    installment_id: str
    idempotency_key: str=Field(min_length=8,max_length=100)

class GenerateIn(BaseModel):
    loans: int=Field(gt=0,le=10000); seed: int=20261022; reporting_date: date=date(2026,10,26)

@app.get('/health')
def health():
    return {'status':'ok'}

@app.get('/metrics')
def metrics():
    t=read_tables(folder())
    cases=t['collection_cases']
    anomalies=detect(t,date.fromisoformat(__import__('json').load(open(folder()/'metadata.json'))['reporting_date']))
    return {'loans':len(t['loans']),'cases':len(cases),'overdue_cases':sum(int(c['arrears_paise'])>0 for c in cases),'total_arrears_paise':sum(int(c['arrears_paise']) for c in cases),'anomalies':len(anomalies)}

@app.get('/cases')
def cases(status: str|None=None, priority_category: str|None=None):
    data=rows('collection_cases')
    if status:
        data=[x for x in data if x['status']==status]
    if priority_category:
        data=[x for x in data if x['priority_category']==priority_category]
    return sorted(data,key=lambda x:(-float(x['priority_score']),x['case_id']))

@app.get('/cases/{case_id}')
def case_detail(case_id: str):
    match=next((c for c in rows('collection_cases') if c['case_id']==case_id),None)
    if not match:
        raise HTTPException(404,'Collection case not found')
    return {'case':match,'contacts':[x for x in rows('contact_attempts') if x['case_id']==case_id],'promises':[x for x in rows('promises_to_pay') if x['case_id']==case_id]}

@app.get('/anomalies')
def anomalies():
    t=read_tables(folder())
    md=__import__('json').load(open(folder()/'metadata.json'))
    return detect(t,date.fromisoformat(md['reporting_date']))

@app.post('/validate')
def validate():
    t=read_tables(folder())
    gt=rows('ground_truth')
    md=__import__('json').load(open(folder()/'metadata.json'))
    return validate_tables(t,date.fromisoformat(md['reporting_date']),gt,detect(t,date.fromisoformat(md['reporting_date'])))

@app.post('/generate')
def generate(body: GenerateIn):
    return generate_dataset(folder(),body.loans,body.seed,body.reporting_date,True)

@app.post('/cases/{case_id}/contact-attempts')
def add_contact(case_id: str, body: ContactIn):
    c=next((x for x in rows('collection_cases') if x['case_id']==case_id),None)
    if not c:
        raise HTTPException(404,'Collection case not found')
    if body.attempted_at.tzinfo is None:
        raise HTTPException(422,'attempted_at must include an explicit timezone offset')

    pref=next(x for x in rows('contact_preferences') if x['customer_id']==c['customer_id'])
    decision=contact_decision(pref,body.attempted_at,body.channel)

    if not decision['allowed']:
        raise HTTPException(422,decision)

    prior=[x for x in rows('contact_attempts') if x['case_id']==case_id]; aid=f"CTP-{case_id}-{len(prior)+1:03d}"
    item={'contact_attempt_id':aid,'case_id':case_id,'attempted_at':body.attempted_at.isoformat(),'channel':body.channel,'outcome':body.outcome,'compliance_status':'allowed'}
    append('contact_attempts',item)
    append_event('ContactAttempt',aid,'contact_attempt_recorded',item['attempted_at'],{'case_id':case_id,'compliance_status':'allowed'})
    return item

@app.post('/cases/{case_id}/promises')
def add_promise(case_id: str, body: PromiseIn):
    c=next((x for x in rows('collection_cases') if x['case_id']==case_id),None)
    if not c:
        raise HTTPException(404,'Collection case not found')
    if body.promised_amount_paise>int(c['arrears_paise']):
        raise HTTPException(422,'Promise cannot exceed current arrears')

    old=rows('promises_to_pay')
    numbers=[int(x['promise_id'].rsplit('-',1)[-1]) for x in old if x['promise_id'].rsplit('-',1)[-1].isdigit()]
    item={'promise_id':f"PTP-{max(numbers,default=0)+1:06d}",'case_id':case_id,'loan_id':c['loan_id'],'promised_amount_paise':body.promised_amount_paise,'due_date':body.due_date.isoformat(),'created_at':datetime.now(timezone.utc).isoformat(),'status':'pending','paid_by_due_paise':0}
    append('promises_to_pay',item)
    append_event('PromiseToPay',item['promise_id'],'promise_created',item['created_at'],{'case_id':case_id,'amount_paise':body.promised_amount_paise})
    return item

@app.post('/payments')
def add_payment(body: PaymentIn):
    if body.paid_at.tzinfo is None:
        raise HTTPException(422,'paid_at must include an explicit timezone offset')
    event_path=folder()/'event_history.csv'
    if event_path.exists():
        prior_events=list(csv.DictReader(event_path.open(encoding='utf-8',newline='')))
        for event in prior_events:
            if event['entity_type']=='Payment' and event['event_type']=='payment_allocated':
                details=__import__('json').loads(event['details'])
                if details.get('idempotency_key')==body.idempotency_key:
                    if details.get('request')!={'loan_id':body.loan_id,'customer_id':body.customer_id,'paid_at':body.paid_at.isoformat(),'amount_paise':body.amount_paise,'installment_id':body.installment_id}:
                        raise HTTPException(409,'Idempotency key was already used with a different payment request')
                    return next(x for x in rows('payments') if x['payment_id']==event['entity_id'])

    loan=next((x for x in rows('loans') if x['loan_id']==body.loan_id),None)
    ins=next((x for x in rows('installments') if x['installment_id']==body.installment_id),None)

    if not loan or not ins:
        raise HTTPException(404,'Loan or installment not found')
    if ins['loan_id']!=body.loan_id:
        raise HTTPException(422,'Installment does not belong to loan')
    if not any(x['customer_id']==body.customer_id and x['account_id']==loan['account_id'] for x in rows('accounts')):
        raise HTTPException(422,'Customer does not own this loan')

    old=rows('payments');ins_rows=rows('installments')
    loan_installments=sorted((x for x in ins_rows if x['loan_id']==body.loan_id),key=lambda x:(x['due_date'],x['sequence']))
    old_allocations={x['allocation_installment_id']:0 for x in loan_installments}

    for payment in old:
        if payment['allocation_status']=='allocated' and payment['allocation_installment_id'] in old_allocations:old_allocations[payment['allocation_installment_id']]+=int(payment['allocation_paise'])
    oldest_open=next((x for x in loan_installments if old_allocations[x['installment_id']]<int(x['amount_paise'])),None)

    if not oldest_open or oldest_open['installment_id']!=body.installment_id:
        raise HTTPException(422,'Payment must allocate to the oldest unpaid installment')

    allocated=old_allocations[body.installment_id]

    if allocated+body.amount_paise>int(ins['amount_paise']):
        raise HTTPException(422,'Payment would exceed the installment balance')

    numeric_ids=[int(x['payment_id'].rsplit('-',1)[-1]) for x in old if x['payment_id'].startswith('PMT-2026-') and x['payment_id'].rsplit('-',1)[-1].isdigit()]

    item={'payment_id':f'PMT-2026-{max(numeric_ids,default=0)+1:06d}','loan_id':body.loan_id,'customer_id':body.customer_id,'paid_at':body.paid_at.isoformat(),'amount_paise':body.amount_paise,'allocation_installment_id':body.installment_id,'allocation_paise':body.amount_paise,'allocation_status':'allocated'}

    append('payments',item);old.append(item)

    target=next(x for x in ins_rows if x['installment_id']==body.installment_id)
    target_paid=allocated+body.amount_paise
    target['paid_paise']=str(target_paid)
    target['status']='paid' if target_paid==int(target['amount_paise']) else 'partial'
    replace_rows('installments',ins_rows)
    asof=date.fromisoformat(__import__('json').load(open(folder()/'metadata.json'))['reporting_date'])
    loan_installments=[x for x in ins_rows if x['loan_id']==body.loan_id]
    arrears=arrears_for(loan_installments,asof);dpd=dpd_for(loan_installments,asof)
    case_rows=rows('collection_cases')
    case=next(x for x in case_rows if x['loan_id']==body.loan_id)
    case['arrears_paise']=str(arrears);case['days_past_due']=str(dpd)
    score,category,explanation=priority(arrears,dpd,missed_promise='missed_promise' in case['risk_factors'].split('|'),hardship='hardship' in case['risk_factors'].split('|'),restricted='contact_restricted' in case['risk_factors'].split('|'))
    case.update(priority_score=score,priority_category=category,score_explanation=explanation)

    if case['status']!='disputed':
        case['status']='open' if arrears else 'closed'

    case['recommended_action']='manual_review' if case['status']=='disputed' or 'contact_restricted' in case['risk_factors'].split('|') else ('contact_permitted_channel' if arrears else 'no_collection_action')
    replace_rows('collection_cases',case_rows)
    loan_rows=rows('loans');loan_row=next(x for x in loan_rows if x['loan_id']==body.loan_id)
    if all(int(x['paid_paise'])==int(x['amount_paise']) for x in loan_installments):loan_row['status']='closed'
    replace_rows('loans',loan_rows)
    account_rows=rows('accounts')
    account_id=loan['account_id']
    if all(x['status']=='closed' for x in loan_rows if x['account_id']==account_id):
        next(x for x in account_rows if x['account_id']==account_id)['status']='closed'
    replace_rows('accounts',account_rows)
    snapshots=rows('delinquency_snapshots')
    snapshot=next(x for x in snapshots if x['loan_id']==body.loan_id);snapshot.update(arrears_paise=str(arrears),days_past_due=str(dpd))
    replace_rows('delinquency_snapshots',snapshots)
    append_event('Payment',item['payment_id'],'payment_allocated',item['paid_at'],{'loan_id':item['loan_id'],'allocation_installment_id':item['allocation_installment_id'],'idempotency_key':body.idempotency_key,'request':{'loan_id':body.loan_id,'customer_id':body.customer_id,'paid_at':body.paid_at.isoformat(),'amount_paise':body.amount_paise,'installment_id':body.installment_id}})
    return item

@app.post('/promises/{promise_id}/reconcile')
def reconcile(promise_id: str):
    ps=rows('promises_to_pay')
    p=next((x for x in ps if x['promise_id']==promise_id),None)

    if not p:
        raise HTTPException(404,'Promise not found')

    old_status=p['status']
    p.update(reconcile_promise(p,rows('payments')))
    # Rewrite only this promise row atomically through a temp replacement while retaining other event rows.
    path=folder()/'promises_to_pay.csv'
    allrows=ps
    replace_rows('promises_to_pay',allrows)

    if old_status!=p['status']:append_event('PromiseToPay',promise_id,'promise_reconciled',datetime.now(timezone.utc).isoformat(),{'status':p['status'],'paid_by_due_paise':p['paid_by_due_paise']})
    return p
