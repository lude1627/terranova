import re
from datetime import date


ROLES = ("Administrador", "Operador", "Consulta")
PLOT_STATUSES = ("Disponible", "Reservado", "Vendido")
FREQUENCIES = ("Mensual", "Quincenal", "Semanal")
PAYMENT_TYPES = ("Abono", "Cuota", "Otro", "Cuota inicial")
PAYMENT_METHODS = ("Transferencia", "Efectivo", "Consignación", "Otro")


class InputError(ValueError):
    pass


def _object(data):
    if not isinstance(data, dict):
        raise InputError("El contenido debe ser un objeto JSON.")
    return data


def _text(data, key, *, required=True, maximum=255, minimum=0, default=""):
    value = data.get(key, default)
    if not isinstance(value, str):
        raise InputError(f"El campo {key} debe ser texto.")
    value = value.strip()
    if required and len(value) < max(1, minimum):
        raise InputError(f"El campo {key} es obligatorio.")
    if len(value) < minimum or len(value) > maximum:
        raise InputError(f"El campo {key} debe tener entre {minimum} y {maximum} caracteres.")
    return value


def _integer(data, key, *, minimum=0, maximum=10**14, default=None):
    value = data.get(key, default)
    if isinstance(value, bool):
        raise InputError(f"El campo {key} debe ser numérico.")
    try:
        numeric = int(value)
    except (ValueError, TypeError, OverflowError) as exc:
        raise InputError(f"El campo {key} debe ser un número entero.") from exc
    if str(value).strip() not in (str(numeric), f"{numeric}.0"):
        raise InputError(f"El campo {key} debe ser un número entero.")
    if not minimum <= numeric <= maximum:
        raise InputError(f"El campo {key} debe estar entre {minimum} y {maximum}.")
    return numeric


def _number(data, key, *, minimum=0, maximum=10_000_000, default=None):
    value = data.get(key, default)
    if isinstance(value, bool):
        raise InputError(f"El campo {key} debe ser numérico.")
    try:
        numeric = float(value)
    except (ValueError, TypeError, OverflowError) as exc:
        raise InputError(f"El campo {key} debe ser numérico.") from exc
    if not minimum <= numeric <= maximum:
        raise InputError(f"El campo {key} debe estar entre {minimum} y {maximum}.")
    return numeric


def _choice(data, key, allowed, default=None):
    value = data.get(key, default)
    if value not in allowed:
        raise InputError(f"El valor del campo {key} no es válido.")
    return value


def _date(data, key="date"):
    value = _text(data, key, maximum=10, minimum=10)
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise InputError(f"El campo {key} debe ser una fecha válida (AAAA-MM-DD).") from exc
    return value


def _email(value, *, required=True):
    if not isinstance(value, str):
        raise InputError("El correo electrónico no es válido.")
    value = value.strip()
    if not value and not required:
        return ""
    if len(value) > 254 or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value):
        raise InputError("El correo electrónico no es válido.")
    return value


def validate_login(data):
    data = _object(data)
    email = _email(data.get("email"))
    password = _text(data, "password", maximum=128, minimum=1)
    return {"email": email, "password": password}


def validate_password(data):
    data = _object(data)
    return {
        "current_password": _text(data, "current_password", maximum=128, minimum=1),
        "new_password": _text(data, "new_password", maximum=128, minimum=12),
    }


def validate_client(data):
    data = _object(data)
    return {
        "name": _text(data, "name", maximum=140, minimum=2),
        "document": _text(data, "document", maximum=40, minimum=3),
        "phone": _text(data, "phone", required=False, maximum=40),
        "email": _email(data.get("email", ""), required=False),
        "address": _text(data, "address", required=False, maximum=200),
        "notes": _text(data, "notes", required=False, maximum=1000),
    }


def validate_plot(data):
    data = _object(data)
    return {
        "code": _text(data, "code", maximum=40, minimum=1),
        "project": _text(data, "project", maximum=140, minimum=1),
        "block": _text(data, "block", required=False, maximum=40),
        "area": _number(data, "area", minimum=0.000001, maximum=10_000_000),
        "price": _integer(data, "price"),
        "status": _choice(data, "status", PLOT_STATUSES, "Disponible"),
    }


def validate_sale(data):
    data = _object(data)
    sale = {
        "client_id": _integer(data, "client_id", minimum=1),
        "plot_id": _integer(data, "plot_id", minimum=1),
        "date": _date(data),
        "price": _integer(data, "price"),
        "initial": _integer(data, "initial"),
        "installments": _integer(data, "installments", minimum=1, maximum=600),
        "frequency": _choice(data, "frequency", FREQUENCIES, "Mensual"),
        "interest": _number(data, "interest", maximum=100, default=0),
        "notes": _text(data, "notes", required=False, maximum=1000),
        "initial_method": _choice(data, "initial_method", PAYMENT_METHODS, "Transferencia"),
    }
    if sale["initial"] > sale["price"]:
        raise InputError("La cuota inicial no puede superar el precio de venta.")
    return sale


def validate_payment(data):
    data = _object(data)
    return {
        "sale_id": _integer(data, "sale_id", minimum=1),
        "date": _date(data),
        "amount": _integer(data, "amount", minimum=1),
        "type": _choice(data, "type", PAYMENT_TYPES, "Abono"),
        "method": _choice(data, "method", PAYMENT_METHODS, "Efectivo"),
        "note": _text(data, "note", required=False, maximum=500),
    }


def validate_user(data):
    data = _object(data)
    return {
        "name": _text(data, "name", maximum=140, minimum=2),
        "email": _email(data.get("email")),
        "password": _text(data, "password", maximum=128, minimum=12),
        "role": _choice(data, "role", ROLES),
    }


def validate_backup(data):
    data = _object(data)
    if data.get("version") != 1:
        raise InputError("La versión de la copia no es compatible.")
    clients = [validate_client(item) for item in _list(data, "clients")]
    plots = [validate_plot(item) for item in _list(data, "plots")]
    sales = []
    for item in _list(data, "sales"):
        item = _object(item)
        client_document = _text(item, "client_document", maximum=40, minimum=3)
        plot_code = _text(item, "plot_code", maximum=40, minimum=1)
        sale = validate_sale({
            "client_id": 1,
            "plot_id": 1,
            "date": item.get("date"),
            "price": item.get("price"),
            "initial": item.get("initial"),
            "installments": item.get("installments"),
            "frequency": item.get("frequency"),
            "interest": item.get("interest"),
            "notes": item.get("notes", ""),
        })
        sales.append({
            "client_document": client_document,
            "plot_code": plot_code,
            "date": sale["date"],
            "price": sale["price"],
            "initial": sale["initial"],
            "installments": sale["installments"],
            "frequency": sale["frequency"],
            "interest": sale["interest"],
            "notes": sale["notes"],
        })
    payments = []
    for item in _list(data, "payments"):
        item = _object(item)
        payments.append({
            "plot_code": _text(item, "plot_code", maximum=40, minimum=1),
            "date": _date(item),
            "amount": _integer(item, "amount", minimum=1),
            "type": _choice(item, "type", PAYMENT_TYPES, "Abono"),
            "method": _choice(item, "method", PAYMENT_METHODS, "Efectivo"),
            "note": _text(item, "note", required=False, maximum=500),
        })

    client_documents = [client["document"] for client in clients]
    plot_codes = [plot["code"] for plot in plots]
    sale_plots = [sale["plot_code"] for sale in sales]
    if len(set(client_documents)) != len(client_documents):
        raise InputError("La copia contiene documentos de cliente repetidos.")
    if len(set(plot_codes)) != len(plot_codes):
        raise InputError("La copia contiene códigos de lote repetidos.")
    if any(sale["client_document"] not in client_documents for sale in sales):
        raise InputError("La copia contiene ventas con clientes inexistentes.")
    if any(sale["plot_code"] not in plot_codes for sale in sales):
        raise InputError("La copia contiene ventas con lotes inexistentes.")
    if len(set(sale_plots)) != len(sale_plots):
        raise InputError("La copia asigna más de una venta al mismo lote.")
    statuses = {plot["code"]: plot["status"] for plot in plots}
    if any(statuses[sale["plot_code"]] != "Vendido" for sale in sales):
        raise InputError("Los lotes con venta deben figurar como vendidos.")
    if any(payment["plot_code"] not in sale_plots for payment in payments):
        raise InputError("La copia contiene abonos con ventas inexistentes.")
    prices = {sale["plot_code"]: sale["price"] for sale in sales}
    totals = {code: 0 for code in sale_plots}
    for payment in payments:
        totals[payment["plot_code"]] += payment["amount"]
    if any(amount > prices[code] for code, amount in totals.items()):
        raise InputError("La copia contiene pagos que superan el precio de venta.")

    return {"version": 1, "clients": clients, "plots": plots, "sales": sales, "payments": payments}


def _list(data, key):
    value = data.get(key)
    if not isinstance(value, list):
        raise InputError(f"El campo {key} debe ser una lista.")
    return value
