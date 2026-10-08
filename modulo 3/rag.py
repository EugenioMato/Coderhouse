"""Cadena RAG: recupera fragmentos relevantes y responde solo con ellos.

El flujo:

    pregunta → retriever (ChromaDB) → contexto → prompt → LLM → RespuestaRAG

La parte importante no es la recuperación sino el *grounding*: el prompt
obliga al modelo a responder únicamente con lo que está en el contexto, y el
esquema de salida tiene un campo booleano para que el "no lo sé" sea un dato
verificable y no una frase que haya que interpretar.
"""

import logging
import os

from dotenv import load_dotenv
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable, RunnableParallel, RunnablePassthrough
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel, Field

from embeddings import (
    COLECCION,
    DIRECTORIO_VECTORSTORE,
    TOP_K,
    crear_embeddings,
)

load_dotenv()

logger = logging.getLogger(__name__)

# Mismo criterio que en el módulo 2: los modelos "lite" tienen una cuota
# diaria más alta en el tier gratuito.
MODELO_LLM = os.getenv("GEMINI_MODEL", "gemini-flash-lite-latest")


# -- Esquema de salida --------------------------------------------------


class RespuestaRAG(BaseModel):
    """Respuesta del sistema, con sus fuentes."""

    respuesta: str = Field(
        min_length=1,
        description=(
            "La respuesta a la pregunta, basada únicamente en el contexto. "
            "Si el contexto no alcanza, explicá que no tenés esa información."
        ),
    )

    fuentes: list[str] = Field(
        default_factory=list,
        description=(
            "Nombres de los archivos del contexto que respaldan la respuesta "
            "(por ejemplo: incidentes.md). Lista vacía si no se pudo responder."
        ),
    )

    tiene_respuesta: bool = Field(
        description=(
            "true si el contexto contenía la información necesaria; false si "
            "la pregunta no se puede responder con el contexto dado."
        ),
    )


# -- Prompt -------------------------------------------------------------

# El filtro de veracidad. Las instrucciones son explícitas y repetidas a
# propósito: es lo único que separa una respuesta fundada de una inventada.
PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "Sos un asistente técnico que responde preguntas sobre la "
            "documentación interna de un sistema de pagos.\n\n"
            "REGLAS ESTRICTAS:\n"
            "1. Respondé ÚNICAMENTE con información que esté en el CONTEXTO. "
            "No uses conocimiento previo ni completes con suposiciones.\n"
            "2. Si el CONTEXTO no contiene la respuesta, poné "
            "tiene_respuesta=false y explicá que no tenés esa información en "
            "la documentación. No intentes adivinar.\n"
            "3. Citá en 'fuentes' los archivos de los que sacaste la "
            "respuesta, tal como aparecen en el contexto.\n"
            "4. Que una pregunta se parezca a algo del contexto no significa "
            "que esté respondida ahí. Si falta el dato puntual que se pide, "
            "tiene_respuesta=false.\n\n"
            "CONTEXTO:\n{contexto}",
        ),
        ("human", "{pregunta}"),
    ]
)


# -- Piezas de la cadena ------------------------------------------------


def abrir_vectorstore() -> Chroma:
    """Abre la base ya indexada."""
    if not os.path.isdir(DIRECTORIO_VECTORSTORE):
        raise RuntimeError(
            f"No existe {DIRECTORIO_VECTORSTORE}. Corré primero: "
            "python ingesta.py"
        )

    return Chroma(
        persist_directory=DIRECTORIO_VECTORSTORE,
        embedding_function=crear_embeddings(),
        collection_name=COLECCION,
    )


def formatear_documentos(documentos: list[Document]) -> str:
    """Convierte los fragmentos recuperados en el bloque de contexto.

    Cada fragmento va etiquetado con su archivo de origen: así el modelo
    puede citar la fuente, y se puede verificar de dónde salió cada dato.
    """
    if not documentos:
        return "(no se encontró ningún fragmento relevante)"

    partes = []
    for documento in documentos:
        fuente = documento.metadata.get("fuente", "desconocido")
        numero = documento.metadata.get("fragmento", "?")
        partes.append(
            f"--- Fuente: {fuente} (fragmento {numero}) ---\n"
            f"{documento.page_content}"
        )

    return "\n\n".join(partes)


def crear_modelo() -> ChatGoogleGenerativeAI:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "Falta GEMINI_API_KEY. Copiá .env.example a .env y poné tu clave."
        )

    parametros = {
        "model": MODELO_LLM,
        "google_api_key": api_key,
        # Temperatura 0: en RAG queremos fidelidad al contexto, no creatividad.
        "temperature": 0.0,
        "max_output_tokens": 1024,
    }

    # Los modelos "lite" rechazan thinking_budget con un 400 (ver módulo 2).
    if "lite" not in MODELO_LLM:
        parametros["thinking_budget"] = 0

    return ChatGoogleGenerativeAI(**parametros)


def crear_cadena(*, k: int = TOP_K) -> Runnable:
    """Arma la cadena LCEL completa.

    El `RunnableParallel` resuelve las dos entradas del prompt a la vez: el
    contexto sale del retriever, y la pregunta pasa de largo.
    """
    retriever = abrir_vectorstore().as_retriever(search_kwargs={"k": k})

    contexto_y_pregunta = RunnableParallel(
        contexto=retriever | formatear_documentos,
        pregunta=RunnablePassthrough(),
    )

    cadena = (
        contexto_y_pregunta
        | PROMPT
        | crear_modelo().with_structured_output(RespuestaRAG)
    )

    return cadena.with_retry(stop_after_attempt=3, wait_exponential_jitter=True)


_cadena: Runnable | None = None


def obtener_cadena() -> Runnable:
    global _cadena
    if _cadena is None:
        _cadena = crear_cadena()
    return _cadena


# -- API pública --------------------------------------------------------


async def get_rag_response(query: str) -> RespuestaRAG | None:
    """Responde una pregunta usando los documentos indexados.

    Devuelve None si la consulta falló (error de API, cuota agotada, respuesta
    inválida tras los reintentos). Un fallo no se propaga como excepción.
    """
    if not query or not query.strip():
        logger.error("La consulta está vacía.")
        return None

    logger.info("Consulta: %s", query)

    try:
        respuesta = await obtener_cadena().ainvoke(query)
    except Exception as error:  # noqa: BLE001 - nada escapa hacia el llamador
        logger.error("Falló la consulta (%s): %s", type(error).__name__, error)
        return None

    if respuesta.tiene_respuesta:
        logger.info(
            "Respondida con %d fuente(s): %s",
            len(respuesta.fuentes),
            ", ".join(respuesta.fuentes) or "sin citar",
        )
    else:
        logger.info("Sin respuesta en el contexto (el modelo no alucinó).")

    return respuesta


async def recuperar_fragmentos(query: str, *, k: int = TOP_K):
    """Devuelve los fragmentos y sus scores, para inspeccionar el retriever.

    No es parte del flujo de respuesta: sirve para mostrar qué recuperó la
    búsqueda semántica antes de que el LLM intervenga.
    """
    base = abrir_vectorstore()
    return await base.asimilarity_search_with_relevance_scores(query, k=k)
