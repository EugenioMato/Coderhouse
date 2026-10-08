"""Configuración compartida entre la ingesta y la consulta.

Este módulo existe por una sola razón: que haya **un único lugar** donde se
define con qué se vectoriza. El error más común en RAG es indexar con un
modelo de embeddings y consultar con otro — las distancias dejan de tener
sentido y los resultados salen aleatorios.

Teniendo el objeto acá, `ingesta.py` y `rag.py` no pueden diferir.
"""

import os

from dotenv import load_dotenv
from langchain_google_genai import GoogleGenerativeAIEmbeddings

load_dotenv()

# Único modelo de embeddings disponible en el tier gratuito de Gemini. Los
# anteriores (text-embedding-004, embedding-001) devuelven 404: están
# retirados.
MODELO_DE_EMBEDDINGS = "gemini-embedding-001"

# El modelo devuelve 3072 dimensiones por defecto. 768 alcanza de sobra para
# un corpus chico y hace la base local bastante más liviana.
DIMENSIONES = 768

# Dónde persiste ChromaDB y cómo se llama la colección. El nombre debe tener
# entre 3 y 512 caracteres: uno más corto falla con InvalidArgumentError.
DIRECTORIO_VECTORSTORE = "./vectorstore"
COLECCION = "lumen-docs"

# Fragmentos a recuperar por consulta. El enunciado pide entre 3 y 5: pasarle
# demasiados fragmentos al modelo degrada la atención ("lost in the middle")
# y puede romper el límite de tokens.
TOP_K = 4


def crear_embeddings() -> GoogleGenerativeAIEmbeddings:
    """Construye el objeto de embeddings que usan la ingesta y la consulta."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "Falta GEMINI_API_KEY. Copiá .env.example a .env y poné tu clave."
        )

    return GoogleGenerativeAIEmbeddings(
        model=MODELO_DE_EMBEDDINGS,
        google_api_key=api_key,
        output_dimensionality=DIMENSIONES,
    )
