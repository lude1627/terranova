import csv
import io
import json
import mimetypes
import os
import re
import shutil
import sqlite3
import sys
import time
from datetime import date
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlsplit


def load_dotenv() -> None:
    env_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
    example_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env.example")
    if not os.path.isfile(env_file) and os.path.isfile(example_file):
        shutil.copyfile(example_file, env_file)
    if not os.path.isfile(env_file):
        return
    with open(env_file, encoding="utf-8-sig") as file:
        for line in file:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip("\"'")
            if key and key not in os.environ:
                os.environ[key] = value


load_dotenv()

from backend.database import ROOT, connect, initialize_database
from backend.schemas import (
    InputError,
    validate_backup,
    validate_client,
    validate_login,
    validate_password,
    validate_payment,
    validate_plot,
    validate_sale,
    validate_user,
)
from backend.security import (
    SESSION_SECONDS,
    create_session,
    hash_password,
    read_session,
    verify_password,
)


SECRET_KEY = os.getenv("TERRANOVA_SECRET_KEY", "local-development-key-change-before-use")
if os.getenv("TERRANOVA_ENV", "development").lower() == "production":
    if not os.getenv("TERRANOVA_SECRET_KEY"):
        raise RuntimeError("Configura TERRANOVA_SECRET_KEY antes de iniciar en producción.")
    if os.getenv("TERRANOVA_COOKIE_SECURE", "false").lower() != "true":
        raise RuntimeError("En producción debes configurar TERRANOVA_COOKIE_SECURE=true.")
COOKIE_NAME = "terranova_session"
COOKIE_SECURE = os.getenv("TERRANOVA_COOKIE_SECURE", "false").lower() == "true"
MAX_REQUEST_BYTES = 5 * 1024 * 1024
PORT = int(os.getenv("TERRANOVA_PORT", "8000"))


class AuthenticationError(Exception):
    pass


def rows(db: sqlite3.Connection, query: str, params: tuple = ()) -> list[dict]:
    return [dict(row) for row in db.execute(query, params).fetchall()]


def one(db: sqlite3.Connection, query: str, params: tuple = ()) -> dict | None:
    row = db.execute(query, params).fetchone()
    return dict(row) if row else None


def record_audit(
    db: sqlite3.Connection,
    user_id: int | None,
    action: str,
    entity: str,
    entity_id: int | None = None,
    details: str = "",
) -> None:
    db.execute(
        "INSERT INTO audit_logs (user_id, action, entity, entity_id, details) VALUES (?, ?, ?, ?, ?)",
        (user_id, action, entity, entity_id, details[:500]),
    )


def sale_balance(db: sqlite3.Connection, sale_id: int) -> int:
    result = db.execute(
        "SELECT s.price - COALESCE(SUM(p.amount), 0) FROM sales s "
        "LEFT JOIN payments p ON p.sale_id = s.id WHERE s.id = ? GROUP BY s.id",
        (sale_id,),
    ).fetchone()
    return max(0, int(result[0])) if result else 0


def csv_content(records: list[dict], empty_label: str) -> str:
    output = io.StringIO(newline="")
    writer = csv.writer(output, delimiter=";")
    if records:
        writer.writerow(records[0].keys())
        writer.writerows(record.values() for record in records)
    else:
        writer.writerow([empty_label])
    return "\ufeff" + output.getvalue()


def export_backup(db: sqlite3.Connection) -> dict:
    return {
        "version": 1,
        "created_at": date.today().isoformat(),
        "clients": rows(db, "SELECT name, document, phone, email, address, notes FROM clients ORDER BY id"),
        "plots": rows(db, "SELECT code, project, block, area, price, status FROM plots ORDER BY id"),
        "sales": rows(
            db,
            """SELECT c.document AS client_document, p.code AS plot_code, s.date,
                      s.price, s.initial, s.installments, s.frequency, s.interest, s.notes
               FROM sales s JOIN clients c ON c.id=s.client_id
               JOIN plots p ON p.id=s.plot_id ORDER BY s.id""",
        ),
        "payments": rows(
            db,
            """SELECT pl.code AS plot_code, p.date, p.amount, p.type, p.method, p.note
               FROM payments p JOIN sales s ON s.id=p.sale_id
               JOIN plots pl ON pl.id=s.plot_id ORDER BY p.id""",
        ),
    }


def restore_backup(db: sqlite3.Connection, payload: dict, user_id: int) -> None:
    db.execute("BEGIN IMMEDIATE")
    with db:
        db.execute("DELETE FROM payments")
        db.execute("DELETE FROM sales")
        db.execute("DELETE FROM plots")
        db.execute("DELETE FROM clients")
        db.executemany(
            """INSERT INTO clients (name, document, phone, email, address, notes)
               VALUES (:name, :document, :phone, :email, :address, :notes)""",
            payload["clients"],
        )
        db.executemany(
            """INSERT INTO plots (code, project, block, area, price, status)
               VALUES (:code, :project, :block, :area, :price, :status)""",
            payload["plots"],
        )
        client_ids = {
            row["document"]: row["id"] for row in db.execute("SELECT id, document FROM clients")
        }
        plot_ids = {row["code"]: row["id"] for row in db.execute("SELECT id, code FROM plots")}
        for sale in payload["sales"]:
            db.execute(
                """INSERT INTO sales
                   (client_id, plot_id, date, price, initial, installments, frequency, interest, notes)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    client_ids[sale["client_document"]],
                    plot_ids[sale["plot_code"]],
                    sale["date"],
                    sale["price"],
                    sale["initial"],
                    sale["installments"],
                    sale["frequency"],
                    sale["interest"],
                    sale["notes"],
                ),
            )
        sale_ids = {
            row["code"]: row["id"]
            for row in db.execute("SELECT p.code, s.id FROM sales s JOIN plots p ON p.id=s.plot_id")
        }
        for payment in payload["payments"]:
            db.execute(
                """INSERT INTO payments (sale_id, date, amount, type, method, note)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    sale_ids[payment["plot_code"]],
                    payment["date"],
                    payment["amount"],
                    payment["type"],
                    payment["method"],
                    payment["note"],
                ),
            )
        record_audit(db, user_id, "restaurar_copia", "base_de_datos")


class TerranovaHandler(BaseHTTPRequestHandler):
    server_version = "TerranovaLocal/1.0"

    def log_message(self, format_string, *args):
        sys.stderr.write(f"{self.address_string()} - {format_string % args}\n")

    def do_GET(self):
        self.handle_request()

    def do_POST(self):
        self.handle_request()

    def do_PATCH(self):
        self.handle_request()

    def do_DELETE(self):
        self.handle_request()

    def handle_request(self):
        parsed = urlsplit(self.path)
        path = unquote(parsed.path)
        if path == "/api/health":
            self.send_json(200, {"status": "ok"})
            return
        if not path.startswith("/api/"):
            self.serve_static(path)
            return

        db = connect()
        try:
            result = self.dispatch(db, path, parse_qs(parsed.query))
            db.commit()
        except InputError as exc:
            db.rollback()
            self.send_json(422, {"detail": str(exc)})
            return
        except AuthenticationError as exc:
            db.rollback()
            self.send_json(401, {"detail": str(exc)})
            return
        except PermissionError as exc:
            db.rollback()
            self.send_json(403, {"detail": str(exc)})
            return
        except LookupError as exc:
            db.rollback()
            self.send_json(404, {"detail": str(exc)})
            return
        except FileNotFoundError as exc:
            db.rollback()
            self.send_json(404, {"detail": str(exc)})
            return
        except sqlite3.IntegrityError as exc:
            db.rollback()
            self.send_json(409, {"detail": self.integrity_message(str(exc))})
            return
        except json.JSONDecodeError:
            db.rollback()
            self.send_json(400, {"detail": "El cuerpo de la solicitud no contiene JSON válido."})
            return
        except Exception:
            db.rollback()
            self.send_json(500, {"detail": "Error interno del servidor local."})
            raise
        finally:
            db.close()

        if result is None:
            self.send_response(204)
            self.add_security_headers()
            cookie = getattr(self, "pending_cookie", None)
            if cookie:
                self.send_header("Set-Cookie", cookie)
                del self.pending_cookie
            self.end_headers()
        elif isinstance(result, tuple) and len(result) == 3 and result[0] == "csv":
            self.send_bytes(200, result[1].encode("utf-8"), "text/csv; charset=utf-8", {
                "Content-Disposition": f'attachment; filename="{result[2]}"'
            })
        else:
            code, payload = result if isinstance(result, tuple) and len(result) == 2 else (200, result)
            self.send_json(code, payload)

    def read_body(self):
        length = int(self.headers.get("Content-Length", "0"))
        if length < 0 or length > MAX_REQUEST_BYTES:
            raise InputError("El cuerpo de la solicitud excede el tamaño permitido.")
        if not length:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except UnicodeDecodeError as exc:
            raise InputError("El contenido debe estar codificado como UTF-8.") from exc

    def session_user(self, db: sqlite3.Connection, roles: tuple[str, ...] | None = None) -> dict:
        cookie = SimpleCookie()
        cookie.load(self.headers.get("Cookie", ""))
        morsel = cookie.get(COOKIE_NAME)
        user_id = read_session(morsel.value if morsel else None, SECRET_KEY)
        if user_id is None:
            raise AuthenticationError("Inicia sesión para continuar.")
        user = one(
            db,
            "SELECT id, name, email, role, active FROM users WHERE id=?",
            (user_id,),
        )
        if user is None or not user["active"]:
            raise AuthenticationError("La sesión ya no es válida.")
        if roles and user["role"] not in roles:
            raise PermissionError("No tienes permiso para realizar esta acción.")
        return user

    def dispatch(self, db: sqlite3.Connection, path: str, query: dict):
        method = self.command
        if path == "/api/auth/login" and method == "POST":
            payload = validate_login(self.read_body())
            user = db.execute(
                """SELECT id, name, email, role, active, password_hash
                   FROM users WHERE email=? COLLATE NOCASE""",
                (payload["email"],),
            ).fetchone()
            if user is None or not user["active"] or not verify_password(
                payload["password"], user["password_hash"]
            ):
                raise AuthenticationError("Correo o contraseña incorrectos.")
            token = create_session(user["id"], SECRET_KEY)
            self.pending_cookie = (
                f"{COOKIE_NAME}={token}; Max-Age={SESSION_SECONDS}; Path=/; HttpOnly; SameSite=Strict"
                + ("; Secure" if COOKIE_SECURE else "")
            )
            record_audit(db, user["id"], "inicio_sesion", "sesion")
            return {"id": user["id"], "name": user["name"], "email": user["email"], "role": user["role"]}

        if path == "/api/auth/me" and method == "GET":
            return self.session_user(db)
        if path == "/api/auth/logout" and method == "POST":
            user = self.session_user(db)
            record_audit(db, user["id"], "cierre_sesion", "sesion")
            self.pending_cookie = (
                f"{COOKIE_NAME}=; Max-Age=0; Path=/; HttpOnly; SameSite=Strict"
                + ("; Secure" if COOKIE_SECURE else "")
            )
            return None
        if path == "/api/auth/password" and method == "POST":
            user = self.session_user(db)
            payload = validate_password(self.read_body())
            row = db.execute("SELECT password_hash FROM users WHERE id=?", (user["id"],)).fetchone()
            if row is None or not verify_password(payload["current_password"], row["password_hash"]):
                raise InputError("La contraseña actual no es correcta.")
            db.execute(
                "UPDATE users SET password_hash=? WHERE id=?",
                (hash_password(payload["new_password"]), user["id"]),
            )
            record_audit(db, user["id"], "cambio_contrasena", "usuario", user["id"])
            return None

        if path == "/api/dashboard" and method == "GET":
            self.session_user(db)
            counts = {
                row["status"]: row["count"]
                for row in db.execute("SELECT status, COUNT(*) AS count FROM plots GROUP BY status")
            }
            revenue = db.execute("SELECT COALESCE(SUM(amount),0) FROM payments").fetchone()[0]
            balance = db.execute(
                """SELECT COALESCE(SUM(MAX(s.price - COALESCE(p.total,0),0)),0)
                   FROM sales s LEFT JOIN (
                     SELECT sale_id,SUM(amount) AS total FROM payments GROUP BY sale_id
                   ) p ON p.sale_id=s.id"""
            ).fetchone()[0]
            inventory = db.execute(
                "SELECT COALESCE(SUM(price),0) FROM plots WHERE status='Disponible'"
            ).fetchone()[0]
            recent = rows(
                db,
                """SELECT p.id,p.date,p.amount,p.type,p.method,p.note,c.name AS client_name,
                          pl.code AS plot_code
                   FROM payments p JOIN sales s ON s.id=p.sale_id
                   JOIN clients c ON c.id=s.client_id JOIN plots pl ON pl.id=s.plot_id
                   ORDER BY p.date DESC,p.id DESC LIMIT 8""",
            )
            return {
                "plots": {key: counts.get(key, 0) for key in ("Disponible", "Reservado", "Vendido")},
                "total_plots": db.execute("SELECT COUNT(*) FROM plots").fetchone()[0],
                "revenue": revenue,
                "balance": balance,
                "inventory_value": inventory,
                "recent_payments": recent,
            }

        if path == "/api/plots" and method == "GET":
            self.session_user(db)
            return rows(db, "SELECT * FROM plots ORDER BY project,block,code")
        if path == "/api/plots" and method == "POST":
            user = self.session_user(db, ("Administrador", "Operador"))
            payload = validate_plot(self.read_body())
            cursor = db.execute(
                """INSERT INTO plots (code,project,block,area,price,status)
                   VALUES (:code,:project,:block,:area,:price,:status)""",
                payload,
            )
            record_audit(db, user["id"], "crear", "lote", cursor.lastrowid)
            return 201, one(db, "SELECT * FROM plots WHERE id=?", (cursor.lastrowid,))
        match = re.fullmatch(r"/api/plots/(\d+)", path)
        if match and method == "PATCH":
            user = self.session_user(db, ("Administrador", "Operador"))
            plot_id = int(match.group(1))
            db.execute("BEGIN IMMEDIATE")
            if not db.execute("SELECT 1 FROM plots WHERE id=?", (plot_id,)).fetchone():
                raise LookupError("No se encontró el lote.")
            payload = validate_plot(self.read_body())
            if payload["status"] != "Vendido" and db.execute(
                "SELECT 1 FROM sales WHERE plot_id=?", (plot_id,)
            ).fetchone():
                raise InputError("Un lote con contrato no puede volver a estado disponible o reservado.")
            db.execute(
                """UPDATE plots SET code=:code,project=:project,block=:block,area=:area,
                   price=:price,status=:status WHERE id=:id""",
                {**payload, "id": plot_id},
            )
            record_audit(db, user["id"], "actualizar", "lote", plot_id)
            return one(db, "SELECT * FROM plots WHERE id=?", (plot_id,))
        if match and method == "DELETE":
            user = self.session_user(db, ("Administrador", "Operador"))
            plot_id = int(match.group(1))
            cursor = db.execute("DELETE FROM plots WHERE id=?", (plot_id,))
            if not cursor.rowcount:
                raise LookupError("No se encontró el lote.")
            record_audit(db, user["id"], "eliminar", "lote", plot_id)
            return None

        if path == "/api/clients" and method == "GET":
            self.session_user(db)
            return rows(db, "SELECT * FROM clients ORDER BY name")
        if path == "/api/clients" and method == "POST":
            user = self.session_user(db, ("Administrador", "Operador"))
            payload = validate_client(self.read_body())
            cursor = db.execute(
                """INSERT INTO clients (name,document,phone,email,address,notes)
                   VALUES (:name,:document,:phone,:email,:address,:notes)""",
                payload,
            )
            record_audit(db, user["id"], "crear", "cliente", cursor.lastrowid)
            return 201, one(db, "SELECT * FROM clients WHERE id=?", (cursor.lastrowid,))
        match = re.fullmatch(r"/api/clients/(\d+)", path)
        if match and method == "PATCH":
            user = self.session_user(db, ("Administrador", "Operador"))
            client_id = int(match.group(1))
            if not db.execute("SELECT 1 FROM clients WHERE id=?", (client_id,)).fetchone():
                raise LookupError("No se encontró el cliente.")
            payload = validate_client(self.read_body())
            db.execute(
                """UPDATE clients SET name=:name,document=:document,phone=:phone,email=:email,
                   address=:address,notes=:notes WHERE id=:id""",
                {**payload, "id": client_id},
            )
            record_audit(db, user["id"], "actualizar", "cliente", client_id)
            return one(db, "SELECT * FROM clients WHERE id=?", (client_id,))
        if match and method == "DELETE":
            user = self.session_user(db, ("Administrador", "Operador"))
            client_id = int(match.group(1))
            cursor = db.execute("DELETE FROM clients WHERE id=?", (client_id,))
            if not cursor.rowcount:
                raise LookupError("No se encontró el cliente.")
            record_audit(db, user["id"], "eliminar", "cliente", client_id)
            return None

        if path == "/api/sales" and method == "GET":
            self.session_user(db)
            sales = rows(
                db,
                """SELECT s.*,c.name AS client_name,c.document AS client_document,
                          p.code AS plot_code,p.project AS project,
                          COALESCE(SUM(pay.amount),0) AS paid
                   FROM sales s JOIN clients c ON c.id=s.client_id JOIN plots p ON p.id=s.plot_id
                   LEFT JOIN payments pay ON pay.sale_id=s.id
                   GROUP BY s.id ORDER BY s.date DESC,s.id DESC""",
            )
            for sale in sales:
                sale["balance"] = max(0, sale["price"] - sale["paid"])
                base = max(0, sale["price"] - sale["initial"])
                periods = max(1, sale["installments"])
                per_year = {"Mensual": 12, "Quincenal": 24, "Semanal": 52}.get(sale["frequency"], 12)
                rate = sale["interest"] / 100 / per_year
                sale["estimated_installment"] = (
                    base * rate / (1 - (1 + rate) ** -periods) if rate else base / periods
                )
            return sales
        if path == "/api/sales" and method == "POST":
            user = self.session_user(db, ("Administrador", "Operador"))
            payload = validate_sale(self.read_body())
            db.execute("BEGIN IMMEDIATE")
            plot = db.execute("SELECT status FROM plots WHERE id=?", (payload["plot_id"],)).fetchone()
            if plot is None:
                raise LookupError("No se encontró el lote.")
            if plot["status"] == "Vendido" or db.execute(
                "SELECT 1 FROM sales WHERE plot_id=?", (payload["plot_id"],)
            ).fetchone():
                raise InputError("El lote ya tiene una venta registrada.")
            if db.execute("SELECT 1 FROM clients WHERE id=?", (payload["client_id"],)).fetchone() is None:
                raise LookupError("No se encontró el cliente.")
            with db:
                cursor = db.execute(
                    """INSERT INTO sales (client_id,plot_id,date,price,initial,installments,
                       frequency,interest,notes) VALUES (?,?,?,?,?,?,?,?,?)""",
                    (
                        payload["client_id"], payload["plot_id"], payload["date"], payload["price"],
                        payload["initial"], payload["installments"], payload["frequency"],
                        payload["interest"], payload["notes"],
                    ),
                )
                sale_id = cursor.lastrowid
                db.execute("UPDATE plots SET status='Vendido' WHERE id=?", (payload["plot_id"],))
                if payload["initial"]:
                    db.execute(
                        """INSERT INTO payments (sale_id,date,amount,type,method,note)
                           VALUES (?, ?, ?, 'Cuota inicial', ?, 'Pago inicial')""",
                        (sale_id, payload["date"], payload["initial"], payload["initial_method"]),
                    )
                record_audit(db, user["id"], "crear", "venta", sale_id)
            return 201, one(db, "SELECT * FROM sales WHERE id=?", (sale_id,))

        if path == "/api/payments" and method == "GET":
            self.session_user(db)
            return rows(
                db,
                """SELECT p.*,c.name AS client_name,pl.code AS plot_code
                   FROM payments p JOIN sales s ON s.id=p.sale_id
                   JOIN clients c ON c.id=s.client_id JOIN plots pl ON pl.id=s.plot_id
                   ORDER BY p.date DESC,p.id DESC""",
            )
        if path == "/api/payments" and method == "POST":
            user = self.session_user(db, ("Administrador", "Operador"))
            payload = validate_payment(self.read_body())
            db.execute("BEGIN IMMEDIATE")
            if not db.execute("SELECT 1 FROM sales WHERE id=?", (payload["sale_id"],)).fetchone():
                raise LookupError("No se encontró el contrato.")
            balance = sale_balance(db, payload["sale_id"])
            if balance == 0:
                raise InputError("Este contrato ya está saldado.")
            if payload["amount"] > balance:
                raise InputError("El abono no puede superar el saldo pendiente.")
            cursor = db.execute(
                """INSERT INTO payments (sale_id,date,amount,type,method,note)
                   VALUES (:sale_id,:date,:amount,:type,:method,:note)""",
                payload,
            )
            record_audit(db, user["id"], "crear", "abono", cursor.lastrowid)
            return 201, one(db, "SELECT * FROM payments WHERE id=?", (cursor.lastrowid,))
        match = re.fullmatch(r"/api/payments/(\d+)", path)
        if match and method == "DELETE":
            user = self.session_user(db, ("Administrador", "Operador"))
            payment_id = int(match.group(1))
            cursor = db.execute("DELETE FROM payments WHERE id=?", (payment_id,))
            if not cursor.rowcount:
                raise LookupError("No se encontró el pago.")
            record_audit(db, user["id"], "eliminar", "abono", payment_id)
            return None

        if path == "/api/reports/export" and method == "GET":
            self.session_user(db)
            report_type = query.get("report_type", [""])[0]
            reports = {
                "plots": ("Lotes", """SELECT code AS Codigo,project AS Proyecto,block AS Manzana,
                          area AS Area_m2,price AS Precio,status AS Estado FROM plots ORDER BY project,code"""),
                "clients": ("Clientes", """SELECT name AS Nombre,document AS Documento,phone AS Telefono,
                            email AS Correo,address AS Direccion FROM clients ORDER BY name"""),
                "sales": ("Ventas", """SELECT s.id AS Contrato,c.name AS Cliente,p.code AS Lote,
                          s.date AS Fecha,s.price AS Precio,s.initial AS Cuota_inicial,
                          s.installments AS Cuotas,s.frequency AS Frecuencia,s.interest AS Interes,
                          COALESCE(SUM(pay.amount),0) AS Abonado,
                          MAX(s.price-COALESCE(SUM(pay.amount),0),0) AS Saldo
                          FROM sales s JOIN clients c ON c.id=s.client_id
                          JOIN plots p ON p.id=s.plot_id LEFT JOIN payments pay ON pay.sale_id=s.id
                          GROUP BY s.id ORDER BY s.date DESC"""),
                "payments": ("Abonos", """SELECT p.date AS Fecha,c.name AS Cliente,pl.code AS Lote,
                             p.type AS Tipo,p.method AS Medio,p.amount AS Valor,p.note AS Nota
                             FROM payments p JOIN sales s ON s.id=p.sale_id
                             JOIN clients c ON c.id=s.client_id JOIN plots pl ON pl.id=s.plot_id
                             ORDER BY p.date DESC"""),
            }
            if report_type not in reports:
                raise InputError("Tipo de informe no válido.")
            label, statement = reports[report_type]
            filename = f"terranova-{report_type}.csv"
            return "csv", csv_content(rows(db, statement), label), filename

        if path == "/api/users" and method == "GET":
            self.session_user(db, ("Administrador",))
            return rows(db, "SELECT id,name,email,role,active,created_at FROM users ORDER BY name")
        if path == "/api/users" and method == "POST":
            user = self.session_user(db, ("Administrador",))
            payload = validate_user(self.read_body())
            cursor = db.execute(
                "INSERT INTO users (name,email,password_hash,role) VALUES (?,?,?,?)",
                (payload["name"], payload["email"], hash_password(payload["password"]), payload["role"]),
            )
            record_audit(db, user["id"], "crear", "usuario", cursor.lastrowid)
            return 201, one(db, "SELECT id,name,email,role,active FROM users WHERE id=?", (cursor.lastrowid,))
        match = re.fullmatch(r"/api/users/(\d+)/status", path)
        if match and method == "PATCH":
            user = self.session_user(db, ("Administrador",))
            user_id = int(match.group(1))
            payload = self.read_body()
            if not isinstance(payload, dict) or not isinstance(payload.get("active"), bool):
                raise InputError("El estado activo debe ser verdadero o falso.")
            if user_id == user["id"] and not payload["active"]:
                raise InputError("No puedes desactivar tu propio usuario.")
            cursor = db.execute("UPDATE users SET active=? WHERE id=?", (int(payload["active"]), user_id))
            if not cursor.rowcount:
                raise LookupError("No se encontró el usuario.")
            record_audit(db, user["id"], "actualizar_estado", "usuario", user_id)
            return one(db, "SELECT id,name,email,role,active FROM users WHERE id=?", (user_id,))

        if path == "/api/audit" and method == "GET":
            self.session_user(db, ("Administrador",))
            try:
                limit = int(query.get("limit", ["100"])[0])
            except ValueError as exc:
                raise InputError("El límite debe ser un número entero.") from exc
            if not 1 <= limit <= 500:
                raise InputError("El límite debe estar entre 1 y 500.")
            return rows(
                db,
                """SELECT a.id,u.name AS user_name,a.action,a.entity,a.entity_id,a.details,a.created_at
                   FROM audit_logs a LEFT JOIN users u ON u.id=a.user_id
                   ORDER BY a.id DESC LIMIT ?""",
                (limit,),
            )

        if path == "/api/admin/backup" and method == "GET":
            self.session_user(db, ("Administrador",))
            return export_backup(db)
        if path == "/api/admin/restore" and method == "POST":
            user = self.session_user(db, ("Administrador",))
            payload = validate_backup(self.read_body())
            restore_backup(db, payload, user["id"])
            return None

        if path.startswith("/api/") and not path.startswith((
            "/api/auth/", "/api/plots", "/api/clients", "/api/sales", "/api/payments",
            "/api/reports/", "/api/users", "/api/audit", "/api/admin/"
        )):
            raise LookupError("No se encontró la ruta solicitada.")
        raise InputError("Método no permitido para esta ruta.")

    def serve_static(self, path: str):
        relative = "index.html" if path in ("", "/") else path.lstrip("/")
        target = (ROOT / "frontend" / relative).resolve()
        frontend = (ROOT / "frontend").resolve()
        if not target.is_relative_to(frontend) or not target.is_file():
            self.send_json(404, {"detail": "No se encontró el recurso solicitado."})
            return
        content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        if content_type in ("text/html", "text/css", "application/javascript"):
            content_type += "; charset=utf-8"
        self.send_bytes(200, target.read_bytes(), content_type)

    def send_json(self, status_code: int, payload: dict | list):
        self.send_bytes(
            status_code,
            json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            "application/json; charset=utf-8",
        )

    def send_bytes(self, status_code: int, body: bytes, content_type: str, extra_headers=None):
        self.send_response(status_code)
        self.add_security_headers()
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for key, value in (extra_headers or {}).items():
            self.send_header(key, value)
        cookie = getattr(self, "pending_cookie", None)
        if cookie:
            self.send_header("Set-Cookie", cookie)
            del self.pending_cookie
        self.end_headers()
        self.wfile.write(body)

    def add_security_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "same-origin")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; style-src 'self'; script-src 'self'; "
            "img-src 'self' data:; connect-src 'self'; object-src 'none'; "
            "base-uri 'self'; frame-ancestors 'none'",
        )

    @staticmethod
    def integrity_message(message: str) -> str:
        if "UNIQUE constraint failed" in message:
            return "Ya existe un registro con esos datos únicos."
        if "FOREIGN KEY constraint failed" in message:
            return "No se puede eliminar un registro que tiene operaciones asociadas."
        if "CHECK constraint failed" in message or "NOT NULL constraint failed" in message:
            return "Los datos no cumplen las reglas de la base de datos."
        return "La operación entra en conflicto con los datos existentes."


def main():
    load_dotenv()
    initialize_database()
    host = os.getenv("TERRANOVA_HOST", "127.0.0.1")
    server = ThreadingHTTPServer((host, PORT), TerranovaHandler)
    server.daemon_threads = True
    print(f"Terranova está disponible en http://{host}:{PORT}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nCerrando Terranova...", flush=True)
    finally:
        server.server_close()


if __name__ == "__main__":
    load_dotenv()
    main()
