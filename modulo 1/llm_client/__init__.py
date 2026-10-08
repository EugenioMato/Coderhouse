"""Paquete del cliente unificado de LLMs.

Uso típico:

    from llm_client import AsyncLLMManager, ChatMessage, ModelConfig

    cliente = AsyncLLMManager().crear_cliente()
    respuesta = await cliente.generate(mensajes, config)
"""

from llm_client.base import BaseLLMClient
from llm_client.gemini_client import GeminiClient
from llm_client.manager import AsyncLLMManager, ProveedorNoImplementado
from llm_client.schemas import (
    MODELOS_POR_DEFECTO,
    ChatMessage,
    ModelConfig,
    ModelResponse,
    Provider,
    Role,
    TokenUsage,
)

__all__ = [
    "MODELOS_POR_DEFECTO",
    "AsyncLLMManager",
    "BaseLLMClient",
    "ChatMessage",
    "GeminiClient",
    "ModelConfig",
    "ModelResponse",
    "Provider",
    "ProveedorNoImplementado",
    "Role",
    "TokenUsage",
]
