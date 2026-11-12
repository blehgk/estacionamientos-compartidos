from datetime import datetime, timedelta

from .db import registrar

TARIFA_MIN = 30
DURACION_MIN, DURACION_MAX = 60, 120
ANTICIPACION_MIN = timedelta(minutes=15)
ANTICIPACION_MAX = timedelta(days=7)
ACTIVAS = ("confirmada", "en_curso", "reubicada")
EN_ACTIVAS = ",".join(repr(e) for e in ACTIVAS)


class ReglaError(Exception):
    """Una operacion viola una regla de negocio."""


def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="minutes")


def _dt(texto: str) -> datetime:
    return datetime.fromisoformat(texto)


def _reserva(con, reserva_id: int):
    r = con.execute("SELECT * FROM reservas WHERE id=?", (reserva_id,)).fetchone()
    if r is None:
        raise ReglaError(f"No existe la reserva {reserva_id}.")
    return r


def _parking(con, parking_id: int):
    p = con.execute("SELECT * FROM estacionamientos WHERE id=?", (parking_id,)).fetchone()
    if p is None:
        raise ReglaError(f"No existe el estacionamiento {parking_id}.")
    return p


def _propio(con, parking_id: int, propietario_id: int | None):
    p = _parking(con, parking_id)
    if p["tipo"] == "comodin":
        raise ReglaError("Los comodines no tienen propietario.")
    if propietario_id is not None and p["propietario_id"] != propietario_id:
        raise ReglaError("Ese estacionamiento pertenece a otro propietario.")
    return p


def hay_conflicto(con, parking_id: int, inicio: datetime, fin: datetime,
                  excluir_reserva: int | None = None) -> bool:
    i, f = _iso(inicio), _iso(fin)
    reservas = con.execute(
        f"SELECT 1 FROM reservas WHERE parking_id=? AND estado IN ({EN_ACTIVAS})"
        " AND id IS NOT ? AND inicio < ? AND fin > ?",
        (parking_id, excluir_reserva, f, i),
    ).fetchone()
    bloqueos = con.execute(
        "SELECT 1 FROM bloqueos WHERE parking_id=? AND inicio < ? AND fin > ?",
        (parking_id, f, i),
    ).fetchone()
    return reservas is not None or bloqueos is not None


def estacionamientos_compatibles(con, inicio: datetime, fin: datetime) -> list[int]:
    ids = [r["id"] for r in con.execute(
        "SELECT id FROM estacionamientos WHERE tipo='normal' AND estado='liberado' ORDER BY id")]
    return [p for p in ids if not hay_conflicto(con, p, inicio, fin)]


def reservar(con, cliente_id: int, inicio: datetime, fin: datetime, ahora: datetime) -> int:
    if con.execute("SELECT 1 FROM clientes WHERE id=?", (cliente_id,)).fetchone() is None:
        raise ReglaError(f"No existe el cliente {cliente_id}.")
    if fin <= inicio:
        raise ReglaError("El termino debe ser posterior al inicio.")
    minutos = int((fin - inicio).total_seconds() // 60)
    if not DURACION_MIN <= minutos <= DURACION_MAX:
        raise ReglaError("La reserva debe durar entre 1 y 2 horas.")
    if not ANTICIPACION_MIN <= inicio - ahora <= ANTICIPACION_MAX:
        raise ReglaError("Se reserva con 15 minutos a 7 dias de anticipacion.")
    if not estacionamientos_compatibles(con, inicio, fin):
        raise ReglaError("No hay estacionamientos disponibles para ese periodo.")
    monto = minutos * TARIFA_MIN
    cur = con.execute(
        "INSERT INTO reservas (parking_id, cliente_id, inicio, fin, estado, monto)"
        " VALUES (NULL, ?, ?, ?, 'pendiente', ?)",
        (cliente_id, _iso(inicio), _iso(fin), monto),
    )
    registrar(con, "creada", ahora, reserva_id=cur.lastrowid, cliente_id=cliente_id,
              inicio=_iso(inicio), fin=_iso(fin), estado="pendiente", valor=monto)
    return cur.lastrowid


def reembolso(monto: int, inicio: datetime, ahora: datetime) -> int:
    if ahora <= inicio - timedelta(hours=1):
        return monto
    if ahora < inicio:
        return monto // 2
    return 0


def cancelar(con, reserva_id: int, ahora: datetime) -> int:
    r = _reserva(con, reserva_id)
    if r["estado"] not in ("pendiente", "confirmada", "reubicada"):
        raise ReglaError(f"No se puede cancelar una reserva {r['estado']}.")
    dev = r["monto"] if r["estado"] == "pendiente" else reembolso(r["monto"], _dt(r["inicio"]), ahora)
    con.execute("UPDATE reservas SET estado='cancelada' WHERE id=?", (reserva_id,))
    con.execute("UPDATE clientes SET credito = credito + ? WHERE id=?", (dev, r["cliente_id"]))
    registrar(con, "cancelada", ahora, reserva_id=reserva_id, parking_id=r["parking_id"],
              cliente_id=r["cliente_id"], inicio=r["inicio"], fin=r["fin"],
              estado="cancelada", valor=dev)
    return dev


def liberar(con, parking_id: int, ahora: datetime, propietario_id: int | None = None) -> None:
    """Deja el estacionamiento disponible y quita sus bloqueos que siguen vigentes."""
    _propio(con, parking_id, propietario_id)
    con.execute("DELETE FROM bloqueos WHERE parking_id=? AND fin > ?", (parking_id, _iso(ahora)))
    con.execute("UPDATE estacionamientos SET estado='liberado' WHERE id=?", (parking_id,))
    registrar(con, "liberado", ahora, parking_id=parking_id, estado="liberado")


def _comodin_libre(con, inicio: str, fin: str, excluir: int) -> int | None:
    for c in con.execute("SELECT id FROM estacionamientos WHERE tipo='comodin' ORDER BY id"):
        if not hay_conflicto(con, c["id"], _dt(inicio), _dt(fin), excluir_reserva=excluir):
            return c["id"]
    return None


def bloquear(con, parking_id: int, inicio: datetime, fin: datetime, motivo: str,
             ahora: datetime, propietario_id: int | None = None) -> list[int]:
    _propio(con, parking_id, propietario_id)
    if fin <= inicio:
        raise ReglaError("El termino debe ser posterior al inicio.")
    afectadas = [r for r in con.execute(
        "SELECT * FROM reservas WHERE parking_id=? AND estado IN ('confirmada','en_curso')"
        " AND inicio < ? AND fin > ?", (parking_id, _iso(fin), _iso(inicio)))]
    con.execute("INSERT INTO bloqueos (parking_id, inicio, fin, motivo) VALUES (?,?,?,?)",
                (parking_id, _iso(inicio), _iso(fin), motivo))
    registrar(con, "bloqueado", ahora, parking_id=parking_id, inicio=_iso(inicio),
              fin=_iso(fin), estado="bloqueado", detalle=motivo)
    for r in afectadas:
        comodin = _comodin_libre(con, r["inicio"], r["fin"], r["id"])
        if comodin is not None:
            con.execute("UPDATE reservas SET parking_id=?, estado='reubicada' WHERE id=?",
                        (comodin, r["id"]))
            registrar(con, "reubicada", ahora, reserva_id=r["id"], parking_id=comodin,
                      cliente_id=r["cliente_id"], inicio=r["inicio"], fin=r["fin"],
                      estado="reubicada", detalle=f"desde {parking_id}: {motivo}")
        else:
            con.execute("UPDATE reservas SET estado='cancelada' WHERE id=?", (r["id"],))
            con.execute("UPDATE clientes SET credito = credito + ? WHERE id=?",
                        (r["monto"], r["cliente_id"]))
            registrar(con, "cancelada", ahora, reserva_id=r["id"], parking_id=parking_id,
                      cliente_id=r["cliente_id"], inicio=r["inicio"], fin=r["fin"],
                      estado="cancelada", valor=r["monto"], detalle="sin comodin")
    con.commit()
    return [r["id"] for r in afectadas]


def vuelvo_ahora(con, parking_id: int, ahora: datetime, propietario_id: int | None = None) -> int:
    _propio(con, parking_id, propietario_id)
    r = con.execute(
        "SELECT * FROM reservas WHERE parking_id=? AND estado IN ('confirmada','en_curso')"
        " AND inicio <= ? AND fin > ?", (parking_id, _iso(ahora), _iso(ahora))).fetchone()
    if r is None:
        raise ReglaError("No hay una reserva en curso en ese estacionamiento.")
    fin = _dt(r["fin"])
    bloquear(con, parking_id, ahora, fin, "vuelvo ahora", ahora, propietario_id)
    estado = con.execute("SELECT estado FROM reservas WHERE id=?", (r["id"],)).fetchone()[0]
    if estado == "cancelada":  # sin comodin: bloquear ya devolvio el monto completo
        return r["monto"]
    credito = int((fin - ahora).total_seconds() // 60) * TARIFA_MIN
    con.execute("UPDATE clientes SET credito = credito + ? WHERE id=?", (credito, r["cliente_id"]))
    registrar(con, "vuelvo_ahora", ahora, reserva_id=r["id"], parking_id=parking_id,
              cliente_id=r["cliente_id"], inicio=r["inicio"], fin=r["fin"],
              estado="reubicada", valor=credito)
    return credito


def _parking_apto(con, parking_id: int, inicio: str, fin: str, excluir: int, permitir_comodin: bool):
    p = _parking(con, parking_id)
    if p["estado"] != "liberado":
        raise ReglaError("El estacionamiento no esta liberado.")
    if p["tipo"] == "comodin" and not permitir_comodin:
        raise ReglaError("Los comodines solo se usan como reubicacion.")
    if hay_conflicto(con, parking_id, _dt(inicio), _dt(fin), excluir_reserva=excluir):
        raise ReglaError("El estacionamiento tiene conflicto en ese periodo.")


def asignar(con, reserva_id: int, parking_id: int, ahora: datetime) -> None:
    r = _reserva(con, reserva_id)
    if r["estado"] != "pendiente":
        raise ReglaError(f"Solo se asignan reservas pendientes (esta esta {r['estado']}).")
    _parking_apto(con, parking_id, r["inicio"], r["fin"], reserva_id, permitir_comodin=False)
    con.execute("UPDATE reservas SET parking_id=?, estado='confirmada' WHERE id=?",
                (parking_id, reserva_id))
    registrar(con, "asignada", ahora, reserva_id=reserva_id, parking_id=parking_id,
              cliente_id=r["cliente_id"], inicio=r["inicio"], fin=r["fin"],
              estado="confirmada", valor=r["monto"])


def reasignar(con, reserva_id: int, nuevo_parking_id: int, ahora: datetime) -> None:
    r = _reserva(con, reserva_id)
    if r["estado"] not in ("confirmada", "reubicada"):
        raise ReglaError(f"No se puede reasignar una reserva {r['estado']}.")
    if nuevo_parking_id == r["parking_id"]:
        raise ReglaError("La reserva ya esta en ese estacionamiento.")
    _parking_apto(con, nuevo_parking_id, r["inicio"], r["fin"], reserva_id, permitir_comodin=True)
    con.execute("UPDATE reservas SET parking_id=? WHERE id=?", (nuevo_parking_id, reserva_id))
    registrar(con, "reasignada", ahora, reserva_id=reserva_id, parking_id=nuevo_parking_id,
              cliente_id=r["cliente_id"], inicio=r["inicio"], fin=r["fin"],
              estado=r["estado"], valor=r["monto"], detalle=f"desde {r['parking_id']}")


def registrar_salida(con, reserva_id: int, ahora: datetime) -> int:
    r = _reserva(con, reserva_id)
    if r["estado"] not in ACTIVAS:
        raise ReglaError(f"No se puede cerrar una reserva {r['estado']}.")
    atraso = int((ahora - _dt(r["fin"])).total_seconds() // 60)
    recargo = 60 * (atraso - 5) if atraso > 5 else 0
    con.execute("UPDATE reservas SET estado='cerrada' WHERE id=?", (reserva_id,))
    registrar(con, "cerrada", ahora, reserva_id=reserva_id, parking_id=r["parking_id"],
              cliente_id=r["cliente_id"], inicio=r["inicio"], fin=r["fin"],
              estado="cerrada", valor=recargo,
              detalle=f"atraso {max(atraso, 0)} min")
    return recargo
