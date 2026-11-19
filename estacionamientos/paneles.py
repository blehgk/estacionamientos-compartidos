"""Acciones y consultas de cada panel autenticado."""
from .acceso import emitir_acceso
from .acciones import clp, leer_fecha, leer_id
from .modelos import Periodo, ReglaError
from .servicios import Sistema

TITULOS = {"cliente": "Usuario", "propietario": "Propietario", "admin": "Administrador"}
CAMPOS = {
    "inicio": ("Inicio", "datetime-local"), "fin": ("Termino", "datetime-local"),
    "plaza": ("Estacionamiento", "select"), "reserva": ("Reserva", "select"),
    "bloqueo": ("Bloqueo", "select"), "propietario": ("Propietario", "select"),
    "nombre": ("Nombre", "text"), "motivo": ("Motivo (opcional)", "text"),
    "usuario": ("ID del usuario", "number"), "rol": ("Rol", "select"),
}
OPCIONES = {
    "cliente": {
        "reservar": ("Solicitar reserva", ("inicio", "fin")),
        "disponibilidad": ("Consultar disponibilidad", ("inicio", "fin")),
        "prever_cancelacion": ("Cancelar reserva", ("reserva",)),
    },
    "propietario": {
        "publicar": ("Ofrecer plaza", ("plaza",)),
        "bloquear": ("Bloquear por horario", ("plaza", "inicio", "fin", "motivo")),
        "quitar_bloqueo": ("Retirar un bloqueo", ("bloqueo",)),
        "vuelvo_ahora": ("Vuelvo ahora", ("plaza",)),
    },
    "admin": {
        "asignar": ("Asignar", ("reserva", "plaza")),
        "reasignar": ("Reasignar", ("reserva", "plaza")),
        "salida": ("Registrar salida", ("reserva",)),
        "crear_cliente": ("Crear cliente", ("nombre",)),
        "crear_propietario": ("Crear propietario", ("nombre",)),
        "crear_plaza": ("Vincular nueva plaza", ("propietario",)),
        "rechazar": ("Rechazar solicitud", ("reserva",)),
        "disponibilidad": ("Consultar disponibilidad", ("inicio", "fin")),
        "emitir_acceso": ("Emitir o restablecer acceso", ("rol", "usuario")),
    },
}
ACCIONES_SIN_HORA = {"crear_cliente", "crear_propietario", "emitir_acceso"}


def _periodo(form: dict) -> Periodo:
    inicio, fin = leer_fecha(form["inicio"]), leer_fecha(form["fin"])
    if fin <= inicio:
        raise ReglaError("El termino debe ser posterior al inicio.")
    return Periodo(inicio, fin)


def _resultado_reservas(sistema: Sistema, ids: list[int]) -> str:
    return " ".join(f"Reserva {r}: {sistema.repo.reserva(r).estado}." for r in ids)


def _operar_usuario(sistema: Sistema, usuario: int, accion: str, form: dict, ahora):
    if accion == "reservar":
        periodo = _periodo(form)
        reserva = sistema.reservar(usuario, periodo.inicio, periodo.fin, ahora)
        return f"Solicitud {reserva} pendiente. Administracion debe confirmar tu plaza.", None

    reserva_id = leer_id(form["reserva"])
    if not sistema.repo.reserva_del_cliente(reserva_id, usuario):
        raise ReglaError("La reserva no esta disponible en tu cuenta.")
    reserva = sistema.repo.reserva(reserva_id)
    importe = sistema.calcular_cancelacion(reserva, ahora)
    if accion == "prever_cancelacion":
        return "", (reserva.id, importe)
    if importe != int(form["importe"]):
        raise ReglaError("El importe cambio. Consulta la cancelacion de nuevo.")
    sistema.cancelar(reserva.id, ahora)
    return f"Reserva {reserva.id} cancelada. Credito abonado: {clp(importe)}.", None


def _operar_propietario(sistema: Sistema, usuario: int, accion: str, form: dict, ahora) -> str:
    if accion == "quitar_bloqueo":
        sistema.quitar_bloqueo(leer_id(form["bloqueo"]), usuario, ahora)
        return "Bloqueo retirado. Se conservaron las demas franjas."

    plaza = leer_id(form["plaza"])
    if accion == "publicar":
        sistema.publicar(plaza, usuario, ahora)
        return f"Estacionamiento {plaza} ofrecido. Se conservaron los bloqueos programados."
    if accion == "bloquear":
        periodo = _periodo(form)
        if periodo.fin <= ahora:
            raise ReglaError("La franja de bloqueo ya termino.")
        ids = sistema.bloquear(plaza, periodo.inicio, periodo.fin, form.get("motivo", "").strip(), ahora, usuario)
        resumen = _resultado_reservas(sistema, ids) if ids else "Sin reservas afectadas."
        return f"Bloqueo registrado. {resumen}"

    sistema._propio(plaza, usuario)
    reserva = sistema.repo.reserva_que_cubre(plaza, ahora)
    credito = sistema.vuelvo_ahora(plaza, ahora, usuario)
    resultado = _resultado_reservas(sistema, [reserva.id])
    return f"{resultado} Credito abonado al cliente: {clp(credito)}."


def operar_admin(con, sistema: Sistema, accion: str, form: dict, ahora) -> str:
    if accion in {"crear_cliente", "crear_propietario", "emitir_acceso"}:
        if accion == "emitir_acceso":
            rol = form["rol"]
            if rol not in {"cliente", "propietario"}:
                raise ReglaError("Selecciona Usuario o Propietario.")
            usuario = leer_id(form["usuario"])
        else:
            rol = accion.removeprefix("crear_")
            usuario = sistema.crear_usuario(rol, form["nombre"])
            ids = {"cliente_id" if rol == "cliente" else "propietario_id": usuario}
            sistema.repo.registrar(f"{rol}_creado", ahora, **ids)
        clave = emitir_acceso(con, rol, usuario)
        return f"App {TITULOS[rol]}. ID: {usuario}. Clave: {clave}. Copia los datos y entregalos al titular."

    if accion == "crear_plaza":
        plaza = sistema.crear_estacionamiento(leer_id(form["propietario"]), ahora)
        return f"Estacionamiento {plaza} vinculado. El propietario puede ofrecerlo desde su app."

    reserva = leer_id(form["reserva"])
    if accion == "salida":
        recargo = sistema.registrar_salida(reserva, ahora)
        return f"Reserva {reserva} cerrada. Recargo: {clp(recargo)}."
    if accion == "rechazar":
        if sistema.repo.reserva(reserva).estado != "pendiente":
            raise ReglaError("Solo se rechazan solicitudes pendientes.")
        credito = sistema.cancelar(reserva, ahora, detalle="rechazo administrativo")
        return f"Solicitud {reserva} rechazada. Credito abonado: {clp(credito)}."
    plaza = leer_id(form["plaza"])
    if accion == "asignar":
        sistema.asignar(reserva, plaza, ahora)
        return f"Reserva {reserva} confirmada en la plaza {plaza}."
    sistema.reasignar(reserva, plaza, ahora)
    return f"Reserva {reserva} reasignada a la plaza {plaza}."


def procesar(con, rol: str, usuario: int, accion: str, form: dict, ahora):
    if accion not in OPCIONES[rol] and (rol, accion) != ("cliente", "cancelar"):
        raise ReglaError("Esta accion no esta disponible en tu panel.")
    sistema = Sistema(con, autoconfirmar=False)
    if accion == "disponibilidad":
        periodo = _periodo(form)
        if periodo.inicio < ahora:
            raise ReglaError("Elige una franja futura.")
        libres = sistema.estacionamientos_compatibles(periodo.inicio, periodo.fin)
        if rol == "admin":
            plazas = ", ".join(map(str, libres)) or "ninguna"
            return f"Plazas normales compatibles para ese horario: {plazas}.", None
        return f"Plazas compatibles: {len(libres)}. La plaza se confirma cuando Administracion asigna tu solicitud.", None
    if rol == "cliente":
        return _operar_usuario(sistema, usuario, accion, form, ahora)
    if rol == "propietario":
        return _operar_propietario(sistema, usuario, accion, form, ahora), None
    return operar_admin(con, sistema, accion, form, ahora), None


def _filas(con, sql: str, *args):
    return [tuple(fila) for fila in con.execute(sql, args)]


def panel_data(con, rol: str, usuario: int, ahora) -> tuple[str, list, dict]:
    ahora_txt = ahora.isoformat(timespec="minutes")
    tablas, opciones = [], {}
    nombre = TITULOS[rol]
    if rol == "cliente":
        nombre, credito = con.execute("SELECT nombre, credito FROM clientes WHERE id=?", (usuario,)).fetchone()
        reservas = _filas(con, """
            SELECT r.id, r.parking_id, r.inicio, r.fin,
                   CASE WHEN r.estado='pendiente' AND r.fin<=? THEN 'vencida' ELSE r.estado END,
                   r.monto,
                   COALESCE(SUM(CASE WHEN h.evento='cerrada' THEN h.valor END),0) AS recargo,
                   COALESCE(SUM(CASE WHEN h.evento IN ('vuelvo_ahora','cancelada') THEN h.valor END),0) AS credito,
                   MAX(0,r.monto + COALESCE(SUM(CASE WHEN h.evento='cerrada' THEN h.valor END),0)
                       - COALESCE(SUM(CASE WHEN h.evento IN ('vuelvo_ahora','cancelada') THEN h.valor END),0))
            FROM reservas r LEFT JOIN historial h ON h.reserva_id=r.id AND h.cliente_id=r.cliente_id
            WHERE r.cliente_id=? GROUP BY r.id ORDER BY r.id DESC
        """, ahora_txt, usuario)
        tablas.append(("Mis reservas", ("#", "Plaza", "Inicio", "Fin", "Estado", "Base", "Recargo", "Credito", "Total"), reservas))
        tablas.append(("Mi actividad", ("Hora", "Evento", "Reserva", "Plaza", "Valor"), _filas(con,
            "SELECT ts, evento, reserva_id, parking_id, valor FROM historial WHERE cliente_id=? AND reserva_id IS NOT NULL"
            " ORDER BY ts DESC, id DESC LIMIT 50", usuario)))
        opciones["reserva"] = [(f[0], f"#{f[0]} · {f[4]}") for f in reservas if f[4] in {"pendiente", "vencida", "confirmada", "reubicada"}]
        return f"{nombre} · Credito acumulado: {clp(credito)}", tablas, opciones

    if rol == "propietario":
        nombre = con.execute("SELECT nombre FROM propietarios WHERE id=?", (usuario,)).fetchone()[0]
    plazas = _filas(con, """SELECT e.id, e.propietario_id, e.tipo,
        CASE WHEN EXISTS (SELECT 1 FROM bloqueos b WHERE b.parking_id=e.id AND b.inicio<=? AND b.fin>?)
             THEN 'bloqueo activo'
             WHEN EXISTS (SELECT 1 FROM reservas r WHERE r.parking_id=e.id AND r.inicio<=?
                          AND r.estado IN ('confirmada','reubicada','en_curso'))
             THEN 'ocupada o sin salida'
             WHEN e.estado='liberado' THEN 'ofrecida'
             ELSE 'sin oferta' END
        FROM estacionamientos e WHERE (?='admin' OR e.propietario_id=?) ORDER BY e.id
    """, ahora_txt, ahora_txt, ahora_txt, rol, usuario)
    opciones["plaza"] = [(f[0], f"Plaza {f[0]} · {f[2]} · {f[3]}") for f in plazas]
    tablas.append(("Estacionamientos" if rol == "admin" else "Mis plazas", ("#", "Propietario", "Tipo", "Estado actual"), plazas))
    bloqueos = _filas(con, """SELECT b.id,b.parking_id,b.inicio,b.fin,b.motivo FROM bloqueos b
        JOIN estacionamientos e ON e.id=b.parking_id
        WHERE (?='admin' OR e.propietario_id=?) AND b.fin>? ORDER BY b.inicio,b.id
    """, rol, usuario, ahora_txt)
    tablas.append(("Bloqueos vigentes y futuros", ("#", "Plaza", "Inicio", "Fin", "Motivo"), bloqueos))
    opciones["bloqueo"] = [(f[0], f"#{f[0]} · plaza {f[1]} · {f[2]} a {f[3]}") for f in bloqueos]
    if rol == "admin":
        reservas = _filas(con, """SELECT r.id,c.nombre,r.parking_id,r.inicio,r.fin,
            CASE WHEN r.estado='pendiente' AND r.fin<=? THEN 'vencida'
                 WHEN r.estado IN ('confirmada','reubicada','en_curso') AND r.fin<=? THEN 'sin salida'
                 ELSE r.estado END, r.monto
            FROM reservas r JOIN clientes c ON c.id=r.cliente_id ORDER BY r.id DESC
        """, ahora_txt, ahora_txt)
        tablas.insert(0, ("Reservas", ("#", "Cliente", "Plaza", "Inicio", "Fin", "Estado", "Base"), reservas))
        opciones["reserva"] = [(f[0], f"#{f[0]} · {f[1]} · {f[5]}") for f in reservas if f[5] not in {"cerrada", "cancelada"}]
        usuarios = _filas(con, """SELECT 'cliente', id, nombre FROM clientes
            UNION ALL SELECT 'propietario', id, nombre FROM propietarios ORDER BY 1, 2""")
        tablas.append(("Usuarios", ("Rol", "ID", "Nombre"), usuarios))
        opciones["propietario"] = [(f[1], f"{f[1]} · {f[2]}") for f in usuarios if f[0] == "propietario"]
        opciones["rol"] = [("cliente", "Usuario"), ("propietario", "Propietario")]
    else:
        reservas = _filas(con, """SELECT r.id,r.parking_id,r.inicio,r.fin,r.estado FROM reservas r
            JOIN estacionamientos e ON e.id=r.parking_id WHERE e.propietario_id=?
            ORDER BY r.inicio DESC""", usuario)
        tablas.append(("Reservas de mis plazas", ("#", "Plaza", "Inicio", "Fin", "Estado"), reservas))
    historial = _filas(con, """SELECT ts,evento,reserva_id,parking_id,inicio,fin,valor,detalle
        FROM historial WHERE (?='admin' OR propietario_id=?) ORDER BY ts DESC, id DESC LIMIT 50""", rol, usuario)
    tablas.append(("Historial", ("Hora", "Evento", "Reserva", "Plaza", "Inicio", "Fin", "Valor", "Detalle"), historial))
    return nombre, tablas, opciones
