"""Tres aplicaciones locales con acceso y paneles independientes."""
from argparse import ArgumentParser
from collections import deque
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime
from html import escape
from http.cookies import CookieError, SimpleCookie
from http.server import BaseHTTPRequestHandler, HTTPServer
from secrets import compare_digest, token_urlsafe
from time import monotonic
from urllib.parse import parse_qs, urlsplit

from .acceso import autenticar, credencial
from .acciones import clp, leer_fecha, leer_id, texto_celda
from .db import conectar, sembrar
from .modelos import ReglaError
from .paneles import ACCIONES_SIN_HORA, CAMPOS, OPCIONES, TITULOS, panel_data, procesar

PUERTOS = {"cliente": 8000, "propietario": 8001, "admin": 8002}
RUTAS = {"usuario": "cliente", "propietario": "propietario", "administrador": "admin"}
MAX_CUERPO = 64 * 1024
VIGENCIA = 8 * 60 * 60
MONEDA = {"Base", "Recargo", "Credito", "Total", "Valor"}
CSS = """
:root{color-scheme:light;--bg:#f4f6f8;--panel:#fff;--line:#c9d2dc;--text:#172634;--muted:#526173;--accent:#1f4e79}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:15px/1.48 system-ui,sans-serif}
header{display:flex;gap:.5rem 1rem;flex-wrap:wrap;justify-content:space-between;align-items:center;background:var(--panel);border-bottom:1px solid var(--line);padding:.7rem 1rem}
header form{margin:0}h1{font-size:1.15rem;margin:0}h2{font-size:1rem;margin:0 0 .5rem}p{margin:.45rem 0}
main,.flash{max-width:82rem;margin:0 auto;padding:1rem}main{display:grid;grid-template-columns:minmax(245px,310px) minmax(0,1fr);gap:1rem;align-items:start}
main.login{display:block;max-width:28rem;margin:3rem auto}
.card,.flash div{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:.9rem}
.flash{padding-bottom:0}.flash .error{background:#fff4e5;color:#703d04}.flash div{overflow-wrap:anywhere}
section+section,details+details{margin-top:.65rem}section>details{border-top:1px solid var(--line);padding-top:.5rem;margin-top:.4rem}
summary,label{font-weight:600}summary{cursor:pointer;color:var(--accent)}small,.muted{color:var(--muted)}
label{display:block;margin:.55rem 0 .25rem}
input,select,button{font:inherit;border:1px solid var(--line);border-radius:6px;padding:.45rem .6rem;max-width:100%}
input,select{width:100%;background:var(--bg);color:var(--text);min-height:39px}
button{background:var(--accent);color:#fff;cursor:pointer;margin-top:.75rem}
header button{margin:0;background:var(--panel);color:var(--accent);font-size:.88rem}
button:hover{filter:brightness(1.12)}a{color:var(--accent)}
:focus-visible,.flash div:focus{outline:2px solid var(--accent);outline-offset:2px}
.tabla{overflow:auto}table{border-collapse:collapse;width:100%;font-size:.88rem}
th,td{text-align:left;padding:.42rem .52rem;border-bottom:1px solid var(--line)}th{color:var(--muted);white-space:nowrap}
td{white-space:nowrap}td.detalle{max-width:26ch;min-width:12ch;white-space:normal;overflow-wrap:anywhere}td.num{text-align:right;white-space:nowrap;font-variant-numeric:tabular-nums}
.salto{position:absolute;left:-1000px;top:.5rem}.salto:focus{left:.5rem;background:var(--panel);padding:.6rem;z-index:2}
@media(max-width:780px){main{display:flex;flex-direction:column;align-items:stretch}aside{min-width:0}}
@media(pointer:coarse){button,input,select{min-height:44px}summary{padding:.25rem 0}}
"""
AYUDAS = {
    "reservar": "De 60 a 120 minutos. Desde 15 minutos hasta 7 dias antes. Tarifa de $30 por minuto.",
    "disponibilidad": "Consulta cuantas plazas admiten la franja. Una solicitud queda pendiente hasta ser asignada.",
    "prever_cancelacion": "Revisa el importe que se abonara como credito antes de confirmar.",
    "publicar": "Habilita las reservas en esta plaza y conserva los bloqueos programados.",
    "bloquear": "Las reservas afectadas se moveran a un comodin disponible o se cancelaran con reembolso.",
    "quitar_bloqueo": "Retira solamente la franja seleccionada.",
    "vuelvo_ahora": "Recupera tu plaza durante una reserva en curso. Si no hay reserva en curso, usa Bloquear por horario.",
    "rechazar": "Resuelve una solicitud pendiente a la que no se le puede asignar una plaza.",
    "crear_plaza": "La plaza quedara vinculada al propietario y empezara sin oferta.",
    "emitir_acceso": "La nueva clave reemplaza la anterior y cierra las sesiones vigentes de esa cuenta.",
}


def _pagina(rol: str, contenido: str, encabezado: str = "", aviso: str = "", error: bool = False) -> str:
    titulo = TITULOS[rol]
    alerta = ""
    if aviso:
        tipo = ' class="error" role="alert"' if error else ' role="status"'
        alerta = (f'<div class="flash"><div{tipo} tabindex="-1" autofocus>'
                  f'{escape(aviso)}</div></div>')
    return f"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="theme-color" content="#f4f6f8">
<title>Estacionamientos compartidos · {titulo}</title><style>{CSS}</style></head><body>
<a class="salto" href="#contenido">Saltar al contenido</a>
<header><h1>Estacionamientos compartidos · {titulo}</h1>{encabezado}</header>
{alerta}{contenido}</body></html>"""


def pagina_ingreso(rol: str, aviso: str = "") -> str:
    ayuda = "Solicita tu ID y clave a Administracion." if rol != "admin" else "Ingresa con el acceso de Administracion."
    ingreso = f"""<main class="login" id="contenido"><section class="card"><h2>Iniciar sesi&oacute;n</h2>
<p>{ayuda}</p><form method="post" action="/ingresar">
<label for="usuario">ID de la cuenta</label><input id="usuario" name="usuario" inputmode="numeric" autocomplete="username" required>
<label for="clave">Clave</label><input id="clave" type="password" name="clave" autocomplete="current-password" maxlength="128" required>
<button>Entrar</button></form></section></main>"""
    return _pagina(rol, ingreso, aviso=aviso, error=bool(aviso))


def _tabla(titulo, columnas, filas) -> str:
    nombre = escape(titulo)
    if not filas:
        return '<p class="muted">Sin registros.</p>'
    cabecera = "".join(f'<th scope="col">{escape(c)}</th>' for c in columnas)
    cuerpo = []
    for fila in filas:
        celdas = []
        for valor, columna in zip(fila, columnas):
            dinero = columna in MONEDA and valor is not None
            texto = clp(valor) if dinero else texto_celda(valor, columna)
            clase = " class=num" if dinero else (" class=detalle" if columna in {"Detalle", "Motivo"} else "")
            celdas.append(f'<td{clase}>{escape(texto)}</td>')
        cuerpo.append(f"<tr>{''.join(celdas)}</tr>")
    return (f'<div class="tabla" role="region" aria-label="{nombre}" tabindex="0">'
            f'<table><thead><tr>{cabecera}</tr></thead><tbody>{"".join(cuerpo)}</tbody></table></div>')


def _oculto(nombre: str, valor: str) -> str:
    return f'<input type="hidden" name="{nombre}" value="{escape(str(valor), quote=True)}">'


def _campo(accion, campo, valores, opciones) -> str:
    etiqueta, tipo = CAMPOS.get(campo, ("Hora de la operacion", "datetime-local"))
    id_campo = f"{accion}-{campo}"
    valor = valores.get(campo, "")
    obligatorio = "" if campo in {"motivo", "hora"} else " required"
    label = f'<label for="{id_campo}">{etiqueta}</label>'
    if tipo == "select":
        elementos = ['<option value="">Selecciona</option>']
        for ident, texto in opciones.get(campo, ()):
            ident = str(ident)
            selecto = " selected" if ident == valor else ""
            elementos.append(f'<option value="{escape(ident)}"{selecto}>{escape(texto)}</option>')
        return f'{label}<select id="{id_campo}" name="{campo}"{obligatorio}>{"".join(elementos)}</select>'
    min_id = ' min="1" step="1"' if tipo == "number" else ""
    return (f'{label}<input id="{id_campo}" name="{campo}" type="{tipo}"'
            f' value="{escape(valor)}"{obligatorio}{min_id}>')


def pagina_panel(con, rol, usuario, csrf, ahora, accion="", aviso="", valores=None, cancelar=None, simulacion=False):
    cuenta, tablas, opciones = panel_data(con, rol, usuario, ahora)
    identidad = f'<span>{escape(cuenta)}</span>' if rol != "admin" else ""
    encabezado = (f'{identidad}<form method="post" action="/salir">'
                  f'{_oculto("csrf", csrf)}<button>Cerrar sesi&oacute;n</button></form>')
    formularios, vistas = [], []
    if rol == "propietario" and not opciones["plaza"]:
        aviso = aviso or "Administracion debe vincular una plaza para que puedas ofrecerla."
    for clave, (titulo, campos) in OPCIONES[rol].items():
        seleccionado = clave == accion
        if simulacion and clave not in ACCIONES_SIN_HORA:
            campos = (*campos, "hora")
        contenido = "".join(_campo(clave, c, (valores or {}) if seleccionado else {}, opciones) for c in campos)
        ayuda = f'<p class="muted">{escape(AYUDAS[clave])}</p>' if clave in AYUDAS else ""
        principal = {"cliente": "reservar", "propietario": "publicar", "admin": "asignar"}[rol]
        abierto = " open" if seleccionado or (not accion and clave == principal) else ""
        formularios.append(f'<details{abierto}><summary>{titulo}</summary>{ayuda}'
                           f'<form method="post" action="/{clave}" aria-label="{titulo}">'
                           f'{_oculto("csrf", csrf)}{contenido}<button>{titulo}</button></form></details>')
    if cancelar:
        reserva, importe = cancelar
        formularios.insert(0, f'<section><h2>Confirmar cancelaci&oacute;n</h2>'
            f'<p>Reserva {reserva}. Se abonara {clp(importe)} como credito.</p>'
            f'<form method="post" action="/cancelar">{_oculto("csrf", csrf)}'
            f'{_oculto("reserva", reserva)}{_oculto("importe", importe)}'
            f'{_oculto("hora", (valores or {}).get("hora", ""))}'
            '<button>Confirmar cancelaci&oacute;n</button></form><a href="/">Volver</a></section>')
    for titulo, columnas, filas in tablas:
        vistas.append(f'<section class="card"><h2>{titulo}</h2>{_tabla(titulo, columnas, filas)}</section>')
    demo = '<p><small>Simulacion de horario habilitada.</small></p>' if simulacion else ""
    contenido = (f'<main id="contenido"><aside class="card"><h2>Acciones</h2>{demo}{"".join(formularios)}</aside>'
                 f'<div>{"".join(vistas)}</div></main>')
    return _pagina(rol, contenido, encabezado, aviso, aviso.startswith("No se pudo:"))


@dataclass
class Sesion:
    usuario: int
    sello: tuple
    csrf: str
    vence: float
    aviso: str = ""


class Servidor(HTTPServer):
    allow_reuse_address = True

    def __init__(self, direccion, rol: str, con, simulacion: bool = False, reloj=None):
        self.rol = rol
        self.con = con
        self.simulacion = simulacion
        self.reloj = reloj or datetime.now
        self.sesiones: dict[str, Sesion] = {}
        self.intentos: deque = deque()
        self.cookie = f"panel_{rol}"
        super().__init__(direccion, Manejador)
        self.origenes = {f"http://{host}:{self.server_port}" for host in ("127.0.0.1", "localhost")}

    def ahora(self):
        return self.reloj().replace(second=0, microsecond=0)


class Manejador(BaseHTTPRequestHandler):
    timeout = 10

    def _cabeceras(self):
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "same-origin")
        self.send_header("Content-Security-Policy",
                         "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'")

    def _html(self, contenido, codigo=200):
        cuerpo = contenido.encode("utf-8")
        self.send_response(codigo)
        self._cabeceras()
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(cuerpo)))
        self.end_headers()
        self.wfile.write(cuerpo)

    def _volver(self, accion="", cookie=None):
        self.send_response(303)
        self._cabeceras()
        self.send_header("Location", f"/?accion={accion}" if accion else "/")
        if cookie is not None:
            self.send_header("Set-Cookie", f"{self.server.cookie}={cookie}; Path=/; HttpOnly; SameSite=Strict")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _host(self):
        return f"http://{self.headers.get('Host', '')}" in self.server.origenes

    def _sesion(self):
        ahora = monotonic()
        for id_sesion, sesion in tuple(self.server.sesiones.items()):
            if sesion.vence <= ahora:
                del self.server.sesiones[id_sesion]
        try:
            valor = SimpleCookie(self.headers.get("Cookie", "")).get(self.server.cookie)
        except CookieError:
            valor = None
        token = valor.value if valor else ""
        sesion = self.server.sesiones.get(token)
        if sesion and credencial(self.server.con, self.server.rol, sesion.usuario) != sesion.sello:
            self.server.sesiones.pop(token, None)
            sesion = None
        return token, sesion

    def _panel(self, sesion, accion="", aviso="", valores=None, cancelar=None, codigo=200):
        self._html(pagina_panel(self.server.con, self.server.rol, sesion.usuario, sesion.csrf,
                                self.server.ahora(), accion, aviso, valores, cancelar,
                                self.server.simulacion), codigo)

    def do_GET(self):
        if not self._host():
            self.send_error(400)
            return
        url = urlsplit(self.path)
        if url.path != "/":
            self.send_error(404)
            return
        _, sesion = self._sesion()
        if sesion is None:
            self._html(pagina_ingreso(self.server.rol))
            return
        accion = parse_qs(url.query).get("accion", [""])[0]
        aviso, sesion.aviso = sesion.aviso, ""
        self._panel(sesion, accion, aviso)

    def _form(self):
        try:
            largo = int(self.headers.get("Content-Length", "-1"))
            if not 0 <= largo <= MAX_CUERPO or self.headers.get_content_type() != "application/x-www-form-urlencoded":
                raise ValueError()
            cuerpo = self.rfile.read(largo).decode("utf-8")
            return {k: v[0] for k, v in parse_qs(cuerpo, keep_blank_values=True, max_num_fields=12).items()}
        except (UnicodeDecodeError, ValueError):
            self.send_error(400, "Formulario invalido")
            return None

    def _ingresar(self, form):
        ahora = monotonic()
        intentos = self.server.intentos
        while intentos and intentos[0] < ahora - 60:
            intentos.popleft()
        if len(intentos) >= 12:
            self._html(pagina_ingreso(self.server.rol, "Espera un minuto para intentar de nuevo."), 429)
            return
        try:
            usuario = leer_id(form.get("usuario", ""))
            sello = autenticar(self.server.con, self.server.rol, usuario, form.get("clave", ""))
        except ValueError:
            sello = None
        if sello is None:
            intentos.append(ahora)
            self._html(pagina_ingreso(self.server.rol, "ID o clave incorrectos para este panel."), 401)
            return
        anterior, _ = self._sesion()
        self.server.sesiones.pop(anterior, None)
        token = token_urlsafe(32)
        self.server.sesiones[token] = Sesion(usuario, sello, token_urlsafe(32), ahora + VIGENCIA)
        self._volver(cookie=token)

    def do_POST(self):
        if not self._host() or self.headers.get("Origin") != f"http://{self.headers['Host']}":
            self.send_error(403)
            return
        accion = urlsplit(self.path).path.removeprefix("/")
        if accion == "ingresar":
            form = self._form()
            if form is not None:
                self._ingresar(form)
            return
        token, sesion = self._sesion()
        if sesion is None:
            self._html(pagina_ingreso(self.server.rol, "Inicia sesion para continuar."), 401)
            return
        if accion not in OPCIONES[self.server.rol] and accion != "salir" and (self.server.rol, accion) != ("cliente", "cancelar"):
            self.send_error(404)
            return
        form = self._form()
        if form is None:
            return
        if not compare_digest(form.get("csrf", "").encode("utf-8"), sesion.csrf.encode("ascii")):
            self.send_error(403)
            return
        if accion == "salir":
            del self.server.sesiones[token]
            self._volver(cookie="; Max-Age=0")
            return

        con, rol = self.server.con, self.server.rol
        try:
            ahora = self.server.ahora()
            if self.server.simulacion and accion not in ACCIONES_SIN_HORA and form.get("hora"):
                ahora = leer_fecha(form["hora"])
            with con:
                con.execute("BEGIN IMMEDIATE")
                if credencial(con, rol, sesion.usuario) != sesion.sello:
                    raise ReglaError("El acceso cambio. Inicia sesion de nuevo.")
                aviso, vista_previa = procesar(con, rol, sesion.usuario, accion, form, ahora)
        except ReglaError as error:
            destino = "prever_cancelacion" if accion == "cancelar" else accion
            self._panel(sesion, destino, f"No se pudo: {error}", form, codigo=422)
            return
        except (ValueError, KeyError):
            self._panel(sesion, accion, "No se pudo: revisa los campos e ingresa fechas y horas locales validas.", form, codigo=422)
            return
        if vista_previa:
            self._panel(sesion, accion, valores=form, cancelar=vista_previa)
            return
        sesion.aviso = aviso
        self._volver(accion if accion != "cancelar" else "prever_cancelacion")

    def log_message(self, *_):
        pass


def serve(rol: str, puerto: int | None = None, simulacion: bool = False) -> None:
    with closing(conectar()) as con:
        sembrar(con)
        with Servidor(("127.0.0.1", PUERTOS[rol] if puerto is None else puerto), rol, con, simulacion) as servidor:
            print(f"{TITULOS[rol]}: http://localhost:{servidor.server_port}", flush=True)
            servidor.serve_forever()


if __name__ == "__main__":
    parser = ArgumentParser(description="Inicia una aplicacion local de estacionamientos.")
    parser.add_argument("app", choices=RUTAS)
    parser.add_argument("--puerto", type=int)
    parser.add_argument("--simulacion", action="store_true", help="Habilita un reloj editable para ensayar.")
    args = parser.parse_args()
    serve(RUTAS[args.app], args.puerto, args.simulacion)
