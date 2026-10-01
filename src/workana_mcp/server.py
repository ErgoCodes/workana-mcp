"""Servidor MCP de Workana (solo lectura): buscar proyectos, ver detalles y evaluar oportunidades."""

from __future__ import annotations

import json
from typing import Annotated, Literal

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from . import analysis, parsers
from .client import DEFAULT_SKILLS, WorkanaClient, WorkanaError, build_search_url

mcp = FastMCP("workana_mcp")
_client = WorkanaClient()

READ_ONLY = {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True}

Formato = Literal["markdown", "json"]
Categoria = Literal["programacion", "diseno", "redaccion", "marketing", "soporte", "legal", "finanzas", "ingenieria", "todas"]
Subcategoria = Literal["web", "diseno_web", "ecommerce", "wordpress", "apps_moviles", "data_science",
                       "escritorio", "inteligencia_artificial", "otros"]
Publicados = Literal["24h", "3d", "semana", "cualquiera"]

SKILLS_DESC = (
    "Skills de Workana (se combinan con O). Acepta nombres ('React', 'Node.js', 'TypeScript') o slugs "
    "('react-js', 'node-js', 'typescript', 'next-js', 'express-js', 'nest-js', 'javascript', 'react-native', "
    "'vue-js', 'angular', 'mongodb', 'mysql', 'sql', 'api', 'rest-api', 'firebase', 'docker', 'python', 'php', "
    "'laravel', 'wordpress', 'shopify', 'chatbot', 'web-scraping'). Vacío = tu stack por defecto (React, Node, "
    "TypeScript, Next, Express, Nest). Pasa [] junto con 'texto' para buscar solo por texto."
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _money(b: dict) -> str:
    if not b or (b.get("min") is None and b.get("max") is None):
        return (b or {}).get("texto") or "—"
    return b.get("texto") or "—"


def _passes(p: dict, presupuesto_min_usd: float | None, tarifa_min_hora: float | None, max_propuestas: int | None) -> bool:
    b = p.get("presupuesto") or {}
    top = b.get("max") if b.get("max") is not None else b.get("min")
    if max_propuestas is not None and p.get("propuestas") is not None and p["propuestas"] > max_propuestas:
        return False
    if b.get("por_hora"):
        if tarifa_min_hora is not None and top is not None and top < tarifa_min_hora:
            return False
    elif presupuesto_min_usd is not None and top is not None and top < presupuesto_min_usd:
        return False
    return True


def _merge(listing: dict | None, page: dict | None) -> dict:
    """Combina datos del listado (presupuesto, país, pago verificado) con la página (cliente, descripción completa)."""
    if not listing and not page:
        return {}
    out = dict(listing or {})
    if page:
        for k in ("slug", "url", "titulo", "estado", "fecha_publicacion", "categoria", "subcategoria", "tamano",
                  "alcance", "plazo", "otros_campos", "freelancers_interesados", "otros_proyectos_del_cliente"):
            if page.get(k) is not None:
                out[k] = page[k]
        if page.get("descripcion"):
            out["descripcion"] = page["descripcion"]
        if page.get("skills"):
            out["skills"] = page["skills"]
        if page.get("propuestas") is not None:
            out["propuestas"] = page["propuestas"]
        cli = dict(out.get("cliente") or {})
        for k, v in (page.get("cliente") or {}).items():
            if v is not None and (cli.get(k) is None or k in ("calificacion",)):
                cli[k] = v
        out["cliente"] = cli
        if not out.get("presupuesto"):
            out["presupuesto"] = parsers.parse_budget(page.get("presupuesto_pagina"))
    return out


async def _full_project(proyecto: str) -> dict:
    page = await _client.project(proyecto)
    listing = await _client.find_in_search(page["slug"], page["titulo"])
    merged = _merge(listing, page)
    if listing is None:
        merged["nota"] = ("No se encontró el proyecto en el listado público: presupuesto, país y pago verificado "
                          "pueden faltar.")
    return merged


def _row(i: int, p: dict, ev: dict | None = None) -> str:
    c = p.get("cliente") or {}
    bits = [
        f"**{i}. [{p.get('titulo')}]({p.get('url')})**",
        f"   💵 {_money(p.get('presupuesto'))} · 📨 {p.get('propuestas', '?')} propuestas · 🕒 {p.get('publicado') or p.get('fecha_publicacion') or '?'}"
        f" · 🌎 {c.get('pais') or c.get('codigo_pais') or '?'}"
        f" · {'✅ pago verificado' if c.get('metodo_pago_verificado') else '⚠️ pago no verificado'}"
        + (f" · ⭐ {c['calificacion']:g}" if c.get("calificacion") else ""),
        f"   🧩 {', '.join(p.get('skills') or []) or '—'}",
    ]
    if ev:
        bits.append(f"   🎯 Oportunidad **{ev['puntaje']}/100** ({ev['prioridad']})"
                    + (f" · 🚩 {'; '.join(ev['alertas'])}" if ev["alertas"] else ""))
    desc = " ".join((p.get("descripcion") or "").split())
    if desc:
        bits.append(f"   {desc[:260]}{'…' if len(desc) > 260 else ''}")
    bits.append(f"   slug: `{p.get('slug')}`")
    return "\n".join(bits)


def _eval_md(p: dict, ev: dict) -> str:
    c = p.get("cliente") or {}
    lines = [
        f"# {p.get('titulo')}",
        f"{p.get('url')}",
        "",
        f"**Oportunidad: {ev['puntaje']}/100 — prioridad {ev['prioridad']}**",
        "",
        "| Criterio | Puntos |", "|---|---|",
        *[f"| {k.replace('_', ' ')} | {v} |" for k, v in ev["desglose"].items()],
        "",
        f"- Estado: {p.get('estado') or '?'} · Publicado: {p.get('fecha_publicacion') or p.get('publicado') or '?'}",
        f"- Presupuesto: {_money(p.get('presupuesto'))} ({ev['presupuesto_nota']})"
        + (f" · Tamaño: {p['tamano']}" if p.get("tamano") else "")
        + (f" · Plazo: {p['plazo']}" if p.get("plazo") else ""),
        f"- Competencia: {p.get('propuestas', '?')} propuestas"
        + (f", {p['freelancers_interesados']} interesados" if p.get("freelancers_interesados") is not None else ""),
        f"- Cliente: {c.get('nombre') or '?'} · {c.get('pais') or c.get('codigo_pais') or '?'}"
        f" · publicados {c.get('proyectos_publicados', '?')} · pagados {c.get('proyectos_pagados', '?')}"
        f" · miembro desde {c.get('miembro_desde') or '?'}"
        + (f" · ⭐ {c['calificacion']:g}" if c.get("calificacion") else "")
        + f" · {'pago verificado' if c.get('metodo_pago_verificado') else 'pago NO verificado'}",
        f"- Skills: {', '.join(p.get('skills') or [])}",
        f"  - Coinciden con tu perfil: {', '.join(ev['skills']['coinciden']) or '—'}"
        f" ({ev['skills']['porcentaje_cubierto']}%)",
        f"  - No tienes: {', '.join(ev['skills']['no_tengo']) or '—'}",
    ]
    for title, key in (("🚩 Alertas", "alertas"), ("👍 A favor", "a_favor"), ("👎 En contra", "en_contra"), ("💡 Consejos para la propuesta", "consejos")):
        if ev[key]:
            lines += ["", f"**{title}**", *[f"- {x}" for x in ev[key]]]
    if p.get("descripcion"):
        lines += ["", "**Descripción**", p["descripcion"]]
    if p.get("nota"):
        lines += ["", f"_Nota: {p['nota']}_"]
    return "\n".join(lines)


def _coverage(res: dict) -> str:
    total, seen = res.get("total") or 0, len(res.get("proyectos") or [])
    txt = f"vistos {seen} de {total} que reporta Workana ({res.get('consultas')} consultas)"
    if res.get("incompleto") and seen < total:
        txt += "; sube max_consultas para ver el resto"
    return txt


def _err(e: Exception) -> str:
    return f"Error: {e}"


# ---------------------------------------------------------------------------
# tools
# ---------------------------------------------------------------------------

@mcp.tool(name="workana_buscar_proyectos", annotations={"title": "Buscar proyectos en Workana", **READ_ONLY})
async def workana_buscar_proyectos(
    texto: Annotated[str | None, Field(description="Texto libre, p. ej. 'dashboard', 'ecommerce', 'api'.", max_length=120)] = None,
    skills: Annotated[list[str] | None, Field(description=SKILLS_DESC, max_length=15)] = None,
    categoria: Annotated[Categoria, Field(description="Categoría de Workana.")] = "programacion",
    subcategoria: Annotated[Subcategoria | None, Field(description="Subcategoría (solo para 'programacion').")] = None,
    idioma: Annotated[Literal["es", "pt", "en", "todos"], Field(description="Idioma del proyecto.")] = "es",
    modalidad: Annotated[Literal["precio_fijo", "por_hora"] | None, Field(description="Tipo de contrato.")] = None,
    publicados: Annotated[Publicados, Field(description="Antigüedad máxima del proyecto.")] = "semana",
    pocas_propuestas: Annotated[bool, Field(description="Solo proyectos con 0-4 propuestas.")] = False,
    pais_cliente: Annotated[str | None, Field(description="Código ISO del país del cliente, p. ej. 'AR', 'MX', 'ES', 'US'.", min_length=2, max_length=2)] = None,
    presupuesto_min_usd: Annotated[float | None, Field(description="Descarta proyectos de precio fijo cuyo máximo sea menor.", ge=0)] = None,
    tarifa_min_hora: Annotated[float | None, Field(description="Descarta proyectos por hora cuya tarifa máxima sea menor (USD/h).", ge=0)] = None,
    max_propuestas: Annotated[int | None, Field(description="Descarta proyectos con más propuestas que esto.", ge=0)] = None,
    max_consultas: Annotated[int, Field(description="Máximo de peticiones al listado. Sin sesión Workana oculta 13 de cada 20 resultados, así que el servidor divide la búsqueda (por skill, modalidad, propuestas, subcategoría) para verlos todos. Más consultas = más completo pero más lento (~1,5 s c/u).", ge=1, le=30)] = 20,
    ordenar_por: Annotated[Literal["oportunidad", "recientes", "menos_propuestas"], Field(description="Orden del resultado.")] = "oportunidad",
    mis_skills: Annotated[list[str] | None, Field(description="Tu stack para calcular el encaje. Vacío = perfil por defecto (React, Node, TypeScript, Next…).")] = None,
    formato: Annotated[Formato, Field(description="'markdown' para leer, 'json' para procesar.")] = "markdown",
) -> str:
    """Busca proyectos abiertos en Workana con filtros y les pone un puntaje rápido de oportunidad (0-100)
    según encaje con tu stack, competencia, presupuesto, cliente y frescura.
    Solo lee el listado público: para datos del cliente (proyectos pagados, antigüedad) usa workana_evaluar_proyecto."""
    sk = DEFAULT_SKILLS if skills is None else skills
    try:
        res = await _client.search_all(
            max_consultas=max_consultas, texto=texto, skills=sk, categoria=categoria, subcategoria=subcategoria,
            idioma=idioma, modalidad=modalidad, publicados=publicados, pocas_propuestas=pocas_propuestas,
            pais_cliente=pais_cliente)
    except WorkanaError as e:
        return _err(e)
    items, total, first_url = res["proyectos"], res["total"], res["url_busqueda"]
    cobertura = _coverage(res)
    filtered = [p for p in items if _passes(p, presupuesto_min_usd, tarifa_min_hora, max_propuestas)]
    evals = {p["slug"]: analysis.evaluate(p, mis_skills) for p in filtered}
    if ordenar_por == "oportunidad":
        filtered.sort(key=lambda p: -evals[p["slug"]]["puntaje"])
    elif ordenar_por == "menos_propuestas":
        filtered.sort(key=lambda p: (p.get("propuestas") is None, p.get("propuestas") or 0))
    else:
        filtered.sort(key=lambda p: (p.get("horas_desde_publicacion") is None, p.get("horas_desde_publicacion") or 0))

    if formato == "json":
        return json.dumps({
            "total_en_workana": total, "leidos": len(items), "tras_filtros": len(filtered), "url": first_url,
            "consultas": res["consultas"], "cobertura": cobertura,
            "proyectos": [{**p, "oportunidad": {k: evals[p["slug"]][k] for k in ("puntaje", "prioridad", "desglose", "alertas")}}
                          for p in filtered],
        }, ensure_ascii=False, indent=1)
    if not filtered:
        return (f"No hay proyectos con esos filtros (Workana reporta {total or 0} en total; leídos {len(items)}). "
                "Prueba con publicados='semana', más skills o sin presupuesto mínimo.\n" + (first_url or ""))
    head = (f"**{len(filtered)} proyectos** tras tus filtros — {cobertura} — orden: {ordenar_por}\n"
            f"[Ver búsqueda en Workana]({first_url})\n")
    return head + "\n\n".join(_row(i, p, evals[p["slug"]]) for i, p in enumerate(filtered, 1)) + \
        "\n\n_Puntaje rápido sin datos del cliente. Usa workana_evaluar_proyecto con el slug para el análisis completo._"


@mcp.tool(name="workana_ver_proyecto", annotations={"title": "Ver un proyecto de Workana", **READ_ONLY})
async def workana_ver_proyecto(
    proyecto: Annotated[str, Field(description="URL del proyecto (https://www.workana.com/job/...) o su slug.", min_length=3)],
    formato: Annotated[Formato, Field(description="'markdown' o 'json'.")] = "markdown",
) -> str:
    """Ficha completa de un proyecto: descripción entera, skills, presupuesto, propuestas, freelancers interesados,
    y datos del cliente (país, calificación, proyectos publicados/pagados, miembro desde, pago verificado, otros proyectos)."""
    try:
        p = await _full_project(proyecto)
    except (WorkanaError, ValueError) as e:
        return _err(e)
    if formato == "json":
        return json.dumps(p, ensure_ascii=False, indent=1)
    c = p.get("cliente") or {}
    lines = [
        f"# {p.get('titulo')}", p.get("url") or "", "",
        f"- Estado: {p.get('estado')} · Publicado: {p.get('fecha_publicacion') or p.get('publicado')}",
        f"- Categoría: {p.get('categoria')} / {p.get('subcategoria')}",
        f"- Presupuesto: {_money(p.get('presupuesto'))} · Modalidad: {p.get('modalidad', '?')}"
        + (f" · Tamaño: {p['tamano']}" if p.get("tamano") else "") + (f" · Alcance: {p['alcance']}" if p.get("alcance") else "")
        + (f" · Plazo: {p['plazo']}" if p.get("plazo") else ""),
        f"- Propuestas: {p.get('propuestas')} · Freelancers interesados: {p.get('freelancers_interesados')}",
        f"- Skills: {', '.join(p.get('skills') or [])}",
        f"- Cliente: {c.get('nombre')} · {c.get('pais') or c.get('codigo_pais')} · ⭐ {c.get('calificacion')}"
        f" · publicados {c.get('proyectos_publicados')} · pagados {c.get('proyectos_pagados')}"
        f" · miembro desde {c.get('miembro_desde')} · pago verificado: {'sí' if c.get('metodo_pago_verificado') else 'no'}",
        "", "## Descripción", p.get("descripcion") or "—",
    ]
    if p.get("otros_proyectos_del_cliente"):
        lines += ["", "## Otros proyectos del cliente",
                  *[f"- {o['titulo']} ({o.get('estado')}; {o.get('detalle')})" for o in p["otros_proyectos_del_cliente"]]]
    if p.get("nota"):
        lines += ["", f"_Nota: {p['nota']}_"]
    return "\n".join(lines)


@mcp.tool(name="workana_evaluar_proyecto", annotations={"title": "Evaluar si conviene postularse", **READ_ONLY})
async def workana_evaluar_proyecto(
    proyecto: Annotated[str, Field(description="URL del proyecto o su slug.", min_length=3)],
    mis_skills: Annotated[list[str] | None, Field(description="Tu stack. Vacío = perfil por defecto (React, Node, TypeScript, Next, Express…).")] = None,
    formato: Annotated[Formato, Field(description="'markdown' o 'json'.")] = "markdown",
) -> str:
    """Analiza a fondo un proyecto y dice si vale la pena postularse: puntaje 0-100 con desglose (encaje de skills,
    competencia, presupuesto, calidad del cliente, frescura), alertas (pago fuera de Workana, trabajo gratis,
    contacto por WhatsApp…), puntos a favor/en contra y consejos para la propuesta."""
    try:
        p = await _full_project(proyecto)
    except (WorkanaError, ValueError) as e:
        return _err(e)
    ev = analysis.evaluate(p, mis_skills)
    if formato == "json":
        return json.dumps({"proyecto": p, "evaluacion": ev}, ensure_ascii=False, indent=1)
    return _eval_md(p, ev)


@mcp.tool(name="workana_mejores_oportunidades", annotations={"title": "Mejores oportunidades de Workana", **READ_ONLY})
async def workana_mejores_oportunidades(
    skills: Annotated[list[str] | None, Field(description=SKILLS_DESC, max_length=15)] = None,
    texto: Annotated[str | None, Field(description="Texto libre opcional.", max_length=120)] = None,
    publicados: Annotated[Publicados, Field(description="Antigüedad máxima.")] = "3d",
    idioma: Annotated[Literal["es", "pt", "en", "todos"], Field(description="Idioma del proyecto.")] = "es",
    modalidad: Annotated[Literal["precio_fijo", "por_hora"] | None, Field(description="Tipo de contrato.")] = None,
    presupuesto_min_usd: Annotated[float | None, Field(description="Mínimo para proyectos de precio fijo (USD).", ge=0)] = 100,
    tarifa_min_hora: Annotated[float | None, Field(description="Mínimo para proyectos por hora (USD/h).", ge=0)] = 10,
    max_propuestas: Annotated[int | None, Field(description="Descarta proyectos con más propuestas.", ge=0)] = 40,
    max_consultas: Annotated[int, Field(description="Máximo de peticiones al listado. Sin sesión Workana oculta 13 de cada 20 resultados, así que el servidor divide la búsqueda (por skill, modalidad, propuestas, subcategoría) para verlos todos. Más consultas = más completo pero más lento (~1,5 s c/u).", ge=1, le=30)] = 20,
    top: Annotated[int, Field(description="Cuántos proyectos analizar a fondo (1 petición extra c/u).", ge=1, le=10)] = 5,
    mis_skills: Annotated[list[str] | None, Field(description="Tu stack. Vacío = perfil por defecto.")] = None,
    formato: Annotated[Formato, Field(description="'markdown' o 'json'.")] = "markdown",
) -> str:
    """Flujo completo para el día: busca proyectos recientes de tu stack, descarta los malos (presupuesto bajo,
    demasiada competencia), analiza a fondo los mejores N (incluye historial de pagos del cliente) y los devuelve
    ordenados por puntaje con alertas y consejos. Ideal para una revisión diaria."""
    sk = DEFAULT_SKILLS if skills is None else skills
    try:
        res = await _client.search_all(max_consultas=max_consultas, texto=texto, skills=sk, categoria="programacion",
                                       idioma=idioma, modalidad=modalidad, publicados=publicados)
    except WorkanaError as e:
        return _err(e)
    items = res["proyectos"]
    cands = [p for p in items if _passes(p, presupuesto_min_usd, tarifa_min_hora, max_propuestas)]
    quick = sorted(cands, key=lambda p: -analysis.evaluate(p, mis_skills)["puntaje"])[:top]
    results = []
    for p in quick:
        try:
            page = await _client.project(p["slug"])
            full = _merge(p, page)
        except WorkanaError:
            full = p
        results.append((full, analysis.evaluate(full, mis_skills)))
    results.sort(key=lambda x: -x[1]["puntaje"])
    if formato == "json":
        return json.dumps({"leidos": len(items), "candidatos": len(cands), "cobertura": _coverage(res),
                           "resultados": [{"proyecto": p, "evaluacion": ev} for p, ev in results]},
                          ensure_ascii=False, indent=1)
    if not results:
        return (f"Leí {len(items)} proyectos y ninguno pasó los filtros (presupuesto ≥ {presupuesto_min_usd}, "
                f"tarifa ≥ {tarifa_min_hora}/h, ≤ {max_propuestas} propuestas). Prueba publicados='semana' o baja los mínimos.")
    out = [f"**Top {len(results)}** de {len(cands)} candidatos (publicados: {publicados}; {_coverage(res)})\n"]
    for i, (p, ev) in enumerate(results, 1):
        out.append(_row(i, p, ev))
        c = p.get("cliente") or {}
        extra = []
        if c.get("proyectos_pagados") is not None:
            extra.append(f"cliente: {c.get('proyectos_publicados')} publicados / {c.get('proyectos_pagados')} pagados, desde {c.get('miembro_desde')}")
        if p.get("freelancers_interesados") is not None:
            extra.append(f"{p['freelancers_interesados']} interesados")
        if extra:
            out.append("   👤 " + " · ".join(extra))
        if ev["en_contra"]:
            out.append("   👎 " + " ".join(ev["en_contra"][:3]))
        out.append("   💡 " + ev["consejos"][0])
        out.append("")
    return "\n".join(out)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
