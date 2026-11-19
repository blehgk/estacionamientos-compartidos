from argparse import ArgumentParser
from contextlib import closing
from datetime import datetime

from .acceso import ADMIN_ID, autenticar, pedir_clave

from .acciones import (ALTAS_USUARIO, CONFIRMAR, FORMS, NOMBRES, VISTAS, creditos_texto, ejecutar,
                       leer_fecha, leer_id, texto_celda)
from .db import conectar, consultar, sembrar
from .modelos import ReglaError
from .paneles import ACCIONES_SIN_HORA, CAMPOS, OPCIONES, panel_data, procesar


def pedir_opcion(prompt: str, validas: set[str], leer=input) -> str:
    while True:
        valor = leer(prompt).strip()
        if valor in validas:
            return valor
        print("Opcion no valida.")


def pedir_entero(prompt: str, leer=input) -> int:
    while True:
        try:
            return leer_id(leer(prompt))
        except ValueError:
            print("Escribe un numero entero positivo valido.")


def pedir_fecha(prompt: str, leer=input, opcional: bool = False) -> datetime | None:
    while True:
        texto = leer(prompt).strip()
        if not texto and opcional:
            return None
        try:
            return leer_fecha(texto)
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
        if accion not in ALTAS_USUARIO:
            form["hora"] = pedir_hora(leer)
        if accion in CONFIRMAR and pedir_opcion(f"{CONFIRMAR[accion]}? (s/n): ", {"s", "n"}, leer) == "n":
            print("Cancelado.")
            continue
        print(ejecutar(con, accion, form))


def _administracion(con, simulacion: bool) -> None:
    acciones = OPCIONES["admin"]
    orden = tuple(acciones)
    ver = str(len(orden) + 1)
    validas = {"0", ver, *(str(i) for i in range(1, len(orden) + 1))}
    while True:
        print("\n-- Administrador --")
        for num, clave in enumerate(orden, 1):
            print(f"{num} {acciones[clave][0]}")
        print(f"{ver} Ver estado\n0 Salir")
        opcion = pedir_opcion("> ", validas)
        if opcion == "0":
            return
        ahora = datetime.now().replace(second=0, microsecond=0)
        _, tablas, opciones = panel_data(con, "admin", ADMIN_ID, ahora)
        if opcion == ver:
            for titulo, columnas, filas in tablas:
                print(f"\n{titulo}\n" + " | ".join(columnas))
                for fila in filas:
                    print(" | ".join(texto_celda(v, c) for v, c in zip(fila, columnas)))
            continue

        clave = orden[int(opcion) - 1]
        form = {}
        for campo in acciones[clave][1]:
            etiqueta, tipo = CAMPOS[campo]
            if tipo == "select":
                for ident, descripcion in opciones[campo]:
                    print(f"  {ident}  {descripcion}")
                tipo = "text"
            form[campo] = pedir_campo(etiqueta, tipo)
        if simulacion and clave not in ACCIONES_SIN_HORA:
            hora = pedir_fecha("Hora de la operacion (Enter = ahora): ", opcional=True)
            if hora:
                ahora = hora
        try:
            with con:
                con.execute("BEGIN IMMEDIATE")
                aviso, _ = procesar(con, "admin", ADMIN_ID, clave, form, ahora)
        except ReglaError as error:
            print(f"No se pudo: {error}")
        except (KeyError, ValueError):
            print("No se pudo: revisa los datos ingresados.")
        else:
            print(aviso)


def main() -> None:
    parser = ArgumentParser(description="Administracion desde la terminal.")
    parser.add_argument("--simulacion", action="store_true")
    args = parser.parse_args()
    with closing(conectar()) as con:
        sembrar(con)
        if not autenticar(con, "admin", ADMIN_ID, pedir_clave("Clave de Administrador: ")):
            raise SystemExit("Acceso incorrecto. Configura la clave con python -m estacionamientos.acceso.")
        _administracion(con, args.simulacion)
