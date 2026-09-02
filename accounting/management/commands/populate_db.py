import os
import sys
import random
import datetime
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.db import transaction
from accounting.models import Customer, Voucher


FIRST_NAMES = [
    "آریا", "پارس", "ایران", "البرز", "زاگرس", "خلیج فارس", "نگین", "پویا", "رسا", "آوا",
    "سپهر", "کیهان", "رایان", "تارا", "نوین", "پیشرو", "پارت", "آرتین", "فراز", "سامان",
    "دانش", "پژوهش", "توسعه", "صنعت", "بازرگانی", "فولاد", "پترو", "تک", "افق", "سروش"
]

COMPANY_TYPES = [
    "صنایع", "گروه تجاری", "شرکت بین‌المللی", "بازرگانی", "فناوری اطلاعات",
    "تولیدی و صنعتی", "مجتمع فولاد", "پخش سراسری", "سامانه نوین", "گسترش تجارت"
]

DESCRIPTIONS = [
    ("فروش کالا - فاکتور رسمی", True),       # Debit (Customer owes money)
    ("ارائه خدمات فنی و مهندسی", True),       # Debit
    ("صدور صورتحساب پروژه‌ای", True),         # Debit
    ("فروش تجهیزات و قطعات یدکی", True),     # Debit
    ("دریافت نقدی / حواله ساتنا", False),     # Credit (Payment received)
    ("واریز به حساب بانکی شرکت", False),       # Credit
    ("دریافت چک صیادی", False),               # Credit
    ("تسویه فاکتور و تخفیف تجاری", False),    # Credit
    ("مرجوعی کالا و صدور سند اصلاحی", False), # Credit
]


class Command(BaseCommand):
    help = "Populate database with large-scale customer and voucher data for performance testing."

    def add_arguments(self, parser):
        parser.add_argument(
            '--customers',
            type=int,
            default=1000,
            help='Number of customers to create (default: 1000)'
        )
        parser.add_argument(
            '--min-vouchers',
            type=int,
            default=200,
            help='Minimum number of vouchers per customer (default: 200)'
        )
        parser.add_argument(
            '--max-vouchers',
            type=int,
            default=300,
            help='Maximum number of vouchers per customer (default: 300, can be set up to 100000)'
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
            help='Delete existing customers and vouchers before populating'
        )

    def handle(self, *args, **options):
        num_customers = options['customers']
        min_vouchers = options['min_vouchers']
        max_vouchers = options['max_vouchers']
        batch_size = options['batch_size']
        flush = options['flush']

        if min_vouchers > max_vouchers:
            self.stderr.write(self.style.ERROR("Error: --min-vouchers cannot be greater than --max-vouchers"))
            return

        self.stdout.write(self.style.MIGRATE_HEADING("=== Accounting Database Population Tool ==="))
        self.stdout.write(f"Target Customers: {num_customers:,}")
        self.stdout.write(f"Vouchers per Customer: {min_vouchers:,} to {max_vouchers:,}")
        self.stdout.write(f"Bulk Batch Size: {batch_size:,}")

        if flush:
            self.stdout.write(self.style.WARNING("Flushing existing vouchers and customers..."))
            Voucher.objects.all().delete()
            Customer.objects.all().delete()
            self.stdout.write("Existing data deleted.")

        start_time = datetime.datetime.now()

        # Step 1: Bulk create customers
        self.stdout.write("\nCreating customers...")
        existing_count = Customer.objects.count()
        customers_to_create = []
        for i in range(1, num_customers + 1):
            idx = existing_count + i
            comp_type = random.choice(COMPANY_TYPES)
            name_part1 = random.choice(FIRST_NAMES)
            name_part2 = random.choice(FIRST_NAMES)
            name = f"{comp_type} {name_part1} {name_part2} (سهامی خاص)"
            code = f"CUST-{idx:05d}"
            customers_to_create.append(Customer(name=name, code=code, is_active=True))

        with transaction.atomic():
            created_customers = Customer.objects.bulk_create(customers_to_create, batch_size=batch_size)
        
        # If bulk_create didn't return IDs (e.g. some DB backends), fetch created
        all_customers = list(Customer.objects.order_by('id')[existing_count:existing_count + num_customers])
        self.stdout.write(self.style.SUCCESS(f"Successfully created {len(all_customers):,} customers."))

        # Step 2: Bulk create vouchers for each customer
        self.stdout.write("\nGenerating voucher transactions in bulk...")
        start_date = datetime.date(2023, 1, 1)
        end_date = datetime.date(2026, 8, 31)
        total_days = (end_date - start_date).days

        total_vouchers_created = 0
        voucher_batch = []
        global_voucher_seq = Voucher.objects.count() + 1

        for cust_idx, customer in enumerate(all_customers, 1):
            vouchers_for_this_cust = random.randint(min_vouchers, max_vouchers)
            
            for _ in range(vouchers_for_this_cust):
                global_voucher_seq += 1
                v_num = f"VCH-{global_voucher_seq:08d}"
                rand_day_offset = random.randint(0, total_days)
                v_date = start_date + datetime.timedelta(days=rand_day_offset)
                
                desc, is_debit = random.choice(DESCRIPTIONS)
                # Realistic accounting amount between 50,000 and 50,000,000 Tomans / Rials
                raw_amount = random.randint(50, 50000) * 1000
                amount = Decimal(str(raw_amount))

                if is_debit:
                    debit = amount
                    credit = Decimal('0.00')
                else:
                    debit = Decimal('0.00')
                    credit = amount

                voucher_batch.append(Voucher(
                    customer=customer,
                    voucher_number=v_num,
                    date=v_date,
                    debit=debit,
                    credit=credit,
                    description=desc,
                    reference=f"REF-{random.randint(100000, 999999)}"
                ))

                if len(voucher_batch) >= batch_size:
                    with transaction.atomic():
                        Voucher.objects.bulk_create(voucher_batch, batch_size=batch_size)
                    total_vouchers_created += len(voucher_batch)
                    voucher_batch = []

            # Progress log every 50 customers
            if cust_idx % 50 == 0 or cust_idx == len(all_customers):
                elapsed = (datetime.datetime.now() - start_time).total_seconds()
                rate = total_vouchers_created / elapsed if elapsed > 0 else 0
                self.stdout.write(
                    f"Progress: [{cust_idx}/{len(all_customers)} customers] - "
                    f"Vouchers created: {total_vouchers_created:,} ({rate:.0f} vouchers/sec)"
                )

        # Flush remaining vouchers in batch
        if voucher_batch:
            with transaction.atomic():
                Voucher.objects.bulk_create(voucher_batch, batch_size=batch_size)
            total_vouchers_created += len(voucher_batch)
            voucher_batch = []

        total_elapsed = (datetime.datetime.now() - start_time).total_seconds()
        self.stdout.write("\n" + "=" * 50)
        self.stdout.write(self.style.SUCCESS("Database population completed successfully!"))
        self.stdout.write(f"Total Customers in DB: {Customer.objects.count():,}")
        self.stdout.write(f"Total Vouchers in DB: {Voucher.objects.count():,}")
        self.stdout.write(f"New Vouchers Created: {total_vouchers_created:,}")
        self.stdout.write(f"Total Time Taken: {total_elapsed:.2f} seconds")
        self.stdout.write("=" * 50)
