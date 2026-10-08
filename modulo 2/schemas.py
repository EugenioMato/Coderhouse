"""Contrato de salida del pipeline de extracción.

Este esquema cumple dos funciones a la vez:

1. Le dice al modelo qué forma tiene que tener la respuesta: LangChain lo
   traduce a JSON Schema y lo manda en el pedido, por eso las `description`
   de cada campo importan tanto como los tipos.
2. Valida lo que vuelve. Si el modelo corta la respuesta a mitad o inventa un
   nivel de criticidad que no existe, Pydantic lo rechaza y la cadena
   reintenta.
"""

from enum import StrEnum

from pydantic import BaseModel, Field, field_validator


class NivelDeCriticidad(StrEnum):
    """Qué tan urgente es lo que describe el texto."""

    BAJA = "baja"
    MEDIA = "media"
    ALTA = "alta"


class ExtraccionTecnica(BaseModel):
    """Entidades técnicas extraídas de un texto sin procesar."""

    tecnologias: list[str] = Field(
        min_length=1,
        description=(
            "Nombres propios de tecnologías, frameworks, bases de datos o "
            "servicios mencionados en el texto (por ejemplo: FastAPI, Redis, "
            "PostgreSQL). Solo lo que aparece explícitamente, sin inferir."
        ),
    )

    nivel_de_criticidad: NivelDeCriticidad = Field(
        description=(
            "Urgencia del problema descripto. 'alta' si hay caídas, pérdida "
            "de datos o afecta producción; 'media' si hay degradación o "
            "riesgo; 'baja' si es informativo o una mejora pendiente."
        ),
    )

    resumen_tecnico: str = Field(
        min_length=10,
        max_length=500,
        description=(
            "Una o dos oraciones que expliquen la arquitectura y el problema "
            "principal, en términos técnicos y sin repetir el texto original."
        ),
    )

    @field_validator("tecnologias")
    @classmethod
    def limpiar_tecnologias(cls, valores: list[str]) -> list[str]:
        """Normaliza la lista: sin espacios sobrantes, vacíos ni repetidos.

        El modelo suele devolver "Redis " o repetir una tecnología que el
        texto menciona dos veces. Se limpia acá para que el objeto validado
        sea confiable, conservando el orden en que aparecieron.
        """
        limpias: list[str] = []
        vistas: set[str] = set()

        for valor in valores:
            nombre = valor.strip()
            if not nombre or nombre.casefold() in vistas:
                continue
            if cls._es_excusa(nombre):
                continue
            vistas.add(nombre.casefold())
            limpias.append(nombre)

        if not limpias:
            raise ValueError("No se encontró ninguna tecnología en el texto.")
        return limpias

    @staticmethod
    def _es_excusa(nombre: str) -> bool:
        """Detecta cuando el modelo rellenó la lista con una disculpa.

        `min_length=1` obliga al modelo a devolver algo, y ante un texto sin
        tecnologías responde cosas como "No se mencionan tecnologías" o
        "ninguna" en lugar de un nombre. Eso pasaría la validación por ser un
        string no vacío, así que se descarta explícitamente: mejor que la
        extracción falle y se vea, que guardar basura como si fuera un dato.
        """
        texto = nombre.casefold()

        if texto in {"ninguna", "ninguno", "n/a", "na", "none", "-", "sin datos"}:
            return True

        # Una frase larga no es el nombre de una tecnología.
        señales = ("no se menciona", "no hay", "no aplica", "no se identific")
        return any(señal in texto for señal in señales)
