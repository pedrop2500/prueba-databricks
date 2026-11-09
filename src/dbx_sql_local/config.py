"""Configuración de perfiles serverless y tablas lógicas por entorno."""

from __future__ import annotations

import re
try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10 / Databricks Runtime 14.3.
    import tomli as tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast
from urllib.parse import urlsplit


@dataclass(frozen=True)
class ComputeTarget:
    name: str
    host: str
    auth: str
    profile: str | None
    mode: str = "serverless"
    cluster_id: str | None = None


@dataclass(frozen=True)
class Environment:
    name: str
    catalog: str
    schema: str
    tables: dict[str, str]
    variables: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class ProjectConfig:
    compute: dict[str, ComputeTarget]
    environments: dict[str, Environment]
    default_environment: str | None = None


def _section(value: object, location: str) -> dict[str, object]:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise ValueError(f"{location} debe ser una sección")
    return cast(dict[str, object], value)


def _required_string(data: dict[str, object], key: str, location: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{location}.{key} debe ser un texto no vacío")
    return value.strip()


def load_config(path: str | Path = "config.toml", *, require_compute: bool = True) -> ProjectConfig:
    config_path = Path(path)
    with config_path.open("rb") as file:
        raw: dict[str, object] = tomllib.load(file)
    compute_data = _section(raw.get("compute", {}), "compute")
    environment_data = _section(raw.get("environments"), "environments")
    if require_compute and not compute_data:
        raise ValueError("Define al menos un destino en [compute.<nombre>]")
    if not environment_data:
        raise ValueError("Define al menos un entorno en [environments.<nombre>]")

    compute: dict[str, ComputeTarget] = {}
    for name, raw_data in compute_data.items():
        location = f"compute.{name}"
        data = _section(raw_data, location)
        host = _required_string(data, "host", location)
        parsed_host = urlsplit(host)
        if parsed_host.scheme != "https" or not parsed_host.netloc or parsed_host.path or parsed_host.query or parsed_host.fragment:
            raise ValueError(f"{location}.host debe ser la URL base https del workspace")
        auth = _required_string(data, "auth", location)
        if auth not in {"browser", "profile"}:
            raise ValueError(f"{location}.auth debe ser 'browser' o 'profile'")
        profile = _required_string(data, "profile", location) if auth == "profile" else None
        mode = data.get("mode", "serverless")
        if not isinstance(mode, str) or mode not in {"serverless", "all-purpose"}:
            raise ValueError(f"{location}.mode debe ser 'all-purpose' o 'serverless'")
        cluster_id = _required_string(data, "cluster_id", location) if mode == "all-purpose" else None
        if mode == "serverless" and data.get("cluster_id"):
            raise ValueError(f"{location}: serverless no utiliza cluster_id")
        compute[name] = ComputeTarget(
            name=name,
            host=host,
            auth=auth,
            profile=profile,
            mode=mode,
            cluster_id=cluster_id,
        )

    environments: dict[str, Environment] = {}
    for name, raw_data in environment_data.items():
        location = f"environments.{name}"
        data = _section(raw_data, location)
        catalog = _required_string(data, "catalog", location)
        schema = _required_string(data, "schema", location)
        database_data = _section(data.get("databases", {}), f"{location}.databases")
        databases: dict[str, str] = {}
        for alias, path in database_data.items():
            if not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*", alias):
                raise ValueError(f"Alias de base de datos no válido: {alias}")
            if not isinstance(path, str) or len(path.split(".")) != 2:
                raise ValueError(f"{location}.databases.{alias} debe ser catalogo.esquema")
            parts = [part.strip() for part in path.split(".")]
            for part in parts:
                _quoted_identifier(part)
            databases[alias] = ".".join(parts)
        table_data = _section(data.get("tables", {}), f"{location}.tables")
        tables: dict[str, str] = {}
        for alias, table in table_data.items():
            if not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*", alias):
                raise ValueError(f"Alias de tabla no válido: {alias}")
            if isinstance(table, dict):
                table_location = f"{location}.tables.{alias}"
                if set(table) != {"database", "table"}:
                    raise ValueError(f"{table_location} debe contener solo database y table")
                database = _required_string(table, "database", table_location)
                name_in_database = _required_string(table, "table", table_location)
                if database not in databases:
                    raise ValueError(f"{table_location}: base de datos {database!r} no definida en {location}.databases")
                if "." in name_in_database:
                    raise ValueError(f"{table_location}.table debe ser solo el nombre de tabla, sin catálogo ni esquema")
                table = f"{databases[database]}.{name_in_database}"
            if not isinstance(table, str) or not table.strip():
                raise ValueError(f"{location}.tables.{alias} debe ser un nombre de tabla")
            qualified_table(table, catalog, schema)
            tables[alias] = table
        variables = _section(data.get("variables", {}), f"{location}.variables")
        for variable in variables:
            if not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*", variable):
                raise ValueError(f"Nombre de variable no válido: {variable}")
            if variable in tables:
                raise ValueError(f"{location}: {variable!r} está definido como tabla y como variable; usa nombres distintos")
        environments[name] = Environment(
            name=name,
            catalog=catalog,
            schema=schema,
            tables=tables,
            variables=variables,
        )
    project = _section(raw.get("project", {}), "project")
    default_environment = project.get("default_environment")
    if default_environment is not None and (
        not isinstance(default_environment, str) or default_environment not in environments
    ):
        raise ValueError("project.default_environment debe ser un entorno definido")
    return ProjectConfig(compute=compute, environments=environments, default_environment=default_environment)


def _quoted_identifier(part: str) -> str:
    part = part.strip()
    if not part or "`" in part or "\x00" in part:
        raise ValueError(f"Identificador SQL no válido: {part!r}")
    return f"`{part}`"


def qualified_table(table: str, catalog: str | None, schema: str | None) -> str:
    """Devuelve un nombre seguro de 3 partes: catalog.schema.table."""
    parts = table.split(".")
    if len(parts) == 1:
        if catalog is None or schema is None:
            raise ValueError("Falta catálogo o esquema para completar el nombre de tabla")
        parts = [catalog, schema, parts[0]]
    elif len(parts) == 2:
        if catalog is None:
            raise ValueError("Falta catálogo para completar el nombre de tabla")
        parts = [catalog, *parts]
    elif len(parts) != 3:
        raise ValueError(f"Nombre de tabla no válido: {table!r}")
    return ".".join(_quoted_identifier(part) for part in parts)


_PLACEHOLDER = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z_0-9]*)\s*\}\}")


def render_sql(sql: str, environment: Environment) -> str:
    """Sustituye {{ alias }} por la tabla física del entorno seleccionado."""
    def replace(match: re.Match[str]) -> str:
        alias = match.group(1)
        if alias not in environment.tables:
            raise ValueError(f"La tabla lógica {alias!r} no existe en {environment.name}")
        return qualified_table(
            environment.tables[alias], environment.catalog, environment.schema
        )

    result = _PLACEHOLDER.sub(replace, sql)
    if "{{" in result or "}}" in result:
        raise ValueError("Hay un marcador {{ ... }} sin resolver")
    if not result.strip():
        raise ValueError("Escribe una consulta SQL")
    return result
