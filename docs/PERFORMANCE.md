# Performance & scaling

Smart Campus is built so the browser only ever receives one page of data. This document
records the decisions that make that true, the measured numbers at 100k records, and what to
change for millions.

## 1. What is already in place

**Pagination everywhere.** Every list endpoint takes `page` / `page_size` (1–200) and returns
`total` + `pages`. The daily attendance register caps a sheet at 2,000 people and paginates the
rendered list 40 at a time; the monthly report caps rows per request and asks you to filter by
department. Exports never stream more than `EXPORT_ROW_LIMIT` (50,000) rows.

**Indexes chosen for the actual query patterns**

| Table | Index | Purpose |
| --- | --- | --- |
| students | `student_id`, `enrollment_no`, `email` (unique) | duplicate rejection + exact lookup |
| students | `department_id`, `semester`, `academic_status`, `created_at`, `updated_at` | filters and sort |
| students | `(department_id, semester)`, `(academic_status, created_at)` | the two hottest combinations |
| faculty | `faculty_id`, `email` (unique), `department_id`, `employment_status` | CRUD + filters |
| attendance | `(student_id, date)` / `(faculty_id, date)` unique | one row per person per day (NULLs make each a partial key) |
| attendance | `(date, status)`, `(person_type, date)` | daily summary + trend |
| activity_logs | `(entity, created_at)`, `created_at` | log page and dashboard feed |

**Aggregation in SQL, never in Python.** Dashboard and report numbers are `COUNT(*)` and
`GROUP BY` queries; no endpoint loads a table to count it.

**No `SELECT *`.** ORM queries select the mapped columns; relationship names are joined with
`joinedload` only where the response needs them (department/course), so a 25-row page costs 1–2
queries instead of 51.

**Write-side.** Bulk attendance is one request with up to 5,000 records, applied as
insert-or-update against the day's existing marks. The importer validates rows individually
inside savepoints, so one bad row never aborts the file.

## 2. Measured (SQLite, 100,000 students · 340,000 attendance rows)

```
Page 1 · department + semester filter (25 rows)     5.9 ms
Total count for the same filter                     0.4 ms
Deep page · OFFSET 20,000 (25 rows)                 0.9 ms
Exact Student ID lookup                             0.2 ms
Contains search · name LIKE '%Aadhya%' (count)     20.7 ms
Dashboard · three COUNT(*) queries                  7.3 ms
Chart · students per department (GROUP BY)          7.4 ms
Chart · admissions per month (filtered GROUP BY)   20.9 ms
Report · monthly attendance 30d (GROUP BY, 500)     4.5 ms
Chart · 14-day attendance trend                    17.9 ms
```

`scripts/benchmark.py` reproduces this dataset and timings on any machine.

The one slow path is a **leading-wildcard search** (`%term%`), because no B-tree index can serve
it. It is acceptable at 100k (≈20 ms) and is fixed at scale in §3.

## 3. Scaling to millions of rows

### 3.1 PostgreSQL

```bash
pip install -r requirements-postgres.txt
export DATABASE_URL="postgresql+psycopg://user:pass@host:5432/smartcampus"
alembic upgrade head
python run.py
```

Suggested starting configuration for a 4–8 GB RAM database server:

```
shared_buffers = 25% of RAM
effective_cache_size = 60% of RAM
work_mem = 32MB                 # GROUP BY / sort for reports
maintenance_work_mem = 512MB
random_page_cost = 1.1          # SSD
max_connections = 100           # put PgBouncer in front for >50 app workers
default_statistics_target = 200
```

Notes:

- The engine pool is `pool_size=10, max_overflow=20, pool_recycle=1800`; with `N` uvicorn
  workers plan `10 × N` connections.
- `ANALYZE` after large imports (or `autovacuum_analyze_scale_factor = 0.05` on `students`
  and `attendance`).
- Create indexes concurrently in production:
  `CREATE INDEX CONCURRENTLY ...`.

### 3.2 Leading-wildcard search

Swap `ILIKE '%term%'` for trigram indexes:

```sql
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE INDEX ix_students_name_trgm ON students USING gin (full_name gin_trgm_ops);
CREATE INDEX ix_students_email_trgm ON students USING gin (email gin_trgm_ops);
```

A `GIN` trigram index keeps contains-search in single-digit milliseconds at millions of rows.
For prefix search on IDs (`SC2026…`), a plain B-tree index with `text_pattern_ops` is enough.

### 3.3 Attendance at millions of rows

`attendance` grows fastest (people × days). At ~10M rows:

1. **Partition by year (or month)** on `date` — Postgres 13+ declarative partitioning:
   ```sql
   CREATE TABLE attendance (…) PARTITION BY RANGE (date);
   CREATE TABLE attendance_2026 PARTITION OF attendance
     FOR VALUES FROM ('2026-01-01') TO ('2027-01-01');
   ```
   Monthly reports then scan one partition; old years can be detached and archived.
2. Keep the per-partition unique constraints on `(student_id, date)` / `(faculty_id, date)`.
3. Add a rollup table (`attendance_monthly`: person, month, present, absent, late, excused) if the
   monthly report is opened often — refresh it nightly, and read the live table only for the
   current month.

### 3.4 Deep pagination

`OFFSET 200,000` is linear work even with an index. If users page that deep, switch to keyset
pagination:

```sql
SELECT * FROM students
WHERE (created_at, id) < (:last_created_at, :last_id)
ORDER BY created_at DESC, id DESC
LIMIT 25;
```

The API's `page` contract can keep working — translate `page` to a keyset internally, or add
`after` as an additional parameter for the infinite-scroll case.

### 3.5 Other levers

- **Exports**: move to a background job that writes the file to disk and e-mails/links it, instead
  of holding 50k rows in memory.
- **Caching**: dashboard aggregates are ideal for a 30–60 s cache (Redis or an in-process TTL
  cache); they are read-heavy and change slowly.
- **Read replicas**: point reporting/exports at a replica with a second `SessionLocal`.
- **Analytics of admissions by month**: the existing `GROUP BY` on an indexed `admission_date`
  is fine to ~10M; beyond that precompute a monthly summary table.
- **Compression**: `toast` + `pg_dump` compression already keeps backups small; attendance text
  columns are narrow by design.
- **Monitoring**: log slow queries (`log_min_duration_statement = 250`) and keep `EXPLAIN
  (ANALYZE, BUFFERS)` on the monthly report.

## 4. Frontend performance

- Route-level code splitting is the next win: the bundle is ~880 kB (Recharts dominates). Split
  `Charts` and the export libraries with `React.lazy` when the app is served over slow links.
- Tables render one page (25–100 rows); nothing virtualises a million rows because nothing ever
  fetches them.
- Requests are debounced (350 ms search), cancellable (`AbortController`), and never fire for an
  unmounted page.
