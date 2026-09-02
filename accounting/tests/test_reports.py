import datetime
from decimal import Decimal
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status

from django.contrib.auth import get_user_model
from accounting.models import Customer, Voucher
from accounting.services import get_customer_balance_queryset, get_balance_report_summary
from accounting.tasks import export_customer_balance_csv_task

User = get_user_model()


class CustomerBalanceReportTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.url = reverse('accounting:customer-balance-report')

        # Create and authenticate user
        self.user = User.objects.create_user(username='testuser', password='password123')
        self.client.force_authenticate(user=self.user)

        # Create customers
        self.c1 = Customer.objects.create(name="Alpha Corp", code="CUST-001")
        self.c2 = Customer.objects.create(name="Beta LLC", code="CUST-002")
        self.c3 = Customer.objects.create(name="Gamma Inc", code="CUST-003")

        # Report target range: 2024-02-01 to 2024-02-28
        self.start_date = datetime.date(2024, 2, 1)
        self.end_date = datetime.date(2024, 2, 28)

        # Transactions for Customer 1:
        # Prior to range (Opening balance: 1000 - 200 = 800)
        Voucher.objects.create(
            customer=self.c1, voucher_number="V-101", date=datetime.date(2024, 1, 15),
            debit=Decimal('1000.00'), credit=Decimal('0.00'), description="Invoice #1"
        )
        Voucher.objects.create(
            customer=self.c1, voucher_number="V-102", date=datetime.date(2024, 1, 20),
            debit=Decimal('0.00'), credit=Decimal('200.00'), description="Payment #1"
        )
        # In range (Turnover: Debit 500, Credit 300)
        Voucher.objects.create(
            customer=self.c1, voucher_number="V-103", date=datetime.date(2024, 2, 10),
            debit=Decimal('500.00'), credit=Decimal('0.00'), description="Invoice #2"
        )
        Voucher.objects.create(
            customer=self.c1, voucher_number="V-104", date=datetime.date(2024, 2, 20),
            debit=Decimal('0.00'), credit=Decimal('300.00'), description="Payment #2"
        )
        # After range (Should NOT affect report)
        Voucher.objects.create(
            customer=self.c1, voucher_number="V-105", date=datetime.date(2024, 3, 5),
            debit=Decimal('700.00'), credit=Decimal('0.00'), description="Invoice #3"
        )

        # Transactions for Customer 2:
        # Prior to range (Opening balance: 0 - 1500 = -1500 -> Creditor)
        Voucher.objects.create(
            customer=self.c2, voucher_number="V-201", date=datetime.date(2024, 1, 10),
            debit=Decimal('0.00'), credit=Decimal('1500.00'), description="Prepayment"
        )
        # In range (Turnover: Debit 200, Credit 100)
        Voucher.objects.create(
            customer=self.c2, voucher_number="V-202", date=datetime.date(2024, 2, 15),
            debit=Decimal('200.00'), credit=Decimal('100.00'), description="Invoice & Discount"
        )

        # Customer 3 has no transactions (Balanced: 0)

    def test_balance_calculation_logic(self):
        """
        Tests mathematical precision of opening balance, period turnover, and closing balance.
        """
        qs = get_customer_balance_queryset(self.start_date, self.end_date)
        res_map = {item.id: item for item in qs}

        # Customer 1 verification
        item1 = res_map[self.c1.id]
        self.assertEqual(item1.opening_debit, Decimal('1000.00'))
        self.assertEqual(item1.opening_credit, Decimal('200.00'))
        self.assertEqual(item1.opening_balance, Decimal('800.00'))
        self.assertEqual(item1.period_debit, Decimal('500.00'))
        self.assertEqual(item1.period_credit, Decimal('300.00'))
        self.assertEqual(item1.period_turnover, Decimal('200.00'))
        self.assertEqual(item1.closing_balance, Decimal('1000.00'))

        # Customer 2 verification
        item2 = res_map[self.c2.id]
        self.assertEqual(item2.opening_balance, Decimal('-1500.00'))
        self.assertEqual(item2.period_debit, Decimal('200.00'))
        self.assertEqual(item2.period_credit, Decimal('100.00'))
        self.assertEqual(item2.period_turnover, Decimal('100.00'))
        self.assertEqual(item2.closing_balance, Decimal('-1400.00'))

        # Customer 3 verification
        item3 = res_map[self.c3.id]
        self.assertEqual(item3.opening_balance, Decimal('0.00'))
        self.assertEqual(item3.period_debit, Decimal('0.00'))
        self.assertEqual(item3.period_credit, Decimal('0.00'))
        self.assertEqual(item3.closing_balance, Decimal('0.00'))

    def test_summary_aggregation(self):
        """
        Tests grand total calculation across all customers.
        """
        qs = get_customer_balance_queryset(self.start_date, self.end_date)
        summary = get_balance_report_summary(qs)

        # Total Opening: 800 + (-1500) + 0 = -700
        self.assertEqual(summary['total_opening_balance'], Decimal('-700.00'))
        # Total Period Debit: 500 + 200 = 700
        self.assertEqual(summary['total_period_debit'], Decimal('700.00'))
        # Total Period Credit: 300 + 100 = 400
        self.assertEqual(summary['total_period_credit'], Decimal('400.00'))
        # Total Closing: 1000 + (-1400) + 0 = -400
        self.assertEqual(summary['total_closing_balance'], Decimal('-400.00'))

    def test_api_report_endpoint_success(self):
        """
        Tests GET /api/reports/customer-balance/ with valid parameters.
        """
        response = self.client.get(self.url, {
            'start_date': '2024-02-01',
            'end_date': '2024-02-28',
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()

        self.assertIn('results', data)
        self.assertIn('summary', data)
        self.assertIn('period', data)
        self.assertEqual(len(data['results']), 3)

        # Check status field
        c1_data = next(r for r in data['results'] if r['code'] == 'CUST-001')
        self.assertEqual(c1_data['balance_status'], 'DEBTOR')
        self.assertEqual(c1_data['closing_balance'], '1000.00')

        c2_data = next(r for r in data['results'] if r['code'] == 'CUST-002')
        self.assertEqual(c2_data['balance_status'], 'CREDITOR')
        self.assertEqual(c2_data['closing_balance'], '-1400.00')

        c3_data = next(r for r in data['results'] if r['code'] == 'CUST-003')
        self.assertEqual(c3_data['balance_status'], 'BALANCED')
        self.assertEqual(c3_data['closing_balance'], '0.00')

    def test_api_filter_by_customer(self):
        """
        Tests report filtering for a single specific customer.
        """
        response = self.client.get(self.url, {
            'start_date': '2024-02-01',
            'end_date': '2024-02-28',
            'customer_code': self.c1.code,
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(len(data['results']), 1)
        self.assertEqual(data['results'][0]['code'], 'CUST-001')

    def test_api_filter_by_customer_case_insensitive(self):
        """
        Tests case-insensitivity and leading/trailing whitespace in customer_code filter.
        """
        response = self.client.get(self.url, {
            'start_date': '2024-02-01',
            'end_date': '2024-02-28',
            'customer_code': '  cust-001  ',
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(len(data['results']), 1)
        self.assertEqual(data['results'][0]['code'], 'CUST-001')

    def test_api_filter_by_nonexistent_customer(self):
        """
        Tests validation error when customer_code does not exist.
        """
        response = self.client.get(self.url, {
            'start_date': '2024-02-01',
            'end_date': '2024-02-28',
            'customer_code': 'NON-EXISTENT',
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        data = response.json()
        self.assertIn('customer_code', data)

    def test_api_invalid_date_range(self):
        """
        Tests validation error when start_date > end_date.
        """
        response = self.client.get(self.url, {
            'start_date': '2024-03-01',
            'end_date': '2024-02-01',
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        data = response.json()
        self.assertIn('end_date', data)

    def test_no_n_plus_one_queries(self):
        """
        Ensures constant number of queries regardless of the number of customers and vouchers.
        """
        # Add 10 more customers with vouchers
        for i in range(10):
            c = Customer.objects.create(name=f"Extra {i}", code=f"CUST-EXTRA-{i}")
            Voucher.objects.create(
                customer=c, voucher_number=f"V-EXTRA-{i}", date=datetime.date(2024, 2, 5),
                debit=Decimal('100.00'), credit=Decimal('50.00')
            )

        with self.assertNumQueries(3):
            # 1 query for count (pagination)
            # 1 query for customer queryset with all annotated calculations
            # 1 query for grand total aggregate summary
            response = self.client.get(self.url, {
                'start_date': '2024-02-01',
                'end_date': '2024-02-28',
            })
            self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_async_task_export(self):
        """
        Tests background CSV export task saving to storage.
        """
        from django.core.files.storage import default_storage

        result = export_customer_balance_csv_task(
            start_date_str='2024-02-01',
            end_date_str='2024-02-28'
        )
        self.assertEqual(result['status'], 'SUCCESS')
        self.assertEqual(result['records_count'], 3)
        self.assertGreater(result['file_size_bytes'], 0)
        self.assertIn('file_path', result)
        self.assertTrue(default_storage.exists(result['file_path']))

        # Clean up created test file
        default_storage.delete(result['file_path'])

    def test_csv_export_endpoint_submission(self):
        """
        Tests POST /api/reports/customer-balance/export-async/
        """
        export_url = reverse('accounting:customer-balance-export-async')
        response = self.client.post(export_url, {
            'start_date': '2024-02-01',
            'end_date': '2024-02-28',
        })
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        data = response.json()
        self.assertIn('task_id', data)
        self.assertEqual(data['status'], 'PENDING')
