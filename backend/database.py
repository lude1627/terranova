import os
import sqlite3
from contextlib import closing
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATABASE_PATH = Path(os.getenv("TERRANOVA_DB_PATH", str(ROOT / "data" / "terranova.sqlite3")))
if not DATABASE_PATH.is_absolute():
    DATABASE_PATH = ROOT / DATABASE_PATH


def connect() -> sqlite3.Connection:
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DATABASE_PATH, timeout=15)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    db.execute("PRAGMA busy_timeout = 15000")
    return db


def initialize_database() -> None:
    from backend.security import hash_password

    with closing(connect()) as db:
        with db:
            db.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT NOT NULL COLLATE NOCASE UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL CHECK (role IN ('Administrador', 'Operador', 'Consulta')),
                active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS clients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                document TEXT NOT NULL UNIQUE,
                phone TEXT NOT NULL DEFAULT '',
                email TEXT NOT NULL DEFAULT '',
                address TEXT NOT NULL DEFAULT '',
                notes TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS plots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL UNIQUE,
                project TEXT NOT NULL,
                block TEXT NOT NULL DEFAULT '',
                area REAL NOT NULL CHECK (area > 0),
                price INTEGER NOT NULL CHECK (price >= 0),
                status TEXT NOT NULL DEFAULT 'Disponible'
                    CHECK (status IN ('Disponible', 'Reservado', 'Vendido')),
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS sales (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id INTEGER NOT NULL REFERENCES clients(id) ON DELETE RESTRICT,
                plot_id INTEGER NOT NULL UNIQUE REFERENCES plots(id) ON DELETE RESTRICT,
                date TEXT NOT NULL,
                price INTEGER NOT NULL CHECK (price >= 0),
                initial INTEGER NOT NULL DEFAULT 0 CHECK (initial >= 0),
                installments INTEGER NOT NULL CHECK (installments > 0),
                frequency TEXT NOT NULL DEFAULT 'Mensual',
                interest REAL NOT NULL DEFAULT 0 CHECK (interest >= 0),
                notes TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sale_id INTEGER NOT NULL REFERENCES sales(id) ON DELETE RESTRICT,
                date TEXT NOT NULL,
                amount INTEGER NOT NULL CHECK (amount > 0),
                type TEXT NOT NULL DEFAULT 'Abono',
                method TEXT NOT NULL DEFAULT 'Efectivo',
                note TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                action TEXT NOT NULL,
                entity TEXT NOT NULL,
                entity_id INTEGER,
                details TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            CREATE INDEX IF NOT EXISTS idx_payments_sale_id ON payments(sale_id);
            CREATE INDEX IF NOT EXISTS idx_payments_date ON payments(date);
            CREATE INDEX IF NOT EXISTS idx_sales_client_id ON sales(client_id);
            CREATE INDEX IF NOT EXISTS idx_audit_created_at ON audit_logs(created_at);
            """
        )
            if db.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
                initial_password = os.getenv("TERRANOVA_ADMIN_PASSWORD", "Cambiar123!!")
                if len(initial_password) < 12:
                    raise RuntimeError("TERRANOVA_ADMIN_PASSWORD debe tener al menos 12 caracteres.")
                db.execute(
                    "INSERT INTO users (name, email, password_hash, role) VALUES (?, ?, ?, ?)",
                    (
                        "Administrador",
                        os.getenv("TERRANOVA_ADMIN_EMAIL", "admin@terranova.local"),
                        hash_password(initial_password),
                        "Administrador",
                    ),
                )
            if db.execute("SELECT COUNT(*) FROM plots").fetchone()[0] == 0:
                _insert_demo_data(db)


def _insert_demo_data(db: sqlite3.Connection) -> None:
    clients = [
        ("María Fernanda López", "1023456789", "300 555 0198", "maria@example.com", "Cartagena", ""),
        ("Carlos Andrés Pérez", "1098765432", "310 555 0142", "carlos@example.com", "Turbaco", ""),
    ]
    db.executemany(
        "INSERT INTO clients (name, document, phone, email, address, notes) VALUES (?, ?, ?, ?, ?, ?)",
        clients,
    )
    plot_data = [
        ("A-01", "Senderos del Sol", "A", 120, 30_000_000, "Vendido"),
        ("A-02", "Senderos del Sol", "A", 125, 31_500_000, "Disponible"),
        ("A-03", "Senderos del Sol", "A", 120, 30_000_000, "Reservado"),
        ("A-04", "Senderos del Sol", "A", 130, 32_500_000, "Disponible"),
        ("A-05", "Senderos del Sol", "A", 120, 30_000_000, "Vendido"),
        ("B-01", "Senderos del Sol", "B", 140, 35_000_000, "Disponible"),
        ("B-02", "Senderos del Sol", "B", 120, 30_000_000, "Vendido"),
        ("B-03", "Senderos del Sol", "B", 150, 37_500_000, "Disponible"),
        ("B-04", "Senderos del Sol", "B", 125, 31_500_000, "Reservado"),
        ("B-05", "Senderos del Sol", "B", 120, 30_000_000, "Disponible"),
        ("C-01", "Mirador Verde", "C", 160, 40_000_000, "Disponible"),
        ("C-02", "Mirador Verde", "C", 150, 37_500_000, "Vendido"),
        ("C-03", "Mirador Verde", "C", 135, 34_000_000, "Disponible"),
        ("C-04", "Mirador Verde", "C", 140, 35_000_000, "Disponible"),
        ("C-05", "Mirador Verde", "C", 145, 36_500_000, "Disponible"),
    ]
    db.executemany(
        "INSERT INTO plots (code, project, block, area, price, status) VALUES (?, ?, ?, ?, ?, ?)",
        plot_data,
    )
    sales = [
        (1, 1, "2026-10-03", 30_000_000, 6_000_000, 48, "Mensual", 0, "Ejemplo demostrativo"),
        (2, 5, "2026-10-12", 30_000_000, 5_000_000, 50, "Mensual", 0, "Ejemplo demostrativo"),
    ]
    db.executemany(
        """INSERT INTO sales
           (client_id, plot_id, date, price, initial, installments, frequency, interest, notes)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        sales,
    )
    db.executemany(
        "INSERT INTO payments (sale_id, date, amount, type, method, note) VALUES (?, ?, ?, ?, ?, ?)",
        [
            (1, "2026-10-03", 6_000_000, "Cuota inicial", "Transferencia", "Pago inicial"),
            (1, "2026-10-15", 500_000, "Abono", "Efectivo", "Abono de octubre"),
            (2, "2026-10-12", 5_000_000, "Cuota inicial", "Transferencia", "Pago inicial"),
        ],
    )
