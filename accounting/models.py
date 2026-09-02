from decimal import Decimal
from django.db import models
from django.core.validators import MinValueValidator
from django.core.exceptions import ValidationError


class Customer(models.Model):
    """
    Model representing a customer / client account.
    In standard accounting, customer accounts are receivable accounts (Asset nature, Debit balance).
    """
    name = models.CharField(max_length=255, verbose_name="Customer Name")
    code = models.CharField(max_length=50, unique=True, db_index=True, verbose_name="Customer Code")
    is_active = models.BooleanField(default=True, db_index=True, verbose_name="Is Active")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Created At")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Updated At")

    class Meta:
        verbose_name = "Customer"
        verbose_name_plural = "Customers"
        ordering = ['code']

    def __str__(self):
        return f"{self.code} - {self.name}"


class Voucher(models.Model):
    """
    Model representing an accounting voucher / transaction record.
    Stores debit and credit amounts for a customer on a given date.
    
    Debit: Increase in customer debt / receivables (e.g. Sales, Services rendered).
    Credit: Decrease in customer debt / receivables (e.g. Payments received, Returns).
    """
    customer = models.ForeignKey(
        Customer,
        on_delete=models.CASCADE,
        related_name='vouchers',
        verbose_name="Customer",
        # db_index is automatically created by Django for ForeignKey fields
    )
    voucher_number = models.CharField(
        max_length=50,
        db_index=True,
        verbose_name="Voucher / Document Number"
    )
    date = models.DateField(
        db_index=True,
        verbose_name="Transaction Date"
    )
    debit = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        verbose_name="Debit Amount (بدهکار)"
    )
    credit = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        verbose_name="Credit Amount (بستانکار)"
    )
    description = models.TextField(
        blank=True,
        default='',
        verbose_name="Description / Note"
    )
    reference = models.CharField(
        max_length=100,
        blank=True,
        default='',
        verbose_name="Reference Document / Invoice"
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Created At")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Updated At")

    class Meta:
        ordering = ['date', 'id']
        indexes = [
            # Compound index covers both (customer, date) and (customer)-only lookups.
            # A standalone date index is redundant — PostgreSQL can use this for date-only scans too.
            models.Index(fields=['customer', 'date'], name='idx_voucher_cust_date'),
        ]

    def clean(self):
        if self.debit == Decimal('0.00') and self.credit == Decimal('0.00'):
            raise ValidationError("A voucher transaction must have either debit or credit amount greater than zero.")

    def save(self, *args, **kwargs):
        # Enforce clean() even on direct ORM saves (e.g., Voucher.objects.create / .save)
        # Django only calls clean() automatically through forms; full_clean() ensures it always runs.
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Voucher #{self.voucher_number} - {self.customer.code} - {self.date} (D: {self.debit}, C: {self.credit})"
