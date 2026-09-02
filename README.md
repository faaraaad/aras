# Aras Accounting System

A high-performance accounting report and customer balance management platform built with **Django REST Framework**, **Celery**, and **Redis**.

---

## 🚀 Quick Start with Docker Compose

Run the entire backend stack (Django API, Redis, Celery Worker, and Celery Beat) with a single command:

```bash
# Start all services in the background
docker compose up --build -d

# View real-time logs
docker compose logs -f

# Stop services
docker compose down
```

### Services Breakdown

| Service | Port | Description |
| :--- | :--- | :--- |
| **`web`** | `8000` | Django WSGI API served via Gunicorn (auto-applies migrations) |
| **`redis`** | `6379` | Celery message broker & result backend |
| **`celery_worker`** | - | Handles async report generation and CSV exports |
| **`celery_beat`** | - | Periodic task scheduler |

---

## 💾 Populate Database

Seed the database with high-volume realistic dummy customers and voucher transactions for stress/performance testing.

### Inside Docker (Recommended)
```bash
# Seed with 1,000 customers and 200-300 vouchers each
docker compose exec web python populate_db.py --customers 1000 --min-vouchers 200 --max-vouchers 300

# Flush existing data before seeding
docker compose exec web python populate_db.py --customers 1000 --flush
```

### Local CLI / Management Command
```bash
# Direct script
python populate_db.py --customers 1000 --min-vouchers 200 --max-vouchers 300

# Django management command
python manage.py populate_db --customers 1000 --min-vouchers 200 --max-vouchers 300 --batch-size 5000
```

#### Available Flags
- `--customers`: Number of customers to create *(default: 1000)*
- `--min-vouchers`: Min vouchers per customer *(default: 200)*
- `--max-vouchers`: Max vouchers per customer *(default: 300)*
- `--batch-size`: Bulk insert batch size *(default: 5000)*
- `--flush`: Clears existing records before populating

---

## 🌐 URLs & API Endpoints

### Application URLs

| Interface | URL | Description |
| :--- | :--- | :--- |
| **API Base** | `http://localhost:8000/api/` | REST API base route |
| **Django Admin** | `http://localhost:8000/admin/` | Admin management panel |
| **Health Check** | `http://localhost:8000/api/health/` | Service health status |

---

### Authentication Endpoints (JWT)

| Method | Endpoint | Description | Auth Required |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/auth/register/` | Register a new user | No |
| `POST` | `/api/auth/token/` | Obtain access & refresh token pair | No |
| `POST` | `/api/auth/token/refresh/` | Refresh expired access token | No |
| `POST` | `/api/auth/token/verify/` | Verify token validity | No |
| `GET` | `/api/auth/me/` | Get current user profile | Yes (`Bearer <token>`) |
| `POST` | `/api/auth/logout/` | Blacklist refresh token & logout | Yes (`Bearer <token>`) |

---

### Accounting & Report Endpoints

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/api/reports/customer-balance/` | **Synchronous Report** (Paginated). Query params: `start_date`, `end_date`, `customer_code`, `page` |
| `POST` | `/api/reports/customer-balance/async/` | **Submit Async Report Job**. Payload: `{"start_date": "...", "end_date": "...", "customer_code": "..."}` &rarr; returns `job_id` |
| `GET` | `/api/reports/customer-balance/async/<job_id>/` | **Poll Async Report Status**. Returns `PENDING`, `STARTED`, or `SUCCESS` with result dataset |
| `POST` | `/api/reports/customer-balance/export-async/` | **Submit Async CSV Export**. Payload: date range &rarr; returns `task_id` |
| `GET` | `/api/reports/customer-balance/export-async/<task_id>/` | **Poll Export Status**. Checks generation progress |
| `GET` | `/api/reports/customer-balance/export-async/<task_id>/download/` | **Download Exported CSV File** |

---

## ⚡ Celery Background Tasks

Located in [`accounting/tasks.py`](accounting/tasks.py):

1. **`generate_customer_balance_report_task`**
   - Calculates aggregated turnover, opening/closing balances, and serializes full report datasets for heavy background processing.
2. **`export_customer_balance_csv_task`**
   - Stream-writes customer vouchers into formatted CSV files stored under `media/exports/` for client download.

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

## 🧪 Running Tests

Execute unit and integration test suites:

```bash
# Run all tests
python manage.py test

# Run specific test suites
python manage.py test accounting.tests.test_auth
python manage.py test accounting.tests.test_reports
```
