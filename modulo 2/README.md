# Pipeline de Extracción de Entidades Técnicas

Pre-entrega 2 — Pipeline de procesamiento validado.

Recibe un párrafo de texto sin procesar (descripción de arquitectura, log de
error, reporte de incidente) y devuelve un objeto Pydantic validado con las
tecnologías mencionadas, el nivel de criticidad y un resumen técnico.

Construido con LangChain (LCEL), `with_structured_output()` y reintentos
automáticos.

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

## Variables de entorno

| Variable | Obligatoria | Para qué sirve |
|---|---|---|
| `GEMINI_API_KEY` | sí | Clave de Google AI Studio. |
| `GEMINI_MODEL` | no | Modelo a usar. Por defecto `gemini-flash-lite-latest`. |

## Cómo ejecutar

```powershell
.venv\Scripts\python.exe main.py            # pipeline completo, llama a la API
.venv\Scripts\python.exe probar_schemas.py  # valida el esquema, sin llamar a la API
```

`main.py` corre cuatro casos, de más fácil a más hostil:

1. **Descripción de arquitectura** — el caso típico.
2. **Log de error con stack trace** — otro formato de entrada.
3. **Texto ambiguo** — la prueba de estrés: un texto sin tecnologías, para ver
   si el validador lo rechaza.
4. **Tres textos en paralelo** — con `asyncio.gather`.

`probar_schemas.py` verifica el validador de forma determinista y **sin gastar
cuota de API**: útil porque el modelo es impredecible, pero las reglas del
esquema no.

## Ejemplo de salida

Entrada:

> El servicio de pagos corre sobre FastAPI con caché en Redis y persistencia
> en PostgreSQL. Bajo carga alta se agota el pool de conexiones y la API
> empieza a devolver 503 en producción.

Salida:

```json
{
  "tecnologias": [
    "FastAPI",
    "Redis",
    "PostgreSQL"
  ],
  "nivel_de_criticidad": "alta",
  "resumen_tecnico": "Saturación del pool de conexiones en la base de datos bajo alta concurrencia, generando errores de servicio no disponible en la API."
}
```

Con un log de error como entrada, el pipeline extrae igual:

```json
{
  "tecnologias": ["Celery", "PostgreSQL", "RabbitMQ"],
  "nivel_de_criticidad": "alta",
  "resumen_tecnico": "Falla de conectividad en la capa de persistencia durante la ejecución de tareas asíncronas, provocando el agotamiento de reintentos y la saturación del sistema de mensajería."
}
```

## Arquitectura

```
texto  →  ChatPromptTemplate  →  modelo + structured output  →  ExtraccionTecnica
                                         ↑
                                   with_retry (3 intentos)
```

| Archivo | Qué contiene |
|---|---|
| `schemas.py` | El modelo Pydantic `ExtraccionTecnica` y el enum `NivelDeCriticidad`. |
| `chain.py` | El prompt, el modelo, la cadena LCEL y `process_text()`. |
| `main.py` | Mini-script de prueba asíncrono. |
| `probar_schemas.py` | Prueba del validador, sin API. |

### La cadena LCEL

```python
cadena = PROMPT | crear_modelo().with_structured_output(ExtraccionTecnica)
return cadena.with_retry(stop_after_attempt=3, wait_exponential_jitter=True)
```

El `with_retry` va sobre la cadena **completa**, no solo sobre el modelo: así
cubre tanto un error de la API como un fallo de validación del esquema.

### El esquema como contrato de ida y vuelta

`schemas.py` cumple dos funciones a la vez, y por eso las `description` de
cada campo importan tanto como los tipos:

- **De ida**: LangChain traduce el esquema a JSON Schema y lo manda en el
  pedido, así que las descripciones le indican al modelo qué extraer.
- **De vuelta**: Pydantic valida la respuesta. Si el modelo corta el JSON a
  mitad o inventa un nivel de criticidad, la validación falla y se reintenta.

Restricciones: `tecnologias` no puede estar vacía, `nivel_de_criticidad` es un
enum cerrado (`baja`/`media`/`alta`) y `resumen_tecnico` tiene largo mínimo y
máximo.

## Decisiones de implementación

Tres cosas que se descubrieron probando contra la API, no leyendo la
documentación.

### El modelo rellena la lista con excusas

`min_length=1` obliga al modelo a devolver al menos una tecnología. Ante un
texto que no menciona ninguna, en vez de fallar responde:

```json
{ "tecnologias": ["No se mencionan tecnologías explícitamente"] }
```

Eso **pasaba la validación**, porque es un string no vacío. Es basura que
entra al sistema como si fuera un dato. El validador ahora la detecta y la
descarta, junto con `"ninguna"`, `"N/A"` y variantes: mejor que la extracción
falle visiblemente que guardar un dato inventado.

### Los modelos `lite` rechazan `thinking_budget`

Los Gemini 3.x razonan antes de responder y esos tokens se descuentan del
presupuesto de salida, por lo que conviene desactivarlo (`thinking_budget=0`)
para que el JSON no llegue cortado. Pero los modelos `lite` devuelven
`400 INVALID_ARGUMENT` si se les manda ese parámetro.

El cliente decide por el nombre del modelo, sin hacer una llamada de prueba
para averiguarlo: con una cuota de 20 pedidos diarios, gastar una en un sondeo
no es gratis.

### La cuota del tier gratuito es por modelo y por día

`gemini-3.5-flash` permite **20 pedidos por día**. Las pruebas del pipeline la
agotan rápido, y el error llega como `429 RESOURCE_EXHAUSTED`. Por eso:

- El modelo por defecto es `gemini-flash-lite-latest`, con cuota más alta.
- Se puede cambiar por `.env` (`GEMINI_MODEL`) sin tocar el código.
- `probar_schemas.py` valida el esquema sin consumir cuota.

Cuando la cuota se agota, el pipeline lo loguea con el motivo real y devuelve
`None` en lugar de romperse.

### El `finish_reason` y las respuestas incompletas

El enunciado advierte que el LLM puede cortar la respuesta por falta de
tokens. Con `with_structured_output()` ese caso no se manifiesta como un
`finish_reason` que haya que inspeccionar a mano: el objeto llega incompleto y
**falla la validación de Pydantic**, que es justamente lo que dispara el
`with_retry`. Además se usa `max_output_tokens=1024`, holgado para esta salida.

## Manejo de errores

`process_text()` nunca propaga una excepción: devuelve `ExtraccionTecnica` o
`None`, con el motivo en los logs. Es el mismo criterio del módulo 1 — un
fallo del proveedor no debe tirar abajo el programa que usa el pipeline.

Los logs usan el módulo `logging` (no `print`) y muestran el texto recibido,
el resultado de la validación y, si falla, por qué.

## Nota sobre el proveedor

La consigna sugiere `ChatOpenAI` o `ChatAnthropic`. Acá se usa
**`ChatGoogleGenerativeAI`** porque Gemini tiene capa gratuita y es la clave
disponible.

Esto no afecta lo que la entrega demuestra: LangChain abstrae el proveedor, y
la cadena LCEL, el esquema Pydantic, `with_structured_output()`,
`with_retry()` y `ainvoke()` son los mismos con cualquier modelo. Cambiar a
OpenAI es cambiar la clase del cliente en `chain.py:crear_modelo()`.

## Nota sobre Windows

La consola de Windows usa `cp1252` y no puede imprimir acentos: sin
intervención, los scripts mueren con `UnicodeEncodeError`. Tanto `main.py`
como `probar_schemas.py` reconfiguran la salida a UTF-8 al arrancar.
