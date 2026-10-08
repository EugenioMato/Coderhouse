"""Script de prueba del pipeline de extracción.

Corre cuatro casos, de más fácil a más hostil:

  1. Descripción de arquitectura (el ejemplo del enunciado).
  2. Log de error con stack trace: otro formato de entrada.
  3. Texto ambiguo: la prueba de estrés — ver si el modelo se recupera o si
     el validador rechaza la respuesta.
  4. Varios textos en paralelo con asyncio.gather.

Correr con:  .venv\\Scripts\\python.exe main.py
"""

import asyncio
import logging
import sys

from chain import process_text
from schemas import ExtraccionTecnica

# La consola de Windows usa cp1252 y no puede imprimir acentos: sin esto, el
# script muere con UnicodeEncodeError al mostrar los resultados.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(
    level=logging.INFO,
    format="  [%(levelname)s] %(message)s",
)
# El SDK de Google y httpx loguean cada pedido HTTP; con eso no se leen los
# logs propios del pipeline.
for ruidoso in ("httpx", "google_genai", "langchain_google_genai"):
    logging.getLogger(ruidoso).setLevel(logging.WARNING)


ARQUITECTURA = (
    "El servicio de pagos corre sobre FastAPI con caché en Redis y "
    "persistencia en PostgreSQL. Bajo carga alta se agota el pool de "
    "conexiones y la API empieza a devolver 503 en producción."
)

LOG_DE_ERROR = (
    "2026-10-07 03:14:22 ERROR [worker-3] celery.app.trace: "
    "Task procesar_factura[8f2a] raised unexpected: "
    "OperationalError('could not connect to server: Connection refused') "
    'File "/app/db.py", line 47, in get_session '
    "engine = create_engine(settings.POSTGRES_DSN) "
    "-- reintentos agotados tras 5 intentos, cola de RabbitMQ creciendo."
)

TEXTO_AMBIGUO = (
    "Estuvimos viendo el tema ese que quedó pendiente de la reunión. "
    "Parece que había algo raro con lo del otro día, así que lo dejamos "
    "para más adelante cuando haya tiempo."
)

CONCURRENTES = [
    "Migramos el frontend de Vue a React y el bundler de Webpack a Vite; "
    "los tiempos de build bajaron a la mitad.",
    "Kafka está acumulando lag en el topic de eventos y los consumidores "
    "en Go no alcanzan a procesar; riesgo de pérdida de mensajes.",
    "Agregamos tests de integración con pytest sobre el cliente de Stripe; "
    "nada urgente, es deuda técnica que veníamos arrastrando.",
]


def titulo(texto: str) -> None:
    print(f"\n{'=' * 64}\n{texto}\n{'=' * 64}")


def mostrar(resultado: ExtraccionTecnica | None) -> None:
    if resultado is None:
        print("\n  Sin resultado válido (ver los logs de arriba).")
        return
    print(f"\n{resultado.model_dump_json(indent=2)}")


async def caso_arquitectura() -> None:
    titulo("1) Descripción de arquitectura")
    print(f"Entrada: {ARQUITECTURA[:80]}...\n")
    mostrar(await process_text(ARQUITECTURA))


async def caso_log() -> None:
    titulo("2) Log de error (otro formato de entrada)")
    print(f"Entrada: {LOG_DE_ERROR[:80]}...\n")
    mostrar(await process_text(LOG_DE_ERROR))


async def caso_ambiguo() -> None:
    titulo("3) Prueba de estrés: texto ambiguo, sin tecnologías")
    print(f"Entrada: {TEXTO_AMBIGUO[:80]}...\n")
    print("Se espera que falle la validación: el esquema exige al menos una")
    print("tecnología, y este texto no menciona ninguna.\n")

    resultado = await process_text(TEXTO_AMBIGUO)
    mostrar(resultado)

    if resultado is None:
        print("\n  El validador rechazó la respuesta y el pipeline devolvió")
        print("  None en lugar de romperse. Es el comportamiento buscado.")
    else:
        print("\n  El modelo encontró algo que interpretó como tecnología.")
        print("  El objeto es válido, aunque el texto fuera vago.")


async def caso_concurrente() -> None:
    titulo("4) Tres textos en paralelo (asyncio.gather)")

    resultados = await asyncio.gather(*(process_text(t) for t in CONCURRENTES))

    for texto, resultado in zip(CONCURRENTES, resultados):
        print(f"\n  {texto[:62]}...")
        if resultado is None:
            print("    sin resultado válido")
            continue
        print(f"    tecnologías: {', '.join(resultado.tecnologias)}")
        print(f"    criticidad:  {resultado.nivel_de_criticidad.value}")


async def main() -> None:
    print("Pipeline de extracción de entidades técnicas")

    await caso_arquitectura()
    await caso_log()
    await caso_ambiguo()
    await caso_concurrente()

    print(f"\n{'=' * 64}\nListo.\n")


if __name__ == "__main__":
    asyncio.run(main())
