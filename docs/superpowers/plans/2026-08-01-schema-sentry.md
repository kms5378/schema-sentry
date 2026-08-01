# Schema Sentry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a PostgreSQL metadata-consistency service that detects schema drift, explains affected Airflow pipelines, blocks unsafe execution, and alerts through Slack and email.

**Architecture:** A synchronous Python application keeps domain policy free of framework dependencies, persists catalog and scan state in a dedicated PostgreSQL repository, and exposes FastAPI endpoints plus one server-rendered dashboard. Airflow remains a separate orchestrator that calls the HTTP API for scheduled scans and pipeline preflight validation; Docker Compose deploys the stack to a personal mini PC.

**Tech Stack:** Python 3.12, uv 0.12.1, FastAPI 0.141.1, Pydantic 2.13.4, Pydantic Settings 2.14.2, SQLAlchemy 2.0.51, Alembic 1.18.5, psycopg 3.3.4, PostgreSQL 17.10, Airflow 3.3.0, Jinja2 3.1.6, HTMX 2.0.10, httpx 0.28.1, PyYAML 6.0.3, structlog 26.1.0, Caddy 2.11.4, Mailpit 1.30.6, Docker Compose, pytest 9.1.1, Ruff 0.16.1, mypy 2.3.0.

## Global Constraints

- Delivery window is 14 calendar days for one developer.
- PostgreSQL is the only source database supported by the MVP.
- Use synchronous SQLAlchemy and psycopg; do not introduce Celery, Redis, Kafka, or an async database layer.
- Source credentials are read-only; secrets never enter Git, API output, logs, or alert error text.
- The UI is one server-rendered dashboard; do not add a SPA, catalog editor, settings page, or dedicated lineage page.
- Lineage is declared in version-controlled YAML; do not add automatic SQL parsing.
- Any open `BREAKING` change blocks every dependent pipeline.
- Core domain and application packages must maintain at least 85 percent test coverage.
- Each task ends with a focused commit and an immediate `git push origin main`; do not combine features into a later bulk push.
- Before every push, run the task-specific tests plus `uv run ruff check .` and `uv run mypy src`.
- Use Conventional Commit messages exactly as specified in each task.
- MCP remains out of scope unless every Task 1-12 acceptance check passes by Day 12.
- Follow the approved design at `docs/superpowers/specs/2026-08-01-schema-sentry-design.md`.

---

## Planned File Map

```text
schema-sentry/
├── .env.example
├── .github/workflows/ci.yml
├── Dockerfile
├── Makefile
├── README.md
├── alembic.ini
├── catalog.yaml
├── docker-compose.yml
├── docker-compose.prod.yml
├── pyproject.toml
├── uv.lock
├── airflow/dags/
│   ├── daily_revenue.py
│   └── schema_consistency_scan.py
├── airflow/tests/
│   ├── test_dag_imports.py
│   └── test_schema_guard.py
├── airflow/Dockerfile
├── alembic/
│   ├── env.py
│   └── versions/0001_metadata_repository.py
├── demo/sql/
│   ├── 001_game_schema.sql
│   ├── 010_breaking_change.sql
│   └── 011_restore_schema.sql
├── deploy/
│   ├── Caddyfile
│   └── postgres/source/001-create-reader.sh
├── docs/
│   ├── architecture.md
│   ├── operations.md
│   └── portfolio-mapping.md
├── scripts/
│   ├── demo.sh
│   └── smoke-test.sh
├── src/schema_sentry/
│   ├── api/
│   │   ├── app.py
│   │   ├── dependencies.py
│   │   ├── security.py
│   │   ├── routers/{alerts,changes,dashboard,health,pipelines,scans}.py
│   │   ├── schemas/{alerts,changes,pipelines,scans}.py
│   │   ├── static/{app.css,htmx.min.js}
│   │   └── templates/{dashboard.html,partials/change_list.html}
│   ├── application/
│   │   ├── catalog_service.py
│   │   ├── change_service.py
│   │   ├── notification_service.py
│   │   ├── ports.py
│   │   ├── scan_service.py
│   │   └── validation_service.py
│   ├── domain/
│   │   ├── diff.py
│   │   ├── enums.py
│   │   ├── fingerprint.py
│   │   ├── lineage.py
│   │   ├── models.py
│   │   └── type_rules.py
│   ├── infrastructure/
│   │   ├── db/
│   │   │   ├── base.py
│   │   │   ├── session.py
│   │   │   ├── postgres_collector.py
│   │   │   ├── models/{__init__,alerts,catalog,lineage,scans}.py
│   │   │   └── repositories/{__init__,alerts,catalog,changes,scans}.py
│   │   └── notifications/{email,slack}.py
│   ├── cli.py
│   ├── config.py
│   └── logging.py
└── tests/
    ├── api/
    ├── integration/
    ├── unit/application/
    └── unit/domain/
```

The grouped names in braces represent separate focused files, not one generated file.

---

### Task 1: Reproducible Project Foundation

**Files:**
- Create: `pyproject.toml`
- Create: `uv.lock`
- Create: `.env.example`
- Create: `src/schema_sentry/__init__.py`
- Create: `src/schema_sentry/config.py`
- Create: `src/schema_sentry/logging.py`
- Create: `src/schema_sentry/api/app.py`
- Create: `tests/conftest.py`
- Create: `tests/unit/test_config.py`
- Create: `tests/api/test_live.py`
- Create: `tests/integration/test_source_permissions.py`
- Create: `Dockerfile`
- Create: `docker-compose.yml`
- Create: `deploy/postgres/source/001-create-reader.sh`
- Create: `.github/workflows/ci.yml`
- Create: `Makefile`
- Modify: `.gitignore`

**Interfaces:**
- Produces: `Settings`, `get_settings() -> Settings`, `configure_logging() -> None`, `create_app() -> FastAPI`.
- Produces: repository PostgreSQL at `metadata-db:5432/schema_sentry`, source PostgreSQL at `source-db:5432/game_source`, and API at `api:8000`.

- [ ] **Step 1: Write configuration and liveness tests**

```python
def test_production_rejects_disabled_auth(monkeypatch):
    monkeypatch.setenv("SCHEMA_SENTRY_ENVIRONMENT", "production")
    monkeypatch.setenv("SCHEMA_SENTRY_AUTH_DISABLED", "true")
    with pytest.raises(ValueError, match="AUTH_DISABLED"):
        Settings()

def test_live_does_not_touch_dependencies(client):
    response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "alive"}

def test_source_reader_cannot_create_tables(source_reader_connection):
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        source_reader_connection.execute("CREATE TABLE public.forbidden(id integer)")
```

- [ ] **Step 2: Run the focused tests and confirm collection fails**

Run: `uv run pytest tests/unit/test_config.py tests/api/test_live.py tests/integration/test_source_permissions.py -q`

Expected: FAIL because the package and fixtures do not exist.

- [ ] **Step 3: Add pinned application and development dependencies**

```toml
[project]
name = "schema-sentry"
version = "0.1.0"
requires-python = ">=3.12,<3.13"
dependencies = [
  "alembic==1.18.5", "fastapi==0.141.1", "httpx==0.28.1",
  "jinja2==3.1.6", "psycopg[binary]==3.3.4", "pydantic==2.13.4",
  "pydantic-settings==2.14.2", "pyyaml==6.0.3", "sqlalchemy==2.0.51",
  "structlog==26.1.0", "typer==0.27.0", "uvicorn[standard]==0.52.0"
]

[dependency-groups]
dev = [
  "mypy==2.3.0", "pytest==9.1.1", "pytest-cov==7.1.0",
  "pytest-asyncio==1.4.0", "respx==0.23.1", "ruff==0.16.1"
]

[project.scripts]
schema-sentry = "schema_sentry.cli:app"

[build-system]
requires = ["hatchling==1.31.0"]
build-backend = "hatchling.build"

[tool.ruff]
target-version = "py312"
line-length = 100

[tool.mypy]
python_version = "3.12"
strict = true

[tool.pytest.ini_options]
testpaths = ["tests"]
```

Run: `uv lock && uv sync --frozen`

Expected: `uv.lock` is generated and all pins resolve on Python 3.12.

- [ ] **Step 4: Implement settings, logging, and the app factory**

```python
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SCHEMA_SENTRY_", env_file=".env")
    environment: Literal["development", "test", "production"] = "development"
    metadata_database_url: str
    source_database_url: str
    api_key: SecretStr
    auth_disabled: bool = False
    log_level: str = "INFO"

    @model_validator(mode="after")
    def protect_production(self) -> "Settings":
        if self.environment == "production" and self.auth_disabled:
            raise ValueError("AUTH_DISABLED cannot be true in production")
        return self

def create_app() -> FastAPI:
    app = FastAPI(title="Schema Sentry", version="0.1.0")
    app.add_api_route("/health/live", lambda: {"status": "alive"})
    return app
```

- [ ] **Step 5: Add containers and CI**

Use `python:3.12-slim`, `ghcr.io/astral-sh/uv:0.12.1`, and two `postgres:17.10-bookworm` services. The source service creates `game_source`; the metadata service uses `schema_sentry`. `001-create-reader.sh` reads `SCHEMA_SENTRY_SOURCE_READER_PASSWORD`, creates a `NOINHERIT` login, grants `CONNECT`, schema `USAGE`, and table `SELECT`, and grants no DDL or write privilege. CI defines both PostgreSQL services and runs these exact commands:

```sh
#!/bin/sh
set -eu
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  --set=reader_password="$SCHEMA_SENTRY_SOURCE_READER_PASSWORD" \
  --set=database_name="$POSTGRES_DB" <<'SQL'
CREATE ROLE schema_sentry_reader NOINHERIT LOGIN PASSWORD :'reader_password';
GRANT CONNECT ON DATABASE :"database_name" TO schema_sentry_reader;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
CREATE SCHEMA IF NOT EXISTS mart;
REVOKE CREATE ON SCHEMA mart FROM PUBLIC;
GRANT USAGE ON SCHEMA public, mart TO schema_sentry_reader;
ALTER DEFAULT PRIVILEGES IN SCHEMA public, mart GRANT SELECT ON TABLES TO schema_sentry_reader;
SQL
```

```yaml
- run: uv sync --frozen
- run: uv run ruff check .
- run: uv run mypy src
- run: uv run pytest --cov=src/schema_sentry --cov-report=term-missing --cov-fail-under=85
```

- [ ] **Step 6: Verify the feature locally**

Run: `docker compose up -d source-db metadata-db && uv run pytest tests/unit/test_config.py tests/api/test_live.py tests/integration/test_source_permissions.py -q && uv run ruff check . && uv run mypy src`

Expected: all commands PASS.

- [ ] **Step 7: Commit the project foundation**

```bash
git add pyproject.toml uv.lock .env.example src tests Dockerfile docker-compose.yml deploy Makefile .github .gitignore
git commit -m "chore: bootstrap schema sentry service"
```

- [ ] **Step 8: Push immediately**

Run: `git push origin main`

Expected: `main -> main` succeeds.

---

### Task 2: Schema Type and Diff Policy Engine

**Files:**
- Create: `src/schema_sentry/domain/enums.py`
- Create: `src/schema_sentry/domain/models.py`
- Create: `src/schema_sentry/domain/type_rules.py`
- Create: `src/schema_sentry/domain/diff.py`
- Create: `src/schema_sentry/domain/fingerprint.py`
- Create: `tests/unit/domain/test_type_rules.py`
- Create: `tests/unit/domain/test_diff.py`
- Create: `tests/unit/domain/test_fingerprint.py`

**Interfaces:**
- Produces enums: `ScanStatus`, `ScanTrigger`, `ChangeType`, `Severity`, `ChangeState`, `PipelineCriticality`, `AlertChannel`, and `AlertStatus`.
- Produces immutable models: `CanonicalType`, `DatasetRef`, `ColumnRef`, `ColumnDefinition`, and `SchemaChange`.
- Produces: `canonicalize_postgres_type(data_type, udt_name, character_maximum_length, numeric_precision, numeric_scale) -> CanonicalType`.
- Produces: `diff_columns(expected, observed) -> tuple[SchemaChange, ...]`.
- Produces: `compare_column(ref, before, after, dependencies) -> tuple[SchemaChange, ...]` and `change_sort_key(change) -> tuple[str, str, str, str]`.
- Produces: `change_fingerprint(source_key, change) -> str`.

- [ ] **Step 1: Write the policy matrix as parameterized failing tests**

```python
@pytest.mark.parametrize(("before", "after", "severity"), [
    ("integer", "bigint", Severity.WARNING),
    ("numeric(12,2)", "character varying", Severity.BREAKING),
    ("character varying(50)", "character varying(20)", Severity.BREAKING),
])
def test_type_change_policy(before, after, severity):
    assert classify_type_change(parse_type(before), parse_type(after)).severity is severity

def test_drop_dependency_is_breaking(column, dependency):
    changes = diff_columns([column], [], dependencies=[dependency])
    assert changes[0].change_type is ChangeType.DROP_COLUMN
    assert changes[0].severity is Severity.BREAKING
```

- [ ] **Step 2: Verify the new tests fail**

Run: `uv run pytest tests/unit/domain -q`

Expected: FAIL with missing domain modules.

- [ ] **Step 3: Implement immutable domain models and enums**

```python
@dataclass(frozen=True, slots=True)
class ColumnDefinition:
    dataset: DatasetRef
    name: str
    data_type: CanonicalType
    nullable: bool
    default: str | None

@dataclass(frozen=True, slots=True)
class SchemaChange:
    dataset: DatasetRef
    column_name: str
    change_type: ChangeType
    severity: Severity
    before: ColumnDefinition | None
    after: ColumnDefinition | None
```

- [ ] **Step 4: Implement canonicalization and deterministic diffing**

Canonicalize `int4`/`integer`, `int8`/`bigint`, varchar length, numeric precision/scale, timestamp timezone, default whitespace, and nullability. Sort output by `(schema, table, column, change_type)` so tests and fingerprints remain stable.

```python
def diff_columns(
    expected: Sequence[ColumnDefinition],
    observed: Sequence[ColumnDefinition],
    dependencies: Collection[ColumnRef] = (),
) -> tuple[SchemaChange, ...]:
    expected_by_ref = {column.ref: column for column in expected}
    observed_by_ref = {column.ref: column for column in observed}
    dependency_set = set(dependencies)
    changes: list[SchemaChange] = []
    for ref in sorted(expected_by_ref.keys() | observed_by_ref.keys()):
        before = expected_by_ref.get(ref)
        after = observed_by_ref.get(ref)
        changes.extend(compare_column(ref, before, after, dependency_set))
    return tuple(sorted(changes, key=change_sort_key))
```

- [ ] **Step 5: Implement SHA-256 fingerprints from canonical JSON**

```python
def change_fingerprint(source_key: str, change: SchemaChange) -> str:
    payload = {"source": source_key, "change": change.to_canonical_dict()}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()
```

- [ ] **Step 6: Verify policy coverage and static checks**

Run: `uv run pytest tests/unit/domain -q && uv run ruff check . && uv run mypy src`

Expected: PASS, including every row in the approved policy table.

- [ ] **Step 7: Commit and push the policy engine**

```bash
git add src/schema_sentry/domain tests/unit/domain
git commit -m "feat: detect breaking schema changes"
git push origin main
```

---

### Task 3: Metadata Repository Schema

**Files:**
- Create: `alembic.ini`
- Create: `alembic/env.py`
- Create: `alembic/versions/0001_metadata_repository.py`
- Create: `src/schema_sentry/infrastructure/db/base.py`
- Create: `src/schema_sentry/infrastructure/db/session.py`
- Create: `src/schema_sentry/infrastructure/db/models/__init__.py`
- Create: `src/schema_sentry/infrastructure/db/models/catalog.py`
- Create: `src/schema_sentry/infrastructure/db/models/scans.py`
- Create: `src/schema_sentry/infrastructure/db/models/lineage.py`
- Create: `src/schema_sentry/infrastructure/db/models/alerts.py`
- Create: `src/schema_sentry/infrastructure/db/repositories/__init__.py`
- Create: `src/schema_sentry/infrastructure/db/repositories/catalog.py`
- Create: `src/schema_sentry/infrastructure/db/repositories/scans.py`
- Create: `src/schema_sentry/infrastructure/db/repositories/changes.py`
- Create: `src/schema_sentry/infrastructure/db/repositories/alerts.py`
- Create: `tests/integration/conftest.py`
- Create: `tests/integration/test_migrations.py`
- Create: `tests/integration/test_repository_constraints.py`

**Interfaces:**
- Produces: `session_scope() -> Iterator[Session]` and `RepositoryBundle(scans, catalog, changes, alerts)`.
- Consumes: Task 2 enums and domain models.
- Database contract: UUID primary keys, UTC timestamps, string enums, JSONB before/after payloads.

- [ ] **Step 1: Write migration and constraint tests**

```python
def test_upgrade_creates_all_tables(metadata_engine):
    command.upgrade(alembic_config, "head")
    names = set(inspect(metadata_engine).get_table_names())
    assert names == {
        "alembic_version", "data_sources", "datasets", "expected_columns",
        "scan_runs", "observed_columns", "schema_changes", "pipelines",
        "lineage_edges", "alert_deliveries",
    }

def test_only_one_open_fingerprint_per_source(session, open_change_factory):
    session.add_all([open_change_factory(), open_change_factory()])
    with pytest.raises(IntegrityError):
        session.commit()
```

- [ ] **Step 2: Run integration tests and confirm failure**

Run: `docker compose up -d metadata-db && uv run pytest tests/integration/test_migrations.py tests/integration/test_repository_constraints.py -q`

Expected: FAIL because Alembic and ORM models are absent.

- [ ] **Step 3: Define the exact repository tables**

```text
data_sources(id, key UNIQUE, display_name, connection_ref, enabled, baseline_version, created_at)
datasets(id, source_id FK, schema_name, table_name, owner, description, UNIQUE source/schema/table)
expected_columns(id, dataset_id FK, name, data_type_json JSONB, nullable, default, ordinal, UNIQUE dataset/name)
scan_runs(id, source_id FK, trigger, status, started_at, finished_at, duration_ms, error_code, error_message)
observed_columns(id, scan_id FK, schema_name, table_name, name, data_type_json JSONB, nullable, default, ordinal)
schema_changes(id, scan_id FK, source_id FK, dataset_id FK, column_name, change_type, severity, state, fingerprint, before_json, after_json, baseline_version, created_at, accepted_at, resolved_at)
pipelines(id, key UNIQUE, airflow_dag_id UNIQUE, owner, criticality)
lineage_edges(id, pipeline_id FK, upstream_dataset_id FK, upstream_column, downstream_dataset_id FK, downstream_column, UNIQUE pipeline/upstream/downstream columns)
alert_deliveries(id, scan_id FK, channel, status, attempt_count, provider_message_id, last_error, next_retry_at, created_at, sent_at)
```

Add a partial unique index on `(source_id, fingerprint)` where `state = 'OPEN'` so a resolved change may alert again if it reoccurs later.

- [ ] **Step 4: Implement sessions and repository mappings**

```python
@contextmanager
def session_scope(factory: sessionmaker[Session]) -> Iterator[Session]:
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
```

- [ ] **Step 5: Verify upgrade, downgrade, and constraints**

Run: `uv run alembic upgrade head && uv run pytest tests/integration/test_migrations.py tests/integration/test_repository_constraints.py -q && uv run alembic downgrade base && uv run alembic upgrade head`

Expected: every command succeeds.

- [ ] **Step 6: Run static checks, commit, and push**

```bash
uv run ruff check .
uv run mypy src
git add alembic.ini alembic src/schema_sentry/infrastructure/db tests/integration
git commit -m "feat: add metadata repository schema"
git push origin main
```

---

### Task 4: PostgreSQL Collection and Baseline Scan

**Files:**
- Create: `src/schema_sentry/application/ports.py`
- Create: `src/schema_sentry/application/scan_service.py`
- Create: `src/schema_sentry/infrastructure/db/postgres_collector.py`
- Modify: `src/schema_sentry/infrastructure/db/repositories/scans.py`
- Create: `tests/unit/application/test_scan_service.py`
- Create: `tests/integration/test_postgres_collector.py`
- Create: `tests/integration/test_scan_lifecycle.py`
- Create: `demo/sql/001_game_schema.sql`
- Modify: `docker-compose.yml`

**Interfaces:**
- Produces: `SchemaCollector.collect() -> tuple[ColumnDefinition, ...]`.
- Produces: `ScanService.run_scan(source_key: str, trigger: ScanTrigger) -> ScanReport`.
- Produces repository methods `try_source_lock`, `create_running_scan`, `complete_initial_baseline`, `complete_drift_scan`, and `fail_scan`.

- [ ] **Step 1: Write collector and first-scan tests**

```python
def test_collector_reads_game_columns(source_engine, collector):
    columns = collector.collect()
    amount = next(c for c in columns if c.dataset.table == "purchases" and c.name == "amount")
    assert amount.data_type.render() == "numeric(12,2)"
    assert amount.nullable is False

def test_first_scan_creates_baseline_without_changes(scan_service, repository):
    report = scan_service.run_scan("game", ScanTrigger.MANUAL)
    assert report.baseline_created is True
    assert report.changes == ()
    assert repository.expected_column_count("game") > 0
```

- [ ] **Step 2: Confirm focused tests fail**

Run: `uv run pytest tests/unit/application/test_scan_service.py tests/integration/test_postgres_collector.py tests/integration/test_scan_lifecycle.py -q`

Expected: FAIL with missing collector and scan service.

- [ ] **Step 3: Create the exact game analytics source schema**

```sql
CREATE SCHEMA IF NOT EXISTS mart;
CREATE TABLE public.players (
    player_id bigint PRIMARY KEY,
    nickname character varying(50) NOT NULL,
    created_at timestamptz NOT NULL
);
CREATE TABLE public.matches (
    match_id bigint PRIMARY KEY,
    region character varying(20) NOT NULL,
    started_at timestamptz NOT NULL
);
CREATE TABLE public.sessions (
    session_id bigint PRIMARY KEY,
    player_id bigint NOT NULL REFERENCES public.players(player_id),
    started_at timestamptz NOT NULL,
    ended_at timestamptz
);
CREATE TABLE public.purchases (
    purchase_id bigint PRIMARY KEY,
    player_id bigint NOT NULL REFERENCES public.players(player_id),
    purchased_at timestamptz NOT NULL,
    amount numeric(12,2) NOT NULL
);
CREATE TABLE mart.daily_revenue (
    date date PRIMARY KEY,
    revenue numeric(18,2) NOT NULL
);
```

```sql
INSERT INTO public.players VALUES
    (1, 'alpha', '2026-01-01T00:00:00Z'),
    (2, 'bravo', '2026-01-01T00:00:00Z');
INSERT INTO public.purchases VALUES
    (101, 1, '2026-08-01T01:00:00Z', 1200.00),
    (102, 2, '2026-08-01T02:00:00Z', 800.00),
    (103, 1, '2026-08-02T01:00:00Z', 500.00);
```

- [ ] **Step 4: Implement a parameterized, read-only collector query**

```sql
SELECT table_schema, table_name, column_name, ordinal_position,
       is_nullable, data_type, udt_name, character_maximum_length,
       numeric_precision, numeric_scale, column_default
FROM information_schema.columns
WHERE table_schema = ANY(%(included_schemas)s)
ORDER BY table_schema, table_name, ordinal_position
```

Reject wildcard schemas; default `included_schemas` is exactly `("public", "mart")`. Set `connect_timeout=3` and `statement_timeout=5000` milliseconds.

- [ ] **Step 5: Implement the scan orchestration contract**

```python
class ScanService:
    def run_scan(self, source_key: str, trigger: ScanTrigger) -> ScanReport:
        with self.repository.try_source_lock(source_key) as acquired:
            if not acquired:
                raise ScanAlreadyRunning(source_key)
            scan_id = self.repository.create_running_scan(source_key, trigger)
            try:
                observed = self.collector_for(source_key).collect()
                return self._compare_and_persist(scan_id, source_key, observed)
            except Exception as exc:
                self.repository.fail_scan(scan_id, sanitize_error(exc))
                raise
```

Initial scans populate datasets and expected columns in one transaction and create zero schema changes.

- [ ] **Step 6: Verify initial, repeated, failed, and concurrent scans**

Run: `uv run pytest tests/unit/application/test_scan_service.py tests/integration/test_postgres_collector.py tests/integration/test_scan_lifecycle.py -q`

Expected: baseline is created once, the second unchanged scan has zero changes, a connection failure records `FAILED`, and a held advisory lock raises `ScanAlreadyRunning`.

- [ ] **Step 7: Run static checks, commit, and push**

```bash
uv run ruff check .
uv run mypy src
git add src/schema_sentry/application src/schema_sentry/infrastructure/db demo docker-compose.yml tests
git commit -m "feat: scan postgres schema into baseline"
git push origin main
```

---

### Task 5: Versioned Catalog and Lineage Impact

**Files:**
- Create: `catalog.yaml`
- Create: `src/schema_sentry/application/catalog_service.py`
- Create: `src/schema_sentry/domain/lineage.py`
- Create: `src/schema_sentry/cli.py`
- Create: `src/schema_sentry/__main__.py`
- Create: `tests/unit/domain/test_lineage.py`
- Create: `tests/unit/application/test_catalog_service.py`
- Create: `tests/integration/test_catalog_sync.py`
- Modify: `src/schema_sentry/infrastructure/db/repositories/catalog.py`

**Interfaces:**
- Produces: `CatalogService.sync(path: Path) -> CatalogSyncResult`.
- Produces: `LineageGraph.impacts(changes) -> tuple[PipelineImpact, ...]`.
- Produces CLI: `schema-sentry catalog sync catalog.yaml`.
- Consumes Task 3 pipeline and lineage tables.

- [ ] **Step 1: Write atomic-sync and multi-hop impact tests**

```python
def test_invalid_column_rolls_back_entire_catalog(service, repository, invalid_yaml):
    before = repository.catalog_digest()
    with pytest.raises(CatalogValidationError, match="unknown column"):
        service.sync(invalid_yaml)
    assert repository.catalog_digest() == before

def test_impact_traverses_downstream_edges(graph, amount_change):
    impacts = graph.impacts([amount_change])
    assert [(i.pipeline_key, i.downstream_dataset.qualified_name) for i in impacts] == [
        ("daily_revenue", "mart.daily_revenue"),
        ("executive_kpi", "mart.executive_kpi"),
    ]
```

- [ ] **Step 2: Confirm tests fail**

Run: `uv run pytest tests/unit/domain/test_lineage.py tests/unit/application/test_catalog_service.py tests/integration/test_catalog_sync.py -q`

Expected: FAIL with missing catalog and lineage services.

- [ ] **Step 3: Define and validate the catalog schema**

```python
class PipelineConfig(BaseModel):
    key: str
    airflow_dag_id: str
    owner: str
    criticality: PipelineCriticality
    inputs: tuple[ColumnSetConfig, ...]
    outputs: tuple[ColumnSetConfig, ...]

class CatalogConfig(BaseModel):
    pipelines: tuple[PipelineConfig, ...]
```

Validate duplicate keys, duplicate DAG IDs, unknown datasets, unknown columns, empty inputs/outputs, and self-loop edges before opening the replacement transaction.

- [ ] **Step 4: Implement deterministic graph traversal**

Use breadth-first traversal keyed by `ColumnRef`, retain the shortest path for display, and sort impacts by pipeline criticality then key. A visited `(pipeline_key, downstream_column)` set prevents cycles.

```python
def impacts(self, changes: Sequence[SchemaChange]) -> tuple[PipelineImpact, ...]:
    queue = deque((change.ref, ()) for change in changes if change.severity is Severity.BREAKING)
    visited: set[tuple[str, ColumnRef]] = set()
    found: dict[tuple[str, ColumnRef], PipelineImpact] = {}
    while queue:
        column, path = queue.popleft()
        for edge in self.edges_by_upstream.get(column, ()):
            key = (edge.pipeline_key, edge.downstream)
            if key in visited:
                continue
            visited.add(key)
            next_path = (*path, edge)
            found[key] = PipelineImpact.from_path(next_path)
            queue.append((edge.downstream, next_path))
    return tuple(sorted(found.values(), key=impact_sort_key))
```

- [ ] **Step 5: Implement and exercise the CLI**

```python
app = typer.Typer()
catalog_app = typer.Typer()
app.add_typer(catalog_app, name="catalog")

@catalog_app.command("sync")
def sync_catalog(path: Path) -> None:
    result = build_catalog_service().sync(path)
    typer.echo(f"synced pipelines={result.pipeline_count} edges={result.edge_count}")
```

Run: `uv run schema-sentry catalog sync catalog.yaml`

Expected: prints exact non-zero pipeline and edge counts; a second run is idempotent.

- [ ] **Step 6: Verify, commit, and push**

```bash
uv run pytest tests/unit/domain/test_lineage.py tests/unit/application/test_catalog_service.py tests/integration/test_catalog_sync.py -q
uv run ruff check .
uv run mypy src
git add catalog.yaml src/schema_sentry tests
git commit -m "feat: map schema drift to pipeline lineage"
git push origin main
```

---

### Task 6: Change Lifecycle and Pipeline Preflight

**Files:**
- Create: `src/schema_sentry/application/change_service.py`
- Create: `src/schema_sentry/application/validation_service.py`
- Create: `tests/unit/application/test_change_service.py`
- Create: `tests/unit/application/test_validation_service.py`
- Create: `tests/integration/test_change_lifecycle.py`
- Create: `demo/sql/010_breaking_change.sql`
- Create: `demo/sql/011_restore_schema.sql`
- Modify: `src/schema_sentry/application/scan_service.py`
- Modify: `src/schema_sentry/infrastructure/db/repositories/scans.py`
- Modify: `src/schema_sentry/infrastructure/db/repositories/changes.py`

**Interfaces:**
- Produces: `ChangeService.accept(change_id: UUID, expected_baseline_version: int) -> AcceptanceResult`.
- Produces: `ValidationService.validate_pipeline(pipeline_key: str) -> PipelineValidation`.
- Produces repository context `acceptance_transaction(change_id) -> Iterator[LockedAcceptance]`, where `LockedAcceptance` owns the locked source, change, and baseline update operation.
- Extends scan behavior with `OPEN` deduplication and automatic `RESOLVED` transitions.

- [ ] **Step 1: Write lifecycle and preflight tests**

```python
def test_open_breaking_change_blocks_pipeline(validation_service):
    result = validation_service.validate_pipeline("daily_revenue")
    assert result.safe is False
    assert result.blocking_changes[0].column_name == "amount"

def test_stale_acceptance_is_rejected(change_service, open_change):
    with pytest.raises(BaselineVersionConflict):
        change_service.accept(open_change.id, expected_baseline_version=0)

def test_restore_resolves_open_change(run_scan, apply_break, restore_schema):
    breaking = run_scan()
    restore_schema()
    restored = run_scan()
    assert restored.resolved_change_ids == (breaking.changes[0].id,)
```

- [ ] **Step 2: Verify tests fail**

Run: `uv run pytest tests/unit/application/test_change_service.py tests/unit/application/test_validation_service.py tests/integration/test_change_lifecycle.py -q`

Expected: FAIL with missing lifecycle services.

- [ ] **Step 3: Implement optimistic baseline acceptance**

Lock the matching `data_sources` row with SQLAlchemy `select(DataSourceRow).where(DataSourceRow.id == change.source_id).with_for_update()`, compare `baseline_version`, update the exact expected column, increment the version, and mark the change `ACCEPTED` in one transaction.

```python
def accept(self, change_id: UUID, expected_baseline_version: int) -> AcceptanceResult:
    with self.repository.acceptance_transaction(change_id) as locked:
        if locked.source.baseline_version != expected_baseline_version:
            raise BaselineVersionConflict(expected_baseline_version, locked.source.baseline_version)
        locked.apply_change_to_baseline()
        locked.change.mark_accepted(self.clock.now())
        locked.source.baseline_version += 1
        return AcceptanceResult(change_id, locked.source.baseline_version)
```

- [ ] **Step 4: Implement deduplication, resolution, and validation**

Repeated identical drift reuses the existing open change and creates no new alert delivery. When a later observation matches the baseline, mark the open fingerprint `RESOLVED`. Validation returns every open `BREAKING` change whose lineage reaches the requested pipeline. `010_breaking_change.sql` contains `ALTER TABLE public.purchases ALTER COLUMN amount TYPE character varying USING amount::character varying;`. `011_restore_schema.sql` contains `ALTER TABLE public.purchases ALTER COLUMN amount TYPE numeric(12,2) USING amount::numeric;`.

```python
for detected in detected_changes:
    fingerprint = change_fingerprint(source_key, detected)
    open_change = repository.find_open_change(source_key, fingerprint)
    persisted.append(open_change or repository.add_open_change(scan_id, detected, fingerprint))
repository.resolve_open_changes_absent_from(source_key, {change.fingerprint for change in persisted})

def validate_pipeline(self, pipeline_key: str) -> PipelineValidation:
    blocking = self.repository.list_open_breaking_changes_for_pipeline(pipeline_key)
    return PipelineValidation(pipeline_key=pipeline_key, safe=not blocking, blocking_changes=blocking)
```

- [ ] **Step 5: Run the real DDL lifecycle**

Run: `psql "$SOURCE_DATABASE_URL" -f demo/sql/010_breaking_change.sql`, execute a scan, then run `psql "$SOURCE_DATABASE_URL" -f demo/sql/011_restore_schema.sql` and scan again.

Expected: the first scan opens one type-change drift affecting `daily_revenue`; the second resolves it.

- [ ] **Step 6: Verify, commit, and push**

```bash
uv run pytest tests/unit/application tests/integration/test_change_lifecycle.py -q
uv run ruff check .
uv run mypy src
git add src/schema_sentry demo/sql tests
git commit -m "feat: guard pipelines from unresolved drift"
git push origin main
```

---

### Task 7: Authenticated FastAPI Contract

**Files:**
- Create: `src/schema_sentry/api/dependencies.py`
- Create: `src/schema_sentry/api/security.py`
- Create: `src/schema_sentry/api/schemas/scans.py`
- Create: `src/schema_sentry/api/schemas/changes.py`
- Create: `src/schema_sentry/api/schemas/pipelines.py`
- Create: `src/schema_sentry/api/routers/scans.py`
- Create: `src/schema_sentry/api/routers/changes.py`
- Create: `src/schema_sentry/api/routers/pipelines.py`
- Create: `src/schema_sentry/api/routers/health.py`
- Create: `tests/api/conftest.py`
- Create: `tests/api/test_scans.py`
- Create: `tests/api/test_changes.py`
- Create: `tests/api/test_pipelines.py`
- Create: `tests/api/test_health.py`
- Modify: `src/schema_sentry/api/app.py`
- Modify: `src/schema_sentry/config.py`

**Interfaces:**
- Produces approved API paths and JSON schemas from design Section 9 except alert retry, which Task 8 adds.
- Authentication accepts either exact `X-API-Key` or trusted `X-Authenticated-User`; development bypass works only with `environment=development` and `auth_disabled=true`.
- Produces: `OperatorIdentity(subject: str, mechanism: Literal["api-key", "proxy", "bypass"])`; adds `trust_proxy_auth: bool = False` to `Settings`.
- `POST /api/v1/scans` consumes `{"source_key": "game"}`; acceptance consumes `{"baseline_version": 7}`.

- [ ] **Step 1: Write API contract tests**

```python
def test_pipeline_conflict_shape(client, api_key):
    response = client.post(
        "/api/v1/pipelines/daily_revenue/validate",
        headers={"X-API-Key": api_key},
    )
    assert response.status_code == 409
    assert response.json()["safe"] is False
    assert response.json()["blocking_changes"][0]["severity"] == "BREAKING"

def test_mutation_requires_auth(client):
    assert client.post("/api/v1/scans").status_code == 401
```

- [ ] **Step 2: Confirm API tests fail**

Run: `uv run pytest tests/api -q`

Expected: FAIL because routers and dependencies are absent.

- [ ] **Step 3: Implement security and dependency wiring**

Use `secrets.compare_digest` for API keys. Trust `X-Authenticated-User` only when `SCHEMA_SENTRY_TRUST_PROXY_AUTH=true`; production startup requires that the API container is not directly published.

```python
def require_operator(
    x_api_key: Annotated[str | None, Header()] = None,
    x_authenticated_user: Annotated[str | None, Header()] = None,
    settings: Settings = Depends(get_settings),
) -> OperatorIdentity:
    if settings.environment == "development" and settings.auth_disabled:
        return OperatorIdentity(subject="local-development", mechanism="bypass")
    if x_api_key and secrets.compare_digest(x_api_key, settings.api_key.get_secret_value()):
        return OperatorIdentity(subject="api-client", mechanism="api-key")
    if settings.trust_proxy_auth and x_authenticated_user:
        return OperatorIdentity(subject=x_authenticated_user, mechanism="proxy")
    raise HTTPException(status_code=401, detail="operator authentication required")
```

- [ ] **Step 4: Implement routes and exception mapping**

Map `ScanAlreadyRunning` and `BaselineVersionConflict` to `409`, missing IDs to `404`, invalid input to `422`, and sanitized source failure to `503`. `GET /health/ready` checks repository connectivity and Alembic head only; source failure does not make historical results unavailable.

```python
@router.post("/scans", response_model=ScanResponse, status_code=201)
def run_scan(request: ManualScanRequest, _: OperatorIdentity = Depends(require_operator)) -> ScanResponse:
    return ScanResponse.from_report(scan_service.run_scan(request.source_key, ScanTrigger.MANUAL))

@router.post("/pipelines/{pipeline_key}/validate", response_model=PipelineValidationResponse)
def validate_pipeline(pipeline_key: str, _: OperatorIdentity = Depends(require_operator)) -> Response:
    result = validation_service.validate_pipeline(pipeline_key)
    body = PipelineValidationResponse.from_domain(result).model_dump(mode="json")
    return JSONResponse(body, status_code=200 if result.safe else 409)
```

- [ ] **Step 5: Freeze and inspect OpenAPI**

Run: `uv run python -c 'from schema_sentry.api.app import create_app; import json; print(json.dumps(create_app().openapi(), sort_keys=True))' > /tmp/schema-sentry-openapi.json`

Expected: all approved routes appear once, mutation routes declare API-key security, and no secret defaults appear.

- [ ] **Step 6: Verify, commit, and push**

```bash
uv run pytest tests/api -q
uv run ruff check .
uv run mypy src
git add src/schema_sentry/api tests/api
git commit -m "feat: expose schema validation api"
git push origin main
```

---

### Task 8: Slack and Email Delivery with Retry

**Files:**
- Create: `src/schema_sentry/application/notification_service.py`
- Create: `src/schema_sentry/infrastructure/notifications/slack.py`
- Create: `src/schema_sentry/infrastructure/notifications/email.py`
- Create: `src/schema_sentry/api/schemas/alerts.py`
- Create: `src/schema_sentry/api/routers/alerts.py`
- Create: `tests/unit/application/test_notification_service.py`
- Create: `tests/unit/infrastructure/test_slack.py`
- Create: `tests/unit/infrastructure/test_email.py`
- Create: `tests/api/test_alerts.py`
- Modify: `src/schema_sentry/config.py`
- Modify: `src/schema_sentry/application/scan_service.py`
- Modify: `src/schema_sentry/infrastructure/db/repositories/scans.py`
- Modify: `src/schema_sentry/infrastructure/db/repositories/alerts.py`
- Modify: `src/schema_sentry/api/app.py`
- Modify: `src/schema_sentry/api/routers/scans.py`
- Modify: `docker-compose.yml`

**Interfaces:**
- Produces: `Notifier.send(AlertMessage) -> ProviderReceipt`.
- Produces: `NotificationService.dispatch_scan(scan_id: UUID) -> tuple[DeliveryResult, ...]`.
- Produces: `NotificationService.dispatch_system_error(scan_id: UUID) -> tuple[DeliveryResult, ...]` with sanitized source-failure context.
- Produces: `POST /api/v1/alerts/{delivery_id}/retry`.
- Adds local Mailpit at `localhost:8025` and SMTP at `mailpit:1025`.
- Adds settings `slack_webhook_url: SecretStr | None`, `smtp_host: str`, `smtp_port: int`, `email_from: str`, `email_to: tuple[str, ...]`, and `dashboard_base_url: AnyHttpUrl`.

- [ ] **Step 1: Write grouped-message and retry tests**

```python
def test_message_contains_actionable_context(message_factory):
    message = message_factory()
    assert "public.purchases.amount" in message.text
    assert "numeric(12,2) → character varying" in message.text
    assert "daily_revenue_dag" in message.text
    assert "scan #42" in message.text
    assert message.dashboard_url.endswith("/")

def test_fourth_attempt_is_rejected(service, failed_delivery):
    failed_delivery.attempt_count = 3
    with pytest.raises(MaxAttemptsExceeded):
        service.retry(failed_delivery.id)
```

- [ ] **Step 2: Confirm notification tests fail**

Run: `uv run pytest tests/unit/application/test_notification_service.py tests/unit/infrastructure tests/api/test_alerts.py -q`

Expected: FAIL with missing notification modules.

- [ ] **Step 3: Implement Slack and SMTP adapters**

Slack uses `httpx.Client(timeout=5.0)` and Block Kit; email uses `smtplib.SMTP(timeout=5)` with both text and HTML alternatives. Provider exceptions are converted to `DeliveryFailure` with sanitized messages that omit URLs, credentials, and response bodies.

```python
class SlackNotifier:
    channel = AlertChannel.SLACK
    def send(self, message: AlertMessage) -> ProviderReceipt:
        response = self.client.post(self.webhook_url, json=build_slack_blocks(message))
        response.raise_for_status()
        return ProviderReceipt(provider_message_id=response.headers.get("x-slack-req-id"))

class EmailNotifier:
    channel = AlertChannel.EMAIL
    def send(self, message: AlertMessage) -> ProviderReceipt:
        mime = build_multipart_email(message, self.sender, self.recipients)
        with smtplib.SMTP(self.host, self.port, timeout=5) as smtp:
            refused = smtp.send_message(mime)
        if refused:
            raise DeliveryFailure("smtp_recipients_refused")
        return ProviderReceipt(provider_message_id=mime["Message-ID"])
```

- [ ] **Step 4: Implement delivery state transitions**

Allowed transitions are `PENDING -> SENT` and `PENDING|FAILED -> FAILED|SENT`. Increment `attempt_count` before sending; a retry before `next_retry_at` returns `409`, with retry delays of 60, 300, and 900 seconds. Create one delivery per scan per enabled channel only when new alertable fingerprints exist. After Task 8, `ScanService.run_scan` dispatches alerts only after the scan transaction commits; its exception path records the failed scan, dispatches a sanitized system-error alert, and then re-raises the original failure. Adapter failures are captured as delivery results and never replace the scan result.

```python
def attempt_delivery(self, delivery_id: UUID, now: datetime) -> DeliveryResult:
    delivery = self.repository.lock_delivery(delivery_id)
    if delivery.attempt_count >= 3:
        raise MaxAttemptsExceeded(delivery_id)
    if delivery.next_retry_at and now < delivery.next_retry_at:
        raise RetryNotDue(delivery.next_retry_at)
    delivery.start_attempt(now)
    return self._send_and_record(delivery, now)
```

- [ ] **Step 5: Verify payloads, Mailpit, and retry API**

Run: `docker compose up -d mailpit && uv run pytest tests/unit/application/test_notification_service.py tests/unit/infrastructure tests/api/test_alerts.py -q`

Expected: mock Slack payload and SMTP MIME assertions pass; Mailpit health check reports healthy.

- [ ] **Step 6: Run static checks, commit, and push**

```bash
uv run ruff check .
uv run mypy src
git add src/schema_sentry docker-compose.yml tests
git commit -m "feat: notify owners about schema drift"
git push origin main
```

---

### Task 9: Airflow Scheduling and Pipeline Guard

**Files:**
- Create: `airflow/Dockerfile`
- Create: `airflow/dags/schema_consistency_scan.py`
- Create: `airflow/dags/daily_revenue.py`
- Create: `airflow/tests/test_dag_imports.py`
- Create: `airflow/tests/test_schema_guard.py`
- Modify: `docker-compose.yml`
- Modify: `catalog.yaml`

**Interfaces:**
- Produces DAG `schema_consistency_scan` scheduled `*/10 * * * *`.
- Produces DAG `daily_revenue` with tasks `schema_guard` then `aggregate_daily_revenue`.
- Both call Schema Sentry with `X-API-Key` and a five-second HTTP timeout.

- [ ] **Step 1: Write DAG structure and guard tests**

```python
def test_daily_revenue_guard_precedes_sql(dag_bag):
    dag = dag_bag.get_dag("daily_revenue")
    assert dag_bag.import_errors == {}
    assert dag.task_dict["schema_guard"].downstream_task_ids == {"aggregate_daily_revenue"}

def test_guard_raises_on_409(mock_api):
    mock_api.return_status = 409
    with pytest.raises(AirflowFailException, match="blocking schema drift"):
        validate_pipeline("daily_revenue")
```

- [ ] **Step 2: Verify DAG tests fail**

Run: `docker compose run --rm airflow-api-server pytest /opt/airflow/tests -q`

Expected: FAIL because DAGs are absent.

- [ ] **Step 3: Implement Airflow 3 DAGs using the public SDK**

```python
from airflow.sdk import dag, task

@dag(dag_id="schema_consistency_scan", schedule="*/10 * * * *", catchup=False)
def schema_scan_dag():
    @task(retries=2, retry_delay=timedelta(minutes=1))
    def trigger_scan() -> None:
        post_json("/api/v1/scans", {"source_key": "game"})
    trigger_scan()
```

Build `airflow/Dockerfile` from `apache/airflow:3.3.0-python3.12` and add only `psycopg[binary]==3.3.4` and `pytest==9.1.1`. Airflow stores its own metadata in `airflow-db`; it never shares the Schema Sentry repository database.

- [ ] **Step 4: Implement the sample aggregation**

After `schema_guard` succeeds, execute an idempotent `INSERT INTO mart.daily_revenue (date, revenue) SELECT purchased_at::date, SUM(amount) FROM public.purchases GROUP BY purchased_at::date ON CONFLICT (date) DO UPDATE SET revenue = EXCLUDED.revenue`. The breaking demo changes `amount` to text so the guard prevents unsafe aggregation.

- [ ] **Step 5: Verify import and live behavior**

Run: `docker compose up -d airflow-db airflow-api-server airflow-scheduler && docker compose exec airflow-api-server airflow dags list-import-errors`

Expected: output contains `No data found` for import errors, and both DAG IDs appear in `airflow dags list`.

- [ ] **Step 6: Run tests, commit, and push**

```bash
docker compose run --rm airflow-api-server pytest /opt/airflow/tests -q
uv run ruff check .
uv run mypy src
git add airflow docker-compose.yml catalog.yaml
git commit -m "feat: block unsafe airflow pipelines"
git push origin main
```

---

### Task 10: Focused Single-Page Dashboard

**Files:**
- Create: `src/schema_sentry/api/routers/dashboard.py`
- Create: `src/schema_sentry/api/templates/dashboard.html`
- Create: `src/schema_sentry/api/templates/partials/change_list.html`
- Create: `src/schema_sentry/api/static/app.css`
- Create: `src/schema_sentry/api/static/htmx.min.js`
- Create: `tests/api/test_dashboard.py`
- Modify: `src/schema_sentry/api/app.py`

**Interfaces:**
- Produces: `GET /`, `POST /actions/scans`, and `POST /actions/changes/{change_id}/accept`.
- Dashboard actions consume the same `ScanService` and `ChangeService`; they never call the service's own HTTP API.
- Browser authorization relies on trusted `X-Authenticated-User` from Caddy; local development may use the guarded development bypass.

- [ ] **Step 1: Write rendering and action tests**

```python
def test_dashboard_shows_change_impact(client, latest_scan):
    html = client.get("/").text
    assert "public.purchases.amount" in html
    assert "BREAKING" in html
    assert "daily_revenue_dag" in html
    assert "Slack: SENT" in html

def test_accept_action_requires_proxy_identity(client, change):
    response = client.post(f"/actions/changes/{change.id}/accept", data={"baseline_version": 7})
    assert response.status_code == 401
```

- [ ] **Step 2: Confirm dashboard tests fail**

Run: `uv run pytest tests/api/test_dashboard.py -q`

Expected: FAIL because template routes do not exist.

- [ ] **Step 3: Vendor stable HTMX and build the one-page template**

Download `https://raw.githubusercontent.com/bigskysoftware/htmx/v2.0.10/dist/htmx.min.js` into `static/htmx.min.js` and require SHA-256 `71ea67185bfa8c98c39d31717c6fce5d852370fcdfd129db4543774d3145c0de`. The page contains only the header, latest scan summary, change cards, impact text, delivery summary, recent scan summary, `Run Scan`, and `Accept as baseline`.

```html
<main>
  <header><h1>Schema Sentry</h1><button hx-post="/actions/scans">Run Scan</button></header>
  <section aria-labelledby="latest-scan"><h2 id="latest-scan">Latest scan #{{ scan.id }}</h2></section>
  <section id="changes" aria-live="polite">{% include "partials/change_list.html" %}</section>
</main>
```

- [ ] **Step 4: Implement partial actions with explicit conflict UI**

`POST /actions/scans` returns the refreshed change list. Baseline-version conflicts return HTTP 409 with a visible message instructing the operator to refresh; do not silently overwrite.

```python
@router.post("/actions/changes/{change_id}/accept", response_class=HTMLResponse)
def accept_change(
    change_id: UUID,
    baseline_version: Annotated[int, Form()],
    operator: Annotated[OperatorIdentity, Depends(require_operator)],
) -> HTMLResponse:
    change_service.accept(change_id, baseline_version)
    return render_change_list(status_code=200)
```

- [ ] **Step 5: Verify HTML behavior and accessibility basics**

Run: `uv run pytest tests/api/test_dashboard.py -q`

Expected: action buttons have labels, severity is text as well as color, tables/cards use semantic headings, and tests pass without JavaScript execution.

- [ ] **Step 6: Run static checks, commit, and push**

```bash
uv run ruff check .
uv run mypy src
git add src/schema_sentry/api tests/api/test_dashboard.py
git commit -m "feat: add schema drift dashboard"
git push origin main
```

---

### Task 11: Mini PC Production Deployment and Observability

**Files:**
- Create: `docker-compose.prod.yml`
- Create: `deploy/Caddyfile`
- Create: `docs/operations.md`
- Create: `scripts/smoke-test.sh`
- Modify: `.env.example`
- Modify: `Dockerfile`
- Modify: `src/schema_sentry/logging.py`
- Modify: `src/schema_sentry/api/routers/health.py`
- Modify: `Makefile`
- Create: `tests/system/test_secret_redaction.py`

**Interfaces:**
- Publicly exposes only Caddy on ports 80 and 443.
- Caddy forwards authenticated username as `X-Authenticated-User` after `basic_auth` succeeds.
- Produces structured JSON logs with `scan_id`, `source_key`, `pipeline_key`, `duration_ms`, and `status`.
- Produces smoke script checking Caddy, API readiness, repository migration, and Airflow health.

- [ ] **Step 1: Write production-config and redaction tests**

```python
def test_secret_is_redacted_from_exception_log(caplog, settings):
    log_source_failure(ValueError(settings.source_database_url))
    assert settings.source_database_url not in caplog.text
    assert "source_connection_failed" in caplog.text
```

Run: `uv run pytest tests/system/test_secret_redaction.py -q`

Expected: FAIL until logging sanitization is implemented.

- [ ] **Step 2: Implement the hardened Compose overlay**

Pin `caddy:2.11.4-alpine`, `postgres:17.10-bookworm`, `apache/airflow:3.3.0-python3.12`, and `axllent/mailpit:v1.30.6`. Set `read_only: true` where compatible, `security_opt: ["no-new-privileges:true"]`, explicit health checks, named volumes, restart policies, log rotation, and no host ports for API or databases.

- [ ] **Step 3: Configure authenticated reverse proxying**

```caddyfile
{$SCHEMA_SENTRY_DOMAIN} {
    basic_auth {
        {$SCHEMA_SENTRY_ADMIN_USER} {$SCHEMA_SENTRY_ADMIN_HASH}
    }
    reverse_proxy api:8000 {
        header_up X-Authenticated-User {http.auth.user.id}
    }
}
```

Generate the Caddy hash with `docker run --rm -it caddy:2.11.4-alpine caddy hash-password` and enter the password only at its prompt. Generate the API key with `openssl rand -hex 32`, place both outputs in the untracked production environment file with mode `0600`, and never pass a plaintext password as a command argument.

- [ ] **Step 4: Implement JSON logging and smoke checks**

The smoke script must use `set -euo pipefail`, call `/health/live` and authenticated `/health/ready`, verify Alembic head, and query Airflow health. It exits non-zero on any mismatch and prints only service names and statuses.

- [ ] **Step 5: Validate the rendered production configuration**

Run: `docker compose -f docker-compose.yml -f docker-compose.prod.yml config > /tmp/schema-sentry-compose.yml && ! rg -n 'CHANGE_ME|localhost:8000|published: 5432' /tmp/schema-sentry-compose.yml`

Expected: command succeeds and no placeholder secret or unintended port is present.

- [ ] **Step 6: Run tests, commit, and push**

```bash
uv run pytest tests/system/test_secret_redaction.py -q
uv run ruff check .
uv run mypy src
git add docker-compose.prod.yml deploy docs/operations.md scripts/smoke-test.sh .env.example Dockerfile src/schema_sentry Makefile tests/system
git commit -m "feat: harden mini pc deployment"
git push origin main
```

---

### Task 12: End-to-End Demonstration and Failure Paths

**Files:**
- Create: `scripts/demo.sh`
- Create: `tests/system/test_demo_lifecycle.py`
- Create: `tests/system/test_notification_failure.py`
- Modify: `Makefile`
- Modify: `demo/sql/010_breaking_change.sql`
- Modify: `demo/sql/011_restore_schema.sql`

**Interfaces:**
- Produces: `make demo` and a non-interactive `scripts/demo.sh`.
- Demonstrates baseline, breaking drift, impact, notification, pipeline block, restore, and resolution in five minutes.

- [ ] **Step 1: Write an end-to-end lifecycle test**

```python
def test_full_demo_lifecycle(system):
    baseline = system.scan()
    assert baseline.change_count == 0
    system.apply_sql("demo/sql/010_breaking_change.sql")
    broken = system.scan()
    assert broken.breaking_count == 1
    assert system.validate("daily_revenue").status_code == 409
    system.apply_sql("demo/sql/011_restore_schema.sql")
    restored = system.scan()
    assert restored.resolved_count == 1
    assert system.validate("daily_revenue").json()["safe"] is True
```

- [ ] **Step 2: Write notification-failure isolation test**

Stop Mailpit, run a drift scan, and assert the scan is `COMPLETED`, email delivery is `FAILED`, Slack delivery is independently recorded, and retry succeeds after Mailpit restarts.

- [ ] **Step 3: Verify the system tests fail before the script exists**

Run: `uv run pytest tests/system/test_demo_lifecycle.py tests/system/test_notification_failure.py -q`

Expected: FAIL with missing system harness or demo command.

- [ ] **Step 4: Implement an idempotent demo script**

```text
1. restore known schema
2. reset only demo scan/catalog state through a documented test-only command
3. run initial baseline scan
4. apply breaking DDL
5. run drift scan and print scan ID
6. assert pipeline validation returns 409
7. print Mailpit and dashboard URLs
8. restore schema
9. run resolution scan
10. assert pipeline validation returns 200
```

Use explicit container and database names; never delete Docker volumes or unrelated data.

- [ ] **Step 5: Run the complete automated demonstration**

Run: `make demo`

Expected: exits 0 in under five minutes and prints one baseline scan, one breaking scan, one blocked pipeline, and one resolved scan.

- [ ] **Step 6: Run the full quality gate**

Run: `uv run ruff check . && uv run mypy src && uv run pytest --cov=src/schema_sentry --cov-report=term-missing --cov-fail-under=85`

Expected: all checks PASS and coverage is at least 85 percent for domain/application packages.

- [ ] **Step 7: Commit and push the demonstration**

```bash
git add scripts/demo.sh tests/system Makefile demo/sql
git commit -m "test: automate schema drift demonstration"
git push origin main
```

---

### Task 13: Portfolio Documentation and Final Verification

**Files:**
- Create: `README.md`
- Create: `docs/architecture.md`
- Create: `docs/portfolio-mapping.md`
- Modify: `docs/operations.md`
- Modify: `.github/workflows/ci.yml`

**Interfaces:**
- Produces a new reviewer path from clone to five-minute demo.
- Produces exact mapping from KRAFTON responsibilities to repository evidence.
- Produces architecture, data model, API, policy matrix, runbook, limitations, and trade-off documentation.

- [ ] **Step 1: Write documentation verification tests**

Add a CI shell step that fails unless README contains all commands and links below:

```bash
rg -q 'docker compose up' README.md
rg -q 'make demo' README.md
rg -q 'Metadata Repository 정합성 검증' README.md
rg -q 'pipeline.*validate' README.md
test -f docs/architecture.md
test -f docs/operations.md
test -f docs/portfolio-mapping.md
```

- [ ] **Step 2: Write the README in reviewer order**

Use these exact top-level sections: `Problem`, `Five-Minute Demo`, `What It Detects`, `Architecture`, `Pipeline Guard`, `Local Development`, `Mini PC Deployment`, `Testing`, `Job Responsibility Mapping`, `Trade-offs`, and `Future Work`.

- [ ] **Step 3: Document architecture and operations**

Include Mermaid component and sequence diagrams, the repository ER diagram, API table, severity matrix, alert retry behavior, backup/restore commands for the metadata volume, secret rotation, upgrade procedure, and troubleshooting for source failure, migration mismatch, and failed delivery.

- [ ] **Step 4: Document honest limitations**

State explicitly: PostgreSQL only, ten-minute polling rather than real-time CDC, YAML lineage rather than SQL parsing, single operator, no in-app RBAC, and optional MCP omitted unless separately completed.

- [ ] **Step 5: Run final verification from a clean checkout state**

Run: `git status --short`, then `docker compose down`, `docker compose up -d --build`, `scripts/smoke-test.sh`, `make demo`, and the full quality gate.

Expected: worktree is clean before generated runtime state; services become healthy; demo exits 0; lint, typing, tests, and coverage pass.

- [ ] **Step 6: Commit and push portfolio documentation**

```bash
git add README.md docs .github/workflows/ci.yml
git commit -m "docs: complete schema sentry portfolio"
git push origin main
```

- [ ] **Step 7: Verify remote synchronization**

Run: `git fetch origin && test "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)" && git status --short`

Expected: hashes match and `git status --short` prints nothing.

---

## Optional Task 14: Read-Only MCP Surface

Start this task only when Tasks 1-12 pass and the date is no later than Day 12. Otherwise record MCP as future work and stop.

**Files:**
- Create: `src/schema_sentry/mcp/server.py`
- Create: `tests/mcp/test_tools.py`
- Modify: `pyproject.toml`
- Modify: `README.md`

**Interfaces:**
- Produces read-only tools `get_latest_scan`, `list_breaking_changes`, and `validate_pipeline`.
- MCP calls existing query and validation services; it cannot scan, accept a baseline, retry alerts, or mutate catalog state.

- [ ] **Step 1: Write read-only tool tests**

Assert the three tools return the same domain results as FastAPI and that no mutation tool is registered.

- [ ] **Step 2: Implement the minimal MCP adapter**

Keep the adapter below 150 lines and inject existing services. Do not duplicate query or validation policy.

- [ ] **Step 3: Run the complete quality gate**

Run: `uv run ruff check . && uv run mypy src && uv run pytest --cov=src/schema_sentry --cov-fail-under=85`

Expected: PASS.

- [ ] **Step 4: Commit and push separately**

```bash
git add src/schema_sentry/mcp tests/mcp pyproject.toml uv.lock README.md
git commit -m "feat: expose read only metadata mcp tools"
git push origin main
```
