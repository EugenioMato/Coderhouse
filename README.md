# Unified Async LLM Client

Pre-entrega 1 — Cliente de LLM robusto y asíncrono.

Cliente unificado para modelos de lenguaje: una interfaz común, llamadas no
bloqueantes (`async`/`await`), streaming token por token, validación con
Pydantic y errores que nunca rompen el programa que lo usa.

## Requisitos

- Python 3.14 (ver [nota sobre la versión](#nota-sobre-la-versión-de-python))
- Una clave de Gemini, gratuita: https://aistudio.google.com/apikey

## Instalación

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Variables de entorno

Copiar `.env.example` como `.env` y completar la clave:

```powershell
copy .env.example .env
```

| Variable | Obligatoria | Para qué sirve |
|---|---|---|
| `GEMINI_API_KEY` | sí | Clave de Google AI Studio. |
| `LLM_PROVIDER` | no | Proveedor a usar. Por defecto `gemini`. |
| `OPENAI_API_KEY` | no | Reservada; OpenAI no está implementado. |
| `ANTHROPIC_API_KEY` | no | Reservada; Anthropic no está implementado. |

El `.env` está en `.gitignore` y no se sube al repositorio.

## Cómo ejecutar el script de prueba

```powershell
.venv\Scripts\python.exe main.py
```

`main.py` corre cuatro pruebas contra la API real:

1. **Generación normal** — espera la respuesta completa con `await` e informa
   los tokens consumidos.
2. **Streaming** — imprime los fragmentos a medida que llegan (`async for`
   sobre un generador asíncrono).
3. **Manejo de errores** — usa una clave inválida a propósito para mostrar que
   el fallo vuelve como dato estructurado y el programa sigue corriendo.
4. **Concurrencia** — dos preguntas en paralelo con `asyncio.gather`.

Hay dos scripts más:

```powershell
.venv\Scripts\python.exe probar_schemas.py        # valida los esquemas Pydantic
.venv\Scripts\python.exe ejemplos\demo_asincronia.py   # demo didáctica de async
```

## Uso como librería

```python
import asyncio
from dotenv import load_dotenv
from llm_client import AsyncLLMManager, ChatMessage, ModelConfig

async def main():
    load_dotenv()
    manager = AsyncLLMManager()                  # lee LLM_PROVIDER del .env
    cliente = manager.crear_cliente()
    config = ModelConfig(model=manager.modelo_por_defecto, temperature=0.3)
    mensajes = [ChatMessage(role="user", content="¿Qué es la entropía?")]

    # Respuesta completa
    respuesta = await cliente.generate(mensajes, config)
    if respuesta.ok:
        print(respuesta.content, respuesta.usage.total_tokens)
    else:
        print("falló:", respuesta.error)

    # Streaming
    async for trozo in cliente.stream(mensajes, config):
        print(trozo, end="", flush=True)

asyncio.run(main())
```

## Arquitectura

```
llm_client/
├── schemas.py        Esquemas Pydantic: el contrato del proyecto
├── base.py           BaseLLMClient (ABC) + traducción de errores
├── gemini_client.py  Adaptador de Gemini sobre google-genai
└── manager.py        AsyncLLMManager: elige el proveedor
```

El flujo es siempre el mismo: quien usa el cliente arma `ChatMessage` y
`ModelConfig`, y recibe un `ModelResponse`. Qué proveedor contestó no cambia
nada de ese código.

### Esquemas (`schemas.py`)

| Esquema | Qué valida |
|---|---|
| `ChatMessage` | `role` ∈ {system, user, assistant}; `content` no vacío. |
| `ModelConfig` | `temperature` 0–2, `max_tokens` > 0, `top_p` ∈ (0, 1]. Rechaza campos desconocidos (`extra="forbid"`), así un `temprature` mal tipeado falla en vez de pasar en silencio. |
| `TokenUsage` | Tokens de entrada y salida, con `total_tokens` calculado. |
| `ModelResponse` | Respuesta unificada: `content`, `usage` y `error`, más la property `ok`. |

### Errores: se devuelven, no se levantan

Es la decisión central del diseño. Ninguna excepción del proveedor escapa
hacia quien llama: un fallo vuelve como `ModelResponse` con `error` cargado y
`ok == False`. En streaming, el último fragmento es el mensaje de error y el
`async for` termina normalmente.

Esto es lo que permite tratar a todos los proveedores igual, y que un corte de
red o una cuota agotada no tiren abajo el programa.

Gemini no tiene clases de excepción para cuota ni credenciales (a diferencia
de los SDK de OpenAI y Anthropic): todo llega como `ClientError` (4xx) o
`ServerError` (5xx) y hay que mirar el código HTTP.

| Situación | Cómo se detecta | Mensaje |
|---|---|---|
| Cuota agotada | `ClientError` 429 | "Límite de cuota alcanzado…" |
| Clave inválida | `ClientError` 400/401/403 | "Credenciales inválidas…" |
| Caída del proveedor | `ServerError` 5xx | "El proveedor no está disponible…" |
| Timeout | `httpx.TimeoutException` | "Se agotó el tiempo de espera…" |
| Red | `httpx.HTTPError` | "Error de conexión…" |
| Falta la clave | chequeo en el constructor | "Falta GEMINI_API_KEY en el .env" |

**Reintentos:** los hace el propio SDK ante fallas transitorias; en el
constructor se fija cuántos (`max_retries`, por defecto 2). No se escribió un
retry a mano para no duplicar lógica que la librería ya resuelve.

## Decisiones de implementación

Tres cosas que se descubrieron probando contra la API y que explican el código:

**El `system` de Gemini va aparte.** No es un mensaje más de la lista: va en
`system_instruction`. Y los roles de Gemini son `user`/`model`, no
`assistant`. La traducción vive en el adaptador, no en los esquemas, para que
el contrato del proyecto no quede atado a un proveedor.

**El razonamiento consume `max_tokens`.** Los modelos Gemini 3.x razonan antes
de responder y esos tokens se descuentan del presupuesto de salida: con el
thinking activo y un `max_tokens` chico, la respuesta llega cortada
(`finish_reason=MAX_TOKENS`) habiendo gastado casi todo en pensar. Por eso el
cliente manda `thinking_budget=0`. El modelo por defecto es
`gemini-3.5-flash`, elegido porque respeta ese parámetro — otros modelos flash
más nuevos lo ignoran y razonan igual.

Los tokens de razonamiento (`thoughts_token_count`) se suman a los de salida
en `TokenUsage`: vienen en un campo aparte y, sin sumarlos, el total reportado
queda por debajo del real.

**`generate_content_stream` es una corutina que devuelve el iterador.** Hay
que hacer `await` y después `async for`; un `async for` directo sobre la
corutina falla.

## Alcance de esta entrega

Está implementado **sólo el proveedor Gemini**, porque es el que ofrece una
capa gratuita y es la única clave disponible. La consigna pedía OpenAI y
Anthropic.

Lo que sí cumple el requisito de intercambiabilidad es la arquitectura:

- `BaseLLMClient` es una clase abstracta con `generate()` y `stream()`.
- `AsyncLLMManager` es la fábrica que elige el proveedor por configuración.
- El `Literal` `Provider` conserva los tres nombres, y
  `MODELOS_POR_DEFECTO` ya tiene el modelo de cada uno.

Sumar OpenAI o Anthropic es escribir una subclase de `BaseLLMClient` que
traduzca su SDK a estos esquemas y registrarla en `manager._CLIENTES`; ningún
otro archivo cambia. Pedirlos hoy devuelve un `NotImplementedError` con el
mensaje de qué falta, en lugar de fallar de forma confusa.

## Nota sobre la versión de Python

La consigna sugiere Python 3.12; este proyecto corre en **3.14.5**, que es el
intérprete instalado en la máquina de desarrollo. El código no usa ninguna
característica posterior a 3.12 (sólo sintaxis `X | None`, disponible desde
3.10), así que funciona igual en 3.12.

## Nota sobre Windows

La consola de Windows usa `cp1252` y no puede imprimir acentos ni flechas: sin
intervención, los scripts mueren con `UnicodeEncodeError`. Tanto `main.py`
como `probar_schemas.py` reconfiguran la salida a UTF-8 al arrancar.
