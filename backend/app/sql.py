"""SQL identifiers come only from validated configuration and the static dataset registry."""

from .config import Settings
from .datasets import DATASETS
from .errors import AppError
from .models import Query


def order_columns(dataset: str, query: Query) -> list[str]:
    spec = DATASETS[dataset]
    field = query.sort.upper()
    if query.sort != "default" and field not in spec.sorts:
        raise AppError(422, "invalid_sort", "Unsupported sort field.")
    primary = [] if query.sort == "default" else [f"p.{field} {query.direction.upper()} NULLS LAST"]
    return primary + [f"p.{k} ASC NULLS LAST" for k in spec.keys if k != field]


def page_sql(
    settings: Settings,
    dataset: str,
    tenant: str,
    pipeline: str,
    query: Query,
    release: str | None,
    offset: int,
) -> tuple[str, tuple]:
    spec = DATASETS[dataset]
    order = ", ".join(order_columns(dataset, query))
    columns = ", ".join(f"p.{c}" for c in spec.columns)
    conditions, params = ["p.TENANT_ID = %s", "p.PIPELINE_ID = %s"], [tenant, pipeline]
    if release:
        conditions.append("p.RELEASE_ID = %s")
        params.append(release)
    if query.currency:
        conditions.append("p.CURRENCY = %s")
        params.append(query.currency)
    if query.q:
        # CONTAINS treats %, _ and backslash literally; values stay bound parameters.
        conditions.append("(" + " OR ".join(f"CONTAINS(LOWER(p.{c}), LOWER(%s))" for c in spec.search) + ")")
        params.extend([query.q] * len(spec.search))
    db = settings.snowflake_database
    sql = f"""WITH publication AS (
        SELECT ACTIVE_RELEASE_ID, ACTIVE_AS_OF, COUNT(*) OVER () AS _RELEASE_COUNT FROM {db}.SERVING.APP_RELEASE
        WHERE TENANT_ID = %s AND PIPELINE_ID = %s
    ), page AS (
        SELECT {columns}, 1 AS _PRESENT FROM {db}.SERVING.{spec.view} p
        WHERE {" AND ".join(conditions)} ORDER BY {order} LIMIT %s OFFSET %s
    )
    SELECT r.ACTIVE_RELEASE_ID AS _RELEASE_ID, r.ACTIVE_AS_OF AS _AS_OF, r._RELEASE_COUNT, p.*
    FROM publication r LEFT JOIN page p ON TRUE ORDER BY {order}"""
    return sql, (tenant, pipeline, *params, query.limit + 1, offset)


def health_sql(settings: Settings) -> str:
    db = settings.snowflake_database
    return f"""WITH latest_run AS (
       SELECT RUN_ID,TENANT_ID,STATUS FROM {db}.SERVING.RUN_STATUS WHERE TENANT_ID=%s
       QUALIFY ROW_NUMBER() OVER (ORDER BY STARTED_AT DESC, RUN_ID DESC)=1
    ), checks AS (
       SELECT ARRAY_AGG(OBJECT_CONSTRUCT('layer',q.LAYER,'check_name',q.CHECK_NAME,'failures',q.FAILURES)) AS CHECKS
       FROM {db}.SERVING.QUALITY_STATUS q JOIN latest_run r ON q.RUN_ID=r.RUN_ID AND q.TENANT_ID=r.TENANT_ID
    )
    SELECT p.TENANT_ID,p.PIPELINE_ID,p.ACTIVE_RELEASE_ID,p.ACTIVE_AS_OF,p.PUBLISHED_AT,
       p.LAST_ATTEMPT_AT,p.LAST_ATTEMPT_STATUS,p.LAST_ERROR_CODE,r.RUN_ID,r.STATUS AS RUN_STATUS,c.CHECKS
    FROM {db}.SERVING.PIPELINE_STATUS p LEFT JOIN latest_run r ON p.TENANT_ID=r.TENANT_ID
    CROSS JOIN checks c WHERE p.TENANT_ID=%s AND p.PIPELINE_ID=%s"""
