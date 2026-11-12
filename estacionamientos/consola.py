from datetime import datetime

from .acciones import CONFIRMAR, FORMS, NOMBRES, VISTAS, creditos_texto, ejecutar, texto_celda
from .db import conectar, consultar, sembrar


def pedir_opcion(prompt: str, validas: set[str], leer=input) -> str:
    while True:
        valor = leer(prompt).strip()
        if valor in validas:
            return valor
        print("Opcion no valida.")


def pedir_entero(prompt: str, leer=input) -> int:
    while True:
        try:
            return int(leer(prompt).strip())
        except ValueError:
            print("Escribe un numero.")


def pedir_fecha(prompt: str, leer=input, opcional: bool = False) -> datetime | None:
    while True:
        texto = leer(prompt).strip()
        if not texto and opcional:
            return None
        try:
            return datetime.strptime(texto, "%Y-%m-%d %H:%M")
        except ValueError:
            print("Formato: AAAA-MM-DD HH:MM")


def pedir_campo(etiqueta: str, tipo: str, leer=input) -> str:
    if tipo == "number":
        return str(pedir_entero(f"{etiqueta}: ", leer))
    if tipo == "datetime-local":
        return pedir_fecha(f"{etiqueta} (AAAA-MM-DD HH:MM): ", leer).isoformat(timespec="minutes")
    return leer(f"{etiqueta}: ").strip()


def pedir_hora(leer=input) -> str:
    """Hora de la operacion; Enter usa la hora actual (permite simular horas en la demo)."""
    hora = pedir_fecha("Hora de la operacion (AAAA-MM-DD HH:MM, Enter = ahora): ", leer, opcional=True)
    return hora.isoformat(timespec="minutes") if hora else ""


def mostrar_estado(con) -> None:
    datos = consultar(con)
    for titulo, clave, cabeceras in VISTAS:
        print(f"\n{titulo}")
        if not datos[clave]:
            print("  Sin registros")
            continue
        print("  " + " | ".join(cabeceras))
        for fila in datos[clave]:
            print("  " + " | ".join(texto_celda(v, c) for v, c in zip(fila, cabeceras)))
    print(f"\nCredito: {creditos_texto(datos['creditos'])}")


def menu(con, rol: str, leer=input) -> None:
    acciones = FORMS[rol]
    ver = str(len(acciones) + 1)
    validas = {"0", ver, *(str(i) for i in range(1, len(acciones) + 1))}
    while True:
        print(f"\n-- {NOMBRES[rol]} --")
        for i, (_, titulo, _) in enumerate(acciones, 1):
            print(f"{i} {titulo}")
        print(f"{ver} Ver estado\n0 Volver")
        opcion = pedir_opcion("> ", validas, leer)
        if opcion == "0":
            return
        if opcion == ver:
            mostrar_estado(con)
            continue
        accion, _, campos = acciones[int(opcion) - 1]
        form = {nombre: pedir_campo(etiqueta, tipo, leer) for nombre, etiqueta, tipo in campos}
        form["hora"] = pedir_hora(leer)
        if accion in CONFIRMAR and pedir_opcion(f"{CONFIRMAR[accion]}? (s/n): ", {"s", "n"}, leer) == "n":
            print("Cancelado.")
            continue
        print(ejecutar(con, accion, form))


def main() -> None:
    con = conectar()
    sembrar(con)
    roles = list(NOMBRES)
    while True:
        print("\n== Estacionamientos compartidos ==")
        for i, rol in enumerate(roles, 1):
            print(f"{i} {NOMBRES[rol]}")
        print("0 Salir")
        opcion = pedir_opcion("> ", {"0", *(str(i) for i in range(1, len(roles) + 1))})
        if opcion == "0":
            return
        menu(con, roles[int(opcion) - 1])
