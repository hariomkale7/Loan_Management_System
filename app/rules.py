"""Pure business calculations shared by exports, API and dashboard."""
from datetime import date, datetime, time
from decimal import Decimal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

def money(cents: int) -> str:
    return f"{Decimal(int(cents)) / 100:.2f}"

def arrears_for(installments, reporting_date: date) -> int:
    return sum(max(0, int(i['amount_paise']) - int(i.get('paid_paise', 0))) for i in installments
               if date.fromisoformat(i['due_date']) < reporting_date and i.get('status') != 'paid')

def dpd_for(installments, reporting_date: date) -> int:
    overdue = [date.fromisoformat(i['due_date']) for i in installments
               if date.fromisoformat(i['due_date']) < reporting_date and int(i['amount_paise']) > int(i.get('paid_paise', 0))]
    return max(0, (reporting_date - min(overdue)).days) if overdue else 0

def priority(arrears_paise: int, dpd: int, missed_promise=False, hardship=False, restricted=False):
    risk = (10 if missed_promise else 0) + (8 if hardship else 0) + (5 if restricted else 0)
    score = min(100, 2 * min(dpd, 30) + min(arrears_paise // 100000, 40) + risk)
    category = 'low' if score < 30 else ('medium' if score < 60 else 'high')
    factors = [f"DPD contribution {2 * min(dpd, 30):g}", f"arrears contribution {min(arrears_paise / 100000, 40):g}", f"risk points {risk}"]
    return round(score, 2), category, '; '.join(factors)

def contact_decision(preference: dict, at: datetime, channel: str):
    try:
        local = at.astimezone(ZoneInfo(preference['timezone']))
    except (ZoneInfoNotFoundError, KeyError):
        return {'allowed': False, 'reason': 'Unknown or missing preference timezone', 'next_step': 'manual_review'}
    day = local.date().isoformat()
    if not preference.get('effective_start', '') <= day <= preference.get('effective_end', '9999-12-31'):
        return {'allowed': False, 'reason': 'Preference is not effective on contact date', 'next_step': 'manual_review'}
    if preference.get('restricted') == 'true':
        return {'allowed': False, 'reason': 'Customer contact restriction is active', 'next_step': 'do_not_contact'}
    if channel not in preference.get('allowed_channels', '').split('|'):
        return {'allowed': False, 'reason': 'Channel is not permitted by preference', 'next_step': 'use_permitted_channel'}
    start = time.fromisoformat(preference.get('window_start', '09:00'))
    end = time.fromisoformat(preference.get('window_end', '18:00'))
    if not (start <= local.timetz().replace(tzinfo=None) < end):
        return {'allowed': False, 'reason': 'Outside permitted local contact window', 'next_step': f"reschedule_between_{start.strftime('%H%M')}_{end.strftime('%H%M')}"}
    return {'allowed': True, 'reason': 'Contact permitted', 'next_step': 'proceed'}
