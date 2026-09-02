import csv
import io
import datetime
from decimal import Decimal
from .services import get_customer_balance_queryset, get_balance_report_summary
from .serializers import CustomerBalanceItemSerializer

try:
    from celery import shared_task
except ImportError:
    # Fallback decorator if celery is not installed.
    # Supports both @shared_task and @shared_task(bind=True, ...) forms.
    def shared_task(func=None, **decorator_kwargs):
        def decorator(fn):
            def wrapper(*args, **kwargs):
                # When bind=True celery passes the task instance as first arg;
                # in the fallback we skip it so regular calls still work.
                if decorator_kwargs.get('bind'):
                    return fn(None, *args, **kwargs)
                return fn(*args, **kwargs)
            wrapper.delay = lambda *a, **kw: wrapper(*a, **kw)
            return wrapper
        if func is not None:
            # Called as bare @shared_task (no parentheses)
            return decorator(func)
        # Called as @shared_task(...) with arguments
        return decorator


import uuid
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

@shared_task
def export_customer_balance_csv_task(start_date_str, end_date_str, customer_code=None):
    """
    Celery task to handle heavy balance report exports for large datasets.
    Generates CSV, saves it to storage, and returns the file path for client download.
    """
    start_date = datetime.date.fromisoformat(start_date_str)
    end_date = datetime.date.fromisoformat(end_date_str)

    qs = get_customer_balance_queryset(
        start_date=start_date,
        end_date=end_date,
        customer_code=customer_code
    )

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        'Customer Code',
        'Customer Name',
        'Opening Balance',
        'Period Debit',
        'Period Credit',
        'Period Turnover',
        'Closing Balance'
    ])

    for row in qs.iterator(chunk_size=1000):
        writer.writerow([
            row.code,
            row.name,
            str(row.opening_balance),
            str(row.period_debit),
            str(row.period_credit),
            str(row.period_turnover),
            str(row.closing_balance)
        ])

    csv_data = output.getvalue()
    output.close()
    
    # Save CSV file to storage
    file_name = f"exports/customer_balance_{start_date_str}_{end_date_str}_{uuid.uuid4().hex[:8]}.csv"
    saved_path = default_storage.save(file_name, ContentFile(csv_data.encode('utf-8')))

    return {
        'status': 'SUCCESS',
        'file_path': saved_path,
        'filename': f"customer_balance_{start_date_str}_to_{end_date_str}.csv",
        'records_count': qs.count(),
        'file_size_bytes': len(csv_data.encode('utf-8'))
    }


@shared_task(bind=True)
def generate_customer_balance_report_task(self, start_date_str, end_date_str, customer_code=None):
    """
    Celery task to asynchronously generate the full customer balance report.

    Runs the DB query, computes summary metrics, and serializes all rows.
    The result is stored in the Celery result backend so clients can poll
    for it using the task ID (job_id) returned when the job was submitted.

    Returns a dict with:
      - period:  { start_date, end_date }
      - summary: aggregated totals across all matching customers
      - results: list of serialized CustomerBalanceItem dicts
    """
    start_date = datetime.date.fromisoformat(start_date_str)
    end_date = datetime.date.fromisoformat(end_date_str)

    qs = get_customer_balance_queryset(
        start_date=start_date,
        end_date=end_date,
        customer_code=customer_code
    )

    # Compute summary aggregates over the full queryset
    summary_data = get_balance_report_summary(qs)

    # Serialize all rows — evaluate the queryset here inside the worker
    serializer = CustomerBalanceItemSerializer(qs, many=True)

    return {
        'period': {
            'start_date': start_date_str,
            'end_date': end_date_str,
        },
        'summary': summary_data,
        'results': serializer.data,
    }
