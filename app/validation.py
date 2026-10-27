"""Dataset consistency checks."""
from datetime import date
from .generator import validate_tables

def validate_dataset(tables, reporting_date: date, ground_truth=None, detected=None):
    return validate_tables(tables,reporting_date,ground_truth,detected)
