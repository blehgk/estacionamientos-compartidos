# Estacionamientos compartidos

Prototipo en Python para compartir estacionamientos de un edificio: el propietario libera su espacio cuando no lo usa, el cliente lo reserva y el administrador asigna y reasigna. Proyecto de ciclo basico de Ingenieria Civil Informatica (Entrega 2).

Usa solo la libreria estandar de Python (3.10 o superior) y SQLite. No hay nada que instalar.

## Uso

Version de terminal:

```bash
python main.py
```

Version web, abierta en `http://localhost:8000`:

```bash
python -m estacionamientos.web
```

Los datos se guardan en `estacionamientos.db`, en la carpeta desde la que se ejecuta. Se crea sola con datos de prueba: propietarios 1 y 2, clientes 1 y 2, estacionamientos 1 y 2 normales y el 3 como comodin.

## Que hace cada rol

| Rol | Funcionalidades |
|---|---|
| Propietario | Liberar y bloquear su estacionamiento. «Vuelvo ahora»: reubica al cliente en un comodin y le acredita el tiempo no usado. |
| Cliente | Reservar, y cancelar con reembolso escalonado. |
| Administrador | Asignar y reasignar reservas, y registrar la salida con recargo por sobreestadia. |

## Reglas de negocio

- El propietario tiene prioridad: al bloquear, las reservas afectadas se reubican a un comodin o, si no hay, se cancelan con reembolso total.
- Un estacionamiento no puede tener dos reservas superpuestas. Una reserva puede empezar justo cuando termina otra.
- Solo se reserva un estacionamiento liberado y sin bloqueos.
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
| `estacionamientos/acciones.py` | Acciones, formularios y vistas compartidos por la terminal y la web. |
| `estacionamientos/consola.py` | Menus de terminal, generados desde `acciones.py`. |
| `estacionamientos/web.py` | Interfaz web, generada desde `acciones.py`. |
| `docs/documento_tecnico.md` | Modulos, funcionalidades, reglas de negocio y estructura de datos. |

Cada operacion relevante queda en la tabla `historial` con estacionamiento, propietario, cliente, fecha, horas, estado y valor, lista para analizar en la siguiente entrega.

## Decisiones de diseño

- **Logica separada de la interfaz:** asi la terminal y la web comparten las mismas reglas.
- **Una sola definicion de acciones:** la terminal y la web ofrecen lo mismo por construccion.
- **Tema claro y sobrio en la web:** es una herramienta de trabajo con tablas y formularios, y se pidio una presentacion profesional.
- **Web accesible por teclado y lector de pantalla:** enlace para saltar al contenido, navegacion con nombre, formularios con nombre propio, titulo distinto por rol, foco automatico en el resultado de cada operacion y contraste mayor a 5:1. Sin scroll horizontal desde 320 px de ancho.
- **Hora de la operacion opcional:** permite simular horas para probar cancelaciones y sobreestadias sin esperar.

## Limitaciones

- No hay inicio de sesion: el rol se elige desde la interfaz.
- El propietario se valida por su numero, sin contraseña.
- No incluye pagos reales ni el control de acceso por patente.
- La interfaz web esta pensada para usarse en el propio equipo (escucha solo en `127.0.0.1`).
