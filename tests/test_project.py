import csv, json
from datetime import date, datetime, timezone
from app.generator import generate_dataset, ENTITY_FILES, detect
from app.rules import arrears_for, dpd_for, contact_decision
from app.reconciliation import reconcile_promise

def load(path,name):
    with open(path/f'{name}.csv',newline='',encoding='utf-8') as f:return list(csv.DictReader(f))

def test_ten_entities_and_counts(tmp_path):
    report=generate_dataset(tmp_path,20,42,'2026-10-26')
    assert len(ENTITY_FILES)==10 and report['valid']
    assert len(load(tmp_path,'loans'))==20 and len(load(tmp_path,'installments'))==60

def test_ids_and_foreign_keys(tmp_path):
    generate_dataset(tmp_path,20,1,'2026-10-26')
    loans={x['loan_id'] for x in load(tmp_path,'loans')}
    customers={x['customer_id'] for x in load(tmp_path,'customers')}
    assert all(x['loan_id'].startswith('LOAN-2026-') for x in load(tmp_path,'loans'))
    assert all(x['loan_id'] in loans for x in load(tmp_path,'installments'))
    assert all(x['customer_id'] in customers for x in load(tmp_path,'accounts'))

def test_five_labels_are_detected_without_label_input(tmp_path):
    generate_dataset(tmp_path,20,42,'2026-10-26')
    t={n:load(tmp_path,n) for n in ENTITY_FILES}
    gt=load(tmp_path,'ground_truth')
    found=detect(t,date(2026,10,26))
    assert {x['issue_type'] for x in gt}=={x['issue_type'] for x in found}

def test_reproducible_outputs(tmp_path):
    a=tmp_path/'a'
    b=tmp_path/'b';generate_dataset(a,10,7,'2026-10-26')
    generate_dataset(b,10,7,'2026-10-26')
    assert json.loads((a/'manifest.json').read_text())==json.loads((b/'manifest.json').read_text())

def test_contact_boundaries():
    pref={'timezone':'Asia/Kolkata','effective_start':'2026-01-01','effective_end':'2026-12-31','restricted':'false','allowed_channels':'phone|sms','window_start':'09:00','window_end':'18:00'}
    assert contact_decision(pref,datetime(2026,6,1,3,30,tzinfo=timezone.utc),'phone')['allowed']
    assert not contact_decision(pref,datetime(2026,6,1,12,30,tzinfo=timezone.utc),'phone')['allowed']
    pref['restricted']='true';assert not contact_decision(pref,datetime(2026,6,1,3,30,tzinfo=timezone.utc),'phone')['allowed']

def test_arrears_and_dpd():
    rows=[{'amount_paise':10000,'paid_paise':3000,'status':'partial','due_date':'2026-10-01'}]
    assert arrears_for(rows,date(2026,10,26))==7000 and dpd_for(rows,date(2026,10,26))==25

def test_promise_reconciliation():
    promise={'loan_id':'L','created_at':'2026-01-01T00:00:00Z','due_date':'2026-01-10','promised_amount_paise':10000}
    payments=[{'loan_id':'L','paid_at':'2026-01-05T00:00:00Z','allocation_status':'allocated','allocation_paise':9000}]
    assert reconcile_promise(promise,payments,date(2026,1,11))=={'status':'partially_fulfilled','paid_by_due_paise':9000}
