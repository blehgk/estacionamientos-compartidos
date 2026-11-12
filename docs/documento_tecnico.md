# Documento tecnico: Entrega 2: Estacionamientos Compartidos

## 1. Organizacion modular
| Modulo | Responsabilidad |
|---|---|
| `estacionamientos/db.py` | Conexion SQLite, esquema, datos de prueba (`sembrar`) y registro del historial (`registrar`). |
| `estacionamientos/servicios.py` | Reglas de negocio y las 6 funcionalidades. No usa `input()` ni `print()`. Las violaciones de reglas lanzan `ReglaError`. |
| `estacionamientos/acciones.py` | Definicion unica de las acciones, formularios y vistas. La terminal y la web se generan desde aqui, por lo que ofrecen lo mismo y muestran los mismos mensajes y formatos. |
| `estacionamientos/consola.py` | Menus de terminal generados desde `acciones.py`: pide los datos, confirma la cancelacion y muestra el estado (reservas, estacionamientos, historial y credito). |
| `estacionamientos/web.py` | Front web opcional (servidor `http.server` de la libreria estandar). Se inicia con `python -m estacionamientos.web` y se abre en `http://localhost:8000`. |
| `main.py` | Punto de entrada de la version de terminal. |

Decision de diseño: toda funcion de negocio recibe la conexion y la hora (`ahora`), de modo que se prueba sin depender del reloj y la demo puede simular horas.

## 2. Funcionalidades
| Usuario | Obligatoria | Propia |
|---|---|---|
| Propietario | `liberar`, `bloquear` | `vuelvo_ahora` |
| Cliente | `reservar`, `cancelar` | Cancelacion con reembolso escalonado (dentro de `cancelar`/`reembolso`) |
| Administrador | `asignar`, `reasignar` | `registrar_salida` (sobreestadia) |

- **Reservar:** valida duracion, anticipacion y que exista un estacionamiento compatible; la reserva queda `pendiente`.
- **Asignar:** el administrador confirma la reserva en un estacionamiento normal, liberado y sin conflicto.
- **Reasignar:** mueve una reserva a otro estacionamiento (incluye comodines) tras verificar que no haya conflicto.
- **Liberar:** deja el estacionamiento disponible y quita sus bloqueos vigentes. Solo lo puede usar su propietario.
- **Bloquear:** solo el propietario del estacionamiento (nunca un comodin); crea un bloqueo; las reservas afectadas se reubican a un comodin libre o, si no hay, se cancelan con reembolso total.
- **Vuelvo ahora:** bloquea desde el momento actual hasta el fin de la reserva, reubica al cliente y le acredita el tiempo no utilizado.
- **Registrar salida:** cierra la reserva y cobra el recargo por sobreestadia.

## 3. Reglas de negocio implementadas
| Regla | Donde |
|---|---|
| RN01 Prioridad del propietario | `bloquear` y `vuelvo_ahora`: el bloqueo siempre se aplica y desplaza al cliente. |
| RN02 No superposicion | `hay_conflicto` (intervalos semiabiertos: una reserva puede empezar justo cuando termina otra). |
| RN03 Disponibilidad | `estacionamientos_compatibles` y `_parking_apto`: solo `liberado`, no bloqueado y sin conflicto. |
| RN04 Consistencia de estados | Cada operacion actualiza reserva, credito e historial en conjunto. |
| RN05 (propia) Reembolso escalonado | `reembolso`: 100% hasta 1 h antes del inicio, 50% desde ahi hasta el inicio, 0% despues. |
| RN05 (propia) Sobreestadia | `registrar_salida`: desde el minuto 6 de atraso, $60 por minuto (`60 × (atraso − 5)`). |
| Duracion y anticipacion | `reservar`: 60–120 min; 15 min a 7 dias de anticipacion. Tarifa $30/min. |

## 4. Estructura de datos (SQLite, `estacionamientos.db`)
- `propietarios(id, nombre)`
- `clientes(id, nombre, credito)`
- `estacionamientos(id, propietario_id, tipo [normal|comodin], estado [liberado|bloqueado])`
- `bloqueos(id, parking_id, inicio, fin, motivo)`
- `reservas(id, parking_id, cliente_id, inicio, fin, estado, monto)`; estados: `pendiente`, `confirmada`, `en_curso`, `cerrada`, `cancelada`, `reubicada`.
- `historial(id, ts, evento, reserva_id, parking_id, propietario_id, cliente_id, inicio, fin, estado, valor, detalle)`: una fila por cada creacion, asignacion, reasignacion, bloqueo, liberacion, reubicacion, cancelacion, «vuelvo ahora» y cierre. Permite reconstruir estacionamiento, propietario, cliente, fecha, hora de inicio y termino, estado y valor para la Entrega 3.

## 5. Limitaciones conocidas
Sin pagos reales, sin reparto 70/15/15, sin no presentacion a los 20 minutos y sin control de acceso por patente. El nivel «En observacion» del propietario tampoco esta implementado.
