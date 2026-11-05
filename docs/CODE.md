# Código y arquitectura

## Organización

- [`frontend/index.html`](../frontend/index.html): documento en español, navegación, inicio de sesión y diálogo de formularios.
- [`frontend/styles.css`](../frontend/styles.css): estilos propios, componentes reutilizables y adaptación a móvil.
- [`frontend/app.js`](../frontend/app.js): vistas, formularios, llamadas HTTP, exportación y manejo de sesión. Los valores dinámicos se escapan antes de insertarse en HTML.
- [`backend/main.py`](../backend/main.py): servidor HTTP de la biblioteca estándar, API, autenticación, autorización, operaciones, exportaciones, copias y cabeceras HTTP de seguridad.
- [`backend/schemas.py`](../backend/schemas.py): validación de entradas usando únicamente Python estándar.
- [`backend/database.py`](../backend/database.py): conexión SQLite, creación del esquema e inserción de datos de demostración.
- [`backend/security.py`](../backend/security.py): hash PBKDF2-SHA256 y sesiones firmadas con HMAC.
- [`iniciar_terranova.bat`](../iniciar_terranova.bat): lanzador sencillo para Windows.
- [`README.md`](./README.md): presentación y guía de inicio.
- [`REQUISITOS.md`](./REQUISITOS.md): requisitos e instrucciones de instalación.

El servidor HTTP de Python sirve la interfaz y la API desde el mismo origen; no se necesita un servidor JavaScript ni paquetes externos.

## Sesión y permisos

Después de autenticar, la API entrega una cookie de sesión `HttpOnly`, `SameSite=Strict`, firmada mediante HMAC-SHA256, con vencimiento de ocho horas. La contraseña se verifica con PBKDF2-HMAC-SHA256 y sal aleatoria. Las contraseñas nunca se devuelven en respuestas ni se incluyen en las copias JSON.

| Rol | Acceso |
|---|---|
| Administrador | Operaciones, cuentas, configuración, auditoría y restauración |
| Operador | Lectura y mantenimiento de lotes, clientes, ventas y pagos |
| Consulta | Lectura de panel, inventario, clientes, contratos, pagos e informes |

Los permisos se validan en el backend. Ocultar controles de interfaz no sustituye la autorización del servidor.

## Rutas principales

Todas las rutas se sirven desde el host local configurado. No hay un panel OpenAPI/Swagger.

| Método | Ruta | Acceso |
|---|---|---|
| `POST` | `/api/auth/login` | Público |
| `POST` | `/api/auth/logout` | Sesión activa |
| `GET` | `/api/auth/me` | Sesión activa |
| `POST` | `/api/auth/password` | Sesión activa |
| `GET` | `/api/dashboard` | Sesión activa |
| `GET`, `POST`, `PATCH`, `DELETE` | `/api/plots` | Lectura para todos; cambios para Administrador u Operador |
| `GET`, `POST`, `PATCH`, `DELETE` | `/api/clients` | Lectura para todos; cambios para Administrador u Operador |
| `GET`, `POST` | `/api/sales` | Lectura para todos; creación para Administrador u Operador |
| `GET`, `POST`, `DELETE` | `/api/payments` | Lectura para todos; cambios para Administrador u Operador |
| `GET` | `/api/reports/export?report_type=plots\|clients\|sales\|payments` | Sesión activa |
| `GET`, `POST`, `PATCH` | `/api/users` | Administrador |
| `GET` | `/api/audit` | Administrador |
| `GET`, `POST` | `/api/admin/backup`, `/api/admin/restore` | Administrador |

## Reglas relevantes

- Las entradas HTTP se validan con funciones de la biblioteca estándar y se consultan mediante parámetros SQL.
- Un lote vendido no se puede volver a vender; el índice único de `sales.plot_id` refuerza esa condición.
- Los abonos deben ser positivos y no exceder el saldo actual.
- Una eliminación que rompería relaciones se rechaza con un error claro.
- Las operaciones importantes agregan una fila a `audit_logs`.
- La restauración reemplaza los datos operativos en una sola transacción.
- El frontend usa la cookie del mismo origen; no almacena contraseñas o datos de sesión en `localStorage`.

## Cambios y pruebas

Para añadir una función nueva:

1. Añade o ajusta la validación de entrada en `backend/schemas.py`.
2. Implementa la ruta y sus reglas de autorización en `backend/main.py`.
3. Ajusta el esquema solo si hace falta y documenta el cambio en `DATABASE.md`.
4. Conecta la vista correspondiente en `frontend/app.js`; conserva la semántica y los mensajes en español.
5. Inicia el servidor y valida la ruta, los permisos del rol y el flujo de interfaz.

No se deben exponer las rutas de administración públicamente ni cambiar los encabezados de seguridad sin revisar primero el impacto.
