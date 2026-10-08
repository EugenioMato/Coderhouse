"""Fábrica de clientes: elige el proveedor según la configuración.

Es el punto donde se decide *quién* contesta. El resto del programa trabaja
contra `BaseLLMClient` y no necesita saber qué proveedor hay detrás: cambiar
de uno a otro es cambiar la variable LLM_PROVIDER del .env.
"""

import os

from llm_client.base import BaseLLMClient
from llm_client.gemini_client import GeminiClient
from llm_client.schemas import MODELOS_POR_DEFECTO, Provider

# Qué clase implementa cada proveedor. Sumar uno nuevo es escribir la
# subclase de BaseLLMClient y agregarla acá: nada más del código cambia.
_CLIENTES: dict[str, type[BaseLLMClient]] = {
    "gemini": GeminiClient,
}

# De dónde sale la clave de cada proveedor.
_VARIABLES_DE_CLAVE: dict[str, str] = {
    "gemini": "GEMINI_API_KEY",
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
}


class ProveedorNoImplementado(NotImplementedError):
    """El proveedor es válido pero esta entrega no lo implementa."""


class AsyncLLMManager:
    """Construye el cliente asíncrono que corresponda al proveedor pedido."""

    def __init__(self, provider: Provider | None = None) -> None:
        # Sin argumento, manda el .env; si tampoco está, gemini.
        nombre = provider or os.getenv("LLM_PROVIDER", "gemini")
        self.provider = self._validar(nombre)

    def _validar(self, nombre: str) -> Provider:
        """Acepta sólo los proveedores declarados en el Literal Provider."""
        if nombre not in _VARIABLES_DE_CLAVE:
            validos = ", ".join(sorted(_VARIABLES_DE_CLAVE))
            raise ValueError(
                f"Proveedor desconocido: {nombre!r}. Válidos: {validos}."
            )
        return nombre  # type: ignore[return-value]

    @property
    def modelo_por_defecto(self) -> str:
        return MODELOS_POR_DEFECTO[self.provider]

    def crear_cliente(self, *, max_retries: int = 2) -> BaseLLMClient:
        """Instancia el cliente, con la clave leída del entorno."""
        clase = _CLIENTES.get(self.provider)
        if clase is None:
            raise ProveedorNoImplementado(
                f"El proveedor {self.provider!r} no está implementado en esta "
                "entrega (sólo Gemini). La arquitectura ya lo admite: hace "
                f"falta escribir la subclase de BaseLLMClient y registrarla "
                "en manager._CLIENTES."
            )

        api_key = os.getenv(_VARIABLES_DE_CLAVE[self.provider])
        return clase(api_key, max_retries=max_retries)
