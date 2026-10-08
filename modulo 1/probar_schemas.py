"""Prueba manual de los esquemas de schemas.py."""

import sys

from pydantic import ValidationError

# La consola de Windows (cp1252) no puede imprimir los emojis de abajo.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from llm_client.schemas import ChatMessage, ModelConfig, ModelResponse, TokenUsage

# 1) Casos válidos
mensaje = ChatMessage(role="user", content="¿Qué es la entropía?")
config = ModelConfig(model="gemini-flash", temperature=0.3, max_tokens=200)
print("Mensaje OK:", mensaje)
print("Config OK:", config)
print("Como diccionario:", config.model_dump())

# 2) Casos inválidos: cada uno debe fallar con un error claro
casos_invalidos = [
    lambda: ChatMessage(role="robot", content="hola"),
    lambda: ChatMessage(role="user", content=""),
    lambda: ModelConfig(model="x", temperature=3),
    lambda: ModelConfig(model="x", max_tokens=0),
    lambda: ModelConfig(model="x", temprature=0.5),
]
for crear in casos_invalidos:
    try:
        crear()
        print("❌ No falló (y debería)")
    except ValidationError as error:
        print("✅ Rechazado:", error.errors()[0]["msg"])

# 3) Respuestas: una exitosa y una con error
exito = ModelResponse(
    provider="gemini",
    model="gemini-flash",
    content="La entropía mide el desorden...",
    usage=TokenUsage(input_tokens=8, output_tokens=40),
)
falla = ModelResponse(provider="openai", model="gpt", error="API key inválida")
print("Éxito:", exito.ok, "| tokens totales:", exito.usage.total_tokens)
print("Falla:", falla.ok, "| error:", falla.error)