"""Acceso a datos: traduce entre filas SQLite y las entidades del dominio."""
from datetime import datetime

from .db import registrar
from .modelos import ESTADOS_ACTIVOS, Estacionamiento, Periodo, ReglaError, Reserva

EN_ACTIVOS = ",".join(repr(e) for e in ESTADOS_ACTIVOS)


class Repositorio:
    def __init__(self, con):
        self.con = con

    @staticmethod
    def _reserva(fila) -> Reserva:
        return Reserva(fila["id"], fila["parking_id"], fila["cliente_id"],
                       Periodo.desde_texto(fila["inicio"], fila["fin"]), fila["estado"], fila["monto"])

    @staticmethod
    def _estacionamiento(fila) -> Estacionamiento:
        return Estacionamiento(fila["id"], fila["propietario_id"], fila["tipo"], fila["estado"])

    def existe_cliente(self, cliente_id: int) -> bool:
        return self.con.execute("SELECT 1 FROM clientes WHERE id=?", (cliente_id,)).fetchone() is not None

    def estacionamiento(self, parking_id: int) -> Estacionamiento:
        fila = self.con.execute("SELECT * FROM estacionamientos WHERE id=?", (parking_id,)).fetchone()
        if fila is None:
            raise ReglaError(f"No existe el estacionamiento {parking_id}.")
        return self._estacionamiento(fila)

    def estacionamientos(self, tipo: str, solo_liberados: bool = False) -> list[Estacionamiento]:
        filtro = " AND estado='liberado'" if solo_liberados else ""
        filas = self.con.execute(f"SELECT * FROM estacionamientos WHERE tipo=?{filtro} ORDER BY id", (tipo,))
        return [self._estacionamiento(f) for f in filas]

    def reserva(self, reserva_id: int) -> Reserva:
        fila = self.con.execute("SELECT * FROM reservas WHERE id=?", (reserva_id,)).fetchone()
        if fila is None:
            raise ReglaError(f"No existe la reserva {reserva_id}.")
        return self._reserva(fila)

    def hay_conflicto(self, parking_id: int, periodo: Periodo, excluir_reserva: int | None = None) -> bool:
        inicio, fin = periodo.textos()
        reservas = self.con.execute(
            f"SELECT 1 FROM reservas WHERE parking_id=? AND estado IN ({EN_ACTIVOS})"
            " AND id IS NOT ? AND inicio < ? AND fin > ?",
            (parking_id, excluir_reserva, fin, inicio)).fetchone()
        bloqueos = self.con.execute(
            "SELECT 1 FROM bloqueos WHERE parking_id=? AND inicio < ? AND fin > ?",
            (parking_id, fin, inicio)).fetchone()
        return reservas is not None or bloqueos is not None

    def reservas_en_conflicto(self, parking_id: int, periodo: Periodo, estados: tuple[str, ...]) -> list[Reserva]:
        inicio, fin = periodo.textos()
        marcas = ",".join("?" * len(estados))
        filas = self.con.execute(
            f"SELECT * FROM reservas WHERE parking_id=? AND estado IN ({marcas}) AND inicio < ? AND fin > ?",
            (parking_id, *estados, fin, inicio))
        return [self._reserva(f) for f in filas]

    def reserva_que_cubre(self, parking_id: int, momento: datetime) -> Reserva | None:
        texto = momento.isoformat(timespec="minutes")
        fila = self.con.execute(
            "SELECT * FROM reservas WHERE parking_id=? AND estado IN ('confirmada','en_curso')"
            " AND inicio <= ? AND fin > ?", (parking_id, texto, texto)).fetchone()
        return self._reserva(fila) if fila else None

    def crear_reserva(self, cliente_id: int, periodo: Periodo, monto: int) -> int:
        inicio, fin = periodo.textos()
        cur = self.con.execute(
            "INSERT INTO reservas (parking_id, cliente_id, inicio, fin, estado, monto)"
            " VALUES (NULL, ?, ?, ?, 'pendiente', ?)", (cliente_id, inicio, fin, monto))
        return cur.lastrowid

    def guardar(self, reserva: Reserva) -> None:
        self.con.execute("UPDATE reservas SET parking_id=?, estado=? WHERE id=?",
                         (reserva.parking_id, reserva.estado, reserva.id))

    def acreditar(self, cliente_id: int, monto: int) -> None:
        self.con.execute("UPDATE clientes SET credito = credito + ? WHERE id=?", (monto, cliente_id))

    def agregar_bloqueo(self, parking_id: int, periodo: Periodo, motivo: str) -> None:
        inicio, fin = periodo.textos()
        self.con.execute("INSERT INTO bloqueos (parking_id, inicio, fin, motivo) VALUES (?,?,?,?)",
                         (parking_id, inicio, fin, motivo))

    def quitar_bloqueos_vigentes(self, parking_id: int, desde: datetime) -> None:
        self.con.execute("DELETE FROM bloqueos WHERE parking_id=? AND fin > ?",
                         (parking_id, desde.isoformat(timespec="minutes")))

    def marcar_liberado(self, parking_id: int) -> None:
        self.con.execute("UPDATE estacionamientos SET estado='liberado' WHERE id=?", (parking_id,))

    def registrar(self, evento: str, ahora: datetime, **datos) -> None:
        registrar(self.con, evento, ahora, **datos)

    def confirmar(self) -> None:
        self.con.commit()
