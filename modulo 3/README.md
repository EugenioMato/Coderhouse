# Sistema de recuperación semántica local (RAG)

Pre-entrega 3 — Flujo end-to-end de RAG sobre documentación interna.

Indexa un conjunto de documentos en una base vectorial local (ChromaDB),
recupera los fragmentos relevantes para una pregunta y genera una respuesta
que usa **exclusivamente** esa información. Si la respuesta no está en los
documentos, lo dice en lugar de inventarla.

## Requisitos

- Python 3.14 (funciona igual en 3.12)
- Una clave de Gemini, gratuita: https://aistudio.google.com/apikey

## Instalación

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env
```

Después, poner la clave en el `.env`.

## Cómo ejecutar

Son dos pasos: primero se indexa, después se consulta.

```powershell
.venv\Scripts\python.exe ingesta.py    # 1. indexa los documentos de data/
.venv\Scripts\python.exe main.py       # 2. corre las pruebas
```

La ingesta se corre **una sola vez**. Si la base ya tiene documentos, el
script avisa y no reindexa: vectorizar cuesta tiempo y cuota de API. Para
forzar la reindexación (por ejemplo, después de editar los documentos):

```powershell
.venv\Scripts\python.exe ingesta.py --reset
```

## Variables de entorno

| Variable | Obligatoria | Para qué sirve |
|---|---|---|
| `GEMINI_API_KEY` | sí | Clave de Google AI Studio. |
| `GEMINI_MODEL` | no | Modelo de generación. Por defecto `gemini-flash-lite-latest`. |

## El dataset

`data/` tiene cuatro documentos sobre un sistema de pagos ficticio llamado
Lumen, escritos para esta entrega:

| Archivo | Contenido |
|---|---|
| `arquitectura.md` | Servicios, puertos, flujo de un pago, idempotencia. |
| `base-de-datos.md` | Esquema de PostgreSQL, índices, pool de conexiones. |
| `cache-y-colas.md` | Redis y RabbitMQ, TTLs, colas de mensajes muertos. |
| `incidentes.md` | Tres postmortems con fechas, duración e impacto. |

Están escritos con datos concretos (puertos, TTLs, números de incidente) a
propósito: permiten verificar que la respuesta sale del contexto y no del
conocimiento general del modelo.

## Flujo

```
data/*.md
   │
   ├─ ingesta.py ─────────────────────────────────┐
   │   RecursiveCharacterTextSplitter             │
   │   (2000 caracteres, 200 de solapamiento)     │
   │                                              ▼
   │                                        vectorstore/
   │                                        (ChromaDB persistente)
   │                                              │
pregunta ──► retriever (top_k=4) ─────────────────┘
                │
                ▼
          contexto + pregunta ──► prompt ──► LLM ──► RespuestaRAG
```

| Archivo | Qué hace |
|---|---|
| `embeddings.py` | Configuración compartida: el objeto de embeddings y las constantes. |
| `ingesta.py` | Lee, fragmenta e indexa. Verifica si ya está indexado. |
| `rag.py` | La cadena LCEL y `get_rag_response()`. |
| `main.py` | Las pruebas, incluidas las preguntas trampa. |

### La cadena LCEL

```python
contexto_y_pregunta = RunnableParallel(
    contexto=retriever | formatear_documentos,
    pregunta=RunnablePassthrough(),
)

cadena = (
    contexto_y_pregunta
    | PROMPT
    | crear_modelo().with_structured_output(RespuestaRAG)
).with_retry(stop_after_attempt=3)
```

### El esquema de salida

```python
class RespuestaRAG(BaseModel):
    respuesta: str
    fuentes: list[str]
    tiene_respuesta: bool
```

El campo `tiene_respuesta` es la pieza clave del diseño: convierte el "no lo
sé" en un dato estructurado y verificable, en lugar de una frase que haya que
interpretar con heurísticas sobre el texto. Un programa que use este pipeline
puede ramificar con un `if` en vez de buscar "no tengo información" en la
respuesta.

## Ejemplos de salida

### Pregunta que está en los documentos

> ¿Por qué los montos se guardan en centavos y no como decimal?

```json
{
  "respuesta": "Los montos se guardan en centavos como entero porque el tipo float arrastra errores de redondeo, por ejemplo, un cobro de 10,10 se convertía en 10,099999.",
  "fuentes": ["base-de-datos.md"],
  "tiene_respuesta": true
}
```

### Pregunta trampa

> ¿Qué versión de MongoDB usa el servicio de pagos?

```json
{
  "respuesta": "No tengo esa información en la documentación. El contexto indica que el sistema utiliza PostgreSQL 16 como motor de base de datos, pero no menciona MongoDB.",
  "fuentes": [],
  "tiene_respuesta": false
}
```

No solo admite que no sabe: aclara qué dice la documentación en su lugar.

### Resultado de las pruebas

```
Preguntas respondidas con el contexto:  3/3
Trampas detectadas (sin alucinar):      3/3
```

Las trampas son de dos tipos: una sobre un tema que la documentación no toca
(sueldos) y dos que se parecen mucho al contenido pero piden un dato ausente
(Kafka, MongoDB). Las segundas son las difíciles: el retriever devuelve
fragmentos con score alto, y el modelo tiene que notar igual que el dato
puntual no está.

## Decisiones de implementación

### Un solo lugar define los embeddings

El error más común en RAG es indexar con un modelo de embeddings y consultar
con otro: las distancias vectoriales dejan de tener sentido y los resultados
salen aleatorios.

Acá no puede pasar, por construcción: `embeddings.py` es el único módulo que
crea el objeto de embeddings, y tanto `ingesta.py` como `rag.py` lo importan
de ahí. No hay dos lugares donde se pueda desincronizar.

### Los modelos de embedding viejos están retirados

`text-embedding-004` y `embedding-001` devuelven **404**. El único disponible
es `gemini-embedding-001`.

Devuelve **3072 dimensiones** por defecto, que es mucho para un corpus chico;
se reduce a 768 con `output_dimensionality`, lo que hace la base local más
liviana sin perder calidad de recuperación notable.

### `top_k = 4`

El enunciado pide entre 3 y 5. Pasarle demasiados fragmentos al modelo
degrada su atención sobre el contexto ("lost in the middle") y puede romper el
límite de tokens.

### El orden de los separadores del splitter

`RecursiveCharacterTextSplitter` corta por el primer separador de la lista que
encuentre. Se ponen los encabezados de sección (`\n## `, `\n### `) **antes**
que el salto de párrafo, para que cada fragmento tienda a cubrir un tema
completo.

Con documentos de postmortems eso importa: si un fragmento abarca dos
incidentes, una pregunta sobre uno recupera el bloque que contiene los dos y
el contexto queda diluido.

### ChromaDB exige nombres de colección de 3+ caracteres

Un nombre corto falla con `InvalidArgumentError`. Está documentado en el
código porque el mensaje de error no es obvio al leerlo por primera vez.

### Verificación de persistencia

`ingesta.py` consulta cuántos documentos hay antes de indexar. Si ya hay,
no rehace el trabajo. Es el tercer error común que marca el enunciado, y en el
tier gratuito importa: cada reindexación gasta cuota de embeddings.

## Manejo de errores

`get_rag_response()` nunca propaga una excepción: devuelve `RespuestaRAG` o
`None`, con el motivo en los logs. Mismo criterio que en los módulos 1 y 2.

Si se consulta sin haber indexado, el error lo dice con la solución:
`No existe ./vectorstore. Corré primero: python ingesta.py`.

## Nota sobre el proveedor

La consigna sugiere OpenAI. Acá se usa **Gemini** (embeddings y generación)
porque tiene capa gratuita y es la clave disponible. Lo que la entrega
demuestra no cambia: el chunking, la base vectorial, el retriever, la cadena
LCEL y el grounding son los mismos con cualquier proveedor. Cambiar implica
reemplazar dos clases en `embeddings.py` y `rag.py` — y reindexar, porque los
vectores no son compatibles entre modelos.

## Qué no se sube al repositorio

- `vectorstore/` — artefacto binario regenerable con `ingesta.py`.
- `.venv/` y `.env` — entorno local y credenciales.

## Nota sobre Windows

La consola de Windows usa `cp1252` y no puede imprimir acentos: los scripts
reconfiguran la salida a UTF-8 al arrancar.
