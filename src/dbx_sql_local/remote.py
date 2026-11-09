"""Conexión y ejecución SQL mediante Databricks Connect."""

from __future__ import annotations

from .config import ComputeTarget


def connect(target: ComputeTarget):
    """Crea una sesión en all-purpose o serverless, con OAuth o perfil."""
    if target.mode not in {"all-purpose", "serverless"}:
        raise ValueError(f"Tipo de compute desconocido: {target.mode}")
    if target.mode == "all-purpose" and not target.cluster_id:
        raise ValueError("Un destino all-purpose necesita cluster_id")
    try:
        from databricks.connect import DatabricksSession
        from databricks.sdk.core import Config
    except ImportError as exc:
        raise RuntimeError(
            "Falta databricks-connect. Instala una versión compatible con "
            "tu compute (consulta README.md)."
        ) from exc
    if target.auth == "browser":
        compute = {"serverless_compute_id": "auto"} if target.mode == "serverless" else {"cluster_id": target.cluster_id}
        config = Config(host=target.host, auth_type="external-browser", **compute)
        return DatabricksSession.builder.sdkConfig(config).getOrCreate()
    if target.auth == "profile" and target.profile:
        profile_host = Config(profile=target.profile).host
        if not profile_host or profile_host.rstrip("/").lower() != target.host.rstrip("/").lower():
            raise RuntimeError(
                f"El perfil {target.profile!r} no apunta a {target.host}. "
                "Inicia sesión en ese workspace con el perfil indicado en config.toml."
            )
        builder = DatabricksSession.builder.profile(target.profile)
        if target.mode == "serverless":
            builder = builder.serverless()
        else:
            builder = builder.clusterId(target.cluster_id)
        return builder.getOrCreate()
    raise ValueError(f"Método de autenticación desconocido: {target.auth}")


def explain_sql(spark, sql: str) -> str:
    """Solicita el plan SQL al motor remoto."""
    rows = spark.sql(f"EXPLAIN FORMATTED {sql}").collect()
    return "\n".join(str(row[0]) for row in rows)


def run_sql(spark, sql: str, max_rows: int = 200) -> tuple[list[str], list[dict], bool]:
    """Ejecuta SQL remoto y trae como máximo max_rows filas más una de control."""
    if not 1 <= max_rows <= 5000:
        raise ValueError("max_rows debe estar entre 1 y 5000")
    frame = spark.sql(sql)
    columns = frame.columns
    rows = frame.limit(max_rows + 1).collect()
    truncated = len(rows) > max_rows
    data = [row.asDict(recursive=True) for row in rows[:max_rows]]
    return columns, data, truncated
