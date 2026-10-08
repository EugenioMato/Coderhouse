"""Script de validación del cliente unificado de LLMs.

Ejercita las tres cosas que tiene que demostrar la entrega:

  1. Generación asíncrona normal (se espera la respuesta completa).
  2. Streaming (los fragmentos se imprimen a medida que llegan).
  3. Manejo de errores: una clave inválida devuelve un error estructurado
     y el programa sigue corriendo en lugar de cortarse.

Correr con:  .venv\\Scripts\\python.exe main.py
"""

import asyncio
import os
import sys

from dotenv import load_dotenv

# La consola de Windows usa cp1252 por defecto y no puede imprimir acentos ni
# flechas: sin esto, el script muere con UnicodeEncodeError al mostrar texto
# en español. `errors="replace"` evita que un carácter raro corte la corrida.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from llm_client import (
    AsyncLLMManager,
    ChatMessage,
    GeminiClient,
    ModelConfig,
    ModelResponse,
)

PREGUNTA = "¿Qué es la entropía?"


def titulo(texto: str) -> None:
    print(f"\n{'=' * 60}\n{texto}\n{'=' * 60}")


def mostrar_respuesta(respuesta: ModelResponse) -> None:
    """Imprime una respuesta, haya salido bien o mal."""
    if not respuesta.ok:
        print(f"[falló] {respuesta.error}")
        return

    print(respuesta.content)
    if respuesta.usage:
        print(
            f"\n  tokens → entrada: {respuesta.usage.input_tokens}"
            f" | salida: {respuesta.usage.output_tokens}"
            f" | total: {respuesta.usage.total_tokens}"
        )


def armar_mensajes() -> list[ChatMessage]:
    return [
        ChatMessage(
            role="system",
            content="Sos un divulgador científico. Respondé en dos oraciones.",
        ),
        ChatMessage(role="user", content=PREGUNTA),
    ]


async def probar_generacion(cliente, config: ModelConfig) -> None:
    titulo("1) Generación normal (await)")
    print(f"Pregunta: {PREGUNTA}\n")
    respuesta = await cliente.generate(armar_mensajes(), config)
    mostrar_respuesta(respuesta)


async def probar_streaming(cliente, config: ModelConfig) -> None:
    titulo("2) Streaming (async for + yield)")
    print(f"Pregunta: {PREGUNTA}\n")

    fragmentos = 0
    # flush=True para ver el texto aparecer de a poco, sin que se acumule
    # en el buffer de la consola.
    async for trozo in cliente.stream(armar_mensajes(), config):
        print(trozo, end="", flush=True)
        fragmentos += 1

    print(f"\n\n  llegaron {fragmentos} fragmentos")


async def probar_manejo_de_errores(config: ModelConfig) -> None:
    titulo("3) Manejo de errores: clave inválida")
    print("Se usa una clave falsa a propósito.\n")

    roto = GeminiClient("clave-que-no-existe")

    respuesta = await roto.generate(armar_mensajes(), config)
    print(f"  generate → ok={respuesta.ok}")
    print(f"  error: {respuesta.error}")

    print("\n  stream →")
    async for trozo in roto.stream(armar_mensajes(), config):
        print(f"    {trozo}")

    print("\n  El programa siguió corriendo: no hubo excepción sin atrapar.")


async def probar_concurrencia(cliente, config: ModelConfig) -> None:
    """Dos preguntas a la vez, para que se vea el beneficio del async."""
    titulo("4) Dos llamadas en paralelo (asyncio.gather)")

    preguntas = ["¿Qué es la entropía?", "¿Qué es un agujero negro?"]
    tareas = [
        cliente.generate([ChatMessage(role="user", content=p)], config)
        for p in preguntas
    ]
    respuestas = await asyncio.gather(*tareas)

    for pregunta, respuesta in zip(preguntas, respuestas):
        print(f"\n  {pregunta}")
        if respuesta.ok:
            print(f"    {respuesta.content.strip()[:150]}")
        else:
            print(f"    [falló] {respuesta.error}")


async def main() -> None:
    load_dotenv()

    manager = AsyncLLMManager()
    cliente = manager.crear_cliente()
    config = ModelConfig(
        model=manager.modelo_por_defecto, temperature=0.3, max_tokens=300
    )

    print(f"Proveedor: {manager.provider}  |  Modelo: {config.model}")
    if not os.getenv("GEMINI_API_KEY"):
        print("\n[aviso] No hay GEMINI_API_KEY en el .env: todo va a dar error")
        print("        controlado. Copiá .env.example a .env y poné tu clave.")

    await probar_generacion(cliente, config)
    await probar_streaming(cliente, config)
    await probar_manejo_de_errores(config)
    await probar_concurrencia(cliente, config)

    print(f"\n{'=' * 60}\nListo.\n")


if __name__ == "__main__":
    asyncio.run(main())
