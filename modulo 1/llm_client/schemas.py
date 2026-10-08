"""Esquemas de datos (modelos Pydantic) del cliente unificado de LLMs."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# Tipos permitidos: solo estos textos exactos son válidos.
Role = Literal["system", "user", "assistant"]
Provider = Literal["openai", "anthropic", "gemini"]

# Modelo por defecto de cada proveedor. Gemini 3.5 Flash es el elegido porque
# respeta `thinking_budget=0`: otros flash más nuevos razonan igual y gastan
# el presupuesto de max_tokens antes de escribir la respuesta.
MODELOS_POR_DEFECTO: dict[str, str] = {
    "gemini": "gemini-3.5-flash",
    "openai": "gpt-4o-mini",
    "anthropic": "claude-haiku-4-5",
}


class ChatMessage(BaseModel):
    """Un mensaje de la conversación."""

    role: Role
    content: str = Field(min_length=1)


class ModelConfig(BaseModel):
    """Parámetros de generación que se le pasan al modelo."""

    model_config = ConfigDict(extra="forbid")

    model: str = Field(min_length=1)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(default=512, gt=0)
    top_p: float | None = Field(default=None, gt=0.0, le=1.0)


class TokenUsage(BaseModel):
    """Cuántos tokens consumió una llamada."""

    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


class ModelResponse(BaseModel):
    """Respuesta unificada, venga del proveedor que venga."""

    provider: Provider
    model: str
    content: str = ""
    usage: TokenUsage | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None
