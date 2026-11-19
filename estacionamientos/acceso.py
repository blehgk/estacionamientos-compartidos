"""Credenciales de los tres paneles y alta administrativa local."""
from contextlib import closing
from getpass import getpass
from hashlib import scrypt
from hmac import compare_digest
from secrets import token_bytes, token_urlsafe
from sys import stdin

from .db import conectar, sembrar
from .modelos import ReglaError

ADMIN_ID = 1


def _derivar(clave: str, sal: bytes) -> bytes:
    return scrypt(clave.encode("utf-8"), salt=sal, n=2**15, r=8, p=1, maxmem=64 * 1024**2)


def emitir_acceso(con, rol: str, usuario_id: int, clave: str | None = None) -> str:
    if rol == "cliente":
        existe = con.execute("SELECT 1 FROM clientes WHERE id=?", (usuario_id,)).fetchone()
    elif rol == "propietario":
        existe = con.execute("SELECT 1 FROM propietarios WHERE id=?", (usuario_id,)).fetchone()
    else:
        existe = rol == "admin" and usuario_id == ADMIN_ID
    if not existe:
        raise ReglaError("No existe ese usuario para el rol indicado.")
    if clave is None:
        clave = token_urlsafe(18)
    if not 12 <= len(clave) <= 128:
        raise ReglaError("La clave debe tener entre 12 y 128 caracteres.")
    sal = token_bytes(16)
    con.execute(
        "INSERT INTO accesos (rol, usuario_id, sal, clave) VALUES (?, ?, ?, ?)"
        " ON CONFLICT (rol, usuario_id) DO UPDATE SET sal=excluded.sal, clave=excluded.clave",
        (rol, usuario_id, sal, _derivar(clave, sal)))
    return clave


def credencial(con, rol: str, usuario_id: int):
    fila = con.execute("SELECT sal, clave FROM accesos WHERE rol=? AND usuario_id=?", (rol, usuario_id)).fetchone()
    return tuple(fila) if fila else None


def autenticar(con, rol: str, usuario_id: int, clave: str):
    if not 12 <= len(clave) <= 128:
        return None
    actual = credencial(con, rol, usuario_id)
    sal, esperada = actual or (bytes(16), bytes(64))
    if compare_digest(_derivar(clave, sal), esperada):
        return actual
    return None


def pedir_clave(etiqueta: str) -> str:
    if stdin.isatty():
        return getpass(etiqueta)
    return stdin.readline().rstrip("\r\n")


def main() -> None:
    clave = pedir_clave("Nueva clave de Administrador: ")
    if clave != pedir_clave("Confirma la clave: "):
        raise SystemExit("Las claves deben coincidir.")
    try:
        with closing(conectar()) as con:
            sembrar(con)
            with con:
                emitir_acceso(con, "admin", ADMIN_ID, clave)
    except ReglaError as error:
        raise SystemExit(str(error)) from error
    print(f"Acceso de Administrador configurado. ID: {ADMIN_ID}.")


if __name__ == "__main__":
    main()
