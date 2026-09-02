from django.http import FileResponse, Http404
from django.core.files.storage import default_storage
from django.urls import reverse
from rest_framework import generics, status, views
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination

from .models import Customer, Voucher
from .serializers import (
    CustomerBalanceFilterSerializer,
    CustomerBalanceItemSerializer,
    CustomerBalanceSummarySerializer,
    VoucherSerializer,
    VoucherFilterSerializer,
)
from .services import get_customer_balance_queryset, get_balance_report_summary
from .tasks import export_customer_balance_csv_task, generate_customer_balance_report_task

try:
    from celery.result import AsyncResult
except ImportError:
    AsyncResult = None


class StandardResultsSetPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


class VoucherListAPIView(generics.ListAPIView):
    """
    API endpoint to retrieve vouchers filtered by start_date, end_date, and customer_code.

    Query Parameters:
      - start_date (YYYY-MM-DD) [Optional]
      - end_date (YYYY-MM-DD)   [Optional]
      - customer_code (str)     [Optional]
      - page (int)              [Optional]
      - page_size (int)         [Optional]
    """
    serializer_class = VoucherSerializer
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        queryset = Voucher.objects.select_related('customer').all()

        filter_serializer = VoucherFilterSerializer(data=self.request.query_params)
        filter_serializer.is_valid(raise_exception=True)
        params = filter_serializer.validated_data

        start_date = params.get('start_date')
        end_date = params.get('end_date')
        customer_code = params.get('customer_code')

        if start_date:
            queryset = queryset.filter(date__gte=start_date)
        if end_date:
            queryset = queryset.filter(date__lte=end_date)
        if customer_code:
            customer_id = Customer.objects.filter(
                code__iexact=str(customer_code).strip()
            ).values_list('id', flat=True).first()
            if customer_id:
                queryset = queryset.filter(customer_id=customer_id)
            else:
                queryset = queryset.none()

        return queryset.order_by('date', 'id')


class CustomerBalanceExportAsyncAPIView(views.APIView):
    """
    API endpoint to trigger background asynchronous report export (Celery).
    Useful for heavy datasets or downloading large CSV/Excel files.
    """
    def post(self, request, *args, **kwargs):
        filter_serializer = CustomerBalanceFilterSerializer(data=request.data)
        filter_serializer.is_valid(raise_exception=True)
        params = filter_serializer.validated_data

        # Dispatch async task
        async_result = export_customer_balance_csv_task.delay(
            start_date_str=str(params['start_date']),
            end_date_str=str(params['end_date']),
            customer_code=params.get('customer_code')
        )

        task_id = getattr(async_result, 'id', 'sync-task-executed')

        return Response({
            'message': 'Report export job queued successfully.',
            'task_id': task_id,
            'status': 'PENDING'
        }, status=status.HTTP_202_ACCEPTED)


class CustomerBalanceExportStatusView(views.APIView):
    """
    Poll the status of an async CSV export job.

    GET /reports/customer-balance/export-async/<task_id>/
    """
    def get(self, request, task_id, *args, **kwargs):
        if AsyncResult is None:
            return Response(
                {'detail': 'Celery is not installed. Async jobs are unavailable.'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        task_result = AsyncResult(task_id)
        task_state = task_result.state

        if task_state == 'SUCCESS':
            download_url = request.build_absolute_uri(
                reverse('accounting:customer-balance-export-download', kwargs={'task_id': task_id})
            )
            return Response({
                'status': 'SUCCESS',
                'task_id': task_id,
                'download_url': download_url,
                'result': task_result.result,
            }, status=status.HTTP_200_OK)

        if task_state == 'FAILURE':
            return Response({
                'status': 'FAILURE',
                'error': str(task_result.result),
            }, status=status.HTTP_200_OK)

        if task_state == 'REVOKED':
            return Response({'status': 'REVOKED'}, status=status.HTTP_200_OK)

        return Response({'status': task_state}, status=status.HTTP_200_OK)


class CustomerBalanceExportDownloadView(views.APIView):
    """
    Download the generated CSV file for a completed export task.

    GET /reports/customer-balance/export-async/<task_id>/download/
    """
    def get(self, request, task_id, *args, **kwargs):
        if AsyncResult is None:
            return Response(
                {'detail': 'Celery is not installed. Async jobs are unavailable.'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        task_result = AsyncResult(task_id)
        if task_result.state != 'SUCCESS':
            return Response(
                {'detail': f'File is not ready for download. Current status: {task_result.state}'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        result_data = task_result.result or {}
        file_path = result_data.get('file_path')
        filename = result_data.get('filename', 'customer_balance_report.csv')

        if not file_path or not default_storage.exists(file_path):
            raise Http404("Exported file was not found in storage.")

        file_handle = default_storage.open(file_path, 'rb')
        return FileResponse(
            file_handle,
            as_attachment=True,
            filename=filename,
            content_type='text/csv'
        )


class CustomerBalanceReportSubmitView(views.APIView):
    """
    Submit an async customer balance report job.

    POST /reports/customer-balance/async/

    Body Parameters:
      - start_date (YYYY-MM-DD) [Required]
      - end_date (YYYY-MM-DD)   [Required]
      - customer_code (str)     [Optional]

    Returns 202 Accepted with a `job_id` that the client can poll using
    CustomerBalanceReportStatusView to retrieve the completed report.
    """

    def post(self, request, *args, **kwargs):
        filter_serializer = CustomerBalanceFilterSerializer(data=request.data)
        filter_serializer.is_valid(raise_exception=True)
        params = filter_serializer.validated_data

        # Dispatch the report generation to a background Celery worker
        async_result = generate_customer_balance_report_task.delay(
            start_date_str=str(params['start_date']),
            end_date_str=str(params['end_date']),
            customer_code=params.get('customer_code'),
        )

        job_id = getattr(async_result, 'id', 'sync-fallback')

        return Response({
            'message': 'Report generation job queued. Poll the status endpoint with the job_id.',
            'job_id': job_id,
            'status': 'PENDING',
        }, status=status.HTTP_202_ACCEPTED)


class CustomerBalanceReportStatusView(views.APIView):
    """
    Poll the status / result of an async customer balance report job.

    GET /reports/customer-balance/async/<job_id>/

    Response varies by Celery task state:
      - PENDING  → { "status": "PENDING" }
      - SUCCESS  → { "status": "SUCCESS", "result": { period, summary, results } }
      - FAILURE  → { "status": "FAILURE", "error": "<error message>" }
      - REVOKED  → { "status": "REVOKED" }
    """

    def get(self, request, job_id, *args, **kwargs):
        if AsyncResult is None:
            return Response(
                {'detail': 'Celery is not installed. Async jobs are unavailable.'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        task_result = AsyncResult(job_id)
        task_state = task_result.state  # PENDING | STARTED | SUCCESS | FAILURE | REVOKED

        if task_state == 'SUCCESS':
            return Response({
                'status': 'SUCCESS',
                'result': task_result.result,
            }, status=status.HTTP_200_OK)

        if task_state == 'FAILURE':
            # task_result.result holds the exception instance when the task failed
            error_message = str(task_result.result)
            return Response({
                'status': 'FAILURE',
                'error': error_message,
            }, status=status.HTTP_200_OK)

        if task_state == 'REVOKED':
            return Response({'status': 'REVOKED'}, status=status.HTTP_200_OK)

        # PENDING or STARTED — still in progress
        return Response({'status': task_state}, status=status.HTTP_200_OK)


class HealthCheckView(views.APIView):
    """
    Public health check endpoint for container monitors, docker healthchecks, and frontend.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({
            'status': 'healthy',
            'service': 'aras2-accounting-api'
        }, status=status.HTTP_200_OK)

