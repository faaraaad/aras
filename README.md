# Aras Accounting System

A high-performance accounting report and customer balance management platform built with **Django REST Framework**, **Celery**, and **Redis**. Designed for high-volume financial transaction tracking, complex ledger aggregation, and asynchronous reporting.

---

## 📑 Table of Contents

1. [Architectural & Design Decisions](#-architectural--design-decisions)
2. [Data Models & Schema Design](#-data-models--schema-design)
3. [URLs & API Reference](#-urls--api-reference)
4. [Quick Start with Docker Compose](#-quick-start-with-docker-compose)
5. [Database Seeding & Benchmarking](#-database-seeding--benchmarking)
6. [Celery Background Tasks](#-celery-background-tasks)
7. [Local Development Setup](#-local-development-setup)
8. [Testing & Verification](#-testing--verification)

---

## 🏛️ Architectural & Design Decisions

### 1. Asynchronous Report Processing (Celery + Redis)
- **Problem**: Generating financial balance reports and ledger summaries across hundreds of thousands or millions of voucher records can exceed HTTP request timeouts (e.g., 30s gateway limits), consume excessive web worker memory, and cause thread starvation for incoming client requests.
- **Decision**: Heavy report calculations and large CSV exports are decoupled from the synchronous HTTP request-response cycle. Clients submit a job request, receive a unique `job_id` or `task_id` with HTTP `202 Accepted`, and poll the status endpoint until the background Celery worker completes the task.
- **Reliability**: If a worker encounters an error, the task failure is captured in Celery result backend (Redis) with descriptive error messages, preventing silent crashes.

### 2. Single-Query Conditional Aggregation (Eliminating N+1 Queries)
- **Problem**: Calculating opening balance, period debit, period credit, turnover, and closing balance for hundreds of customers often results in `O(N)` database queries if computed per customer or in Python loops.
- **Decision**: In [`accounting/services.py`](accounting/services.py), `get_customer_balance_queryset` utilizes single-pass SQL conditional aggregation using Django's `Sum(..., filter=Q(...))` with `Coalesce` and `ExpressionWrapper`.
- **Formulas Computed Directly in Database**:
  - **Opening Debit**: `Sum(Debit)` where `date < start_date`
  - **Opening Credit**: `Sum(Credit)` where `date < start_date`
  - **Opening Balance**: `Opening Debit - Opening Credit`
  - **Period Debit**: `Sum(Debit)` where `start_date <= date <= end_date`
  - **Period Credit**: `Sum(Credit)` where `start_date <= date <= end_date`
  - **Period Turnover**: `Period Debit - Period Credit`
  - **Closing Balance**: `Opening Balance + Period Turnover`

### 3. High-Performance Database Indexing Strategy
- **Composite Index `(customer, date, id)`** on `Voucher`: Optimizes customer-specific ledger queries and balance calculations spanning specific date ranges with deterministic ordering.
- **Date Composite Index `(date, id)`** on `Voucher`: Accelerates global date-filtered queries and exports across all customers.
- **Functional Index `Lower('code')`** on `Customer`: Speeds up case-insensitive customer code lookups (`code__iexact`) without triggering full table scans.
- **Primary / Unique Indexes**: `Customer.code` (`unique=True`, `db_index=True`) and `Voucher.voucher_number` (`db_index=True`).

### 4. Financial Data Integrity & Decimal Precision
- **No Floating-Point Math**: All financial amounts use `DecimalField(max_digits=15, decimal_places=2)` to prevent floating-point precision loss.
- **Model-Level Validation (`full_clean` in `save`)**: Prevents zero-amount ghost vouchers (both debit and credit equal 0.00) and ensures non-negative numbers via `MinValueValidator(Decimal('0.00'))`.
- **Standardized Balance Status**:
  - `DEBTOR` (بدهکار): Closing balance > 0 (Customer owes the company).
  - `CREDITOR` (بستانکار): Closing balance < 0 (Company owes the customer).
  - `BALANCED` (بی‌حساب / تسویه): Closing balance = 0.

### 5. Stateless JWT Authentication with Token Blacklisting
- Uses `django-rest-framework-simplejwt` for token-based authentication.
- Stateless access tokens (short-lived) minimize database lookups on authenticated API requests.
- Refresh token blacklisting on `/api/auth/logout/` allows secure revocation when users end their sessions.

---

## 🗄️ Data Models & Schema Design

Located in [`accounting/models.py`](accounting/models.py):

### 1. `Customer` Model
Represents a customer / client account in the accounting system (receivable account with debit nature).

| Field | Type | Modifiers / Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | `BigAutoField` | `primary_key=True` | Unique customer auto-increment ID |
| `name` | `CharField(255)` | - | Customer full name or business entity name |
| `code` | `CharField(50)` | `unique=True`, `db_index=True` | Unique customer identification code |
| `is_active` | `BooleanField` | `default=True`, `db_index=True` | Active status flag for report filtering |
| `created_at` | `DateTimeField` | `auto_now_add=True` | Timestamp when the record was created |
| `updated_at` | `DateTimeField` | `auto_now=True` | Timestamp when the record was last updated |

- **Indexes**:
  - `idx_cust_code_lower`: Functional index on `Lower('code')` for fast case-insensitive lookups.
- **Ordering**: `['code']`

---

### 2. `Voucher` Model
Represents a financial voucher / transaction line item associated with a customer.

| Field | Type | Modifiers / Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | `BigAutoField` | `primary_key=True` | Unique voucher transaction ID |
| `customer` | `ForeignKey(Customer)` | `on_delete=CASCADE`, `related_name='vouchers'` | Associated customer account |
| `voucher_number`| `CharField(50)` | `db_index=True` | Document / Voucher reference number |
| `date` | `DateField` | `db_index=True` | Transaction date |
| `debit` | `DecimalField(15, 2)`| `default=0.00`, `MinValueValidator(0.00)` | Debit amount (بدهکار) — Increases receivable |
| `credit` | `DecimalField(15, 2)`| `default=0.00`, `MinValueValidator(0.00)` | Credit amount (بستانکار) — Decreases receivable |
| `description` | `TextField` | `blank=True`, `default=''` | Transaction notes or explanations |
| `reference` | `CharField(100)` | `blank=True`, `default=''` | External reference (e.g. invoice or cheque number) |
| `created_at` | `DateTimeField` | `auto_now_add=True` | Timestamp when the record was created |
| `updated_at` | `DateTimeField` | `auto_now=True` | Timestamp when the record was last updated |

- **Indexes**:
  - `idx_voucher_cust_date_id`: Compound index on `['customer', 'date', 'id']` for customer date-range queries and pagination.
  - `idx_voucher_date_id`: Compound index on `['date', 'id']` for global date filtering.
- **Integrity Validation**:
  - Overridden `clean()` raises `ValidationError` if both `debit` and `credit` are zero.
  - Overridden `save()` invokes `self.full_clean()` before writing to enforce validation at the ORM layer.
- **Ordering**: `['date', 'id']`

---

## 🌐 URLs & API Reference

All routes are mounted under `/api/` (defined in [`accounting/urls.py`](accounting/urls.py) and [`accounting_project/urls.py`](accounting_project/urls.py)).

### 1. System Endpoints

| Method | URL | Description | Auth Required |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/health/` | Service health check for container probes / monitoring | No |
| `GET` | `/admin/` | Django administration portal | Admin Session |

#### Example Health Response (`GET /api/health/`)
```json
{
  "status": "healthy",
  "service": "aras2-accounting-api"
}
```

---

### 2. Authentication Endpoints (JWT)

| Method | URL | Description | Auth Required | Request Body / Parameters |
| :--- | :--- | :--- | :--- | :--- |
| `POST` | `/api/auth/register/` | Register new user and auto-login | No | `{"username", "email", "password", "password_confirm"}` |
| `POST` | `/api/auth/token/` | Obtain access & refresh token pair | No | `{"username", "password"}` |
| `POST` | `/api/auth/token/refresh/` | Refresh expired access token | No | `{"refresh": "<token>"}` |
| `POST` | `/api/auth/token/verify/` | Verify token validity | No | `{"token": "<token>"}` |
| `GET` | `/api/auth/me/` | Retrieve authenticated user profile | Yes (`Bearer <token>`) | None |
| `POST` | `/api/auth/logout/` | Blacklist refresh token & logout | Yes (`Bearer <token>`) | `{"refresh": "<token>"}` |

---

### 3. Voucher Endpoints

#### `GET /api/vouchers/`
Retrieve paginated voucher transactions with optional filters.

- **Query Parameters**:
  - `start_date` *(optional, `YYYY-MM-DD`)*: Filter vouchers on or after this date.
  - `end_date` *(optional, `YYYY-MM-DD`)*: Filter vouchers on or before this date.
  - `customer_code` *(optional, `string`)*: Filter vouchers for a specific customer code.
  - `page` *(optional, integer, default: 1)*: Page number.
  - `page_size` *(optional, integer, default: 20, max: 100)*: Items per page.

- **Response Example**:
```json
{
  "count": 250,
  "next": "http://localhost:8000/api/vouchers/?page=2",
  "previous": null,
  "results": [
    {
      "id": 101,
      "voucher_number": "VCH-2026-0001",
      "date": "2026-01-15",
      "customer": 5,
      "customer_code": "CUST-005",
      "customer_name": "ACME Corporation",
      "debit": "1500000.00",
      "credit": "0.00",
      "description": "Invoice #8841",
      "reference": "INV-8841",
      "created_at": "2026-01-15T10:30:00Z",
      "updated_at": "2026-01-15T10:30:00Z"
    }
  ]
}
```

---

### 4. Accounting Balance Report Endpoints

#### `POST /api/reports/customer-balance/async/`
Submits an asynchronous background task to calculate customer opening balances, period debit/credit, turnover, and closing balances.

- **Request Body**:
```json
{
  "start_date": "2026-01-01",
  "end_date": "2026-03-31",
  "customer_code": "CUST-001"
}
```
*(Note: `customer_code` is optional; omitting it calculates balances across all active customers.)*

- **Response (`202 Accepted`)**:
```json
{
  "message": "Report generation job queued. Poll the status endpoint with the job_id.",
  "job_id": "c7b6f3c1-901d-4eb7-a548-cfae67417531",
  "status": "PENDING"
}
```

---

#### `GET /api/reports/customer-balance/async/<job_id>/`
Polls the execution status and retrieves computed results for an async balance report job.

- **Response when Completed (`200 OK`)**:
```json
{
  "status": "SUCCESS",
  "result": {
    "period": {
      "start_date": "2026-01-01",
      "end_date": "2026-03-31",
      "customer_code": "CUST-001"
    },
    "summary": {
      "total_opening_balance": "500000.00",
      "total_period_debit": "1200000.00",
      "total_period_credit": "700000.00",
      "total_closing_balance": "1000000.00"
    },
    "results": [
      {
        "id": 1,
        "code": "CUST-001",
        "name": "ACME Corp",
        "is_active": true,
        "opening_balance": "500000.00",
        "period_debit": "1200000.00",
        "period_credit": "700000.00",
        "period_turnover": "500000.00",
        "closing_balance": "1000000.00",
        "balance_status": "DEBTOR"
      }
    ]
  }
}
```

---

### 5. CSV Export Endpoints

#### `POST /api/reports/customer-balance/export-async/`
Queues background streaming generation of a CSV export file.

- **Request Body**:
```json
{
  "start_date": "2026-01-01",
  "end_date": "2026-03-31"
}
```
- **Response (`202 Accepted`)**:
```json
{
  "message": "Report export job queued successfully.",
  "task_id": "a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d",
  "status": "PENDING"
}
```

---

#### `GET /api/reports/customer-balance/export-async/<task_id>/`
Checks export generation progress and returns the download URL once ready.

- **Response when Ready (`200 OK`)**:
```json
{
  "status": "SUCCESS",
  "task_id": "a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d",
  "download_url": "http://localhost:8000/api/reports/customer-balance/export-async/a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d/download/",
  "result": {
    "file_path": "exports/customer_balance_2026-01-01_2026-03-31_a1b2c3d4.csv",
    "filename": "customer_balance_report_2026-01-01_2026-03-31.csv",
    "total_records": 1000
  }
}
```

---

#### `GET /api/reports/customer-balance/export-async/<task_id>/download/`
Streams the generated `.csv` file as an attachment (`Content-Type: text/csv`).

---

## 🚀 Quick Start with Docker Compose

Run the entire stack (Django API, Redis, Celery Worker, and Celery Beat) with Docker Compose:

```bash
# Start all services in the background
docker compose up --build -d

# View live container logs
docker compose logs -f

# Stop services
docker compose down
```

### Services Breakdown

| Service | Port | Description |
| :--- | :--- | :--- |
| **`web`** | `8000` | Django WSGI API served via Gunicorn (auto-applies migrations) |
| **`redis`** | `6379` | Celery message broker & result backend |
| **`celery_worker`** | - | Background async task worker (reports & CSV exports) |
| **`celery_beat`** | - | Periodic task scheduler |

---

## 💾 Database Seeding & Benchmarking

Seed the database with high-volume realistic dummy customers and voucher transactions for stress and performance testing:

### Inside Docker (Recommended)
```bash
# Seed with 1,000 customers and 200-300 vouchers each (~250,000 vouchers)
docker compose exec web python populate_db.py --customers 1000 --min-vouchers 200 --max-vouchers 300

# Flush existing data before seeding
docker compose exec web python populate_db.py --customers 1000 --flush
```

### Local CLI / Management Command
```bash
# Standalone script
python populate_db.py --customers 1000 --min-vouchers 200 --max-vouchers 300

# Django management command
python manage.py populate_db --customers 1000 --min-vouchers 200 --max-vouchers 300 --batch-size 5000
```

#### CLI Flags
- `--customers`: Number of customers to create *(default: 1000)*
- `--min-vouchers`: Min vouchers per customer *(default: 200)*
- `--max-vouchers`: Max vouchers per customer *(default: 300)*
- `--batch-size`: Bulk insert batch size *(default: 5000)*
- `--flush`: Clears existing records before populating

---

## ⚡ Celery Background Tasks

Located in [`accounting/tasks.py`](accounting/tasks.py):

1. **`generate_customer_balance_report_task`**
   - Computes aggregated customer balance metrics via `get_customer_balance_queryset` and `get_balance_report_summary`.
   - Serializes payload data using `CustomerBalanceItemSerializer` and returns structured JSON dictionary stored in Redis.
2. **`export_customer_balance_csv_task`**
   - Streams customer balance records and summary rows into formatted CSV files saved under `media/exports/`.

### Running Celery Locally (Without Docker)

```bash
# Start Celery Worker
celery -A accounting_project worker -l INFO --concurrency=4

# Start Celery Beat Scheduler
celery -A accounting_project beat -l INFO
```

---

## 💻 Local Development Setup

```bash
# 1. Create and activate virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Apply migrations & start server
python manage.py migrate
python manage.py runserver 0.0.0.0:8000
```

---

## 🧪 Testing & Verification

Execute the test suites covering authentication, balance reporting, voucher filtering, and Celery async workflows:

```bash
# Run all tests
python manage.py test

# Run specific test suites
python manage.py test accounting.tests.test_auth
python manage.py test accounting.tests.test_vouchers
python manage.py test accounting.tests.test_reports
```
