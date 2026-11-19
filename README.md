# Estacionamientos compartidos

Prototipo en Python para compartir estacionamientos de un edificio: el propietario libera su espacio cuando no lo usa, el cliente lo reserva y el administrador asigna y reasigna. Proyecto de ciclo basico de Ingenieria Civil Informatica (Entrega 2).

Usa solo la libreria estandar de Python (3.10 o superior) y SQLite. No hay nada que instalar.

## Iniciar las tres aplicaciones

Desde la carpeta del proyecto (o `codigo/` dentro del ZIP), configura el acceso de Administrador una vez. El comando pide la clave sin mostrarla. El ID del administrador es **1**.

```bash
python -m estacionamientos.acceso
```

Ejecuta cada app en una terminal distinta, siempre desde **la misma carpeta**:

| Aplicacion | Comando | Direccion local |
| --- | --- | --- |
| Usuario | `python -m estacionamientos.web usuario` | `http://localhost:8000` |
| Propietario | `python -m estacionamientos.web propietario` | `http://localhost:8001` |
| Administrador | `python -m estacionamientos.web administrador` | `http://localhost:8002` |

Cada app tiene su propio inicio de sesion. Una cuenta de Usuario solo ve sus reservas y movimientos. Una cuenta de Propietario solo opera sus plazas. La terminal administrativa se abre con `python main.py` y pide la clave de Administrador.

Las tres comparten `estacionamientos.db` en la carpeta de ejecucion. Si no existe, el programa la crea con dos clientes, dos propietarios, dos plazas normales y un comodin. Para entrar con las fichas existentes, emite sus claves desde Administrador. La base existente se conserva y recibe la tabla de accesos al iniciar una app.

Para un ensayo local, agrega `--simulacion` a los comandos de las apps o a `python main.py`. Aparecera el campo de hora de operacion para avanzar el reloj de un caso. El modo normal usa el reloj del servidor.

## Como comprobar que los datos se guardan en SQLite

1. Desde Administrador, crea un cliente y copia el ID y la clave que devuelve.
2. Entra en Usuario con esos datos, solicita una reserva y anota su numero. En Administrador aparece la solicitud pendiente y se puede asignar.
3. Deten los procesos con **Ctrl+C** y vuelve a iniciarlos desde la misma carpeta. Entra con las mismas credenciales y comprueba que sigan visibles la reserva y sus movimientos.
4. Para revisar desde la terminal, ejecuta `python main.py`, ingresa como Administrador y elige **Ver estado**.

### Mostrar toda la base de datos

Desde la misma carpeta en la que ejecutas la app, usa:

```bash
python -m estacionamientos.db
```

Muestra la estructura y todos los registros en formato SQL, incluido el historial completo. Abre el archivo SQLite en modo de solo lectura. Inicia la app antes de consultarla por primera vez. El volcado contiene hashes de acceso y datos de los usuarios. Mantenlo como material de Administracion.

### Consultar SQLite directamente

Ejecuta este comando desde la carpeta que contiene `estacionamientos.db`. Abre la base en modo de solo lectura y muestra el numero de reserva, cliente, estacionamiento y estado:

```bash
python -c "import sqlite3; db=sqlite3.connect('file:estacionamientos.db?mode=ro', uri=True); print(db.execute('SELECT id, cliente_id, parking_id, estado FROM reservas ORDER BY id').fetchall()); db.close()"
```

En una reserva pendiente, el estacionamiento aparece como `None` porque todavia no tiene plaza asignada.

## Que hace cada rol

| Aplicacion | Flujo |
| --- | --- |
| Usuario | Consulta disponibilidad, solicita, sigue la confirmacion y revisa el monto antes de cancelar. Ve base, recargo, credito y total de sus reservas. |
| Propietario | Ofrece sus plazas, bloquea por horario, retira una franja puntual y usa Vuelvo ahora para recuperar una plaza durante una reserva. |
| Administrador | Crea clientes y propietarios, emite o restablece accesos, vincula plazas, asigna o reasigna, resuelve pendientes sin plaza y registra salidas. |

### Alta de un cliente o propietario

En Administrador, elige **Crear cliente** o **Crear propietario**. En terminal, son las opciones **4** y **5** luego de ingresar. Copia el ID y la clave que se muestran una sola vez y entregalos al titular para que entre a su app. Si se pierde la clave, usa **Emitir o restablecer acceso**. La anterior y sus sesiones quedan invalidadas.

Para un propietario, usa luego **Vincular nueva plaza** y selecciona su ficha. En su app aparecera la plaza como **sin oferta** hasta que el propietario la ofrezca. **Ofrecer plaza** conserva las franjas de bloqueo. **Retirar un bloqueo** elimina solamente el intervalo seleccionado.

## Reglas de negocio

- El propietario tiene prioridad: al bloquear, las reservas afectadas se reubican a un comodin o, si no hay, se cancelan con reembolso total.
- Un estacionamiento no admite dos reservas superpuestas. Se pueden programar turnos consecutivos. Al confirmar un turno que ya comienza, la salida de la ocupacion anterior debe quedar registrada.
- Solo se reserva un estacionamiento ofrecido y sin bloqueos para la franja solicitada. Una solicitud pendiente requiere confirmacion de Administracion. La asignacion y reasignacion rechazan reservas vencidas.
- Duracion de 1 a 2 horas, con anticipacion de 15 minutos a 7 dias. Tarifa de $30 por minuto.
- Cancelacion: reembolso del 100% hasta 1 hora antes, 50% desde ahi hasta el inicio y 0% despues.
- Sobreestadia: desde el minuto 6 de atraso, $60 por minuto.

## Estructura

| Ruta | Contenido |
|---|---|
| `estacionamientos/modelos.py` | Clases del dominio (`Periodo`, `Estacionamiento`, `Reserva`) y sus reglas. |
| `estacionamientos/repositorio.py` | Clase `Repositorio`: acceso a SQLite. |
| `estacionamientos/servicios.py` | Clase `Sistema`: las funcionalidades de cada rol. No imprime ni lee datos. |
| `estacionamientos/db.py` | Esquema SQLite, datos de prueba e historial de operaciones. |
| `estacionamientos/paneles.py` | Operaciones y consultas limitadas a cada rol y cuenta. |
| `estacionamientos/acceso.py` | Configuracion de Administrador, emision de accesos y verificacion de credenciales. |
| `estacionamientos/acciones.py` | Validacion y formato reutilizados por la web, la terminal y el ensayo de negocio. |
| `estacionamientos/consola.py` | Terminal autenticada de Administracion. |
| `estacionamientos/web.py` | Tres aplicaciones web locales con sesiones separadas, formularios y paneles. |
| `docs/documento_tecnico.md` | Modulos, funcionalidades, reglas de negocio y estructura de datos. |

Cada operacion relevante queda en la tabla `historial` con estacionamiento, propietario, cliente, fecha, horas, estado y valor, lista para analizar en la siguiente entrega.

## Decisiones de diseño

- **Logica separada de la interfaz:** asi la terminal y la web comparten las mismas reglas.
- **Operaciones administrativas compartidas:** la terminal y la app de Administrador usan el mismo servicio y las mismas reglas.
- **Tema claro y sobrio en la web:** es una herramienta de trabajo con tablas y formularios, y se pidio una presentacion profesional.
- **Web accesible por teclado y lector de pantalla:** enlace para saltar al contenido, navegacion con nombre, formularios con nombre propio, titulo distinto por rol, foco automatico en el resultado de cada operacion y contraste mayor a 5:1. Sin scroll horizontal desde 320 px de ancho.
- **Modo de simulacion:** permite ensayar fechas, cancelaciones y sobreestadias con un reloj editable.

## Limitaciones

- No incluye pagos reales ni el control de acceso por patente.
- Las apps escuchan solo en `127.0.0.1`. Para uso remoto hacen falta un despliegue con HTTPS y un plan de operacion.
