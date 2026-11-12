"""Entidades del dominio y las reglas que dependen solo de ellas."""
from dataclasses import dataclass
from datetime import datetime, timedelta

TARIFA_MIN = 30
RECARGO_MIN = 60
GRACIA_MIN = 5
ESTADOS_ACTIVOS = ("confirmada", "en_curso", "reubicada")


class ReglaError(Exception):
    """Una operacion viola una regla de negocio."""


@dataclass(frozen=True)
class Periodo:
    """Intervalo semiabierto [inicio, fin): un periodo puede empezar justo cuando termina otro."""
    inicio: datetime
    fin: datetime

    def __post_init__(self):
        if self.fin <= self.inicio:
            raise ValueError("El fin debe ser posterior al inicio.")

    @property
    def minutos(self) -> int:
        return int((self.fin - self.inicio).total_seconds() // 60)

    def se_superpone(self, otro: "Periodo") -> bool:
        return self.inicio < otro.fin and self.fin > otro.inicio

    def contiene(self, momento: datetime) -> bool:
        return self.inicio <= momento < self.fin

    @classmethod
    def desde_texto(cls, inicio: str, fin: str) -> "Periodo":
        return cls(datetime.fromisoformat(inicio), datetime.fromisoformat(fin))

    def textos(self) -> tuple[str, str]:
        return (self.inicio.isoformat(timespec="minutes"), self.fin.isoformat(timespec="minutes"))


@dataclass
class Estacionamiento:
    id: int
    propietario_id: int | None
    tipo: str
    estado: str

    @property
    def es_comodin(self) -> bool:
        return self.tipo == "comodin"

    @property
    def esta_liberado(self) -> bool:
        return self.estado == "liberado"


@dataclass
class Reserva:
    id: int
    parking_id: int | None
    cliente_id: int
    periodo: Periodo
    estado: str
    monto: int

    @property
    def esta_activa(self) -> bool:
        return self.estado in ESTADOS_ACTIVOS

    def reembolso(self, ahora: datetime) -> int:
        """100% si aun no se asigna o hasta 1 hora antes del inicio, 50% hasta el inicio y 0% despues."""
        if self.estado == "pendiente" or ahora <= self.periodo.inicio - timedelta(hours=1):
            return self.monto
        if ahora < self.periodo.inicio:
            return self.monto // 2
        return 0

    def recargo(self, ahora: datetime) -> int:
        """Sobreestadia: desde el minuto 6 de atraso se cobran $60 por cada minuto pasado el minuto 5."""
        atraso = int((ahora - self.periodo.fin).total_seconds() // 60)
        return RECARGO_MIN * (atraso - GRACIA_MIN) if atraso > GRACIA_MIN else 0

    def atraso_minutos(self, ahora: datetime) -> int:
        return max(int((ahora - self.periodo.fin).total_seconds() // 60), 0)
