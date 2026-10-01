# workana-mcp

Servidor MCP para **buscar y evaluar proyectos freelance de Workana** desde Claude.

Workana no tiene API pública, así que el servidor lee las mismas páginas públicas que ves en el navegador **sin iniciar sesión**. Es **solo lectura**: no entra en tu cuenta, no envía propuestas ni mensajes. Tú decides a qué postularte y envías la propuesta a mano.

## Herramientas

| Herramienta | Qué hace |
|---|---|
| `workana_buscar_proyectos` | Búsqueda con filtros: texto, skills, categoría/subcategoría, idioma, precio fijo o por hora, antigüedad (24h/3d/semana), solo con pocas propuestas, país del cliente, presupuesto mínimo, tarifa mínima, máximo de propuestas. Ordena por oportunidad, por fecha o por menos propuestas. |
| `workana_ver_proyecto` | Ficha completa: descripción entera, skills, presupuesto, propuestas, freelancers interesados y el cliente (país, estrellas, proyectos publicados y pagados, miembro desde, pago verificado, otros proyectos suyos). |
| `workana_evaluar_proyecto` | Puntaje de oportunidad 0-100 con desglose, alertas, puntos a favor y en contra, y consejos para la propuesta. |
| `workana_mejores_oportunidades` | Flujo diario: busca proyectos recientes de tu stack, descarta los malos, analiza a fondo los mejores N y los ordena. |

### Cómo se calcula el puntaje (0-100)

- **Encaje con tu stack (30):** tecnologías fuertes (React, Node, TypeScript, Next, Express, Nest) en los skills o en el texto, más el % de skills del proyecto que tienes.
- **Competencia (25):** 0-4 propuestas = 25 … 35+ = 2.
- **Presupuesto (20):** precio fijo (≥ 1000 USD = 20) o tarifa por hora (≥ 45 USD/h = 20).
- **Cliente (15):** pago verificado, calificación, proyectos que ya pagó y cuántos publicó.
- **Frescura (10):** menos de 6 h = 10 … más de una semana = 0.
- **Penalizaciones:** pagar o trabajar fuera de Workana, contacto por WhatsApp o Telegram, e-mail en la descripción, prueba gratis, pago con porcentaje o participación, presupuesto "bajo", "clones" de plataformas grandes, proyecto cerrado.

Prioridad: **alta** a partir de 65, **media** de 45 a 64, **baja** por debajo de 45. Es una heurística para priorizar, no una garantía.

### Tu perfil

Por defecto se usa un stack fullstack: React.js, Node.js, TypeScript, JavaScript, Next.js, Express.js, NestJS, HTML/CSS, API/REST, MongoDB, MySQL/SQL, Git y Firebase. Tienes dos formas de cambiarlo:

- Por consulta, con el parámetro `mis_skills`.
- De forma permanente, con la variable `WORKANA_MIS_SKILLS` en la configuración (lista separada por comas).

## Instalación (Linux)

La carpeta ya está en `~/Documents/mcp/workana-mcp`. Registra el lanzador `run.sh` en Claude Desktop, igual que el de OLX. La primera vez instala las dependencias solo, en `.venv`, y deja el registro en `install.log`.

1. Claude Desktop → **Configuración → Desarrollador → Editar configuración**.
2. Dentro de `"mcpServers"`, junto a `"olx-aluguel"`, agrega:

```json
"workana": {
  "command": "bash",
  "args": ["/RUTA/A/workana-mcp/run.sh"]
}
```

   Opcional, para cambiar tu perfil de skills:

```json
"workana": {
  "command": "bash",
  "args": ["/RUTA/A/workana-mcp/run.sh"],
  "env": { "WORKANA_MIS_SKILLS": "React.js,Node.js,TypeScript,Next.js,NestJS,PostgreSQL,Docker" }
}
```

3. Reinicia Claude Desktop por completo. La primera vez tarda uno o dos minutos mientras instala. Si no aparecen las herramientas `workana_*`, revisa `install.log`.

## Ejemplos (en Claude)

- "Dame las mejores oportunidades de Workana de hoy para mi stack."
- "Busca proyectos de React o Next de precio fijo, publicados en las últimas 24 horas, con pocas propuestas."
- "Evalúa este proyecto: https://www.workana.com/job/…"
- "Busca proyectos por hora de Node.js con tarifa de al menos 20 USD/h y clientes de España o EE. UU."

## Notas y limitaciones

- Sin sesión, Workana solo muestra **7 de cada 20** resultados por página (el resto lo oculta para que te registres). Para verlos todos, cuando una búsqueda tiene resultados ocultos el servidor la divide en búsquedas más pequeñas (modalidad, número de propuestas, subcategoría, skill y, como último recurso, más páginas) y une los resultados. `max_consultas` (20 por defecto, 30 como máximo) limita cuántas peticiones hace. La respuesta dice cuántos proyectos vio del total que reporta Workana.
- La página de un proyecto sin sesión no muestra presupuesto ni pago verificado. El servidor los completa buscando el proyecto en el listado por su título.
- El servidor usa `curl_cffi` (se presenta como Chrome), espera 1,5 s entre peticiones y guarda caché 5 minutos. Si Workana bloquea las consultas, espera unos minutos y usa menos páginas.
- Si Workana cambia su web, habrá que ajustar `parsers.py`. Los tests (`.venv/bin/python tests/test_all.py`) usan respuestas reales guardadas y ayudan a detectarlo.
- Es para **uso personal** y con pocas consultas. No lo uses para recolectar datos de forma masiva ni para automatizar el envío de propuestas: va contra los términos de Workana y pone en riesgo tu cuenta.
