# Smart Campus — Student & Faculty Management System

A complete, secure and scalable records system for a college or university: students,
faculty, departments, courses, attendance and reporting, behind role-based access with a
full audit trail. Premium responsive UI (light + dark), FastAPI backend, SQLAlchemy,
PostgreSQL-ready, and designed to stay fast at millions of rows.

![stack](https://img.shields.io/badge/FastAPI-0.115-009688) ![stack](https://img.shields.io/badge/React-18-61dafb) ![db](https://img.shields.io/badge/SQLite%20%7C%20PostgreSQL-ready-336791)

---

## 1. What it does

| Module | Capabilities |
| --- | --- |
| **Students** | Create, update, delete (typed confirmation), searchable/sortable/paginated register, full profile page with attendance calendar, CSV/XLSX/PDF export, Excel/CSV import with per-row error report, downloadable import template |
| **Faculty** | Same CRUD + search, department/subject/experience tracking, exports |
| **Departments & Courses** | Reference data with student/faculty/course counts; safe deletes (blocked while referenced) |
| **Attendance** | Daily register for students *and* faculty, bulk marking, idempotent re-marking, paginated monthly report with per-person percentage (sortable, Excel/CSV/PDF export), per-student calendar |
| **Dashboard** | Totals, active students, today's attendance %, 5 charts (admissions trend, gender split, students/faculty per department, 14-day attendance), recently added students, recently updated records, live activity feed |
| **Security** | JWT access + refresh tokens, bcrypt hashing, 3 roles, login throttling, audit log of every write, security headers, parameterised queries only |
| **Operations** | Timestamped database backups, one-click restore (SQLite), full project download, system info, migrations |

## 2. Technology

- **Backend** — Python 3.12, FastAPI, SQLAlchemy 2.x, Pydantic v2, Alembic, PyJWT, bcrypt
- **Frontend** — React 18 + TypeScript, Vite, Tailwind CSS, Recharts, framer-motion, lucide-react
- **Database** — SQLite by default; PostgreSQL via one environment variable
- **Exports** — openpyxl (XLSX), reportlab (PDF), standard `csv`

The built frontend is served by FastAPI itself, so there is **one process, one port, no CORS**.

## 3. Quick start

### Windows (PowerShell or double-click `start.bat`)

```powershell
py -3 -m venv backend\.venv; backend\.venv\Scripts\python -m pip install -r requirements.txt; backend\.venv\Scripts\python run.py
```

### macOS / Linux

```bash
python3 -m venv backend/.venv && backend/.venv/bin/pip install -r requirements.txt && backend/.venv/bin/python run.py
```

The app opens at **http://127.0.0.1:8000** (API docs at `/api/docs`).

### First sign-in

| Username | Password |
| --- | --- |
| `admin` | `Admin@12345` |

(or `admin@smartcampus.local`). You are asked to change this password — do it before
letting anyone else in, and set `DEFAULT_ADMIN_PASSWORD` / `SECRET_KEY` for real deployments.

### Optional: demo data

Fresh installs start with reference data only (6 departments, 8 courses, no students —
never fake student records in production).

```bash
backend/.venv/bin/python -m backend.seed --students 2000 --faculty 60 --attendance-days 24 --attendance-people 900
```

## 4. Using the app

1. **Departments → Courses** — create your academic structure first.
2. **Students / Faculty** — add records manually, or bulk-import students from Excel
   (`Students → Import → Template`). Department and course **codes** in the sheet must exist.
3. **Attendance** — pick type, date, department (and semester), tap P/A/L/E per person
   (or "All present"), then **Save**. Re-marking the same day updates instead of duplicating.
4. **Monthly report** — switch the tab, choose month/year; export the table to CSV.
5. **Reports & exports** — registers in Excel/CSV/PDF, plus per-department exports.
6. **Settings** — change password, switch theme, download the project zip, and (as admin)
   create/restore backups.
7. **Activity log** (admin) — every create/update/delete/import/export/backup with user, time and IP.

## 5. Roles

| Role | Can do |
| --- | --- |
| **Admin** | Everything, including users, activity log, backups/restore and project download |
| **Staff** | Students, faculty, departments/courses, attendance, exports — no users, logs or backups |
| **Faculty** | Read records and dashboards, mark attendance |

All checks are enforced in the API (`require_roles`), not just hidden in the UI.

## 6. PostgreSQL (production)

```bash
pip install -r requirements-postgres.txt
export DATABASE_URL="postgresql+psycopg://smartcampus:secret@localhost:5432/smartcampus"
alembic upgrade head
python run.py
```

Or the whole stack with Docker (Postgres 16 + app, frontend built in a Node stage):

```bash
docker compose up --build
```

## 7. Database & schema

```
departments ─┬─< courses ─< students >─ attendance
             ├─< faculty  >─ attendance
             └─< students

users ─< activity_logs
      └─< attendance.marked_by
```

- Unique keys: `students.student_id`, `students.enrollment_no`, `students.email`,
  `faculty.faculty_id`, `faculty.email`, `departments.code`, `courses.code`, `users.username`.
- Foreign keys everywhere with deliberate `RESTRICT` / `CASCADE` / `SET NULL` behaviour.
- Indexes on every filtered/sorted column, composites for the hot paths
  (`department_id + semester`, `academic_status + created_at`, `date + status`,
  `person_type + date`), and unique `(student_id, date)` / `(faculty_id, date)` pairs
  so one attendance row exists per person per day.
- Migrations: `alembic upgrade head` (the app also runs `create_all` as a safety net for
  first boot). Generate the next one with
  `alembic revision --autogenerate -m "message"`.

## 8. API overview (`/api/v1`)

| Group | Endpoints |
| --- | --- |
| Auth | `POST /auth/login`, `POST /auth/refresh`, `GET /auth/me`, `POST /auth/change-password` |
| Students | `GET/POST /students`, `GET/PUT/DELETE /students/{id}`, `GET /students/export?format=csv\|xlsx\|pdf`, `POST /students/import`, `GET /students/import/template` |
| Faculty | `GET/POST /faculty`, `GET/PUT/DELETE /faculty/{id}`, `GET /faculty/export` |
| Reference | `GET/POST/PUT/DELETE /departments`, `GET/POST/PUT/DELETE /courses` |
| Attendance | `GET /attendance/sheet`, `POST /attendance/bulk`, `GET /attendance`, `GET /attendance/monthly` (paged, sortable), `GET /attendance/monthly/export?format=csv\|xlsx\|pdf`, `GET /attendance/summary`, `GET /attendance/trend`, `GET /attendance/person/{type}/{id}/calendar` |
| Dashboard | `GET /dashboard/stats` |
| Admin | `GET /activity`, `GET/POST/PUT/DELETE /users`, `POST /system/backup`, `GET /system/backups`, `GET /system/backups/{name}`, `POST /system/restore`, `GET /system/info`, `GET /system/source.zip` |

All list endpoints accept `page`, `page_size` (max 200) and their own filters/sort fields;
responses are `{ items, total, page, page_size, pages }`.

## 9. Security

- Passwords hashed with **bcrypt** (cost 12), never stored or logged in clear text.
- **JWT** access token (60 min) + refresh token (7 days); role resolved from the database on
  every request, so deactivating a user kills their session immediately.
- Login throttling: 5 failures per user+IP per 15 minutes.
- Every statement goes through SQLAlchemy `select()` with bound parameters — no string-built SQL.
- Deletes require a confirmation dialog plus typing the record's ID; the API records who did it.
- Security headers (CSP, `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`), gzip.
- PII stays in the database; exports and backups are admin/role-gated and audited.

## 10. Performance

Measured on this codebase with **100,000 students and 340,000 attendance rows** (SQLite, one
laptop-class core):

| Query | Time |
| --- | --- |
| Page of 25 · department + semester filter | 5.9 ms |
| Total count for the same filter | 0.4 ms |
| Deep page · `OFFSET 20,000` | 0.9 ms |
| Exact Student ID lookup | 0.2 ms |
| Dashboard · three `COUNT(*)` queries | 7.3 ms |
| Students-per-department chart | 7.4 ms |
| Monthly attendance report (GROUP BY) | 4.5 ms |
| 14-day attendance trend | 17.9 ms |
| `LIKE '%name%'` count (unindexed contains search) | 20.7 ms |

Reproduce with `DATABASE_URL=sqlite:////tmp/bench.db python scripts/benchmark.py`.
Never more than one page of rows crosses the wire; exports are capped by `EXPORT_ROW_LIMIT`.
Full scaling notes (Postgres tuning, partitioning, trigram search): [`docs/PERFORMANCE.md`](docs/PERFORMANCE.md).

## 11. Tests

```bash
backend/.venv/bin/pip install -r requirements-dev.txt
backend/.venv/bin/python -m pytest        # 82 tests
```

Covers auth + RBAC, student/faculty CRUD and duplicate rejection, validation errors,
search/sort/pagination, import error reporting, attendance bulk-mark + monthly maths and
report paging/sorting, CSV/XLSX/PDF exports (students, faculty, attendance), backups,
audit log and the project download.

## 12. Project layout

```
SmartCampus/
├── backend/
│   ├── app.py            FastAPI app + SPA hosting
│   ├── config.py         env-driven settings
│   ├── database.py       engine, session, base
│   ├── models.py         SQLAlchemy models + indexes
│   ├── schemas.py        Pydantic validation
│   ├── security.py       hashing, JWT, RBAC, throttling
│   ├── seed.py           reference data, admin, demo generator
│   ├── routers/          auth, students, faculty, reference, attendance,
│   │                     dashboard, admin, system
│   ├── services/         exports (csv/xlsx/pdf), audit log
│   ├── alembic/          migrations
│   ├── tests/            pytest suite
│   └── static/           built frontend (served by FastAPI)
├── frontend/             React + TS + Tailwind + Recharts source
├── scripts/benchmark.py  scale benchmark
├── docs/PERFORMANCE.md
├── run.py                launcher (prints URLs, opens browser)
├── start.bat / start.sh  one-command start
├── Dockerfile / docker-compose.yml
└── requirements*.txt
```

## 13. Troubleshooting

| Symptom | Fix |
| --- | --- |
| `Address already in use` | Something else uses port 8000 → `python run.py --port 8080` |
| Page says "Frontend build not found" | `cd frontend && npm install && npm run build` |
| Forgot the admin password | `backend/.venv/bin/python -m backend.seed --init` only creates it when no user exists; restore a backup or reset it with a short Python snippet (see docs) |
| Import rejects rows | Department/course codes must already exist; the error table names the row |
| Backup restore on PostgreSQL | Automated live restore is SQLite-only; use `pg_restore` and restart |

## 14. Licence

Provided as-is for institutional use. No personal data is bundled; all demo records are
synthetic and must never be used as real student data.
