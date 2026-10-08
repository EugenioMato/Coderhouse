# Postmortems de incidentes

## INC-041 — Cobros duplicados (3 de marzo)

**Duración**: 2 horas 40 minutos.
**Impacto**: 847 cobros duplicados, por un total de 1.230.000 pesos.

### Qué pasó

Un cliente grande tenía un reintento automático con un tiempo de espera de
3 segundos. El proveedor de tarjetas estaba respondiendo en 3,5 segundos, así
que cada cobro se enviaba dos veces.

Sin claves de idempotencia, el sistema trataba cada pedido como nuevo.

### Cómo se resolvió

Se devolvió el dinero de los 847 cobros en 48 horas. Se implementó el header
`Idempotency-Key` obligatorio, con las claves en Redis y un índice único en
PostgreSQL como segunda barrera.

### Lección

La idempotencia no es opcional en un sistema de cobros. No alcanza con
documentar que el cliente no debe reintentar: hay que hacer que el reintento
sea inofensivo.

## INC-052 — Agotamiento del pool de conexiones (17 de junio)

**Duración**: 55 minutos.
**Impacto**: 12 % de los pedidos devolvieron HTTP 503.

### Qué pasó

Una campaña de marketing multiplicó el tráfico por seis sin aviso. Cada pod
tenía el pool en 50 conexiones y había 6 pods: 300 conexiones contra un límite
de 200 en PostgreSQL.

La base empezó a rechazar conexiones nuevas, incluidas las del worker, así que
la cola de `pagos.procesar` dejó de drenar.

### Cómo se resolvió

Se bajó el pool a 20 conexiones por pod y se agregó PgBouncer en modo
*transaction*. El límite de la instancia se dejó en 200, pero ahora el total
pedido es 150.

### Lección

El pool de conexiones se dimensiona desde el límite de la base hacia los pods,
no al revés. Y hace falta una alerta sobre el porcentaje de conexiones en uso,
no solo sobre la latencia.

## INC-068 — Pérdida de mensajes en la cola de comprobantes (2 de septiembre)

**Duración**: 6 horas hasta detectarlo.
**Impacto**: 2.104 clientes no recibieron su comprobante.

### Qué pasó

Un despliegue cambió la confirmación de los mensajes de manual a automática
por error. Los consumidores confirmaban al recibir el mensaje, antes de enviar
el mail. Cuando el proveedor de mails empezó a dar errores 500, los mensajes
ya estaban confirmados y se perdieron.

No se detectó por monitoreo: lo reportó un cliente.

### Cómo se resolvió

Se volvió a la confirmación manual. Se reconstruyeron los 2.104 comprobantes
desde la tabla `movimientos` y se reenviaron.

Se agregó una alerta sobre la diferencia entre pagos aprobados y comprobantes
enviados en la última hora.

### Lección

La confirmación automática es aceptable solo cuando perder el mensaje no
importa. En todo lo demás, se confirma después de que el trabajo esté hecho.
