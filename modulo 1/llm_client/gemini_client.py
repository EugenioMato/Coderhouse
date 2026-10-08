"""Adaptador de Google Gemini sobre el SDK `google-genai`.

Traduce entre los esquemas del proyecto y la API de Gemini, que tiene tres
diferencias que hay que salvar acá y no en los esquemas:

1. El mensaje `system` no va en la lista de contenidos: va aparte, en
   `system_instruction`.
2. Los roles de Gemini son `user` y `model`; el nuestro es `assistant`.
3. `max_tokens` se llama `max_output_tokens`.
"""

import httpx
from collections.abc import AsyncIterator

from google import genai
from google.genai import errors, types

from llm_client.base import BaseLLMClient
from llm_client.schemas import ChatMessage, ModelConfig, ModelResponse, TokenUsage

# Códigos HTTP que Gemini devuelve cuando el problema es la credencial.
_CODIGOS_DE_CREDENCIAL = (400, 401, 403)


class GeminiClient(BaseLLMClient):
    """Cliente asíncrono de Gemini."""

    provider = "gemini"

    def __init__(self, api_key: str | None, *, max_retries: int = 2) -> None:
        super().__init__(api_key, max_retries=max_retries)
        # El SDK no valida la clave al construirse: si falta, el error recién
        # aparecería en la primera llamada. Lo detectamos antes.
        # Los reintentos ante fallas transitorias los hace el propio SDK;
        # acá sólo se fija cuántos, en lugar de escribir un retry a mano.
        self._cliente = (
            genai.Client(
                api_key=api_key,
                http_options=types.HttpOptions(
                    retry_options=types.HttpRetryOptions(attempts=max_retries)
                ),
            )
            if api_key
            else None
        )

    # -- Traducción de entrada ------------------------------------------

    def _separar_system(
        self, messages: list[ChatMessage]
    ) -> tuple[str | None, list[types.Content]]:
        """Parte los mensajes en (instrucción de sistema, resto del diálogo)."""
        instrucciones: list[str] = []
        contenidos: list[types.Content] = []

        for mensaje in messages:
            if mensaje.role == "system":
                instrucciones.append(mensaje.content)
                continue
            rol = "model" if mensaje.role == "assistant" else "user"
            contenidos.append(
                types.Content(role=rol, parts=[types.Part(text=mensaje.content)])
            )

        system = "\n\n".join(instrucciones) if instrucciones else None
        return system, contenidos

    def _armar_config(
        self, config: ModelConfig, system: str | None
    ) -> types.GenerateContentConfig:
        return types.GenerateContentConfig(
            temperature=config.temperature,
            max_output_tokens=config.max_tokens,
            top_p=config.top_p,
            system_instruction=system,
            # Los modelos Gemini 3.x razonan antes de responder, y ese
            # razonamiento se descuenta de max_output_tokens: con el thinking
            # activado, un max_tokens chico se consume pensando y la respuesta
            # llega cortada (finish_reason=MAX_TOKENS). Para un cliente de
            # propósito general preferimos la respuesta completa.
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        )

    # -- Traducción de errores ------------------------------------------

    def _traducir_error(self, error: Exception) -> str:
        """Convierte una excepción del SDK en un mensaje legible.

        Gemini no tiene clases propias para cuota ni credenciales (a
        diferencia de los SDK de OpenAI y Anthropic): todo llega como
        ClientError (4xx) o ServerError (5xx), y hay que mirar el código.
        """
        if isinstance(error, errors.ClientError):
            if error.code == 429:
                return "Límite de cuota alcanzado: esperá un momento y reintentá."
            if error.code in _CODIGOS_DE_CREDENCIAL:
                return f"Credenciales inválidas o pedido rechazado: {error.message}"
            return f"Error del pedido ({error.code}): {error.message}"

        if isinstance(error, errors.ServerError):
            return f"El proveedor no está disponible ({error.code}): reintentá luego."

        if isinstance(error, (httpx.TimeoutException, TimeoutError)):
            return "Se agotó el tiempo de espera de la conexión."

        if isinstance(error, httpx.HTTPError):
            return f"Error de conexión con el proveedor: {error}"

        # Último recorte de red: que nada escape como crash.
        return f"Error inesperado ({type(error).__name__}): {error}"

    # -- API pública ----------------------------------------------------

    async def generate(
        self, messages: list[ChatMessage], config: ModelConfig
    ) -> ModelResponse:
        if self._cliente is None:
            return self._responder_error(
                config.model, "Falta GEMINI_API_KEY en el .env"
            )

        system, contenidos = self._separar_system(messages)

        try:
            respuesta = await self._cliente.aio.models.generate_content(
                model=config.model,
                contents=contenidos,
                config=self._armar_config(config, system),
            )
        except Exception as error:  # noqa: BLE001 - a propósito: nada escapa
            return self._responder_error(config.model, self._traducir_error(error))

        return ModelResponse(
            provider=self.provider,
            model=config.model,
            content=respuesta.text or "",
            usage=self._leer_tokens(respuesta),
        )

    async def stream(
        self, messages: list[ChatMessage], config: ModelConfig
    ) -> AsyncIterator[str]:
        """Entrega los fragmentos de texto conforme llegan.

        Si algo falla, el último fragmento es el mensaje de error en lugar de
        una excepción: el `async for` de quien llama termina normalmente.
        """
        if self._cliente is None:
            yield "[error] Falta GEMINI_API_KEY en el .env"
            return

        system, contenidos = self._separar_system(messages)

        try:
            # generate_content_stream es una corutina que DEVUELVE el
            # iterador: primero await, después async for. Un `async for`
            # directo sobre la corutina falla.
            flujo = await self._cliente.aio.models.generate_content_stream(
                model=config.model,
                contents=contenidos,
                config=self._armar_config(config, system),
            )
            async for trozo in flujo:
                if trozo.text:
                    yield trozo.text
        except Exception as error:  # noqa: BLE001 - a propósito: nada escapa
            yield f"[error] {self._traducir_error(error)}"

    # -- Uso de tokens --------------------------------------------------

    def _leer_tokens(self, respuesta: types.GenerateContentResponse) -> TokenUsage:
        datos = respuesta.usage_metadata
        if datos is None:
            return TokenUsage()
        # Los tokens de razonamiento (`thoughts`) se facturan como salida pero
        # vienen en un campo aparte: sin sumarlos, el total queda por debajo
        # del real.
        salida = (datos.candidates_token_count or 0) + (
            datos.thoughts_token_count or 0
        )
        return TokenUsage(
            input_tokens=datos.prompt_token_count or 0,
            output_tokens=salida,
        )
