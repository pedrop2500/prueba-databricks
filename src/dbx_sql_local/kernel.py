"""Kernel Jupyter que carga la integración SQL al iniciarse."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory


KERNEL_NAME = "databricks-sql-local"
DISPLAY_NAME = "Databricks SQL Local (Python 3.12)"


def install(prefix: str | None = None, *, name: str = KERNEL_NAME, display_name: str = DISPLAY_NAME, config_path: str | None = None) -> str:
    from jupyter_client.kernelspec import KernelSpecManager

    with TemporaryDirectory() as directory:
        spec = {
            "argv": [
                sys.executable,
                "-m",
                "ipykernel_launcher",
                "-f",
                "{connection_file}",
                "--InteractiveShellApp.extra_extensions=dbx_sql_local.notebook",
            ],
            "display_name": display_name,
            "language": "python",
            "metadata": {"debugger": True},
        }
        spec["env"] = {
            "PYTHONPATH": str(Path(__file__).resolve().parents[1]) + os.pathsep + os.environ.get("PYTHONPATH", "")
        }
        if config_path is not None:
            spec["env"]["DBX_SQL_CONFIG"] = str(Path(config_path).expanduser().resolve())
        (Path(directory) / "kernel.json").write_text(json.dumps(spec, indent=2), encoding="utf-8")
        return KernelSpecManager().install_kernel_spec(
            directory, kernel_name=name, prefix=prefix, user=prefix is None
        )


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "install":
        parser = argparse.ArgumentParser(description="Instala el kernel de Databricks SQL Local")
        parser.add_argument("install")
        parser.add_argument("--prefix")
        parser.add_argument("--name", default=KERNEL_NAME)
        parser.add_argument("--display-name", default=DISPLAY_NAME)
        parser.add_argument("--config")
        args = parser.parse_args()
        print(install(args.prefix, name=args.name, display_name=args.display_name, config_path=args.config))
        return

    from ipykernel.kernelapp import IPKernelApp

    app = IPKernelApp.instance()
    app.initialize()
    app.shell.extension_manager.load_extension("dbx_sql_local.notebook")
    app.start()


if __name__ == "__main__":
    main()
