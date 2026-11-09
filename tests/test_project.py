import sys
import unittest
from pathlib import Path
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dbx_sql_local.config import load_config, render_sql
from dbx_sql_local.runtime import Runtime


class ProjectTests(unittest.TestCase):
    def test_configuration_and_native_session_share_the_same_aliases(self):
        config = load_config(ROOT / "config.toml")
        native = Mock()
        db = Runtime(ROOT / "config.toml", spark=native)
        self.assertEqual(db.environment_name, config.default_environment)
        alias = next(iter(config.environments[db.environment_name].tables))
        path = db.tables[alias]
        db.table(alias)
        native.table.assert_called_once_with(path)
        self.assertEqual(render_sql("SELECT * FROM {{ " + alias + " }}", config.environments[db.environment_name]), "SELECT * FROM " + path)
        self.assertIs(db.session(), native)
        self.assertIsInstance(db.variables.limite_filas, int)


if __name__ == "__main__":
    unittest.main()
