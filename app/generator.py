"""Deterministic synthetic relational dataset generator."""
import csv, hashlib, json, random
import re
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from .rules import arrears_for, dpd_for, priority, money
from .reconciliation import reconcile_promise

ENTITY_FILES = ['customers','accounts','loans','installments','delinquency_snapshots','contact_preferences','contact_attempts','promises_to_pay','payments','collection_cases']
CSV_FIELDS = {
 'customers':['customer_id','first_name','last_name','created_date'],
 'accounts':['account_id','customer_id','account_type','opened_date','status'],
 'loans':['loan_id','account_id','principal_paise','origination_date','term_months','annual_rate_pct','status'],
 'installments':['installment_id','loan_id','sequence','due_date','amount_paise','paid_paise','status'],
 'delinquency_snapshots':['snapshot_id','loan_id','as_of_date','arrears_paise','days_past_due','risk_band'],
 'contact_preferences':['preference_id','customer_id','timezone','allowed_channels','window_start','window_end','restricted','effective_start','effective_end'],
 'contact_attempts':['contact_attempt_id','case_id','attempted_at','channel','outcome','compliance_status'],
 'promises_to_pay':['promise_id','case_id','loan_id','promised_amount_paise','due_date','created_at','status','paid_by_due_paise'],
 'payments':['payment_id','loan_id','customer_id','paid_at','amount_paise','allocation_installment_id','allocation_paise','allocation_status'],
 'collection_cases':['case_id','loan_id','customer_id','opened_date','status','arrears_paise','days_past_due','priority_score','priority_category','risk_factors','score_explanation','recommended_action']}

def generate_dataset(output_dir, loans=100, seed=20261022, reporting_date='2026-10-26', inject_anomalies=True):

    out=Path(output_dir)
    out.mkdir(parents=True,exist_ok=True)
    asof=date.fromisoformat(str(reporting_date))
    rng=random.Random(seed)
    tables={k:[] for k in ENTITY_FILES}; gt=[]
    channels=['phone','sms','email','letter']; zones=['Asia/Kolkata','America/New_York','Europe/London']
    count=max(0,int(loans))
    start=asof.replace(year=asof.year-1)
    # Master records precede dependent records. Every ID is stable by ordinal.
    for n in range(1,count+1):
        cid=f'CUST-{n:06d}'
        aid=f'ACC-{n:06d}'
        lid=f'LOAN-2026-{n:06d}'
        caseid=f'COL-2026-{n:06d}'

        created=start+timedelta(days=rng.randrange(0,365)); orig=created
        tables['customers'].append(dict(customer_id=cid,first_name=f'Person{n:05d}',last_name=f'Synthetic{n:05d}',created_date=created.isoformat()))
        tables['accounts'].append(dict(account_id=aid,customer_id=cid,account_type='installment_loan',opened_date=orig.isoformat(),status='active'))
        principal=rng.randrange(50000,500001); paid_mode=rng.random()
        loanstatus='closed' if paid_mode<.22 and orig+timedelta(days=90)<asof else 'active'
        tables['loans'].append(dict(loan_id=lid,account_id=aid,principal_paise=principal,origination_date=orig.isoformat(),term_months=3,annual_rate_pct='0.00',status=loanstatus))
        split=principal//3
        amounts=[split,split,principal-split*2]
        installments=[]
        allocation_open=True

        for seq,amount in enumerate(amounts,1):
            due=orig+timedelta(days=30*seq)
            paid=amount if (loanstatus=='closed' or (allocation_open and due < asof and rng.random()<.38)) else 0

            if paid==0 and allocation_open and due<asof and rng.random()<.22: paid=rng.randrange(1,amount)
            if paid<amount:
                allocation_open=False

            ins=dict(installment_id=f'INS-{lid}-{seq:03d}',loan_id=lid,sequence=seq,due_date=due.isoformat(),amount_paise=amount,paid_paise=paid,status='paid' if paid>=amount else ('partial' if paid else 'due'))
            installments.append(ins); tables['installments'].append(ins)

            if paid:
                pid=f"PMT-2026-{len(tables['payments'])+1:06d}"
                tables['payments'].append(dict(payment_id=pid,loan_id=lid,customer_id=cid,paid_at=due.isoformat()+'T12:00:00Z',amount_paise=paid,allocation_installment_id=ins['installment_id'],allocation_paise=paid,allocation_status='allocated'))

        arrears=arrears_for(installments,asof); dpd=dpd_for(installments,asof)
        disputed=(n%23==0); hardship=(n%19==0); restricted=(n%29==0)
        risk=[]

        if disputed:risk.append('disputed')
        if hardship:risk.append('hardship')
        if restricted:risk.append('contact_restricted')

        tables['delinquency_snapshots'].append(dict(snapshot_id=f'SNP-{n:06d}',loan_id=lid,as_of_date=asof.isoformat(),arrears_paise=arrears,days_past_due=dpd,risk_band='current' if not dpd else ('high' if dpd>=60 else 'medium' if dpd>=30 else 'low')))
        pref=dict(preference_id=f'PREF-{n:06d}',customer_id=cid,timezone=zones[(n-1)%len(zones)],allowed_channels='|'.join(channels[:3]),window_start='09:00',window_end='18:00',restricted=str(restricted).lower(),effective_start=start.isoformat(),effective_end='9999-12-31')
        tables['contact_preferences'].append(pref)
        status='closed' if loanstatus=='closed' else ('disputed' if disputed else ('open' if arrears else 'closed'))
        promise_record=None

        if arrears and n%17==0:
            created_at=(asof-timedelta(days=30)).isoformat()+'T12:00:00Z'
            if n%34==0:
                promise_due = asof - timedelta(days=7)
            else :
                promise_due = asof+timedelta(days=7)

            promise_record=dict(promise_id=f'PTP-{n:06d}',case_id=caseid,loan_id=lid,promised_amount_paise=max(1,arrears//2),due_date=promise_due.isoformat(),created_at=created_at,status='pending',paid_by_due_paise=0)
            promise_record.update(reconcile_promise(promise_record,tables['payments'],asof))
            if promise_record['status']=='missed':
                risk.append('missed_promise')

        score,cat,why=priority(arrears,dpd,missed_promise=bool(promise_record and promise_record['status']=='missed'),hardship=hardship,restricted=restricted)
        action='manual_review' if disputed or restricted else ('contact_permitted_channel' if arrears else 'no_collection_action')
        case=dict(case_id=caseid,loan_id=lid,customer_id=cid,opened_date=asof.isoformat(),status=status,arrears_paise=arrears,days_past_due=dpd,priority_score=score,priority_category=cat,risk_factors='|'.join(risk),score_explanation=why,recommended_action=action)
        tables['collection_cases'].append(case)

        if promise_record:
            tables['promises_to_pay'].append(promise_record)
        if arrears and n%13==0 and not restricted:
            local=datetime.combine(asof,time(10,0),ZoneInfo(pref['timezone']))
            tables['contact_attempts'].append(dict(contact_attempt_id=f'CTP-{caseid}-001',case_id=caseid,attempted_at=local.astimezone(timezone.utc).isoformat().replace('+00:00','Z'),channel='phone',outcome='no_answer',compliance_status='allowed'))

    if inject_anomalies and count>=1:
        # Five distinct fixtures with independent ground truth. Tweak the first eligible records only.
        case=tables['collection_cases'][0]
        case.update(status='open',arrears_paise=0,days_past_due=0,recommended_action='no_collection_action')
        case.update(priority_score=0,priority_category='low',score_explanation='No arrears and zero days past due; score 0.')
        tables['loans'][0]['status']='closed'
        tables['accounts'][0]['status']='closed'

        for ins0 in tables['installments'][:3]:
            ins0.update(paid_paise=ins0['amount_paise'],status='paid')

        tables['delinquency_snapshots'][0].update(arrears_paise=0,days_past_due=0,risk_band='current')
        tables['payments']=[p for p in tables['payments'] if p['loan_id']!=tables['loans'][0]['loan_id']]

        for ins0 in tables['installments'][:3]:
            tables['payments'].append(dict(payment_id=next_payment_id(tables['payments']),loan_id=tables['loans'][0]['loan_id'],customer_id=tables['customers'][0]['customer_id'],paid_at=asof.isoformat()+'T12:00:00Z',amount_paise=ins0['amount_paise'],allocation_installment_id=ins0['installment_id'],allocation_paise=ins0['amount_paise'],allocation_status='allocated'))
        add_gt(gt,'paid_account_in_collection','Paid-off loan remains open in collections',[case['case_id'],case['loan_id']],'close_case')
        case=tables['collection_cases'][0]
        attempt_id=f"CTP-{case['case_id']}-{sum(a['case_id']==case['case_id'] for a in tables['contact_attempts'])+1:03d}"
        tables['contact_attempts'].append(dict(contact_attempt_id=attempt_id,case_id=case['case_id'],attempted_at=asof.isoformat()+'T23:30:00Z',channel='phone',outcome='connected',compliance_status='injected_exception'))
        add_gt(gt,'contact_outside_window','Contact was made outside the local permitted contact window',[attempt_id,case['case_id']],'block_and_reschedule')

        if count>=2:
            # Prepare a clean disputed account with true outstanding arrears so the two labels
            # attached to this case do not accidentally create a third, unlabeled paid-case issue.
            lo=tables['loans'][1]
            c=tables['collection_cases'][1]
            lo['status']='active'
            tables['accounts'][1]['status']='active'
            tables['payments']=[p for p in tables['payments'] if p['loan_id']!=lo['loan_id']]
            loan_installments=[i for i in tables['installments'] if i['loan_id']==lo['loan_id']]

            for i in loan_installments:
                i.update(paid_paise=0,status='due')

            arrears=arrears_for(loan_installments,asof)
            dpd=dpd_for(loan_installments,asof)
            disputed_score,disputed_category,disputed_explanation=priority(arrears,dpd)
            c.update(arrears_paise=arrears,days_past_due=dpd,priority_score=disputed_score,priority_category=disputed_category,risk_factors='disputed',status='open',recommended_action='contact_permitted_channel',score_explanation=disputed_explanation)
            snap=next(s for s in tables['delinquency_snapshots'] if s['loan_id']==lo['loan_id'])
            snap.update(arrears_paise=arrears,days_past_due=dpd)
            lo=tables['loans'][1]
            ins=tables['installments'][0]
            payid=next_payment_id(tables['payments'])
            tables['payments'].append(dict(payment_id=payid,loan_id=lo['loan_id'],customer_id=tables['accounts'][1]['customer_id'],paid_at=asof.isoformat()+'T12:00:00Z',amount_paise=1000,allocation_installment_id=ins['installment_id'],allocation_paise=1000,allocation_status='injected_wrong_installment'))
            add_gt(gt,'wrong_installment_allocation','Payment references an installment belonging to another loan',[payid,lo['loan_id'],ins['installment_id']],'quarantine_and_review')
            c=tables['collection_cases'][1]
            amt=int(c['arrears_paise'])+10000
            tables['promises_to_pay'].append(dict(promise_id='PTP-ANOM-0001',case_id=c['case_id'],loan_id=c['loan_id'],promised_amount_paise=amt,due_date=(asof+timedelta(days=5)).isoformat(),created_at=asof.isoformat()+'T12:00:00Z',status='pending',paid_by_due_paise=0))
            add_gt(gt,'promise_exceeds_arrears','Promise amount exceeds current arrears',["PTP-ANOM-0001",c['case_id']],'reject_or_manual_review')
            add_gt(gt,'disputed_debt_treated_as_confirmed','Disputed debt is presented as an ordinary open collection case',[c['case_id'],c['loan_id']],'pause_collection_and_review')
    # Refresh identity for empty/small datasets and stable serialization.
    for name, rows in tables.items():
        path=out/f'{name}.csv'
        with path.open('w',newline='',encoding='utf-8') as f:
            writer=csv.DictWriter(f,fieldnames=CSV_FIELDS[name],extrasaction='ignore')
            writer.writeheader()
            writer.writerows(rows)
    write_csv(out/'ground_truth.csv',['anomaly_id','issue_type','description','affected_record_ids','expected_decision','ground_truth'],gt)
    detected=detect(tables,asof)
    write_csv(out/'detected_anomalies.csv',['anomaly_id','issue_type','description','affected_record_ids','expected_decision','ground_truth'],detected)
    events=[]
    def event(entity,entity_id,kind,when,details):
        events.append(dict(event_id=f'EVT-{len(events)+1:08d}',entity_type=entity,entity_id=entity_id,event_type=kind,event_at=when,details=json.dumps(details,sort_keys=True,separators=(',',':'))))
    for p in tables['payments']:
        event('Payment',p['payment_id'],'payment_allocated' if p['allocation_status']=='allocated' else 'payment_quarantined',p['paid_at'],{'loan_id':p['loan_id'],'allocation_status':p['allocation_status']})

    for a in tables['contact_attempts']:
        event('ContactAttempt',a['contact_attempt_id'],'contact_attempt_recorded',a['attempted_at'],{'case_id':a['case_id'],'compliance_status':a['compliance_status']})

    for p in tables['promises_to_pay']:
        event('PromiseToPay',p['promise_id'],'promise_created',p['created_at'],{'case_id':p['case_id'],'amount_paise':p['promised_amount_paise']})
        if p['status']!='pending':
            event('PromiseToPay',p['promise_id'],'promise_reconciled',asof.isoformat()+'T23:59:59Z',{'status':p['status'],'paid_by_due_paise':p['paid_by_due_paise']})

    write_csv(out/'event_history.csv',['event_id','entity_type','entity_id','event_type','event_at','details'],events)
    report=validate_tables(tables,asof,gt,detected)
    (out/'validation_report.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    metadata={'seed':seed,'reporting_date':asof.isoformat(),'loan_count':count,'installment_schedule':'3 equal-principal monthly installments per loan','generation_period_months':12,'anomalies_injected':bool(inject_anomalies),'row_counts':{**{k:len(v) for k,v in tables.items()},'event_history':len(events)},'money_unit':'integer paise','data_provenance':{'type':'synthetic','external_sources':[],'generator':'app.generator.generate_dataset'}}
    (out/'metadata.json').write_text(json.dumps(metadata,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    manifest={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.iterdir()) if p.is_file() and p.name not in ('manifest.json',) and p.suffix.lower() not in ('.sqlite','.db','.tmp')}
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    return report

def add_gt(rows,kind,desc,ids,decision):
    rows.append(dict(anomaly_id=f'ANOM-{len(rows)+1:03d}',issue_type=kind,description=desc,affected_record_ids='|'.join(ids),expected_decision=decision,ground_truth='anomaly'))

def next_payment_id(payments):
    suffixes=[int(p['payment_id'].rsplit('-',1)[-1]) for p in payments if p['payment_id'].startswith('PMT-2026-') and p['payment_id'].rsplit('-',1)[-1].isdigit()]
    return f'PMT-2026-{max(suffixes,default=0)+1:06d}'

def write_csv(path,fields,rows):
    with path.open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=fields)
        w.writeheader();w.writerows(rows)

def detect(t,asof):
    found=[]
    cases={c['case_id']:c for c in t['collection_cases']}
    loans={l['loan_id']:l for l in t['loans']}
    # Rules depend only on operational entities; never receive ground-truth rows.
    for c in t['collection_cases']:
        if c['status']=='open' and int(c['arrears_paise'])==0:
            found.append(_det('paid_account_in_collection','Open collection case has no arrears',[c['case_id'],c['loan_id']],'close_case'))
        if c['risk_factors']=='disputed' and c['status']=='open' and c['recommended_action']=='contact_permitted_channel':
            found.append(_det('disputed_debt_treated_as_confirmed','Disputed case is assigned routine contact action',[c['case_id'],c['loan_id']],'pause_collection_and_review'))
    prefs={p['customer_id']:p for p in t['contact_preferences']}; cases_customer={c['case_id']:c for c in t['collection_cases']}

    for a in t['contact_attempts']:
        c=cases_customer[a['case_id']]; pref=prefs[c['customer_id']]
        try:
            from .rules import contact_decision
            at=datetime.fromisoformat(a['attempted_at'].replace('Z','+00:00'))
            decision=contact_decision(pref,at,a['channel'])
            if not decision['allowed']:
                found.append(_det('contact_outside_window','Contact attempt violates the effective preference or contact window',[a['contact_attempt_id'],c['case_id']],'block_and_reschedule'))
        except (ValueError, KeyError):
            pass
    ins={i['installment_id']:i for i in t['installments']}
    for p in t['payments']:
        if p['allocation_installment_id'] in ins and ins[p['allocation_installment_id']]['loan_id']!=p['loan_id']:
            found.append(_det('wrong_installment_allocation','Allocation installment belongs to a different loan',[p['payment_id'],p['loan_id'],p['allocation_installment_id']],'quarantine_and_review'))
    for p in t['promises_to_pay']:
        c=cases.get(p['case_id'])
        if c and int(p['promised_amount_paise'])>int(c['arrears_paise']):
            found.append(_det('promise_exceeds_arrears','Promise amount exceeds case arrears',[p['promise_id'],c['case_id']],'reject_or_manual_review'))
    return found

def _det(kind,desc,ids,decision):
    return dict(anomaly_id='DET-'+hashlib.sha256((kind+'|'.join(ids)).encode()).hexdigest()[:12],issue_type=kind,description=desc,affected_record_ids='|'.join(ids),expected_decision=decision,ground_truth='')

def validate_tables(t,asof,gt=None,detected=None):
    errors=[]
    for name,rows in t.items():
        # IDs are first column by schema.
        ids=[r[next(iter(r))] for r in rows]
        if len(ids)!=len(set(ids)):
            errors.append(f'{name}: duplicate primary key')

    cust={r['customer_id'] for r in t['customers']}
    acct={r['account_id'] for r in t['accounts']}
    loan={r['loan_id'] for r in t['loans']}; cases={r['case_id'] for r in t['collection_cases']}
    inst={r['installment_id']:r for r in t['installments']}
    if any(r['customer_id'] not in cust for r in t['accounts']):
        errors.append('account customer FK missing')
    if any(r['account_id'] not in acct for r in t['loans']):
        errors.append('loan account FK missing')
    if any(r['loan_id'] not in loan for r in t['installments']+t['delinquency_snapshots']):
        errors.append('installment/snapshot loan FK missing')
    if any(r['customer_id'] not in cust for r in t['contact_preferences']):
        errors.append('preference customer FK missing')
    if any(r['case_id'] not in cases for r in t['promises_to_pay']+t['contact_attempts']):
        errors.append('case FK missing')
    if any(r['loan_id'] not in loan or r['customer_id'] not in cust for r in t['collection_cases']):
        errors.append('case loan/customer FK missing')
    if any(r['loan_id'] not in loan for r in t['promises_to_pay']):
        errors.append('promise loan FK missing')
    allocated_by_installment={}

    for p in t['payments']:
        if p['loan_id'] not in loan:
            errors.append('payment loan FK missing')
        if p['customer_id'] not in cust:
            errors.append('payment customer FK missing')
        if p['allocation_installment_id'] not in inst:
            errors.append('payment installment FK missing')
        if int(p['allocation_paise'])>int(p['amount_paise']):
            errors.append('payment allocation exceeds payment amount')
        if p['allocation_status']=='allocated' and p['allocation_installment_id'] in inst:
            target=inst[p['allocation_installment_id']]
            if target['loan_id']!=p['loan_id']:
                errors.append('normal payment allocated across loans')
            allocated_by_installment[p['allocation_installment_id']]=allocated_by_installment.get(p['allocation_installment_id'],0)+int(p['allocation_paise'])
    for i in t['installments']:
        paid=int(i['paid_paise'])
        amount=int(i['amount_paise'])
        if paid<0 or paid>amount:
            errors.append('installment paid amount outside 0..amount')
        if (i['status']=='paid') != (paid==amount) or (i['status']=='partial') != (0<paid<amount):
            errors.append('installment status does not match balance')
        if allocated_by_installment.get(i['installment_id'],0)!=paid:
            errors.append('installment paid amount does not reconcile to payments')
    installments_by_loan={}

    for installment in t['installments']:
        installments_by_loan.setdefault(installment['loan_id'],[]).append(installment)
    for case in t['collection_cases']:
        li=installments_by_loan.get(case['loan_id'],[])
        if int(case['arrears_paise'])!=arrears_for(li,asof):
            errors.append('case arrears do not reconcile to installments')
        if int(case['days_past_due'])!=dpd_for(li,asof):
            errors.append('case DPD does not reconcile to installments')
    prefs={p['customer_id']:p for p in t['contact_preferences']}
    case_by_id={c['case_id']:c for c in t['collection_cases']}

    from .rules import contact_decision
    for attempt in t['contact_attempts']:
        if attempt['compliance_status']=='injected_exception':
            continue
        c=case_by_id.get(attempt['case_id'])
        pref=prefs.get(c['customer_id']) if c else None
        if not c or not pref or not contact_decision(pref,datetime.fromisoformat(attempt['attempted_at'].replace('Z','+00:00')),attempt['channel'])['allowed']:
            errors.append('normal contact attempt violates customer preference')
    for promise in t['promises_to_pay']:
        expected_promise=reconcile_promise(promise,t['payments'],asof)
        if promise['status']!=expected_promise['status'] or int(promise['paid_by_due_paise'])!=expected_promise['paid_by_due_paise']:
            errors.append('promise lifecycle does not reconcile to eligible payments')
        if int(promise['promised_amount_paise'])>int(next(c['arrears_paise'] for c in t['collection_cases'] if c['case_id']==promise['case_id'])) and promise['promise_id']!='PTP-ANOM-0001':
            errors.append('normal promise amount exceeds case arrears')
    allowed={
        'accounts':('status',{'active','closed'}),'loans':('status',{'active','closed'}),
        'installments':('status',{'due','partial','paid'}),'delinquency_snapshots':('risk_band',{'current','low','medium','high'}),
        'contact_attempts':('channel',{'phone','sms','email','letter'}),'promises_to_pay':('status',{'pending','fulfilled','partially_fulfilled','missed'}),
        'payments':('allocation_status',{'allocated','injected_wrong_installment'}),'collection_cases':('status',{'open','disputed','closed'})}
    for name,(field,values) in allowed.items():
        if any(row.get(field) not in values for row in t[name]):errors.append(f'{name}: invalid {field} enum')
    if any(not re.fullmatch(r'LOAN-2026-\d{6}',x['loan_id']) for x in t['loans']):
        errors.append('loan ID format invalid')
    if any(not re.fullmatch(r'COL-2026-\d{6}',x['case_id']) for x in t['collection_cases']):
        errors.append('collection case ID format invalid')
    for i in t['installments']:
        if not re.fullmatch(rf"INS-{re.escape(i['loan_id'])}-\d{{3}}",i['installment_id']):
            errors.append('installment ID format invalid')
    for p in t['contact_preferences']:
        if p['restricted'] not in ('true','false') or p['window_start']>=p['window_end'] or p['effective_start']>p['effective_end']:
            errors.append('contact preference invalid')
    for attempt in t['contact_attempts']:
        if not re.fullmatch(rf"CTP-{re.escape(attempt['case_id'])}-\d{{3}}",attempt['contact_attempt_id']):
            errors.append('contact attempt ID format invalid')
        if attempt['compliance_status'] not in ('allowed','injected_exception'):
            errors.append('contact compliance status invalid')
    if any(not re.fullmatch(r'PMT-2026-\d{6}',p['payment_id']) for p in t['payments']):
        errors.append('payment ID format invalid')
    loans_by_id={x['loan_id']:x for x in t['loans']}
    for i in t['installments']:
        if date.fromisoformat(i['due_date'])<=date.fromisoformat(loans_by_id[i['loan_id']]['origination_date']):
            errors.append('installment due date does not follow loan origination')
    for p in t['payments']:
        if datetime.fromisoformat(p['paid_at'].replace('Z','+00:00')).date()<date.fromisoformat(loans_by_id[p['loan_id']]['origination_date']):
            errors.append('payment date precedes loan origination')
    for case in t['collection_cases']:
        expected_score,expected_category,_=priority(int(case['arrears_paise']),int(case['days_past_due']),'missed_promise' in case['risk_factors'].split('|'),'hardship' in case['risk_factors'].split('|'),'contact_restricted' in case['risk_factors'].split('|'))
        if float(case['priority_score'])!=expected_score or case['priority_category']!=expected_category:
            errors.append('case priority score does not reconcile to factors')
    expected={k:len(v) for k,v in t.items()}
    # Evaluation unit is a labeled record: issue_type plus the primary affected ID.

    def event_key(row):
        return (row['issue_type'],row['affected_record_ids'].split('|')[0])
    truth=set(event_key(r) for r in (gt or [])); pred=set(event_key(r) for r in (detected or []))
    tp=len(truth&pred); fp=len(pred-truth); fn=len(truth-pred)
    return {'valid':not errors,'errors':errors,'row_counts':expected,'foreign_keys_checked':True,'anomaly_evaluation':{'unit':'(issue_type, first affected record ID)','true_positive':tp,'false_positive':fp,'false_negative':fn,'precision':tp/(tp+fp) if tp+fp else 1.0,'recall':tp/(tp+fn) if tp+fn else 1.0},'dataset_note':'The injected wrong-installment exception is intentionally represented as an invalid allocation for retrospective detection.'}
