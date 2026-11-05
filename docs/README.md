# Terranova

Aplicación local para la gestión de terrenos, clientes, ventas, contratos, pagos, informes y usuarios. La interfaz está en español y funciona en el navegador; el backend usa solo la biblioteca estándar de Python y los datos se guardan en SQLite.

## Funcionalidades

- Panel de indicadores y actividad reciente.
- Inventario de lotes con vista esquemática, búsqueda y estados.
- Registro de clientes.
- Contratos de venta, financiación estimada y saldo.
- Registro de pagos y abonos con validación contra el saldo.
- Exportación de inventario, clientes, ventas y pagos a CSV.
- Usuarios con roles de Administrador, Operador y Consulta.
- Inicio y cierre de sesión; contraseña almacenada con PBKDF2.
- Registro de actividad de las operaciones.
- Respaldo JSON y restauración transaccional de los datos operativos.
- Diseño adaptable a equipos de escritorio, tabletas y móviles.

## Requisitos

- Windows 10/11.
- Python 3.10 o posterior.
- Navegador moderno: Chrome, Edge o Firefox.
- No necesitas conexión a Internet ni instalar paquetes de Python.
- Node.js, FastAPI, Pydantic y una instalación separada de SQLite no son necesarios.

Consulta [REQUISITOS.md](./REQUISITOS.md) para más información.

## Inicio rápido en Windows

Abre PowerShell en la carpeta `Terranova` y ejecuta:

```powershell
py -3 -m backend.main
```

Este comando inicia el servidor y la interfaz completa; no hace falta instalar paquetes. Si `py` no funciona, prueba:

```powershell
python -m backend.main
```

Ejecuta el comando desde la carpeta raíz `Terranova`.

También puedes iniciar la aplicación con doble clic en [`iniciar_terranova.bat`](../iniciar_terranova.bat).

Abre <http://127.0.0.1:8000>. La aplicación crea `.env`, `data\terranova.sqlite3` y los registros ficticios de demostración en el primer inicio. Deja abierta la ventana del servidor; `Ctrl+C` lo detiene.

Si el puerto 8000 está ocupado o la página no abre, inicia el servidor en otro puerto desde PowerShell:

```powershell
$env:TERRANOVA_PORT = "8011"
py -3 -m backend.main
```

En ese caso abre <http://127.0.0.1:8011>. La variable solo se aplica a esa ventana de PowerShell.

Si la página aparece sin estilos, confirma que estás usando el mismo puerto del servidor y prueba una recarga forzada con `Ctrl+F5`. Para comprobar que el archivo de estilos carga, abre `http://127.0.0.1:8011/styles.css` (o cambia `8011` por el puerto que estés usando); debe mostrarse el contenido CSS.

### Acceso inicial

- Correo: `admin@terranova.local`
- Contraseña inicial: `Cambiar123!!`

Cambia la contraseña al entrar desde **Configuración**. Antes del primer inicio, también puedes modificar el correo y la contraseña inicial en `.env`. Esos valores solo se usan al crear el primer usuario; cambiarlos luego no actualiza la cuenta existente.

## Estructura

```text
Terranova/
├── backend/
│   ├── database.py      # Esquema SQLite, conexión y datos de demostración
│   ├── main.py          # API, autenticación, permisos y reglas de negocio
│   ├── schemas.py       # Validación de solicitudes
│   └── security.py      # Hash de contraseñas y sesiones firmadas
├── data/                # La aplicación crea aquí la base SQLite
├── docs/                # Manuales, requisitos y documentación
├── frontend/
│   ├── app.js           # Interfaz y llamadas a la API
│   ├── index.html       # Vistas y estructura accesible
│   └── styles.css       # Diseño adaptable
├── .env.example         # Plantilla de configuración
├── requirements.txt     # Indica que no se requieren paquetes externos
└── iniciar_terranova.bat # Lanzador para Windows
```

## Notas importantes

- SQLite está pensado para un uso local y un número moderado de operaciones. Para despliegues multiusuario con alta concurrencia, migrar a PostgreSQL y desplegar con HTTPS.
- La aplicación inicia ligada a `127.0.0.1`, por lo que solo es accesible desde ese computador. No la publiques en Internet ni expongas el puerto sin una configuración de producción y revisión de seguridad.
- El plano es esquemático. La cuota es una estimación; vencimientos, mora, contratos, intereses legales y contabilidad requieren validación profesional antes de usarse oficialmente.
- La copia JSON contiene clientes, lotes, ventas y pagos. No exporta usuarios, hashes de contraseñas ni registro de auditoría. La restauración reemplaza los datos operativos actuales, pero conserva usuarios y auditoría.
- No subas `.env` ni `data\terranova.sqlite3` a un repositorio público.

## Documentación

- [Requisitos e instalación](./REQUISITOS.md)
- [Código y API](./CODE.md)
- [Base de datos](./DATABASE.md)
