"""Configuración y sesión comunes a desarrollo local y jobs Databricks."""

from __future__ import annotations

import os
from copy import deepcopy
from pathlib import Path

from .config import load_config, qualified_table, render_sql
from .remote import connect


def _config_path() -> Path:
    override = os.environ.get("DBX_SQL_CONFIG")
    if override:
        return Path(override).expanduser().resolve()
    for directory in (Path.cwd(), *Path.cwd().parents):
        candidate = directory / "config.toml"
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(
        "No encuentro config.toml. Abre el notebook dentro del proyecto o define DBX_SQL_CONFIG."
    )


class TablePaths:
    """Rutas del entorno activo, disponibles con atributos y autocompletado."""

    def __init__(self, runtime: Runtime):
        self._runtime = runtime

    def __getitem__(self, alias: str) -> str:
        env = self._runtime.config.environments[self._runtime.environment_name]
        if alias not in env.tables:
            raise KeyError(f"Tabla {alias!r} desconocida en {env.name}. Opciones: {', '.join(env.tables)}")
        return qualified_table(env.tables[alias], env.catalog, env.schema)

    def __getattr__(self, alias: str) -> str:
        try:
            return self[alias]
        except KeyError as exc:
            raise AttributeError(str(exc)) from exc

    def __dir__(self):
        return sorted(set(super().__dir__()) | set(self._runtime.config.environments[self._runtime.environment_name].tables))

    def __repr__(self) -> str:
        env = self._runtime.config.environments[self._runtime.environment_name]
        return repr({alias: self[alias] for alias in env.tables})


class NotebookVariables:
    """Valores TOML del entorno activo, conservando sus tipos Python."""

    def __init__(self, runtime: Runtime):
        self._runtime = runtime

    def __getitem__(self, name: str):
        env = self._runtime.config.environments[self._runtime.environment_name]
        return deepcopy(env.variables[name])

    def __getattr__(self, name: str):
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(f"Variable desconocida: {name}") from exc

    def __dir__(self):
        env = self._runtime.config.environments[self._runtime.environment_name]
        return sorted(set(super().__dir__()) | set(env.variables))

    def __repr__(self) -> str:
        return repr(self._runtime.config.environments[self._runtime.environment_name].variables)


class SparkConfProxy:
    """Añade alias locales conservando los métodos de la configuración Spark."""

    def __init__(self, runtime: Runtime):
        self._runtime = runtime

    def __getattr__(self, name: str):
        if name.startswith("_"):
            raise AttributeError(name)
        from pyspark.sql.conf import RuntimeConfig

        if hasattr(RuntimeConfig, name):
            return getattr(self._runtime.session().conf, name)
        if name in self._runtime.config.environments[self._runtime.environment_name].tables:
            return self._runtime.tables[name]
        if name in self._runtime.config.environments[self._runtime.environment_name].variables:
            return self._runtime.variables[name]
        raise AttributeError(f"Configuración, tabla o variable desconocida: {name}. Usa db.tables o db.variables.")

    def __getitem__(self, name: str):
        if name in self._runtime.config.environments[self._runtime.environment_name].variables:
            return self._runtime.variables[name]
        return self._runtime.tables[name]

    def __dir__(self):
        return sorted(set(super().__dir__()) | set(dir(self._runtime.tables)) | set(dir(self._runtime.variables)) | {"get", "set", "unset", "isModifiable"})

    def get(self, key: str, *args, **kwargs):
        if key in self._runtime.config.environments[self._runtime.environment_name].tables:
            return self._runtime.tables[key]
        if key in self._runtime.config.environments[self._runtime.environment_name].variables:
            return self._runtime.variables[key]
        return self._runtime.session().conf.get(key, *args, **kwargs)


def display_frame(frame, limit: int = 50) -> None:
    """Muestra una vista HTML acotada; nunca recoge el DataFrame completo."""
    import pandas as pd
    from IPython.display import display

    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 5000:
        raise ValueError("limit debe ser un entero entre 1 y 5000")
    rows = frame.limit(limit + 1).collect()
    data = pd.DataFrame([tuple(row) for row in rows[:limit]], columns=frame.columns)
    with pd.option_context("display.max_rows", limit, "display.max_columns", None):
        display(data)
    if len(rows) > limit:
        print(f"Mostrando las primeras {limit} filas; hay más resultados.")


def install_dataframe_display() -> None:
    from pyspark.sql import DataFrame

    classes = [DataFrame]
    try:
        from pyspark.sql.connect.dataframe import DataFrame as ConnectDataFrame
    except ImportError:
        pass
    else:
        classes.append(ConnectDataFrame)
    for cls in classes:
        if not hasattr(cls, "display"):
            cls.display = display_frame


class SparkProxy:
    """Abre la conexión remota al usar spark por primera vez."""

    def __init__(self, runtime: Runtime):
        self._runtime = runtime
        self.conf = SparkConfProxy(runtime)

    def __getattr__(self, name: str):
        return getattr(self._runtime.session(), name)

    def __repr__(self) -> str:
        return f"<Spark: {self._runtime.target_name}>"


class Runtime:
    def __init__(self, config_path: str | Path | None = None, *, spark=None, environment: str | None = None, target: str | None = None):
        self._provided_session = spark is not None
        if self._provided_session and target is not None:
            raise ValueError("Con una sesión existente, el destino lo determina el compute adjunto al notebook o job.")
        self.config = load_config(config_path or _config_path(), require_compute=not self._provided_session)
        self.target_name = "Databricks (compute adjunto)" if self._provided_session else target or next(iter(self.config.compute))
        if target is not None and target not in self.config.compute:
            raise ValueError(f"Destino desconocido: {target}")
        self.environment_name = self.config.default_environment or (
            "PRE" if "PRE" in self.config.environments else next(iter(self.config.environments))
        )
        if environment is not None:
            self.select_environment(environment)
        self._session = spark
        self.tables = TablePaths(self)
        self.variables = NotebookVariables(self)
        self.spark = SparkProxy(self)

    def table(self, alias: str):
        """Lee un alias del entorno activo como DataFrame Spark."""
        return self.spark.table(self.tables[alias])

    def browse(self):
        from .notebook import browse

        return browse(self)

    def session(self):
        if self._session is None:
            self._session = connect(self.config.compute[self.target_name])
        return self._session

    def select_target(self, name: str) -> None:
        if self._provided_session:
            raise ValueError("La sesión pertenece al notebook o job. Configura el compute del job para cambiar de destino.")
        if name not in self.config.compute:
            raise ValueError(f"Destino desconocido: {name}. Opciones: {', '.join(self.config.compute)}")
        if name != self.target_name:
            if self._session is not None:
                self._session.stop()
                self._session = None
            self.target_name = name

    def select_environment(self, name: str) -> None:
        if name not in self.config.environments:
            raise ValueError(
                f"Entorno desconocido: {name}. Opciones: {', '.join(self.config.environments)}"
            )
        self.environment_name = name

    def sql(self, query: str, environment: str | None = None):
        name = environment or self.environment_name
        if name not in self.config.environments:
            raise ValueError(f"Entorno desconocido: {name}")
        return self.session().sql(render_sql(query, self.config.environments[name]))


def _databricks_session():
    """Reutiliza el compute adjunto cuando se ejecuta dentro de Databricks."""
    try:
        from pyspark.sql import SparkSession
    except ImportError:
        return None

    active = SparkSession.getActiveSession()
    if active is not None:
        return active
    if os.environ.get("DATABRICKS_RUNTIME_VERSION"):
        return SparkSession.builder.getOrCreate()
    return None


def setup(config_path: str | Path | None = None, *, spark=None, environment: str | None = None, target: str | None = None) -> Runtime:
    """Punto de entrada idéntico para kernel local, notebooks y jobs.

    Pasa el spark nativo del notebook cuando exista. En scripts Databricks
    se detecta el runtime; fuera de él se usa Connect al hacer la primera consulta.
    """
    environment = environment if environment is not None else os.environ.get("DBX_ENV")
    if isinstance(spark, SparkProxy):
        current = spark._runtime
        if config_path is None:
            if environment is not None:
                current.select_environment(environment)
            if target is not None:
                current.select_target(target)
            install_dataframe_display()
            return current
        # Una sesión nativa pertenece al job; una conexión local nueva sigue siendo perezosa.
        if target is None:
            target = current.target_name if not current._provided_session else None
        if environment is None:
            environment = current.environment_name
        spark = current._session if current._provided_session else None
    elif spark is None:
        spark = _databricks_session()
    runtime = Runtime(config_path, spark=spark, environment=environment, target=target)
    install_dataframe_display()
    return runtime

