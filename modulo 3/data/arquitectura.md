# Arquitectura del servicio de pagos Lumen

Lumen es la plataforma interna de cobros. Procesa pagos con tarjeta y
transferencias para los productos de la empresa.

## Servicios

El sistema se divide en cuatro servicios desplegados por separado:

- **lumen-api**: la puerta de entrada. Expone la API pública en el puerto
  8080. Construida con FastAPI sobre Python 3.12.
- **lumen-worker**: procesa las tareas en segundo plano (conciliación,
  reintentos, envío de comprobantes). Corre con Celery.
- **lumen-webhooks**: recibe las notificaciones de los proveedores de pago.
  Escucha en el puerto 8081, separado de la API pública para que un pico de
  webhooks no afecte los cobros.
- **lumen-admin**: panel interno de operaciones. Next.js, acceso solo por VPN.

## Flujo de un pago

1. El cliente llama a `POST /v1/intentos` con el monto y el medio de pago.
2. `lumen-api` valida el pedido y crea un registro en estado `pendiente`.
3. Se encola una tarea en RabbitMQ para que el worker contacte al proveedor.
4. El proveedor responde de forma asincrónica vía webhook.
5. `lumen-webhooks` actualiza el estado a `aprobado` o `rechazado`.
6. El worker envía el comprobante por mail y libera el bloqueo de idempotencia.

El paso 3 es asincrónico a propósito: el proveedor de tarjetas tarda entre
1,5 y 4 segundos en responder, y mantener la conexión HTTP abierta durante ese
tiempo agotaba el pool de conexiones bajo carga.

## Idempotencia

Todo pedido de cobro requiere un header `Idempotency-Key`. La clave se guarda
en Redis con un TTL de 24 horas. Si llega un segundo pedido con la misma
clave, se devuelve la respuesta original sin volver a cobrar.

Esta decisión se tomó después del incidente del 3 de marzo, cuando un
reintento del cliente generó cobros duplicados.

## Despliegue

Los cuatro servicios corren en Kubernetes, en el namespace `pagos-prod`.
El despliegue es por GitHub Actions, con estrategia *rolling update* y un
máximo de un pod indisponible a la vez.

Las migraciones de base de datos se corren como un Job de Kubernetes antes de
actualizar los pods, nunca desde el arranque de la aplicación.
