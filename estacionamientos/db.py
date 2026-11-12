import sqlite3
from datetime import datetime

ESQUEMA = """
CREATE TABLE IF NOT EXISTS propietarios (
    id INTEGER PRIMARY KEY, nombre TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS clientes (
    id INTEGER PRIMARY KEY, nombre TEXT NOT NULL, credito INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS estacionamientos (
    id INTEGER PRIMARY KEY, propietario_id INTEGER,
    tipo TEXT NOT NULL CHECK (tipo IN ('normal','comodin')),
    estado TEXT NOT NULL CHECK (estado IN ('liberado','bloqueado')));
CREATE TABLE IF NOT EXISTS bloqueos (
    id INTEGER PRIMARY KEY, parking_id INTEGER NOT NULL,
    inicio TEXT NOT NULL, fin TEXT NOT NULL, motivo TEXT);
CREATE TABLE IF NOT EXISTS reservas (
    id INTEGER PRIMARY KEY, parking_id INTEGER, cliente_id INTEGER NOT NULL,
    inicio TEXT NOT NULL, fin TEXT NOT NULL, estado TEXT NOT NULL, monto INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS historial (
    id INTEGER PRIMARY KEY, ts TEXT NOT NULL, evento TEXT NOT NULL,
    reserva_id INTEGER, parking_id INTEGER, propietario_id INTEGER, cliente_id INTEGER,
    inicio TEXT, fin TEXT, estado TEXT, valor INTEGER NOT NULL DEFAULT 0, detalle TEXT);
"""


def conectar(ruta: str = "estacionamientos.db") -> sqlite3.Connection:
    con = sqlite3.connect(ruta)
    con.row_factory = sqlite3.Row
    con.executescript(ESQUEMA)
    return con


def sembrar(con) -> None:
    if con.execute("SELECT COUNT(*) FROM estacionamientos").fetchone()[0]:
        return
    con.executemany(
        "INSERT INTO propietarios (id, nombre) VALUES (?, ?)",
        [(1, "Propietario 1"), (2, "Propietario 2")],
    )
    con.executemany(
        "INSERT INTO clientes (id, nombre) VALUES (?, ?)",
        [(1, "Cliente 1"), (2, "Cliente 2")],
    )
    con.executemany(
        "INSERT INTO estacionamientos (id, propietario_id, tipo, estado) VALUES (?, ?, ?, 'liberado')",
        [(1, 1, "normal"), (2, 2, "normal"), (3, None, "comodin")],
    )
    con.commit()


def registrar(con, evento: str, ahora: datetime, reserva_id=None, parking_id=None,
              cliente_id=None, inicio=None, fin=None, estado=None, valor=0, detalle="") -> None:
    propietario = None
    if parking_id is not None:
        fila = con.execute(
            "SELECT propietario_id FROM estacionamientos WHERE id=?", (parking_id,)
        ).fetchone()
        propietario = fila["propietario_id"] if fila else None
    con.execute(
        "INSERT INTO historial (ts, evento, reserva_id, parking_id, propietario_id, cliente_id,"
        " inicio, fin, estado, valor, detalle) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (ahora.isoformat(timespec="minutes"), evento, reserva_id, parking_id, propietario,
         cliente_id, inicio, fin, estado, valor, detalle),
    )
    con.commit()


def consultar(con) -> dict[str, list[tuple]]:
    """Datos de solo lectura que muestran la terminal y la web."""
    def filas(sql):
        return [tuple(r) for r in con.execute(sql)]
    return {
        "reservas": filas("SELECT id, cliente_id, parking_id, inicio, fin, estado, monto FROM reservas ORDER BY id DESC"),
        "estacionamientos": filas("SELECT id, propietario_id, tipo, estado FROM estacionamientos ORDER BY id"),
        "creditos": filas("SELECT id, credito FROM clientes ORDER BY id"),
        "historial": filas("SELECT ts, evento, reserva_id, parking_id, valor, detalle FROM historial ORDER BY id DESC LIMIT 50"),
    }
