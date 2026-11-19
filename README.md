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

## Como comprobar que los datos se guardan en SQLite

1. Desde la carpeta del proyecto, ejecuta `python -m estacionamientos.web` y abre `http://localhost:8000`.
2. Crea una reserva, anota su numero y comprueba que aparezca en **Reservas**. Abre **Historial (ultimos 50)** para ver el evento `creada`.
3. Deten el servidor con **Ctrl+C**. Inicia la web de nuevo desde la **misma carpeta**. La reserva y su evento deben seguir visibles.
4. Tambien puedes ejecutar `python main.py` desde esa carpeta y elegir **1 Cliente > 3 Ver estado** para ver los mismos datos en la consola.

Cuando ejecutas el proyecto desde el ZIP, usa su carpeta `codigo/`. El archivo `estacionamientos.db` se guarda en la carpeta desde la que iniciaste el programa.

### Mostrar toda la base de datos

Desde la misma carpeta en la que ejecutas la app, usa:

```bash
python -m estacionamientos.db
```

Muestra la estructura y todos los registros en formato SQL, incluido el historial completo. Abre el archivo SQLite en modo de solo lectura. Si todavia no existe `estacionamientos.db`, inicia la app una vez para crearlo.

### Consultar SQLite directamente

Ejecuta este comando desde la carpeta que contiene `estacionamientos.db`. Abre la base en modo de solo lectura y muestra el numero de reserva, cliente, estacionamiento y estado:

```bash
python -c "import sqlite3; db=sqlite3.connect('file:estacionamientos.db?mode=ro', uri=True); print(db.execute('SELECT id, cliente_id, parking_id, estado FROM reservas ORDER BY id').fetchall()); db.close()"
```

En una reserva pendiente, el estacionamiento aparece como `None` porque todavia no tiene plaza asignada.

## Que hace cada rol

| Rol | Funcionalidades |
|---|---|
| Propietario | Liberar y bloquear su estacionamiento. «Vuelvo ahora»: reubica al cliente en un comodin y le acredita el tiempo no usado. |
| Cliente | Reservar, y cancelar con reembolso escalonado. |
| Administrador | Asignar y reasignar reservas, registrar salidas y crear clientes y propietarios. |

### Registrar usuarios desde Administrador

En la terminal, ejecuta `python main.py`, elige **3 Administrador** y luego **4 Crear cliente** o **5 Crear propietario**. Escribe el nombre y anota el ID que muestra la aplicacion. En la version web, ambas opciones aparecen en la pestaña **Administrador**.

SQLite asigna el ID automaticamente. El cliente puede usar su ID para reservar. El alta del propietario solo registra su ficha. Las plazas se administran por separado.

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
