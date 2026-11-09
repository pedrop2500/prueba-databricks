"""Una configuración común para Spark local con Connect y jobs Databricks."""

from .runtime import Runtime, setup

__all__ = ["Runtime", "setup"]
