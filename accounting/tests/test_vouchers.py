import datetime
from decimal import Decimal
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from django.contrib.auth import get_user_model

from accounting.models import Customer, Voucher

User = get_user_model()


class VoucherListAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.url = reverse('accounting:voucher-list')

        # Create and authenticate user
        self.user = User.objects.create_user(username='testuser', password='password123')
        self.client.force_authenticate(user=self.user)

        # Create customers
        self.c1 = Customer.objects.create(name="Alpha Corp", code="CUST-001")
        self.c2 = Customer.objects.create(name="Beta LLC", code="CUST-002")

        # Create vouchers
        self.v1 = Voucher.objects.create(
            customer=self.c1, voucher_number="V-101", date=datetime.date(2024, 1, 15),
            debit=Decimal('1000.00'), credit=Decimal('0.00'), description="Invoice 1", reference="INV-001"
        )
        self.v2 = Voucher.objects.create(
            customer=self.c1, voucher_number="V-102", date=datetime.date(2024, 2, 10),
            debit=Decimal('500.00'), credit=Decimal('0.00'), description="Invoice 2", reference="INV-002"
        )
        self.v3 = Voucher.objects.create(
            customer=self.c1, voucher_number="V-103", date=datetime.date(2024, 3, 5),
            debit=Decimal('0.00'), credit=Decimal('300.00'), description="Payment 1", reference="PAY-001"
        )
        self.v4 = Voucher.objects.create(
            customer=self.c2, voucher_number="V-201", date=datetime.date(2024, 2, 15),
            debit=Decimal('200.00'), credit=Decimal('100.00'), description="Invoice & Disc", reference="INV-003"
        )

    def test_list_all_vouchers(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(data['count'], 4)
        self.assertEqual(len(data['results']), 4)
        # Verify serialized fields
        first_item = data['results'][0]
        self.assertIn('id', first_item)
        self.assertIn('voucher_number', first_item)
        self.assertIn('customer_code', first_item)
        self.assertIn('customer_name', first_item)
        self.assertIn('debit', first_item)
        self.assertIn('credit', first_item)
        self.assertIn('date', first_item)

    def test_filter_by_customer_code(self):
        response = self.client.get(self.url, {'customer_code': 'CUST-001'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(data['count'], 3)
        for item in data['results']:
            self.assertEqual(item['customer_code'], 'CUST-001')

    def test_filter_by_date_range(self):
        response = self.client.get(self.url, {
            'start_date': '2024-02-01',
            'end_date': '2024-02-28',
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(data['count'], 2)
        voucher_numbers = [item['voucher_number'] for item in data['results']]
        self.assertIn('V-102', voucher_numbers)
        self.assertIn('V-201', voucher_numbers)

    def test_filter_by_date_range_and_customer_code(self):
        response = self.client.get(self.url, {
            'start_date': '2024-02-01',
            'end_date': '2024-02-28',
            'customer_code': 'cust-001',
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(data['count'], 1)
        self.assertEqual(data['results'][0]['voucher_number'], 'V-102')

    def test_invalid_date_range(self):
        response = self.client.get(self.url, {
            'start_date': '2024-03-01',
            'end_date': '2024-02-01',
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        data = response.json()
        self.assertIn('end_date', data)
