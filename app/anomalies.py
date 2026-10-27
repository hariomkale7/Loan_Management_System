"""Anomaly detector API; ground truth is intentionally not an argument."""
from datetime import date
from .generator import detect

def detect_anomalies(tables, reporting_date: date):
    return detect(tables,reporting_date)
