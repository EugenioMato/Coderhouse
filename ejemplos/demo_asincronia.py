"""Demo: por qué importa async/await (no forma parte del cliente)."""

import asyncio
import time


async def pedir_al_llm(nombre: str, segundos: float) -> str:
    """Simula una llamada a un LLM que tarda 'segundos' en responder."""
    print(f"  → Pregunta enviada: {nombre}")
    await asyncio.sleep(segundos)  # espera SIN bloquear: el loop atiende otras tareas
    print(f"  ← Respuesta recibida: {nombre}")
    return f"respuesta de {nombre}"


async def pedir_bloqueando(nombre: str, segundos: float) -> str:
    """El error clásico: una espera síncrona dentro de una función async."""
    print(f"  → Pregunta enviada: {nombre}")
    time.sleep(segundos)  # BLOQUEA: congela todo el programa
    print(f"  ← Respuesta recibida: {nombre}")
    return f"respuesta de {nombre}"


async def main() -> None:
    print("1) Una detrás de otra (secuencial):")
    inicio = time.perf_counter()
    await pedir_al_llm("A", 1)
    await pedir_al_llm("B", 1)
    await pedir_al_llm("C", 1)
    print(f"   Tardó {time.perf_counter() - inicio:.1f} s\n")

    print("2) Las tres a la vez (concurrente, con asyncio.gather):")
    inicio = time.perf_counter()
    await asyncio.gather(
        pedir_al_llm("A", 1),
        pedir_al_llm("B", 1),
        pedir_al_llm("C", 1),
    )
    print(f"   Tardó {time.perf_counter() - inicio:.1f} s\n")

    print("3) Las tres a la vez, pero con time.sleep (bloqueante):")
    inicio = time.perf_counter()
    await asyncio.gather(
        pedir_bloqueando("A", 1),
        pedir_bloqueando("B", 1),
        pedir_bloqueando("C", 1),
    )
    print(f"   Tardó {time.perf_counter() - inicio:.1f} s  ← ¡el event loop quedó congelado!")


asyncio.run(main())