"""Ingesta: lee los documentos, los fragmenta y los indexa en ChromaDB.

Se corre una sola vez (o cuando cambien los documentos):

    .venv\\Scripts\\python.exe ingesta.py           # indexa si está vacío
    .venv\\Scripts\\python.exe ingesta.py --reset    # reindexa desde cero

Si la colección ya tiene documentos, no reindexa: vectorizar cuesta tiempo y
cuota de API, así que repetirlo sin necesidad es puro desperdicio.
"""

import argparse
import logging
import shutil
import sys
from pathlib import Path

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from embeddings import (
    COLECCION,
    DIRECTORIO_VECTORSTORE,
    crear_embeddings,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(level=logging.INFO, format="  [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

DIRECTORIO_DATOS = Path("data")

# El enunciado pide fragmentos de al menos 500 tokens con 50 de solapamiento.
# RecursiveCharacterTextSplitter mide en caracteres, no en tokens: con el
# factor habitual de ~4 caracteres por token en español, 2000 caracteres
# equivalen aproximadamente a 500 tokens y 200 de solapamiento a 50.
TAMANO_FRAGMENTO = 2000
SOLAPAMIENTO = 200


def leer_documentos(directorio: Path = DIRECTORIO_DATOS) -> list[Document]:
    """Carga los .md y .txt de la carpeta de datos."""
    if not directorio.is_dir():
        raise FileNotFoundError(
            f"No existe la carpeta {directorio}/. Debe contener los .md a indexar."
        )

    archivos = sorted(
        [*directorio.glob("*.md"), *directorio.glob("*.txt")]
    )
    if not archivos:
        raise FileNotFoundError(f"No hay archivos .md ni .txt en {directorio}/.")

    documentos: list[Document] = []
    for archivo in archivos:
        texto = archivo.read_text(encoding="utf-8")
        documentos.append(
            Document(page_content=texto, metadata={"fuente": archivo.name})
        )
        logger.info("Leído %s (%d caracteres)", archivo.name, len(texto))

    return documentos


def fragmentar(documentos: list[Document]) -> list[Document]:
    """Parte los documentos en fragmentos con solapamiento.

    El splitter corta primero por los separadores más semánticos que
    encuentre, así un fragmento rara vez parte una idea al medio. El
    solapamiento evita perder una frase que caiga justo en el borde.

    El orden de los separadores importa: se ponen los encabezados de sección
    antes que el salto de párrafo, para que cada fragmento tienda a cubrir un
    tema y no el final de uno más el comienzo de otro. Con documentos sobre
    incidentes, eso es la diferencia entre recuperar el postmortem que se
    preguntó y recuperar el bloque que contiene tres.
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=TAMANO_FRAGMENTO,
        chunk_overlap=SOLAPAMIENTO,
        separators=["\n## ", "\n### ", "\n\n", "\n", ". ", " ", ""],
    )

    fragmentos = splitter.split_documents(documentos)

    # Numerar los fragmentos de cada archivo, para poder ubicarlos después.
    contadores: dict[str, int] = {}
    for fragmento in fragmentos:
        fuente = fragmento.metadata["fuente"]
        contadores[fuente] = contadores.get(fuente, 0) + 1
        fragmento.metadata["fragmento"] = contadores[fuente]

    logger.info(
        "%d documentos → %d fragmentos (%d caracteres, %d de solapamiento)",
        len(documentos),
        len(fragmentos),
        TAMANO_FRAGMENTO,
        SOLAPAMIENTO,
    )
    return fragmentos


def contar_indexados() -> int:
    """Cuántos fragmentos hay ya en la base. 0 si no existe."""
    if not Path(DIRECTORIO_VECTORSTORE).is_dir():
        return 0

    try:
        base = Chroma(
            persist_directory=DIRECTORIO_VECTORSTORE,
            embedding_function=crear_embeddings(),
            collection_name=COLECCION,
        )
        return base._collection.count()
    except Exception as error:  # noqa: BLE001 - base corrupta o de otra versión
        logger.warning("No se pudo leer la base existente: %s", error)
        return 0


def indexar(*, reset: bool = False) -> int:
    """Indexa los documentos. Devuelve cuántos fragmentos quedaron.

    Si ya hay documentos y no se pidió reset, no hace nada: reindexar gasta
    cuota de embeddings sin necesidad.
    """
    if reset and Path(DIRECTORIO_VECTORSTORE).is_dir():
        logger.info("Borrando la base anterior (--reset)...")
        shutil.rmtree(DIRECTORIO_VECTORSTORE, ignore_errors=True)

    existentes = contar_indexados()
    if existentes and not reset:
        logger.info(
            "La base ya tiene %d fragmentos indexados; no se reindexa. "
            "Usá --reset para forzarlo.",
            existentes,
        )
        return existentes

    fragmentos = fragmentar(leer_documentos())

    logger.info("Vectorizando e indexando en %s...", DIRECTORIO_VECTORSTORE)
    base = Chroma.from_documents(
        documents=fragmentos,
        embedding=crear_embeddings(),
        persist_directory=DIRECTORIO_VECTORSTORE,
        collection_name=COLECCION,
    )

    total = base._collection.count()
    logger.info("Listo: %d fragmentos indexados.", total)
    return total


def main() -> None:
    parser = argparse.ArgumentParser(description="Indexa los documentos de data/.")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Borra la base y reindexa todo desde cero.",
    )
    argumentos = parser.parse_args()

    print("Ingesta de documentos\n")
    try:
        indexar(reset=argumentos.reset)
    except Exception as error:  # noqa: BLE001
        logger.error("Falló la ingesta (%s): %s", type(error).__name__, error)
        raise SystemExit(1) from error

    print("\nYa podés consultar con:  .venv\\Scripts\\python.exe main.py")


if __name__ == "__main__":
    main()
