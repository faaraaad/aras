#!/usr/bin/env python
"""
Standalone script to populate the database with large-scale customer and voucher data.
Can be run directly via:
    python populate_db.py --customers 1000 --min-vouchers 200 --max-vouchers 500
Or via Django management command:
    python manage.py populate_db --customers 1000 --min-vouchers 200 --max-vouchers 500
"""
import os
import sys
import argparse
import django

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'accounting_project.settings')
django.setup()

from django.core.management import call_command

def main():
    parser = argparse.ArgumentParser(
        description="Populate accounting database with 1000+ customers and configurable vouchers."
    )
    parser.add_argument(
        '--customers',
        type=int,
        default=1000,
        help='Number of customers (default: 1000)'
    )
    parser.add_argument(
        '--min-vouchers',
        type=int,
        default=200,
        help='Minimum vouchers per customer (default: 200)'
    )
    parser.add_argument(
        '--max-vouchers',
        type=int,
        default=300,
        help='Maximum vouchers per customer (default: 300, can be set up to 100000)'
    )
    parser.add_argument(
        '--batch-size',
        type=int,
        default=5000,
        help='Batch size for bulk_create operations (default: 5000)'
    )
    parser.add_argument(
        '--flush',
        action='store_true',
        help='Flush existing customer and voucher records before populating'
    )

    args = parser.parse_args()

    call_command(
        'populate_db',
        customers=args.customers,
        min_vouchers=args.min_vouchers,
        max_vouchers=args.max_vouchers,
        batch_size=args.batch_size,
        flush=args.flush
    )

if __name__ == '__main__':
    main()
