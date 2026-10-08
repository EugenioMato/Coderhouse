# Base de datos de Lumen

Motor: PostgreSQL 16, instancia administrada con una réplica de lectura.

## Tablas principales

### `intentos_de_pago`

El corazón del sistema. Un registro por intento de cobro.

| Columna | Tipo | Nota |
|---|---|---|
| `id` | `uuid` | Clave primaria, generada por la aplicación. |
| `monto_centavos` | `bigint` | En centavos, nunca en decimal. |
| `moneda` | `char(3)` | Código ISO 4217. |
| `estado` | `text` | `pendiente`, `aprobado`, `rechazado`, `expirado`. |
| `clave_idempotencia` | `text` | Único junto con `comercio_id`. |
| `creado_en` | `timestamptz` | Siempre en UTC. |

Los montos se guardan en centavos como entero porque el tipo `float` arrastra
errores de redondeo: un cobro de 10,10 se convertía en 10,099999.

### `movimientos`

Libro contable de solo escritura. No se actualiza ni se borra: una corrección
es un movimiento nuevo con signo opuesto. Esto permite reconstruir el saldo de
cualquier momento sumando los movimientos hasta esa fecha.

### `comercios`

Datos de los comercios habilitados, con sus credenciales de proveedor
cifradas con `pgcrypto`.

## Índices

- `intentos_de_pago(comercio_id, creado_en DESC)` — para el listado del panel,
  que siempre filtra por comercio y ordena por fecha.
- `intentos_de_pago(clave_idempotencia, comercio_id)` — único, hace cumplir la
  idempotencia a nivel de base de datos y no solo en Redis.
- `movimientos(intento_id)` — para reconstruir el detalle de un pago.

No hay índice sobre `estado`: tiene solo cuatro valores posibles y el
planificador prefiere un *sequential scan*. Agregarlo empeoró las escrituras
sin mejorar las consultas.

## Pool de conexiones

El pool se configuró en 20 conexiones por pod, con un máximo de 5 adicionales
de desborde. Con 6 pods, el total son 150 conexiones contra un límite de 200
en la instancia.

Los 50 restantes quedan reservados para las migraciones y el acceso manual de
operaciones.

## Respaldos

Respaldo completo diario a las 04:00 UTC, con retención de 30 días.
Archivado continuo de WAL, que permite recuperación a un punto en el tiempo
con una ventana de 7 días.

La restauración se prueba el primer lunes de cada mes sobre un entorno
descartable. Un respaldo que no se probó no es un respaldo.
