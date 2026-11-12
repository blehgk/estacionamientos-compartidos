"""Acciones, formularios y vistas compartidos por la terminal y la web."""
from datetime import datetime

from .modelos import ReglaError
from .servicios import Sistema

NUMERICAS = {"Monto", "Valor"}


def clp(n) -> str:
    return "$" + f"{int(n):,}".replace(",", ".")


def texto_celda(valor, cabecera: str) -> str:
    if valor is None:
        return "-"
    if cabecera in NUMERICAS:
        return clp(valor)
    texto = str(valor)
    if len(texto) == 16 and texto[10] == "T":
        texto = texto.replace("T", " ")
    return texto


def _id(f, k): return int(f[k].strip())
def _fecha(f, k): return datetime.fromisoformat(f[k].strip())


def _hora(f):
    t = f.get("hora", "").strip()
    return datetime.fromisoformat(t) if t else datetime.now().replace(second=0, microsecond=0)


ACCIONES = {
    "reservar": lambda c, f: f"Reserva {Sistema(c).reservar(_id(f, 'cliente_id'), _fecha(f, 'inicio'), _fecha(f, 'fin'), _hora(f))} creada (pendiente).",
    "cancelar": lambda c, f: f"Reembolso: {clp(Sistema(c).cancelar(_id(f, 'reserva_id'), _hora(f)))}",
    "liberar": lambda c, f: Sistema(c).liberar(_id(f, "parking_id"), _hora(f), _id(f, "propietario_id")) or "Estacionamiento liberado.",
    "bloquear": lambda c, f: f"Reservas afectadas: {Sistema(c).bloquear(_id(f, 'parking_id'), _fecha(f, 'inicio'), _fecha(f, 'fin'), f.get('motivo', '').strip(), _hora(f), _id(f, 'propietario_id'))}",
    "vuelvo_ahora": lambda c, f: f"Credito acreditado al cliente: {clp(Sistema(c).vuelvo_ahora(_id(f, 'parking_id'), _hora(f), _id(f, 'propietario_id')))}",
    "asignar": lambda c, f: Sistema(c).asignar(_id(f, "reserva_id"), _id(f, "parking_id"), _hora(f)) or "Reserva confirmada.",
    "reasignar": lambda c, f: Sistema(c).reasignar(_id(f, "reserva_id"), _id(f, "parking_id"), _hora(f)) or "Reserva reasignada.",
    "salida": lambda c, f: f"Recargo por sobreestadia: {clp(Sistema(c).registrar_salida(_id(f, 'reserva_id'), _hora(f)))}",
}


def ejecutar(con, accion: str, form: dict) -> str:
    if accion not in ACCIONES:
        return "No se pudo: accion desconocida."
    try:
        return str(ACCIONES[accion](con, form))
    except ReglaError as e:
        return f"No se pudo: {e}"
    except KeyError as e:
        return f"No se pudo: falta el campo {e}."
    except (ValueError, TypeError):
        return "No se pudo: revisa los numeros y las fechas (sin zona horaria)."


PROP = ("propietario_id", "Propietario", "number")
# rol -> [(accion, titulo, [(campo, etiqueta, tipo)])]
FORMS = {
    "cliente": [
        ("reservar", "Reservar", [("cliente_id", "Cliente", "number"), ("inicio", "Inicio", "datetime-local"), ("fin", "Termino", "datetime-local")]),
        ("cancelar", "Cancelar reserva", [("reserva_id", "Reserva", "number")]),
    ],
    "propietario": [
        ("liberar", "Liberar", [PROP, ("parking_id", "Estacionamiento", "number")]),
        ("bloquear", "Bloquear", [PROP, ("parking_id", "Estacionamiento", "number"), ("inicio", "Desde", "datetime-local"), ("fin", "Hasta", "datetime-local"), ("motivo", "Motivo", "text")]),
        ("vuelvo_ahora", "Vuelvo ahora", [PROP, ("parking_id", "Estacionamiento", "number")]),
    ],
    "admin": [
        ("asignar", "Asignar", [("reserva_id", "Reserva", "number"), ("parking_id", "Estacionamiento", "number")]),
        ("reasignar", "Reasignar", [("reserva_id", "Reserva", "number"), ("parking_id", "Nuevo estacionamiento", "number")]),
        ("salida", "Registrar salida", [("reserva_id", "Reserva", "number")]),
    ],
}
NOMBRES = {"cliente": "Cliente", "propietario": "Propietario", "admin": "Administrador"}
CONFIRMAR = {"cancelar": "Cancelar esta reserva"}

# (titulo, clave en consultar(), cabeceras)
VISTAS = [
    ("Reservas", "reservas", ["#", "Cliente", "Parking", "Inicio", "Fin", "Estado", "Monto"]),
    ("Estacionamientos", "estacionamientos", ["#", "Propietario", "Tipo", "Estado"]),
    ("Historial (ultimos 50)", "historial", ["Hora", "Evento", "Reserva", "Parking", "Valor", "Detalle"]),
]


def creditos_texto(filas) -> str:
    return " | ".join(f"Cliente {i}: {clp(c)}" for i, c in filas)
