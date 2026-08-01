# KRAFTON Data Foundation Portfolio Mapping

기준 공고: [KRAFTON Jungle — Data Foundation 엔지니어 (인턴)](https://job-boards.greenhouse.io/krafton_jungle_twelve/jobs/8653074002)

이 문서는 공고의 역할을 과장 없이 저장소의 실행 가능한 증거와 연결합니다. 프로젝트는 2주 개인 프로젝트이며 팀 협업이나 실제 사내 데이터 운영 경험을 주장하지 않습니다.

## Responsibility-to-evidence matrix

| 공고의 업무 영역 | 구현한 내용 | 코드·실행 증거 | 검증 증거 |
|---|---|---|---|
| 데이터 파이프라인 구현·테스트·모니터링 | 10분 주기 schema scan DAG, 일 매출 DAG, 실행 전 fail-closed guard | `airflow/dags/schema_consistency_scan.py`, `airflow/dags/daily_revenue.py`, `airflow/dags/schema_sentry_client.py` | `airflow/tests/`, `make demo`의 blocked/safe 전환 |
| **Metadata Repository 정합성 검증** | 실제 `information_schema` snapshot과 기대 컬럼 비교, 변경 lifecycle과 baseline version 관리 | `postgres_collector.py`, `diff.py`, SQLAlchemy repository, Alembic migration | 실제 PostgreSQL DDL 통합 테스트, fingerprint/accept/resolve 테스트 |
| 카탈로그·스키마·리니지 불일치 식별 | transaction형 YAML catalog sync, column lineage의 transitive impact 분석 | `catalog_service.py`, `lineage.py`, `catalog.yaml` | catalog validation/rollback, multi-hop lineage 테스트 |
| 데이터 조회·검증 API | scan/query/change accept/alert retry/pipeline validate endpoint | `src/schema_sentry/api/routers/`와 OpenAPI schema | API unit/integration 계약 테스트, `409` guard 시나리오 |
| 문서화와 팀 지식 축적 | reviewer README, component/sequence/ERD, 정책표, 운영 runbook | `README.md`, `docs/architecture.md`, `docs/operations.md` | CI documentation verification step |
| Modern Data Stack 기술 활용 | PostgreSQL, Airflow 3, FastAPI, SQLAlchemy/Alembic, HTMX, Docker Compose, Caddy | 고정 버전 dependency와 Compose 배포 구성 | Ruff, strict mypy, pytest/coverage, Airflow DAG test, smoke test |

## Interview demonstration narrative

1. `make demo`를 실행해 초기 snapshot과 baseline이 동일함을 보여줍니다.
2. 데모 DDL이 `purchases.amount`를 숫자에서 문자열로 바꿉니다.
3. policy engine이 타입 계열 변경을 `BREAKING`으로 분류합니다.
4. column lineage가 `daily_revenue`와 `mart.daily_revenue.revenue` 영향을 계산합니다.
5. 이메일 delivery와 dashboard에서 scan ID, before/after, 영향 DAG를 확인합니다.
6. Airflow가 사용하는 pipeline validation API가 `409`로 집계를 차단합니다.
7. 원본 타입 복구 후 open drift가 해소되고 validation이 `200`으로 돌아옵니다.

이 흐름은 단순 CRUD가 아니라 실제 상태 → metadata 비교 → 영향도 → 운영 행동이라는 Metadata Repository 정합성 검증의 전체 feedback loop를 보여줍니다.

## Engineering decisions worth discussing

- **두 데이터베이스 분리:** source와 metadata repository를 분리해 source failure나 schema 변경이 catalog history를 직접 훼손하지 않게 했습니다.
- **완전 snapshot 이후 비교:** 일부 컬럼만 읽힌 실패 snapshot으로 false positive를 만들지 않습니다.
- **트랜잭션 advisory lock:** 같은 source의 중복 스캔을 막되 실패 트랜잭션에서도 lock이 자동 해제됩니다.
- **Outbox와 채널 격리:** 스캔 결과는 외부 provider보다 먼저 commit하고, Slack과 email 성공/실패를 독립 기록합니다.
- **낙관적 baseline version:** 오래 열린 브라우저가 최신 baseline을 덮어쓰지 못하게 합니다.
- **Fail-closed guard:** 정합성을 확인할 수 없거나 breaking impact가 있으면 downstream SQL을 실행하지 않습니다.
- **전용 데모 스택:** `make demo`가 개발·운영 Compose 프로젝트나 볼륨을 수정하지 않습니다.

## Requirements evidence

| 공고의 기술 기대 | 프로젝트에서 사용한 방식 |
|---|---|
| Python 데이터 처리·스크립트 | Python 3.12 domain/application code, Typer CLI, Bash automation |
| SQL 조회·집계 | `information_schema` 수집, repository query, `daily_revenue` 집계 SQL |
| FastAPI 경험 | 인증, dependency injection, error contract, OpenAPI, background dispatch, Jinja/HTMX |
| Git workflow | 기능 단위 commit과 CI quality gate; 이 개인 프로젝트에는 팀 PR 경험을 별도로 주장하지 않음 |
| Airflow 경험 | Airflow 3 DAG, scheduling, guard task, retry/timeout, DAG unit test |
| 메타데이터 설계 | baseline/snapshot/change/lineage/outbox 관계 모델과 Alembic migration |
| Docker 이해 | 개발·격리 데모·production overlay, health/dependency gate, least exposure |

## Honest scope and limitations

- PostgreSQL만 지원합니다.
- 변경 감지는 실시간 CDC가 아니라 기본 10분 polling입니다.
- lineage는 SQL parser가 아닌 version-controlled YAML 선언입니다.
- 단일 운영자를 가정하며 애플리케이션 내부 RBAC가 없습니다.
- dashboard는 운영 판단에 필요한 단일 화면이며 범용 catalog editor가 아닙니다.
- MCP는 core 완성도를 우선해 구현 범위에서 제외했습니다.
- 개인 미니 PC 배포는 cloud-native 고가용성이나 multi-node failover를 제공하지 않습니다.

## Verification snapshot

완료 기준은 다음 명령이 모두 성공하는 것입니다.

```bash
make demo
uv run ruff check .
uv run mypy src
uv run pytest --cov=src/schema_sentry --cov-report=term-missing --cov-fail-under=85
docker compose run --rm --no-deps airflow-api-server bash -c 'pytest /opt/airflow/tests -q'
```

숫자는 README에 고정해 오래된 상태로 만들지 않고, 각 commit의 CI 결과와 로컬 final verification에서 확인합니다.
