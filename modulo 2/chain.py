"""Cadena LCEL que extrae entidades técnicas de un texto.

La composición es `prompt | model.with_structured_output(Esquema)`, envuelta
en `.with_retry()`. Las cuatro piezas:

    texto  →  ChatPromptTemplate  →  modelo + parser  →  ExtraccionTecnica

El parser estructurado hace que el modelo tenga que responder con la forma del
esquema; el reintento cubre el caso en que no lo logre (JSON mal formado o
cortado a mitad).
"""

import logging
import os

from dotenv import load_dotenv
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import ValidationError

from schemas import ExtraccionTecnica

load_dotenv()

logger = logging.getLogger(__name__)

# El tier gratuito limita los pedidos por día y por modelo (20/día en los
# flash grandes, más en los lite). Se usa un lite por defecto para que las
# pruebas no agoten la cuota, y se puede cambiar por .env sin tocar el código.
MODELO_POR_DEFECTO = os.getenv("GEMINI_MODEL", "gemini-flash-lite-latest")

# Cuántas veces se reintenta si el modelo no devuelve un objeto válido.
INTENTOS = 3


# -- Prompt -------------------------------------------------------------

# En ChatPromptTemplate, no con f-strings: LangChain gestiona las variables de
# entrada, valida que estén todas y permite reusar el template.
PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "Sos un analista técnico. Extraés información estructurada de "
            "textos sobre software: descripciones de arquitectura, logs de "
            "error o reportes de incidentes.\n\n"
            "Reglas:\n"
            "- Listá solo las tecnologías que el texto menciona de forma "
            "explícita. No inventes ni infieras.\n"
            "- El nivel de criticidad surge del impacto descripto, no de la "
            "cantidad de tecnologías.\n"
            "- El resumen es técnico y propio: no copies el texto original.",
        ),
        ("human", "Analizá el siguiente texto:\n\n{texto}"),
    ]
)


# -- Modelo y cadena ----------------------------------------------------


def crear_modelo(
    modelo: str = MODELO_POR_DEFECTO, *, temperature: float = 0.0
) -> ChatGoogleGenerativeAI:
    """Construye el cliente del LLM.

    `temperature=0` porque esto es extracción, no redacción: queremos la
    misma salida para el mismo texto.
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "Falta GEMINI_API_KEY. Copiá .env.example a .env y poné tu clave."
        )

    parametros = {
        "model": modelo,
        "google_api_key": api_key,
        "temperature": temperature,
        # Presupuesto holgado: si la respuesta se corta por falta de tokens,
        # el objeto llega incompleto y falla la validación.
        "max_output_tokens": 1024,
    }

    # Los modelos Gemini 3.x razonan antes de responder y esos tokens salen
    # del presupuesto de salida, así que conviene desactivar el thinking. Los
    # modelos `lite`, en cambio, rechazan el parámetro con un 400: no se les
    # manda. Se decide por el nombre para no gastar una llamada (y cuota) en
    # averiguarlo.
    if "lite" not in modelo:
        parametros["thinking_budget"] = 0

    return ChatGoogleGenerativeAI(**parametros)


def crear_cadena(
    modelo: str = MODELO_POR_DEFECTO, *, intentos: int = INTENTOS
) -> Runnable:
    """Arma la cadena LCEL completa, con reintentos.

    El `with_retry` va sobre la cadena entera y no solo sobre el modelo: así
    cubre tanto un error de la API como un fallo de validación del esquema.
    """
    cadena = PROMPT | crear_modelo(modelo).with_structured_output(
        ExtraccionTecnica
    )

    return cadena.with_retry(
        stop_after_attempt=intentos,
        wait_exponential_jitter=True,  # espera creciente entre intentos
    )


# Una sola instancia, para no reconstruir la cadena en cada llamada.
_cadena: Runnable | None = None


def obtener_cadena() -> Runnable:
    global _cadena
    if _cadena is None:
        _cadena = crear_cadena()
    return _cadena


# -- API pública --------------------------------------------------------


async def process_text(text: str) -> ExtraccionTecnica | None:
    """Procesa un texto y devuelve el objeto validado.

    Devuelve None si no se pudo extraer nada válido después de los
    reintentos: igual que en el módulo 1, un fallo no se propaga como
    excepción hacia quien llama.
    """
    if not text or not text.strip():
        logger.error("El texto de entrada está vacío.")
        return None

    logger.info("Procesando texto de %d caracteres...", len(text))

    try:
        resultado = await obtener_cadena().ainvoke({"texto": text})

    except ValidationError as error:
        # El modelo respondió, pero su respuesta no cumple el esquema: campo
        # faltante, criticidad inventada, o JSON cortado por falta de tokens.
        # Ya se agotaron los reintentos de la cadena.
        logger.error(
            "La respuesta no pasó la validación tras %d intentos: %s",
            INTENTOS,
            "; ".join(e["msg"] for e in error.errors()),
        )
        return None

    except Exception as error:  # noqa: BLE001 - nada escapa hacia el llamador
        logger.error("Falló la extracción (%s): %s", type(error).__name__, error)
        return None

    logger.info(
        "Validación OK · %d tecnologías · criticidad %s",
        len(resultado.tecnologias),
        resultado.nivel_de_criticidad.value,
    )
    return resultado
