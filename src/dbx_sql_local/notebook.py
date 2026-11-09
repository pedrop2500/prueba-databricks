"""Adaptadores de IPython y selector de rutas del kernel local."""

from __future__ import annotations

import argparse
import html
import shlex
from functools import partial

from .config import render_sql
from .remote import explain_sql, run_sql
from .runtime import Runtime as NotebookRuntime, display_frame, install_dataframe_display, setup


def browse(runtime):
    """Selector local de destino, entorno y rutas configuradas, sin consultas."""
    import ipywidgets as widgets
    from IPython.display import display

    target = widgets.Dropdown(options=[runtime.target_name] if runtime._provided_session else list(runtime.config.compute), value=runtime.target_name, description="Workspace:", disabled=runtime._provided_session)
    environment = widgets.Dropdown(options=list(runtime.config.environments), value=runtime.environment_name, description="Entorno:")
    table = widgets.Dropdown(description="Tabla:")
    preview = widgets.HTML()

    def update_preview(change=None):
        if table.value is None:
            preview.value = "No hay tablas configuradas en este entorno. Añádelas en config.toml."
            return
        path = runtime.tables[table.value]
        code = f"df = spark.table(spark.conf[{table.value!r}])\ndf.display()"
        preview.value = f"<p>Ruta: <code>{html.escape(path)}</code></p><pre>{html.escape(code)}</pre>"

    def update_environment(change=None):
        runtime.select_environment(environment.value)
        env = runtime.config.environments[runtime.environment_name]
        table.options = list(env.tables)
        if table.value not in env.tables:
            table.value = next(iter(env.tables), None)
        update_preview()

    if not runtime._provided_session:
        target.observe(lambda change: runtime.select_target(change["new"]), names="value")
    environment.observe(update_environment, names="value")
    table.observe(update_preview, names="value")
    update_environment()
    panel = widgets.VBox([target, environment, table, preview])
    display(panel)
    return None


def sql_magic(runtime, line: str, cell: str) -> None:
    import pandas as pd
    from IPython.display import HTML, display

    parser = argparse.ArgumentParser(prog="%%sql")
    parser.add_argument("--env", choices=tuple(runtime.config.environments))
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--plan", action="store_true")
    args = parser.parse_args(shlex.split(line))
    environment = runtime.config.environments[args.env or runtime.environment_name]
    query = render_sql(cell, environment)
    if args.plan:
        plan = explain_sql(runtime.session(), query)
        display(
            HTML(
                "<details><summary>Plan de ejecución</summary>"
                f"<pre>{html.escape(plan)}</pre></details>"
            )
        )
    columns, rows, truncated = run_sql(runtime.session(), query, max_rows=args.limit)
    display(pd.DataFrame(rows, columns=columns))
    if truncated:
        print(f"Mostrando las primeras {args.limit} filas; hay más resultados.")


def load_ipython_extension(shell) -> None:
    """Registra spark, db y %%sql al arrancar el kernel dedicado."""
    runtime = setup()
    shell.user_ns["spark"] = runtime.spark
    shell.user_ns["db"] = runtime
    shell.user_ns["tables"] = runtime.tables
    shell.user_ns["variables"] = runtime.variables
    shell.register_magic_function(partial(sql_magic, runtime), "cell", "sql")
    shell.register_magic_function(runtime.select_environment, "line", "db_env")
    shell.register_magic_function(runtime.select_target, "line", "db_target")
    aliases = list(runtime.config.environments[runtime.environment_name].tables)
    example = f"spark.table(spark.conf[{aliases[0]!r}]).display()" if aliases else "db.tables"
    print(
        f"Databricks SQL Local · {runtime.target_name} · {runtime.environment_name}\n"
        "Tablas precargadas: " + ", ".join(aliases) +
        "\nVariables precargadas: " + ", ".join(runtime.config.environments[runtime.environment_name].variables) +
        f"\nUsa {example} o db.browse() para elegir una ruta."
    )
