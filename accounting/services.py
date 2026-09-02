from decimal import Decimal
from django.db.models import Sum, Q, Value, F, DecimalField, ExpressionWrapper
from django.db.models.functions import Coalesce
from .models import Customer

# Module-level constants — avoids re-instantiating Decimal/Value objects on every call
_DECIMAL_FIELD = DecimalField(max_digits=15, decimal_places=2)
_DECIMAL_ZERO = Value(Decimal('0.00'), output_field=_DECIMAL_FIELD)


def get_customer_balance_queryset(start_date, end_date, customer_code=None, is_active_only=True):
    """
    Builds an optimized queryset that calculates opening balance, period debit,
    period credit, and closing balance for each customer in a SINGLE database query.
    
    Prevents N+1 Query Problem by using conditional aggregation (annotate + Sum + Q filter).
    
    Formula:
      - Opening Balance = Sum(Debit[date < start_date]) - Sum(Credit[date < start_date])
      - Period Debit   = Sum(Debit[start_date <= date <= end_date])
      - Period Credit  = Sum(Credit[start_date <= date <= end_date])
      - Period Turnover= Period Debit - Period Credit
      - Closing Balance = Opening Balance + Period Debit - Period Credit
    """
    # Pre-build filter conditions and aggregate expressions so they can be
    # reused in derived annotations without repeating string lookups.
    before_start = Q(vouchers__date__lt=start_date)
    in_period    = Q(vouchers__date__range=(start_date, end_date))

    opening_debit_expr  = Coalesce(Sum('vouchers__debit',  filter=before_start), _DECIMAL_ZERO)
    opening_credit_expr = Coalesce(Sum('vouchers__credit', filter=before_start), _DECIMAL_ZERO)
    period_debit_expr   = Coalesce(Sum('vouchers__debit',  filter=in_period),    _DECIMAL_ZERO)
    period_credit_expr  = Coalesce(Sum('vouchers__credit', filter=in_period),    _DECIMAL_ZERO)

    qs = Customer.objects.all()

    if is_active_only:
        qs = qs.filter(is_active=True)

    if customer_code:
        qs = qs.filter(code__iexact=str(customer_code).strip())

    # Single annotate() call — avoids the subquery Django generates when a second
    # annotate() references annotations from the first (double GROUP BY problem).
    # ExpressionWrapper carries the repeated aggregate expressions; the DB optimizer
    # (PostgreSQL) will evaluate identical aggregate sub-expressions only once.
    qs = qs.annotate(
        # Raw aggregates
        opening_debit=opening_debit_expr,
        opening_credit=opening_credit_expr,
        period_debit=period_debit_expr,
        period_credit=period_credit_expr,
        # Derived balances — computed entirely in the DB, no Python arithmetic
        opening_balance=ExpressionWrapper(
            opening_debit_expr - opening_credit_expr,
            output_field=_DECIMAL_FIELD,
        ),
        period_turnover=ExpressionWrapper(
            period_debit_expr - period_credit_expr,
            output_field=_DECIMAL_FIELD,
        ),
        closing_balance=ExpressionWrapper(
            opening_debit_expr - opening_credit_expr + period_debit_expr - period_credit_expr,
            output_field=_DECIMAL_FIELD,
        ),
    ).order_by('code')

    return qs


def get_balance_report_summary(queryset):
    """
    Computes grand total summary for all customers in the report queryset using aggregate().
    """
    summary = queryset.aggregate(
        total_opening_balance=Coalesce(Sum('opening_balance'), Value(Decimal('0.00'), output_field=DecimalField())),
        total_period_debit=Coalesce(Sum('period_debit'), Value(Decimal('0.00'), output_field=DecimalField())),
        total_period_credit=Coalesce(Sum('period_credit'), Value(Decimal('0.00'), output_field=DecimalField())),
        total_closing_balance=Coalesce(Sum('closing_balance'), Value(Decimal('0.00'), output_field=DecimalField())),
    )
    return summary
