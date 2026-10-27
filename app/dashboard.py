"""Small Streamlit dashboard over generated canonical CSV files."""
import os
from pathlib import Path
import pandas as pd
import streamlit as st
from app.cli import read_tables
from app.generator import detect, validate_tables
from datetime import date
import json

st.set_page_config(page_title='YottaFlex Collections',layout='wide')
st.title('Explainable Collections Intelligence')
st.caption('Synthetic data · transparent prioritization · compliance rules override work priority')
data_dir=Path(os.getenv('YOTTAFLEX_DATA_DIR','data/samples'))

if not (data_dir/'metadata.json').exists():
    st.warning(f'No dataset found at {data_dir}. Generate one with `python -m app.cli generate`.')
    st.stop()
t=read_tables(data_dir)
md=json.loads((data_dir/'metadata.json').read_text()); cases=pd.DataFrame(t['collection_cases'])
anomalies=detect(t,date.fromisoformat(md['reporting_date']))
total_arrears=sum(int(x['arrears_paise']) for x in t['collection_cases'])
c1,c2,c3,c4=st.columns(4)
c1.metric('Loans',len(t['loans']));c2.metric('Overdue cases',sum(int(x['arrears_paise'])>0 for x in t['collection_cases']))
c3.metric('Arrears',f"₹{total_arrears/100:,.2f}");c4.metric('Detected exceptions',len(anomalies))
c5,c6,c7=st.columns(3)
loan_status={x['loan_id']:x['status'] for x in t['loans']}
c5.metric('Paid loans still open in collections',sum(loan_status.get(x['loan_id'])=='closed' and x['status']=='open' for x in t['collection_cases']))
c6.metric('Disputed cases',sum(x['status']=='disputed' or 'disputed' in x['risk_factors'].split('|') for x in t['collection_cases']))
c7.metric('Contact compliance exceptions',sum(x['issue_type']=='contact_outside_window' for x in anomalies))
st.subheader('Priority distribution')
st.bar_chart(cases['priority_category'].value_counts().reindex(['low','medium','high'],fill_value=0))
st.subheader('Collection case worklist')
band=st.selectbox('Priority category',['all','high','medium','low'])
status=st.selectbox('Case status',['all']+sorted(cases.status.unique()))
view=cases.copy()

if band!='all':
    view=view[view.priority_category==band]
if status!='all':
    view=view[view.status==status]
view=view.sort_values(['priority_score','case_id'],ascending=[False,True])

st.dataframe(view[['case_id','loan_id','customer_id','arrears_paise','days_past_due','risk_factors','priority_score','priority_category','score_explanation','recommended_action','status']],use_container_width=True,hide_index=True)
if len(view):
    chosen=st.selectbox('Case details',view.case_id.tolist())
    st.json({'case':next(c for c in t['collection_cases'] if c['case_id']==chosen),'contact_history':[x for x in t['contact_attempts'] if x['case_id']==chosen],'promises':[x for x in t['promises_to_pay'] if x['case_id']==chosen]})
st.subheader('Payment and promise review')
allocation_exceptions=[x for x in anomalies if x['issue_type']=='wrong_installment_allocation']
st.metric('Payment allocation exceptions',len(allocation_exceptions))
promise_status=pd.Series([x['status'] for x in t['promises_to_pay']]).value_counts()
st.bar_chart(promise_status)
st.subheader('Anomaly review')
st.dataframe(pd.DataFrame(anomalies),use_container_width=True,hide_index=True)
st.subheader('Validation')
gt=list(__import__('csv').DictReader(open(data_dir/'ground_truth.csv',encoding='utf-8')))
report=validate_tables(t,date.fromisoformat(md['reporting_date']),gt,anomalies);st.json(report)
