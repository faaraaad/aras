from django.contrib import admin
from .models import Customer, Voucher


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'is_active', 'created_at')
    search_fields = ('code', 'name')
    list_filter = ('is_active',)


@admin.register(Voucher)
class VoucherAdmin(admin.ModelAdmin):
    list_display = ('voucher_number', 'customer', 'date', 'debit', 'credit', 'reference')
    search_fields = ('voucher_number', 'customer__name', 'customer__code', 'reference', 'description')
    list_filter = ('date', 'customer')
    date_hierarchy = 'date'
