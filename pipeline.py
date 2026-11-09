"""El mismo script en local y como tarea Python de Databricks.

Local: python examples/job_portable.py --config config.toml --env PRE
Job:   mismo archivo junto a config.toml y dbx_sql_local/, con --env PRO si procede.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Resuelve la librería junto al script desplegado o desde src/ en el repositorio.
DIRECTORY = Path(__file__).resolve().parent
SOURCE = DIRECTORY if (DIRECTORY / "dbx_sql_local").is_dir() else DIRECTORY.parent / "src"
if SOURCE.is_dir():
    sys.path.insert(0, str(SOURCE))

from dbx_sql_local import setup


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description="Ejemplo Spark portable entre local y Databricks")
    default_config = DIRECTORY / "config.toml"
    if not default_config.is_file():
        default_config = DIRECTORY.parent / "config.toml"
    parser.add_argument("--config", default=str(default_config), help="Ruta TOML; por defecto config.toml junto al código")
    parser.add_argument("--env", default=None, help="Entorno, por ejemplo PRE o PRO; admite DBX_ENV")
    parser.add_argument("--table", default=None, help="Alias de tabla; por defecto, el primero del entorno")
    args = parser.parse_args(argv)

    db = setup(config_path=args.config, environment=args.env, spark=globals().get("spark"))
    spark = db.spark
    aliases = db.config.environments[db.environment_name].tables
    alias = args.table or next(iter(aliases))
    df = spark.table(spark.conf[alias])
    # Las transformaciones y acciones Spark son exactamente las mismas en ambos sitios.
    limit = getattr(db.variables, "limite_filas", 50)
    rows = df.limit(limit).collect()
    print(f"Entorno {db.environment_name}: {len(rows)} filas de {spark.conf[alias]}")


if __name__ == "__main__":
    main()
