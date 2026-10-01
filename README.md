# workana-mcp

![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)
![MCP](https://img.shields.io/badge/MCP-server-8A2BE2)
![Licencia MIT](https://img.shields.io/badge/licencia-MIT-green)
![Solo lectura](https://img.shields.io/badge/acceso-solo%20lectura-lightgrey)

Servidor [MCP](https://modelcontextprotocol.io) para **buscar y evaluar proyectos freelance de Workana** desde Claude.

Workana no tiene API pública, así que el servidor lee las mismas páginas públicas que ves en el navegador **sin iniciar sesión**. Es **solo lectura**: no entra en tu cuenta, no envía propuestas ni mensajes. Tú decides a qué postularte y envías la propuesta a mano.

## Contenido

- [Herramientas](#herramientas)
- [Cómo se calcula el puntaje](#cómo-se-calcula-el-puntaje-0-100)
- [Tu perfil de skills](#tu-perfil-de-skills)
- [Instalación](#instalación)
- [Configuración](#configuración)
- [Ejemplos de uso](#ejemplos-de-uso)
- [Cómo funciona la búsqueda](#cómo-funciona-la-búsqueda)
- [Solución de problemas](#solución-de-problemas)
- [Desarrollo](#desarrollo)
- [Limitaciones y uso responsable](#limitaciones-y-uso-responsable)

## Herramientas

Todas aceptan `formato`: `markdown` (por defecto, para leer) o `json` (para procesar).

| Herramienta | Qué hace |
|---|---|
| `workana_buscar_proyectos` | Búsqueda con filtros y puntaje rápido de oportunidad para cada resultado. Ordena por oportunidad, por fecha o por menos propuestas. |
| `workana_ver_proyecto` | Ficha completa: descripción entera, skills, presupuesto, propuestas, freelancers interesados y el cliente (país, estrellas, proyectos publicados y pagados, miembro desde, pago verificado, otros proyectos suyos). |
| `workana_evaluar_proyecto` | Puntaje de oportunidad 0-100 con desglose, alertas, puntos a favor y en contra, y consejos para la propuesta. |
| `workana_mejores_oportunidades` | Flujo diario: busca proyectos recientes de tu stack, descarta los malos, analiza a fondo los mejores N y los ordena. |

### Filtros de `workana_buscar_proyectos`

| Parámetro | Valores |
|---|---|
| `texto` | Texto libre, p. ej. `dashboard`, `ecommerce`, `api` |
| `skills` | Hasta 15 skills (React, Node, TypeScript, Next, NestJS, Vue, MongoDB…). Por defecto, tu perfil. |
| `categoria` | `programacion` (por defecto), `diseno`, `redaccion`, `marketing`, `soporte`, `legal`, `finanzas`, `ingenieria` |
| `subcategoria` | Solo para `programacion`: `web`, `diseno_web`, `ecommerce`, `wordpress`, `apps_moviles`, `data_science`, `escritorio`, `inteligencia_artificial`, `otros` |
| `idioma` | `es` (por defecto), `pt`, `en`, `todos` |
| `modalidad` | `precio_fijo` o `por_hora` |
| `publicados` | `24h`, `3d`, `semana` (por defecto), `cualquiera` |
| `pocas_propuestas` | Solo proyectos con 0-4 propuestas |
| `pais_cliente` | Código ISO de dos letras: `AR`, `MX`, `ES`, `US`… |
| `presupuesto_min_usd` | Descarta proyectos de precio fijo cuyo máximo sea menor |
| `tarifa_min_hora` | Descarta proyectos por hora cuya tarifa máxima (USD/h) sea menor |
| `max_propuestas` | Descarta proyectos con más propuestas que este número |
| `max_consultas` | Máximo de peticiones al listado (20 por defecto, 30 como máximo) |
| `ordenar_por` | `oportunidad` (por defecto), `recientes`, `menos_propuestas` |
| `mis_skills` | Tu stack para calcular el encaje (ver [Tu perfil de skills](#tu-perfil-de-skills)) |

`workana_mejores_oportunidades` usa filtros más estrictos por defecto: publicados en los últimos `3d`, presupuesto mínimo de 100 USD (precio fijo) o 10 USD/h, máximo 40 propuestas, y analiza a fondo los mejores `top` (5 por defecto, hasta 10).

## Cómo se calcula el puntaje (0-100)

| Criterio | Puntos | Detalle |
|---|---|---|
| **Encaje con tu stack** | 30 | Tecnologías fuertes (React, Node, TypeScript, Next, Express, Nest) en los skills o en el texto, más el % de skills del proyecto que tienes. |
| **Competencia** | 25 | 0-4 propuestas = 25 · 5-9 = 20 · 10-19 = 13 · 20-34 = 7 · 35 o más = 2. |
| **Presupuesto** | 20 | Precio fijo: ≥ 1000 USD = 20, ≥ 500 = 16, ≥ 250 = 12, ≥ 100 = 7. Por hora: ≥ 45 USD/h = 20, ≥ 25 = 15, ≥ 15 = 10. |
| **Cliente** | 15 | Pago verificado, calificación, proyectos que ya pagó y cuántos publicó. |
| **Frescura** | 10 | Menos de 6 h = 10, hasta 24 h = 8, hasta 3 días = 5, hasta una semana = 2, más de una semana = 0. |

A eso se restan **penalizaciones** por señales de riesgo: pagar o trabajar fuera de Workana, contacto por WhatsApp o Telegram, e-mail en la descripción, prueba o trabajo gratis, pago con porcentaje o participación, presupuesto "bajo", "clones" de plataformas grandes y proyecto cerrado.

**Prioridad:** alta desde 65 · media de 45 a 64 · baja por debajo de 45. Es una heurística para priorizar, no una garantía.

El puntaje de `workana_buscar_proyectos` es *rápido*: se calcula solo con el listado, sin datos del cliente. Para el análisis completo usa `workana_evaluar_proyecto`.

## Tu perfil de skills

Por defecto se usa un stack fullstack: React.js, Node.js, TypeScript, JavaScript, Next.js, Express.js, NestJS, HTML/CSS, API/REST, MongoDB, MySQL/SQL, Git y Firebase. Puedes cambiarlo de dos formas:

- **Por consulta**, con el parámetro `mis_skills`.
- **De forma permanente**, con la variable de entorno `WORKANA_MIS_SKILLS` (lista separada por comas).

## Instalación

Requisitos: **Python 3.10 o superior** y un cliente MCP como **Claude Desktop**.

### Opción A: lanzador automático (Linux)

```bash
git clone https://github.com/ErgoCodes/workana-mcp.git
```

En Claude Desktop: **Configuración → Desarrollador → Editar configuración**, y dentro de `mcpServers` agrega:

```json
{
  "mcpServers": {
    "workana": {
      "command": "bash",
      "args": ["/RUTA/A/workana-mcp/run.sh"]
    }
  }
}
```

La primera vez, `run.sh` instala las dependencias solo, en `.venv` (con `uv` si está disponible; si no, con `venv` + `pip`), y deja el registro en `install.log`. Reinicia Claude Desktop por completo: tarda uno o dos minutos mientras instala. Si no aparecen las herramientas `workana_*`, revisa `install.log`.

### Opción B: instalación manual (Windows, Linux y Mac)

```bash
python -m venv .venv
.venv/bin/pip install -e .            # Linux / Mac
.venv\Scripts\pip install -e .        # Windows
```

Y registra el servidor apuntando al Python del entorno virtual:

```json
{
  "mcpServers": {
    "workana": {
      "command": "/RUTA/A/workana-mcp/.venv/bin/python",
      "args": ["-m", "workana_mcp"]
    }
  }
}
```

En Windows, usa `C:\\RUTA\\workana-mcp\\.venv\\Scripts\\python.exe`. El paquete también instala el comando `workana-mcp`, que sirve como `command` en cualquier cliente MCP compatible con transporte stdio.

## Configuración

| Variable de entorno | Efecto | Por defecto |
|---|---|---|
| `WORKANA_MIS_SKILLS` | Tu stack permanente, separado por comas. | Stack fullstack JS/TS (ver arriba) |
| `WORKANA_LOCALE` | Idioma de los textos de la web de Workana: `es`, `pt` o `en`. | `es` |

Se definen en el bloque `env` del servidor:

```json
"workana": {
  "command": "bash",
  "args": ["/RUTA/A/workana-mcp/run.sh"],
  "env": {
    "WORKANA_MIS_SKILLS": "React.js,Node.js,TypeScript,Next.js,NestJS,PostgreSQL,Docker",
    "WORKANA_LOCALE": "es"
  }
}
```

Otros valores fijos del cliente: pausa de **1,2 s** entre peticiones, caché de **5 minutos** y tiempo máximo de **25 s** por petición.

## Ejemplos de uso

- "Dame las mejores oportunidades de Workana de hoy para mi stack."
- "Busca proyectos de React o Next de precio fijo, publicados en las últimas 24 horas, con pocas propuestas."
- "Evalúa este proyecto: https://www.workana.com/job/…"
- "Busca proyectos por hora de Node.js con tarifa de al menos 20 USD/h y clientes de España o EE. UU."
- "Muéstrame los proyectos de la subcategoría data science de la última semana, con skills Python y mi perfil de Python, ordenados por menos propuestas."

## Cómo funciona la búsqueda

Sin sesión, Workana solo muestra **7 de cada 20** resultados por página y oculta el resto para que te registres. Para verlos todos, cuando una búsqueda tiene resultados ocultos el servidor la divide en búsquedas más pequeñas (por modalidad, número de propuestas, subcategoría, skill y, como último recurso, más páginas) y une los resultados, empezando por la que más resultados oculta. `max_consultas` limita cuántas peticiones hace.

La respuesta indica cuántos proyectos vio del total que reporta Workana, para que sepas qué tan completa es la cobertura.

Además, la página de un proyecto sin sesión no muestra presupuesto ni pago verificado: el servidor los completa buscando el proyecto en el listado por su título.

## Solución de problemas

| Síntoma | Qué hacer |
|---|---|
| No aparecen las herramientas `workana_*` | Reinicia Claude Desktop por completo y revisa `install.log` (Opción A). |
| `ensurepip is not available` | Falta el módulo venv: `sudo apt install python3-venv`, y reinicia Claude Desktop. |
| La instalación quedó a medias | Borra `.venv` y `.install_failed`, o ejecuta `bash install.sh` a mano para ver el error. |
| Workana bloquea o devuelve errores | Espera unos minutos y usa menos consultas (`max_consultas`) o menos páginas. |
| "No hay proyectos con esos filtros" | Amplía `publicados` a `semana`, añade más skills o quita el presupuesto mínimo. |
| Cobertura menor al total de Workana | Sube `max_consultas` (hasta 30), a costa de más tiempo (~1,2 s por consulta). |

## Desarrollo

```
src/workana_mcp/
├── server.py      # herramientas MCP y formato de salida
├── client.py      # cliente HTTP: URLs, límite de frecuencia, caché, búsqueda que destapa resultados ocultos
├── parsers.py     # extracción de datos del HTML/JSON de Workana
└── analysis.py    # puntaje de oportunidad, alertas y consejos
tests/
├── test_all.py    # pruebas (sin red, con respuestas reales guardadas)
└── fixtures/
```

```bash
.venv/bin/python tests/test_all.py
```

Las pruebas no hacen peticiones a Workana: usan respuestas reales guardadas. Si Workana cambia su web, fallarán o habrá que ajustar `parsers.py`.

## Limitaciones y uso responsable

- El puntaje es una **heurística** para priorizar, no una garantía de que un proyecto o un cliente sea bueno.
- Es **solo lectura**: no inicia sesión, no envía propuestas ni mensajes.
- Depende del HTML de Workana: si cambia su web, habrá que ajustar `parsers.py`.
- Es para **uso personal** y con pocas consultas. No lo uses para recolectar datos de forma masiva ni para automatizar el envío de propuestas: va contra los términos de Workana y pone en riesgo tu cuenta.

## Licencia

[MIT](LICENSE)
