# Prueba Databricks

Un mismo proyecto Spark para desarrollo local y jobs Databricks

## Empezar

Cookiecutter prepara Python 3.11, `.venv`, dependencias y el kernel **Prueba Databricks (Databricks)**. Si omitiste la instalación, o falló una descarga, repite:

```bash
python bootstrap.py
```

Abre `notebooks/demo.ipynb` en VS Code y selecciona el kernel del proyecto. También puedes ejecutar el mismo script que usarás como job:

```bash
# macOS / Linux
.venv/bin/python pipeline.py --env PRE
# Windows
.venv\Scripts\python.exe pipeline.py --env PRE
```

La primera consulta abre el navegador con `auth = "browser"`. Con perfiles, inicia sesión previamente mediante `databricks auth login --host https://dbc-20aaa784-c47e.cloud.databricks.com --profile DEFAULT`.

El workspace, tipo de compute, `cluster_id` y perfil están en `config.toml`. La versión de Connect y Python debe corresponder a la versión del compute. No necesitas Spark ni Java locales. Para all-purpose necesitas Unity Catalog y modo Assigned/Dedicated o Shared/Standard. Consulta los [requisitos oficiales](https://docs.databricks.com/aws/en/dev-tools/databricks-connect/requirements).

## Tablas, BBDD y variables

Edita las secciones existentes de `config.toml`, sin duplicar sus cabeceras:

```toml
[environments.PRE.databases]
crm = "catalogo_pre.crm"

[environments.PRE.tables]
clientes = { database = "crm", table = "clientes" }

[environments.PRE.variables]
fecha_ejecucion = "2026-01-01"
modo_debug = true
paises = ["ES", "PT"]
```

Las tablas también admiten texto: `"tabla"`, `"esquema.tabla"` o `"catalogo.esquema.tabla"`. Reinicia el kernel después de cambiar la configuración.

```python
from dbx_sql_local import setup

db = setup(spark=globals().get("spark"))
spark = db.spark
variables = db.variables

df = spark.table(spark.conf.viajes_demo)
df.limit(variables.limite_filas).display()
```

La inicialización es la misma en local y Databricks. El kernel ya precarga `spark`, `db`, `tables` y `variables`; incluirla hace portable el notebook. `spark.conf` conserva sus métodos Spark y añade los alias y variables locales. Usa corchetes si un alias coincide con un método.

En local, ejecuta `db.browse()` para seleccionar entorno y tabla, o `%db_env PRO`. En scripts y jobs usa `db.select_environment("PRO")` o `setup(environment="PRO")`. Las magias locales no forman parte de la lógica compartida. `DBX_ENV` permite seleccionar entorno y `[project].default_environment` fija el valor por defecto. Los DataFrames ya creados conservan su tabla al cambiar el entorno.

`display()` conserva la implementación nativa si existe y añade una tabla acotada si no existe. Usa `df.limit(50).display()` para una vista portable. Las variables mantienen sus tipos TOML; no se envían como ajustes Spark ni se sustituyen en los marcadores SQL de tablas.

## Desplegar el mismo pipeline como job

`pipeline.py` importa `src/` junto a sí mismo y busca `config.toml` al lado del script. Dentro de Databricks reutiliza la sesión Spark del job. El compute del job se configura en la tarea; PRE/PRO selecciona las rutas y variables.

La ruta de Workspace elegida al generar está en `databricks.yml`. Con Databricks CLI autenticada:

```bash
databricks bundle validate -t dev
databricks bundle deploy -t dev
databricks bundle run -t dev pipeline
# Para desplegar los parámetros de PRO
databricks bundle deploy -t dev --var environment=PRO
databricks bundle run -t dev pipeline
```

El bundle usa serverless environment version 2; su disponibilidad depende del workspace.


También puedes subir una carpeta autocontenida:

```bash
.venv/bin/python scripts/package_job.py
```

Descomprime `dist/databricks_job.zip`, sube la carpeta completa a Workspace Files y configura una tarea Python script que ejecute `job.py`. No necesitas instalar un wheel ni el kernel en Databricks. Para PRO, añade `["--env", "PRO"]` a los parámetros. Regenera el zip después de cambiar código o config.

El ejemplo lee un número limitado de filas y muestra un resumen; sustituye esa lógica por tu pipeline. Configura los permisos, dependencias adicionales y el compute necesarios para tu código. El uso compartido de la configuración no da acceso a tablas para las que el usuario del job carezca de permisos.

## Pruebas

```bash
.venv/bin/python -m unittest discover -s tests -v
```

`config.toml` contiene rutas e identificadores y se distribuye con el código. Mantén tokens y contraseñas fuera de ese archivo, utilizando la autenticación y secretos de tu entorno.
