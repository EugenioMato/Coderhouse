"""Clase base abstracta y traducción de errores a respuestas estructuradas.

Acá vive la regla central del cliente: ninguna excepción de un proveedor
escapa hacia quien llama. Todo error (cuota, credenciales, red, caída del
servicio) vuelve como un ModelResponse con `error` cargado y `ok == False`,
así el programa que usa el cliente nunca se rompe por una falla de API.
"""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

from llm_client.schemas import ChatMessage, ModelConfig, ModelResponse, Provider


class BaseLLMClient(ABC):
    """Interfaz común a todos los proveedores.

    Una subclase traduce entre estos esquemas y el SDK de su proveedor.
    Quien usa el cliente trabaja siempre con ChatMessage/ModelConfig/
    ModelResponse y no necesita saber quién contesta del otro lado.
    """

    #: Qué proveedor implementa la subclase; se copia en cada respuesta.
    provider: Provider

    def __init__(self, api_key: str | None, *, max_retries: int = 2) -> None:
        self.api_key = api_key
        self.max_retries = max_retries

    @abstractmethod
    async def generate(
        self, messages: list[ChatMessage], config: ModelConfig
    ) -> ModelResponse:
        """Pide la respuesta completa y la devuelve de una sola vez."""

    @abstractmethod
    def stream(
        self, messages: list[ChatMessage], config: ModelConfig
    ) -> AsyncIterator[str]:
        """Devuelve los fragmentos de texto a medida que llegan.

        No es `async def`: devuelve el generador asíncrono directamente, para
        que quien llama pueda hacer `async for trozo in cliente.stream(...)`
        sin un await previo.
        """

    # -- Helpers para las subclases -------------------------------------

    def _responder_error(self, modelo: str, mensaje: str) -> ModelResponse:
        """Arma la respuesta de un fallo, sin contenido."""
        return ModelResponse(
            provider=self.provider, model=modelo, content="", error=mensaje
        )
