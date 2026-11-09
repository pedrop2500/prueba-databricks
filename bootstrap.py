"""Prepara Python, .venv y el kernel de este proyecto en Windows, macOS y Linux."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PYTHON = "3.11"
KERNEL_NAME = "prueba-databricks"
DISPLAY_NAME = "Prueba Databricks (Databricks)"


def binary(directory: Path, name: str) -> Path:
    return directory / ("Scripts" if os.name == "nt" else "bin") / (name + ".exe" if os.name == "nt" else name)


def run(*command: str) -> None:
    environment = {
        **os.environ,
        "UV_CACHE_DIR": str(ROOT / ".bootstrap/uv-cache"),
        "UV_PYTHON_INSTALL_DIR": str(ROOT / ".bootstrap/python"),
        "UV_SYSTEM_CERTS": "true",
        "PYTHONPATH": str(ROOT / "src") + os.pathsep + os.environ.get("PYTHONPATH", ""),
    }
    subprocess.run(list(map(str, command)), cwd=ROOT, env=environment, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-kernel", action="store_true", help="Prepara solo el entorno Python")
    args = parser.parse_args()
    uv = shutil.which("uv")
    if uv is None:
        tools = ROOT / ".bootstrap"
        if not binary(tools, "python").exists():
            venv.EnvBuilder(with_pip=True).create(tools)
        uv_path = binary(tools, "uv")
        if not uv_path.exists():
            run(binary(tools, "python"), "-m", "pip", "install", "--no-cache-dir", "uv>=0.11,<1")
        uv = str(uv_path)
    environment = ROOT / ".venv"
    if not binary(environment, "python").exists():
        run(uv, "venv", "--python", PYTHON, str(environment))
    python = binary(environment, "python")
    version = subprocess.check_output([str(python), "-c", "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"], text=True).strip()
    if version != PYTHON:
        raise SystemExit(f".venv usa Python {version}; se necesita {PYTHON}. Renombra o elimina .venv y repite bootstrap.py.")
    run(uv, "pip", "install", "--python", str(python), "-e", ".[notebook]")
    # Registro por proyecto: cada kernel abre siempre su propio archivo de configuración.
    if not args.skip_kernel:
        run(python, "-m", "dbx_sql_local.kernel", "install", "--name", KERNEL_NAME, "--display-name", DISPLAY_NAME, "--config", str(ROOT / "config.toml"))
    settings = ROOT / ".vscode/settings.json"
    settings.parent.mkdir(exist_ok=True)
    settings.write_text(json.dumps({"python.defaultInterpreterPath": str(python), "python.terminal.activateEnvironment": True}, indent=2) + "\n", encoding="utf-8")
    print(f"Listo. Selecciona el kernel {DISPLAY_NAME!r} o ejecuta {python} pipeline.py")


if __name__ == "__main__":
    main()
