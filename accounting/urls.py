from django.urls import path
from rest_framework_simplejwt.views import TokenObtainPairView
from .views import (
    VoucherListAPIView,
    CustomerBalanceExportAsyncAPIView,
    CustomerBalanceExportStatusView,
    CustomerBalanceExportDownloadView,
    CustomerBalanceReportSubmitView,
    CustomerBalanceReportStatusView,
    HealthCheckView,
)
from .auth_views import (
    RegisterView,
    ProfileView,
    LogoutView,
)

app_name = 'accounting'

urlpatterns = [
    # ── Health check endpoint ──────────────────────────────────────────────────
    path('health/', HealthCheckView.as_view(), name='health_check'),

    # ── Auth endpoints ──────────────────────────────────────────────────────────
    path('auth/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('auth/register/', RegisterView.as_view(), name='auth_register'),
    path('auth/me/', ProfileView.as_view(), name='auth_me'),
    path('auth/logout/', LogoutView.as_view(), name='auth_logout'),

    # ── Voucher & Accounting report endpoints ──────────────────────────────────
    path('vouchers/', VoucherListAPIView.as_view(), name='voucher-list'),

    # CSV export (async workflow: submit, poll status, download file)
    path('reports/customer-balance/export-async/', CustomerBalanceExportAsyncAPIView.as_view(), name='customer-balance-export-async'),
    path('reports/customer-balance/export-async/<str:task_id>/', CustomerBalanceExportStatusView.as_view(), name='customer-balance-export-status'),
    path('reports/customer-balance/export-async/<str:task_id>/download/', CustomerBalanceExportDownloadView.as_view(), name='customer-balance-export-download'),

    # Async report (JSON) — submit job, get back a job_id
    path('reports/customer-balance/async/', CustomerBalanceReportSubmitView.as_view(), name='customer-balance-report-async-submit'),

    # Async report (JSON) — poll job status / retrieve result by job_id
    path('reports/customer-balance/async/<str:job_id>/', CustomerBalanceReportStatusView.as_view(), name='customer-balance-report-async-status'),
]
