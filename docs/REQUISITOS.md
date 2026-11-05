# Requisitos e instalación

## Qué debes instalar

1. **Python 3.10 o posterior**, incluyendo el lanzador de Python para Windows (`py`).
2. Un navegador actualizado: Chrome, Microsoft Edge o Firefox.
3. No se requieren paquetes externos de Python ni un entorno virtual.

No necesitas instalar Node.js, npm, FastAPI, Pydantic, un servidor de base de datos ni paquetes adicionales. Python incluye SQLite y el servidor HTTP que utiliza Terranova. No se necesita conexión a Internet.

La aplicación usa únicamente la biblioteca estándar de Python. `requirements.txt` se conserva en la raíz para compatibilidad con el proyecto, pero no instala dependencias.

## Instalación en Windows

Abre PowerShell en la carpeta `Terranova` y confirma que Python esté disponible:

```powershell
py --version
```

Si Windows muestra que `py` no existe, instala Python desde <https://www.python.org/downloads/windows/> y habilita el lanzador y la opción para agregar Python al `PATH`.

## Inicio de Terranova

Desde PowerShell, en la carpeta `Terranova`, inicia el servidor:

```powershell
py -3 -m backend.main
```

Abre <http://127.0.0.1:8000>. Mantén abierta la ventana de PowerShell mientras usas la aplicación; `Ctrl+C` detiene el servidor. También puedes iniciar el programa con doble clic en [`iniciar_terranova.bat`](../iniciar_terranova.bat).

El primer arranque crea `.env`, la carpeta `data`, la base de datos y los datos de demostración. Para cambiar el puerto o el correo y la contraseña inicial, edita `.env` antes del primer arranque.

No borres `data\terranova.sqlite3` si quieres conservar los datos; descarga también copias de seguridad y guárdalas fuera del computador.
