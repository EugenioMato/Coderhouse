"""Prueba del esquema, sin llamar a la API.

Verifica el validador de forma determinista: el modelo es impredecible, pero
las reglas del esquema no. Además no consume cuota, así que se puede correr
todas las veces que haga falta.

Correr con:  .venv\\Scripts\\python.exe probar_schemas.py
"""

import sys

from pydantic import ValidationError

from schemas import ExtraccionTecnica, NivelDeCriticidad

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

RESUMEN = "Resumen técnico de prueba, con largo suficiente para validar."


def construir(**cambios):
    """Crea un objeto válido, con los campos que se pasen sobreescritos."""
    datos = {
        "tecnologias": ["FastAPI"],
        "nivel_de_criticidad": "media",
        "resumen_tecnico": RESUMEN,
    }
    return ExtraccionTecnica(**(datos | cambios))


print("1) Casos que el validador debe RECHAZAR\n")

rechazos = [
    ("lista vacía", {"tecnologias": []}),
    ("excusa del modelo", {"tecnologias": ["No se mencionan tecnologías"]}),
    ("'ninguna'", {"tecnologias": ["ninguna"]}),
    ("'N/A'", {"tecnologias": ["N/A"]}),
    ("solo vacíos", {"tecnologias": ["", "   "]}),
    ("criticidad inventada", {"nivel_de_criticidad": "urgentísima"}),
    ("resumen demasiado corto", {"resumen_tecnico": "corto"}),
]

for nombre, cambios in rechazos:
    try:
        construir(**cambios)
        print(f"  ❌ {nombre}: pasó, y no debería")
    except ValidationError as error:
        print(f"  ✅ {nombre}: {error.errors()[0]['msg'][:58]}")


print("\n2) Normalización de la lista de tecnologías\n")

objeto = construir(tecnologias=["Redis", "redis ", " REDIS", "PostgreSQL"])
print(f"  entrada: ['Redis', 'redis ', ' REDIS', 'PostgreSQL']")
print(f"  salida:  {objeto.tecnologias}")
print("  (deduplicado sin distinguir mayúsculas, conservando el orden)")


print("\n3) El enum es un enum de verdad\n")

objeto = construir(nivel_de_criticidad="alta")
print(f"  valor: {objeto.nivel_de_criticidad!r}")
print(f"  es NivelDeCriticidad: {isinstance(objeto.nivel_de_criticidad, NivelDeCriticidad)}")
print(f"  opciones: {[n.value for n in NivelDeCriticidad]}")


print("\n4) Serialización a JSON\n")
print(construir(tecnologias=["FastAPI", "Redis", "PostgreSQL"],
                nivel_de_criticidad="alta").model_dump_json(indent=2))
