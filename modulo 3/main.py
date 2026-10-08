"""Pruebas del sistema RAG.

Tres bloques:

  1. Preguntas cuya respuesta está en los documentos.
  2. Preguntas trampa: no están en los documentos, y el modelo tiene que
     admitirlo en lugar de inventar.
  3. Inspección del retriever: qué fragmentos recupera y con qué score.

Requiere haber corrido antes la ingesta:

    .venv\\Scripts\\python.exe ingesta.py
    .venv\\Scripts\\python.exe main.py
"""

import asyncio
import logging
import sys

from rag import RespuestaRAG, get_rag_response, recuperar_fragmentos

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(level=logging.INFO, format="  [%(levelname)s] %(message)s")
# El SDK, httpx y chromadb loguean cada operación; con eso no se leen los
# logs propios del pipeline.
for ruidoso in ("httpx", "google_genai", "langchain_google_genai", "chromadb"):
    logging.getLogger(ruidoso).setLevel(logging.WARNING)


RESPONDIBLES = [
    "¿Cuánto dura el TTL de las claves de idempotencia y por qué?",
    "¿Qué pasó en el incidente INC-052 y cómo se resolvió?",
    "¿Por qué los montos se guardan en centavos y no como decimal?",
]

# Trampas de dos tipos: una sobre un tema que la documentación no toca, y dos
# que se parecen mucho al contenido pero piden un dato que no está. Las
# segundas son las difíciles: el retriever va a traer fragmentos con score
# alto, y el modelo tiene que darse cuenta igual de que el dato falta.
TRAMPAS = [
    "¿Cuál es el sueldo promedio del equipo de infraestructura?",
    "¿Cuántos nodos tiene el cluster de Kafka?",
    "¿Qué versión de MongoDB usa el servicio de pagos?",
]


def titulo(texto: str) -> None:
    print(f"\n{'=' * 66}\n{texto}\n{'=' * 66}")


def mostrar(respuesta: RespuestaRAG | None) -> None:
    if respuesta is None:
        print("    (sin resultado: ver los logs)")
        return

    marca = "✅" if respuesta.tiene_respuesta else "🚫"
    print(f"    {marca} tiene_respuesta = {respuesta.tiene_respuesta}")
    print(f"    {respuesta.respuesta}")
    if respuesta.fuentes:
        print(f"    fuentes: {', '.join(respuesta.fuentes)}")


async def probar_respondibles() -> int:
    titulo("1) Preguntas que SÍ están en los documentos")

    aciertos = 0
    for pregunta in RESPONDIBLES:
        print(f"\n  ❓ {pregunta}")
        respuesta = await get_rag_response(pregunta)
        mostrar(respuesta)
        if respuesta and respuesta.tiene_respuesta:
            aciertos += 1

    print(f"\n  → {aciertos}/{len(RESPONDIBLES)} respondidas con el contexto")
    return aciertos


async def probar_trampas() -> int:
    titulo("2) Preguntas trampa: la respuesta NO está en los documentos")
    print("Lo correcto es que diga que no sabe, no que invente.")

    correctas = 0
    for pregunta in TRAMPAS:
        print(f"\n  ❓ {pregunta}")
        respuesta = await get_rag_response(pregunta)
        mostrar(respuesta)
        if respuesta and not respuesta.tiene_respuesta:
            correctas += 1
        elif respuesta:
            print("    ⚠️  ALUCINACIÓN: respondió algo que no está en los docs")

    print(f"\n  → {correctas}/{len(TRAMPAS)} admitieron no tener la información")
    return correctas


async def inspeccionar_retriever() -> None:
    titulo("3) Qué recupera la búsqueda semántica")
    print("Los fragmentos que el LLM recibe como contexto, con su score.")

    consulta = "reintentos de la cola de comprobantes"
    print(f"\n  Consulta: {consulta}\n")

    for documento, score in await recuperar_fragmentos(consulta):
        fuente = documento.metadata.get("fuente", "?")
        numero = documento.metadata.get("fragmento", "?")
        inicio = documento.page_content[:70].replace("\n", " ")
        print(f"    {score:.3f}  {fuente}#{numero}  {inicio}...")


async def main() -> None:
    print("Sistema de recuperación semántica (RAG) sobre documentación interna")

    aciertos = await probar_respondibles()
    correctas = await probar_trampas()
    await inspeccionar_retriever()

    titulo("Resumen")
    print(f"  Preguntas respondidas con el contexto:  {aciertos}/{len(RESPONDIBLES)}")
    print(f"  Trampas detectadas (sin alucinar):      {correctas}/{len(TRAMPAS)}")
    print()


if __name__ == "__main__":
    asyncio.run(main())
