from decimal import Decimal
from rest_framework import serializers
from .models import Customer, Voucher

# Pre-instantiated at module level — avoids creating a new Decimal on every serialized row
_ZERO = Decimal('0.00')


class VoucherFilterSerializer(serializers.Serializer):
    """
    Validates input query parameters for voucher listing/filtering.
    """
    start_date = serializers.DateField(required=False, allow_null=True)
    end_date = serializers.DateField(required=False, allow_null=True)
    customer_code = serializers.CharField(required=False, allow_null=True, allow_blank=True, max_length=50)

    def validate(self, data):
        start_date = data.get('start_date')
        end_date = data.get('end_date')
        if start_date and end_date and start_date > end_date:
            raise serializers.ValidationError({
                "end_date": "end_date cannot be earlier than start_date."
            })

        customer_code = data.get('customer_code')
        if customer_code is not None:
            customer_code = str(customer_code).strip()
            data['customer_code'] = customer_code if customer_code else None
        else:
            data['customer_code'] = None

        return data


class VoucherSerializer(serializers.ModelSerializer):
    """
    Serializes a Voucher transaction with associated customer information.
    """
    customer_code = serializers.CharField(source='customer.code', read_only=True)
    customer_name = serializers.CharField(source='customer.name', read_only=True)

    class Meta:
        model = Voucher
        fields = [
            'id',
            'voucher_number',
            'date',
            'customer',
            'customer_code',
            'customer_name',
            'debit',
            'credit',
            'description',
            'reference',
            'created_at',
            'updated_at',
        ]


class CustomerBalanceFilterSerializer(serializers.Serializer):
    """
    Validates input query parameters for the customer balance report.
    """
    start_date = serializers.DateField(required=True)
    end_date = serializers.DateField(required=True)
    customer_code = serializers.CharField(required=False, allow_null=True, allow_blank=True, max_length=50)

    def validate(self, data):
        if data['start_date'] > data['end_date']:
            raise serializers.ValidationError({
                "end_date": "end_date cannot be earlier than start_date."
            })

        customer_code = data.get('customer_code')
        if customer_code is not None:
            customer_code = str(customer_code).strip()
            if customer_code:
                customer = Customer.objects.filter(code__iexact=customer_code).first()
                if not customer:
                    raise serializers.ValidationError({
                        "customer_code": f"Customer with code '{customer_code}' does not exist."
                    })
                data['customer_code'] = customer.code
            else:
                data['customer_code'] = None
        else:
            data['customer_code'] = None

        return data


class CustomerBalanceItemSerializer(serializers.ModelSerializer):
    """
    Serializes a single customer's balance metrics.
    """
    opening_balance = serializers.DecimalField(max_digits=15, decimal_places=2, read_only=True)
    period_debit = serializers.DecimalField(max_digits=15, decimal_places=2, read_only=True)
    period_credit = serializers.DecimalField(max_digits=15, decimal_places=2, read_only=True)
    period_turnover = serializers.DecimalField(max_digits=15, decimal_places=2, read_only=True)
    closing_balance = serializers.DecimalField(max_digits=15, decimal_places=2, read_only=True)
    balance_status = serializers.SerializerMethodField()

    class Meta:
        model = Customer
        fields = [
            'id',
            'code',
            'name',
            'is_active',
            'opening_balance',
            'period_debit',
            'period_credit',
            'period_turnover',
            'closing_balance',
            'balance_status',
        ]

    def get_balance_status(self, obj) -> str:
        closing = getattr(obj, 'closing_balance', _ZERO)
        if closing > _ZERO:
            return "DEBTOR"   # بدهکار (بدهی دارد به شرکت)
        elif closing < _ZERO:
            return "CREDITOR" # بستانکار (شرکت به مشتری بدهکار است)
        return "BALANCED"     # بی‌حساب / تسویه


class CustomerBalanceSummarySerializer(serializers.Serializer):
    total_opening_balance = serializers.DecimalField(max_digits=15, decimal_places=2)
    total_period_debit = serializers.DecimalField(max_digits=15, decimal_places=2)
    total_period_credit = serializers.DecimalField(max_digits=15, decimal_places=2)
    total_closing_balance = serializers.DecimalField(max_digits=15, decimal_places=2)
