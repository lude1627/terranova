# Base de datos de Terranova

Terranova usa SQLite y crea por defecto el archivo `data/terranova.sqlite3`. La conexión activa claves foráneas y espera hasta 15 segundos cuando hay un bloqueo temporal. La ruta se puede cambiar con `TERRANOVA_DB_PATH`.

El esquema y los datos de demostración se crean en [`backend/database.py`](../backend/database.py). Los importes se almacenan en pesos enteros; el área del lote admite decimales.

## Entidades

### `users`

| Columna | Tipo | Regla | Propósito |
|---|---|---|---|
| `id` | INTEGER | PK autoincremental | Identificador de la cuenta |
| `name` | TEXT | Obligatorio | Nombre mostrado |
| `email` | TEXT | Obligatorio, único sin distinguir mayúsculas | Identificador de inicio de sesión |
| `password_hash` | TEXT | Obligatorio | Hash PBKDF2-SHA256; nunca se almacena la contraseña en claro |
| `role` | TEXT | Administrador, Operador o Consulta | Control de permisos |
| `active` | INTEGER | 0 o 1 | Permite bloquear una cuenta sin borrarla |
| `created_at` | TEXT | Fecha/hora SQLite | Alta de la cuenta |

### `clients`

Almacena nombre, documento único, teléfono, correo, dirección, notas y fecha de creación. Un cliente puede tener varias ventas. La restricción de clave foránea impide borrarlo cuando tiene contratos asociados.

### `plots`

Almacena código único, proyecto, manzana, área, precio, estado y fecha de creación. Los estados permitidos son `Disponible`, `Reservado` y `Vendido`. Un lote puede tener como máximo una venta.

### `sales`

| Columna | Relación o regla |
|---|---|
| `client_id` | Referencia obligatoria a `clients.id` |
| `plot_id` | Referencia única a `plots.id` |
| `date` | Fecha del contrato en formato ISO `AAAA-MM-DD` |
| `price` | Precio acordado, en pesos enteros |
| `initial` | Cuota inicial declarada |
| `installments` | Número positivo de pagos |
| `frequency` | Frecuencia del plan |
| `interest` | Tasa porcentual anual declarada; se usa para la estimación |
| `notes` | Observaciones |

La creación de una venta marca el lote como vendido y, si hay cuota inicial, genera el movimiento de pago inicial dentro de una transacción.

### `payments`

Cada pago referencia obligatoriamente un contrato y guarda fecha, importe positivo, tipo, medio y nota. El backend impide registrar un importe mayor al saldo calculado del contrato. Los registros de pagos asociados no se eliminan en cascada para conservar la integridad.

### `audit_logs`

Registra quién realizó una acción, qué acción fue, la entidad afectada, su identificador opcional y la fecha. Si se elimina una cuenta, su autoría queda en `NULL`, pero no se elimina el evento.

## Relaciones

```text
clients 1 ─── N sales N ─── 1 plots
sales   1 ─── N payments
users   1 ─── N audit_logs
```

Además, se crean índices para acelerar consultas de pagos por contrato o fecha, ventas por cliente y auditoría por fecha.

## Respaldo y restauración

El respaldo descargable es JSON versión `1` e incluye clientes, lotes, ventas y pagos. Las referencias entre tablas se representan con documento del cliente y código de lote, en vez de depender de identificadores internos; por eso sigue funcionando aunque haya huecos en la numeración.

La restauración valida el formato y referencias y reemplaza los datos operativos dentro de una transacción SQLite. Si hay un error de integridad, la transacción se revierte. No reemplaza usuarios ni auditoría. Conserva siempre una copia previa fuera de la carpeta de la base de datos.

## Consideraciones

- El archivo SQLite es una base local: protégelo con los controles de acceso del sistema operativo y respaldos externos.
- No guardes información real en las filas de demostración. Elimina o sustituye esos ejemplos antes de iniciar una operación real.
- Las reglas de fechas, mora, calendario legal, contratos y contabilidad necesitan validación funcional, jurídica y contable antes de producción.
