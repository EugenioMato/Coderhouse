# Caché y colas en Lumen

## Redis

Una instancia de Redis 7 en modo *cluster*, con tres nodos primarios y una
réplica cada uno.

### Para qué se usa

**Claves de idempotencia.** Prefijo `idem:`, TTL de 24 horas. Es el uso más
crítico: si Redis se cae, la API rechaza los cobros nuevos en lugar de
arriesgar un cobro duplicado. Se eligió fallar antes que cobrar dos veces.

**Caché de datos de comercio.** Prefijo `com:`, TTL de 10 minutos. Evita
consultar PostgreSQL en cada pedido para traer la configuración del comercio,
que casi nunca cambia.

**Límite de tasa.** Prefijo `rl:`, ventana deslizante de 60 segundos. El
límite es de 300 pedidos por minuto por comercio.

### Política de memoria

`maxmemory-policy` en `volatile-lru`: cuando se llena, descarta las claves con
TTL menos usadas. Nunca descarta claves sin TTL, por eso toda clave escrita
lleva expiración obligatoria.

El límite de memoria es 4 GB por nodo. Con el volumen actual se usa alrededor
del 35 %.

## RabbitMQ

Tres colas, todas durables y con confirmación manual:

| Cola | Para qué | Reintentos |
|---|---|---|
| `pagos.procesar` | Contactar al proveedor y cobrar. | 5, con espera exponencial |
| `pagos.comprobantes` | Enviar el mail al cliente. | 3 |
| `pagos.conciliacion` | Cotejar con el reporte diario del proveedor. | 1 |

### Cola de mensajes muertos

Cada cola tiene su *dead letter queue* con el sufijo `.dlq`. Un mensaje que
agota los reintentos cae ahí y dispara una alerta en el canal
`#pagos-alertas`.

Los mensajes de la DLQ se revisan a mano. No se reencolan de forma automática:
un mensaje que falló cinco veces casi nunca se arregla solo, y reencolarlo
automáticamente esconde el problema de fondo.

### Confirmación manual

Los consumidores confirman el mensaje recién después de escribir en
PostgreSQL. Si el worker muere a mitad del procesamiento, el mensaje vuelve a
la cola.

Esto implica que un mensaje puede procesarse dos veces, por eso toda tarea es
idempotente: antes de cobrar, el worker verifica el estado actual del intento
en la base.
