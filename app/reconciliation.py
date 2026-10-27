"""Promise state calculation; only eligible loan payments through due date count."""
from datetime import date, datetime, timezone

def reconcile_promise(promise, payments, as_of=None):
    as_of=as_of or date.today()
    due=date.fromisoformat(promise['due_date'])
    created=promise['created_at']
    created_at=datetime.fromisoformat(created.replace('Z','+00:00'))
    if created_at.tzinfo is None:
        created_at=created_at.replace(tzinfo=timezone.utc)
    eligible=0

    for p in payments:
        if p['loan_id']!=promise['loan_id'] or p.get('allocation_status')!='allocated':
            continue
        paid_at=datetime.fromisoformat(p['paid_at'].replace('Z','+00:00'))

        if paid_at.tzinfo is None:
            paid_at=paid_at.replace(tzinfo=timezone.utc)
        if created_at <= paid_at and paid_at.date() <= due:
            eligible+=int(p['allocation_paise'])

    amount=int(promise['promised_amount_paise'])
    status='pending' if as_of<due else ('fulfilled' if eligible>=amount else ('partially_fulfilled' if eligible>0 else 'missed'))
    return {'status':status,'paid_by_due_paise':min(eligible,amount)}
