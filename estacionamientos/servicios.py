"""Reglas de negocio: las 6 funcionalidades del sistema, expresadas sobre las entidades del dominio."""
from datetime import datetime, timedelta

from .modelos import TARIFA_MIN, Estacionamiento, Periodo, ReglaError, Reserva
from .repositorio import Repositorio

DURACION_MIN, DURACION_MAX = 60, 120
ANTICIPACION_MIN = timedelta(minutes=15)
ANTICIPACION_MAX = timedelta(days=7)

__all__ = ["Sistema", "ReglaError"]


class Sistema:
    """Operaciones del propietario, el cliente y el administrador sobre una base de datos."""

    def __init__(self, con, autoconfirmar: bool = True):
        self.repo = Repositorio(con, autoconfirmar)

    # consultas de disponibilidad

    def hay_conflicto(self, parking_id: int, inicio: datetime, fin: datetime,
                      excluir_reserva: int | None = None) -> bool:
        return self.repo.hay_conflicto(parking_id, Periodo(inicio, fin), excluir_reserva)

    def estacionamientos_compatibles(self, inicio: datetime, fin: datetime) -> list[int]:
        return self._compatibles(Periodo(inicio, fin))

    def _compatibles(self, periodo: Periodo) -> list[int]:
        return [e.id for e in self.repo.estacionamientos("normal", solo_liberados=True)
                if not self.repo.hay_conflicto(e.id, periodo)]

    def _propio(self, parking_id: int, propietario_id: int | None) -> Estacionamiento:
        e = self.repo.estacionamiento(parking_id)
        if e.es_comodin:
            raise ReglaError("Los comodines no tienen propietario.")
        if propietario_id is not None and e.propietario_id != propietario_id:
            raise ReglaError("Ese estacionamiento pertenece a otro propietario.")
        return e

    def _apto(self, parking_id: int, reserva: Reserva, permitir_comodin: bool) -> None:
        e = self.repo.estacionamiento(parking_id)
        if not e.esta_liberado:
            raise ReglaError("El estacionamiento no esta liberado.")
        if e.es_comodin and not permitir_comodin:
            raise ReglaError("Los comodines solo se usan como reubicacion.")
        if self.repo.hay_conflicto(parking_id, reserva.periodo, excluir_reserva=reserva.id):
            raise ReglaError("El estacionamiento tiene conflicto en ese periodo.")

    def _comodin_libre(self, reserva: Reserva) -> int | None:
        for c in self.repo.estacionamientos("comodin"):
            if not self.repo.hay_conflicto(c.id, reserva.periodo, excluir_reserva=reserva.id):
                return c.id
        return None

    def _registrar(self, evento: str, ahora: datetime, reserva: Reserva, **datos) -> None:
        inicio, fin = reserva.periodo.textos()
        datos.setdefault("parking_id", reserva.parking_id)
        datos.setdefault("estado", reserva.estado)
        self.repo.registrar(evento, ahora, reserva_id=reserva.id, cliente_id=reserva.cliente_id,
                            inicio=inicio, fin=fin, **datos)

    def _validar_secuencia(self, reserva: Reserva, ahora: datetime) -> None:
        ultimo = self.repo.ultimo_movimiento(reserva.id)
        if ultimo and ahora < datetime.fromisoformat(ultimo).replace(tzinfo=None):
            raise ReglaError("La hora es anterior al ultimo movimiento de la reserva.")

    def _validar_asignacion(self, reserva: Reserva, plaza: int, ahora: datetime) -> None:
        self._validar_secuencia(reserva, ahora)
        if ahora >= reserva.periodo.fin:
            raise ReglaError("La reserva ya vencio.")

        if ahora >= reserva.periodo.inicio and self.repo.ocupacion_sin_cierre(
            plaza, reserva.id, reserva.periodo.inicio.isoformat(timespec="minutes")
        ):
            raise ReglaError("La plaza tiene una reserva anterior sin salida registrada.")

    def _credito_pendiente(self, reserva: Reserva, monto: int) -> int:
        return max(0, monto - self.repo.credito_por_reubicacion(reserva.id))

    # cliente

    def reservar(self, cliente_id: int, inicio: datetime, fin: datetime, ahora: datetime) -> int:
        if not self.repo.existe_cliente(cliente_id):
            raise ReglaError(f"No existe el cliente {cliente_id}.")
        if fin <= inicio:
            raise ReglaError("El termino debe ser posterior al inicio.")
        periodo = Periodo(inicio, fin)
        if not DURACION_MIN <= periodo.minutos <= DURACION_MAX:
            raise ReglaError("La reserva debe durar entre 1 y 2 horas.")
        if not ANTICIPACION_MIN <= inicio - ahora <= ANTICIPACION_MAX:
            raise ReglaError("Se reserva con 15 minutos a 7 dias de anticipacion.")
        if not self._compatibles(periodo):
            raise ReglaError("No hay estacionamientos disponibles para ese periodo.")
        monto = periodo.minutos * TARIFA_MIN
        reserva_id = self.repo.crear_reserva(cliente_id, periodo, monto)
        self._registrar("creada", ahora, Reserva(reserva_id, None, cliente_id, periodo, "pendiente", monto),
                        valor=monto)
        return reserva_id

    def calcular_cancelacion(self, reserva: Reserva, ahora: datetime) -> int:
        if reserva.estado not in ("pendiente", "confirmada", "reubicada"):
            raise ReglaError(f"No se puede cancelar una reserva {reserva.estado}.")
        self._validar_secuencia(reserva, ahora)
        return self._credito_pendiente(reserva, reserva.reembolso(ahora))

    def cancelar(self, reserva_id: int, ahora: datetime, detalle: str = "") -> int:
        r = self.repo.reserva(reserva_id)
        devuelto = self.calcular_cancelacion(r, ahora)
        r.estado = "cancelada"
        self.repo.guardar(r)
        self.repo.acreditar(r.cliente_id, devuelto)
        self._registrar("cancelada", ahora, r, valor=devuelto, detalle=detalle)
        return devuelto

    # propietario

    def liberar(self, parking_id: int, ahora: datetime, propietario_id: int | None = None) -> None:
        """Deja el estacionamiento disponible y quita sus bloqueos que siguen vigentes."""
        self._propio(parking_id, propietario_id)
        self.repo.quitar_bloqueos_vigentes(parking_id, ahora)
        self.repo.marcar_liberado(parking_id)
        self.repo.registrar("liberado", ahora, parking_id=parking_id, estado="liberado")

    def publicar(self, parking_id: int, propietario_id: int, ahora: datetime) -> None:
        self._propio(parking_id, propietario_id)
        self.repo.marcar_liberado(parking_id)
        self.repo.registrar("liberado", ahora, parking_id=parking_id, estado="liberado")

    def quitar_bloqueo(self, bloqueo_id: int, propietario_id: int, ahora: datetime) -> None:
        b = self.repo.quitar_bloqueo(bloqueo_id, propietario_id, ahora)
        self.repo.registrar("bloqueo_retirado", ahora, parking_id=b["parking_id"], inicio=b["inicio"], fin=b["fin"])

    def bloquear(self, parking_id: int, inicio: datetime, fin: datetime, motivo: str,
                 ahora: datetime, propietario_id: int | None = None) -> list[int]:
        """El propietario tiene prioridad: reubica las reservas afectadas o las cancela con reembolso total."""
        self._propio(parking_id, propietario_id)
        if fin <= inicio:
            raise ReglaError("El termino debe ser posterior al inicio.")
        periodo = Periodo(inicio, fin)
        afectadas = self.repo.reservas_en_conflicto(parking_id, periodo)
        for reserva in afectadas:
            self._validar_secuencia(reserva, ahora)
        self.repo.agregar_bloqueo(parking_id, periodo, motivo)
        ini, fi = periodo.textos()
        self.repo.registrar("bloqueado", ahora, parking_id=parking_id, inicio=ini, fin=fi,
                            estado="bloqueado", detalle=motivo)
        for r in afectadas:
            comodin = self._comodin_libre(r)
            if comodin is not None:
                r.parking_id, r.estado = comodin, "reubicada"
                self.repo.guardar(r)
                self._registrar("reubicada", ahora, r, detalle=f"desde {parking_id}: {motivo}")
            else:
                r.estado = "cancelada"
                devuelto = self._credito_pendiente(r, r.monto)
                self.repo.guardar(r)
                self.repo.acreditar(r.cliente_id, devuelto)
                self._registrar("cancelada", ahora, r, valor=devuelto, detalle="sin comodin")
        self.repo.confirmar()
        return [r.id for r in afectadas]

    def vuelvo_ahora(self, parking_id: int, ahora: datetime, propietario_id: int | None = None) -> int:
        self._propio(parking_id, propietario_id)
        r = self.repo.reserva_que_cubre(parking_id, ahora)
        if r is None:
            raise ReglaError("No hay una reserva en curso en ese estacionamiento. Usa Bloquear para impedir reservas.")
        self.bloquear(parking_id, ahora, r.periodo.fin, "vuelvo ahora", ahora, propietario_id)
        r = self.repo.reserva(r.id)
        if r.estado == "cancelada":  # sin comodin: bloquear ya abono el saldo
            return self._credito_pendiente(r, r.monto)
        minutos_restantes = int((r.periodo.fin - ahora).total_seconds() // 60)
        credito = self._credito_pendiente(r, minutos_restantes * TARIFA_MIN)
        self.repo.acreditar(r.cliente_id, credito)
        self._registrar("vuelvo_ahora", ahora, r, parking_id=parking_id, valor=credito)
        return credito

    # administrador
    def crear_usuario(self, tipo: str, nombre: str) -> int:
        nombre = nombre.strip()
        if not nombre.isprintable() or not any(letra.isalpha() for letra in nombre):
            raise ReglaError("Escribe un nombre valido.")
        return self.repo.crear_usuario(tipo, nombre)

    def crear_estacionamiento(self, propietario_id: int, ahora: datetime) -> int:
        plaza = self.repo.crear_estacionamiento(propietario_id)
        self.repo.registrar("plaza_creada", ahora, parking_id=plaza, estado="bloqueado")
        return plaza

    def asignar(self, reserva_id: int, parking_id: int, ahora: datetime) -> None:
        r = self.repo.reserva(reserva_id)
        if r.estado != "pendiente":
            raise ReglaError(f"Solo se asignan reservas pendientes (esta esta {r.estado}).")
        self._validar_asignacion(r, parking_id, ahora)
        self._apto(parking_id, r, permitir_comodin=False)
        r.parking_id, r.estado = parking_id, "confirmada"
        self.repo.guardar(r)
        self._registrar("asignada", ahora, r, valor=r.monto)

    def reasignar(self, reserva_id: int, nuevo_parking_id: int, ahora: datetime) -> None:
        r = self.repo.reserva(reserva_id)
        if r.estado not in ("confirmada", "reubicada"):
            raise ReglaError(f"No se puede reasignar una reserva {r.estado}.")
        if nuevo_parking_id == r.parking_id:
            raise ReglaError("La reserva ya esta en ese estacionamiento.")
        self._validar_asignacion(r, nuevo_parking_id, ahora)
        self._apto(nuevo_parking_id, r, permitir_comodin=True)
        origen = r.parking_id
        r.parking_id = nuevo_parking_id
        self.repo.guardar(r)
        self._registrar("reasignada", ahora, r, valor=r.monto, detalle=f"desde {origen}")

    def registrar_salida(self, reserva_id: int, ahora: datetime) -> int:
        r = self.repo.reserva(reserva_id)
        if not r.esta_activa:
            raise ReglaError(f"No se puede cerrar una reserva {r.estado}.")
        if ahora < r.periodo.inicio:
            raise ReglaError("No se puede registrar la salida antes del inicio de la reserva.")
        self._validar_secuencia(r, ahora)
        recargo = r.recargo(ahora)
        r.estado = "cerrada"
        self.repo.guardar(r)
        self._registrar("cerrada", ahora, r, valor=recargo, detalle=f"atraso {r.atraso_minutos(ahora)} min")
        return recargo
