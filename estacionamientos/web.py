"""Interfaz web: usa las mismas acciones y vistas que la terminal; sin dependencias externas."""
from html import escape
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, quote, urlparse

from .acciones import (CONFIRMAR, FORMS, NOMBRES, NUMERICAS, VISTAS, creditos_texto, ejecutar,
                       texto_celda)
from .db import conectar, consultar, sembrar

MAX_CUERPO = 64 * 1024

CSS = """
:root{color-scheme:light;--bg:#f4f6f8;--panel:#fff;--line:#d5dbe1;--text:#1f2933;--head:#111827;--muted:#5b6673;--accent:#1f4e79;--warn:#9a5b00}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:14px/1.4 system-ui,sans-serif}
*{scrollbar-width:thin;scrollbar-color:var(--line) transparent}
main>*{min-width:0}header{display:flex;flex-wrap:wrap;gap:.5rem 1rem;align-items:center;padding:.6rem 1rem;border-bottom:1px solid var(--line);background:var(--panel)}
h1{font-size:1rem;margin:0;color:var(--head)}nav{display:flex;gap:2px;background:var(--bg);border:1px solid var(--line);border-radius:8px;padding:2px}
nav a{color:var(--muted);text-decoration:none;padding:.3rem .8rem;border-radius:6px}
nav a.on{background:var(--accent);color:#fff}nav a:focus-visible,button:focus-visible,input:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
main{display:grid;grid-template-columns:minmax(290px,360px) 1fr;gap:1rem;padding:1rem;align-items:start}
@media(max-width:800px){main{grid-template-columns:1fr}}
form,section{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:.8rem;box-shadow:0 1px 2px rgba(16,24,40,.06)}
form{margin-bottom:.8rem}h2{font-size:.9rem;margin:0 0 .5rem;color:var(--head)}
label{display:block;color:var(--muted);font-size:.8rem;margin-top:.4rem}
input{width:100%;background:var(--bg);color:var(--text);border:1px solid var(--line);border-radius:6px;padding:.4rem}
button{margin-top:.6rem;background:var(--accent);color:#fff;border:0;border-radius:6px;padding:.4rem .9rem;cursor:pointer}
.msg{margin:.8rem 1rem 0;padding:.5rem .8rem;border:1px solid var(--line);border-radius:8px;background:var(--panel)}
.msg.err{border-color:var(--warn);color:var(--warn);background:#fff8ec}
.tabla{max-height:42vh;overflow:auto}table{border-collapse:collapse;width:100%}
th,td{text-align:left;padding:.3rem .5rem;border-bottom:1px solid var(--line);white-space:nowrap}th{color:var(--muted);font-weight:500}
details{margin-top:.8rem}summary{cursor:pointer;color:var(--muted)}.muted{color:var(--muted)}
.num{text-align:right;font-variant-numeric:tabular-nums}button:hover{filter:brightness(1.2)}
button,a{touch-action:manipulation}
.salto{position:absolute;left:-999px;top:.5rem}
.salto:focus{left:.5rem;z-index:1;background:var(--panel);color:var(--accent);padding:.4rem .8rem;border:2px solid var(--accent);border-radius:6px}
.msg:focus{outline:2px solid var(--accent);outline-offset:2px}
@media(pointer:coarse){nav a,button,input{min-height:44px}nav a{display:flex;align-items:center}}
"""


def _tabla(cabeceras, filas, etiqueta: str) -> str:
    th = "".join(f'<th scope="col"{" class=num" if c in NUMERICAS else ""}>{c}</th>' for c in cabeceras)
    celdas = lambda fila: "".join(
        f'<td{" class=num" if c in NUMERICAS and v is not None else ""}>{escape(texto_celda(v, c))}</td>'
        for v, c in zip(fila, cabeceras))
    tr = "".join(f"<tr>{celdas(f)}</tr>" for f in filas)
    if not tr:
        tr = f'<tr><td colspan="{len(cabeceras)}" class="muted">Sin registros</td></tr>'
    return (f'<div class="tabla" role="region" aria-label="{etiqueta}" tabindex="0">'
            f'<table><tr>{th}</tr>{tr}</table></div>')


def _form(rol, accion, titulo, campos) -> str:
    inputs = "".join(
        f'<label>{et}<input name="{n}" type="{t}" autocomplete="off"{"" if n == "motivo" else " required"}></label>'
        for n, et, t in campos)
    confirmar = f' onsubmit="return confirm(\'{CONFIRMAR[accion]}?\')"' if accion in CONFIRMAR else ""
    return (f'<form method="post" action="/{rol}/{accion}" aria-labelledby="t-{accion}"{confirmar}>'
            f'<h2 id="t-{accion}">{titulo}</h2>{inputs}'
            f'<label>Hora de la operacion (opcional)<input name="hora" type="datetime-local" autocomplete="off"></label>'
            f'<button>{titulo}</button></form>')


def pagina(con, rol: str, mensaje: str) -> str:
    rol = rol if rol in FORMS else "cliente"
    actual = ' aria-current="page"'
    nav = "".join(f'<a href="/{r}" class="{"on" if r == rol else ""}"{actual if r == rol else ""}>{n}</a>'
                  for r, n in NOMBRES.items())
    error = mensaje.startswith("No se pudo")
    msg = (f'<div class="msg{" err" if error else ""}" role="{"alert" if error else "status"}" tabindex="-1">'
           f'{escape(mensaje)}</div>') if mensaje else ""
    # el foco va al resultado: asi teclado y lector de pantalla lo reciben tras recargar
    foco = '<script>document.querySelector(".msg").focus()</script>' if mensaje else ""
    forms = "".join(_form(rol, *f) for f in FORMS[rol])
    datos = consultar(con)
    tablas = [_tabla(cabeceras, datos[clave], titulo) for titulo, clave, cabeceras in VISTAS]
    reservas = f"<h2>{VISTAS[0][0]}</h2>{tablas[0]}"
    resto = "".join(f"<details><summary>{v[0]}</summary>{t}</details>" for v, t in zip(VISTAS[1:], tablas[1:]))
    return f"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="theme-color" content="#f4f6f8"><title>Estacionamientos compartidos: {NOMBRES[rol]}</title>
<style>{CSS}</style></head><body>
<a class="salto" href="#contenido">Saltar al contenido</a>
<header><h1>Estacionamientos compartidos</h1><nav aria-label="Roles">{nav}</nav></header>{msg}
<main id="contenido"><div>{forms}</div><div><section>{reservas}
<p class="muted">Credito: {creditos_texto(datos["creditos"])}</p>{resto}</section></div></main>{foco}</body></html>"""


class Handler(BaseHTTPRequestHandler):
    con = None

    def _responder(self, rol, mensaje=""):
        cuerpo = pagina(self.con, rol, mensaje).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(cuerpo)))
        self.end_headers()
        self.wfile.write(cuerpo)

    def do_GET(self):
        url = urlparse(self.path)
        self._responder(url.path.strip("/").split("/")[0], parse_qs(url.query).get("m", [""])[0])

    def do_POST(self):  # redirige despues de operar: recargar la pagina no repite la operacion
        partes = self.path.strip("/").split("/")
        rol = partes[0] if partes[0] in FORMS else "cliente"
        try:
            largo = int(self.headers.get("Content-Length", 0))
        except ValueError:
            largo = -1
        if not 0 <= largo <= MAX_CUERPO:
            self.send_error(400, "Cuerpo invalido")
            return
        form = {k: v[0] for k, v in parse_qs(self.rfile.read(largo).decode("utf-8", "replace")).items()}
        self.send_response(303)
        self.send_header("Location", f"/{rol}?m={quote(ejecutar(self.con, partes[-1], form))}")
        self.end_headers()

    def log_message(self, *args):
        pass


def serve(puerto: int = 8000) -> None:
    Handler.con = conectar()
    sembrar(Handler.con)
    print(f"http://localhost:{puerto}  (Ctrl+C para salir)")
    HTTPServer(("127.0.0.1", puerto), Handler).serve_forever()


if __name__ == "__main__":
    serve()
