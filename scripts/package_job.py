"""Empaqueta el script, la configuración y las fuentes, sin entornos ni credenciales del equipo."""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dbx_sql_local.config import load_config


def package_job(config_path: Path, output: Path) -> Path:
    load_config(config_path, require_compute=False)
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory() as temporary:
        folder = Path(temporary) / "databricks_job"
        folder.mkdir()
        shutil.copy2(ROOT / "pipeline.py", folder / "job.py")
        shutil.copy2(config_path, folder / "config.toml")
        shutil.copytree(ROOT / "src/dbx_sql_local", folder / "dbx_sql_local", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        (folder / "LEEME.txt").write_text(
            "Sube esta carpeta completa a Workspace Files o a una carpeta Git de Databricks.\n"
            "Crea una tarea Python script y selecciona job.py, con el Python correspondiente a tu runtime.\n"
            "No necesitas instalar un wheel ni nuestro kernel.\n"
            "El entorno por defecto está en config.toml; para PRO añade [\"--env\", \"PRO\"].\n"
            "El script busca config.toml junto a sí mismo y usa el Spark del job.\n"
            "El ejemplo lee un número limitado de filas del primer alias, o el indicado con --table.\n"
            "La configuración es una copia del archivo elegido al empaquetar.\n"
            "Tras cambiar el código o config, vuelve a empaquetar y subir la carpeta.\n",
            encoding="utf-8",
        )
        with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
            for source in sorted(folder.rglob("*")):
                if source.is_file():
                    archive.write(source, source.relative_to(folder.parent))
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "config.toml")
    parser.add_argument("--output", type=Path, default=ROOT / "dist/databricks_job.zip")
    args = parser.parse_args()
    print(package_job(args.config, args.output))


if __name__ == "__main__":
    main()
