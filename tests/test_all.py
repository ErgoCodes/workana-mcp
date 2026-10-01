"""Tests offline con respuestas reales de Workana guardadas en tests/fixtures.
Ejecuta:  python -m pytest tests   (o  python tests/test_all.py)"""

import asyncio
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from workana_mcp import analysis, parsers, server  # noqa: E402
from workana_mcp.client import build_search_url  # noqa: E402

FX = ROOT / "tests" / "fixtures"
SEARCH = json.loads((FX / "search.json").read_text(encoding="utf-8"))
DETAIL = (FX / "detail.html").read_text(encoding="utf-8")


def test_budget():
    assert parsers.parse_budget("USD 100 - 250") == {"texto": "USD 100 - 250", "moneda": "USD", "min": 100, "max": 250, "por_hora": False}
    b = parsers.parse_budget("USD 1.000 - 3.000")
    assert (b["min"], b["max"]) == (1000, 3000)
    b = parsers.parse_budget("USD 15 - 45 / hora")
    assert b["por_hora"] and b["max"] == 45
    b = parsers.parse_budget("Menos de USD 15 / hora")
    assert b["min"] == 0 and b["max"] == 15 and b["por_hora"]
    b = parsers.parse_budget("Más de USD 3.000")
    assert b["min"] == 3000 and b["max"] is None
    assert parsers.parse_budget("Abierto")["min"] is None


def test_hours_ago():
    assert parsers.hours_ago("Hace 13 horas") == 13
    assert parsers.hours_ago("Hace 11 minutos") < 0.2
    assert parsers.hours_ago("Hace 2 días") == 48
    assert parsers.hours_ago("há 1 hora") == 1
    assert parsers.hours_ago("Hace 1 semana") == 168


def test_slug():
    assert parsers.slug_from("https://www.workana.com/es/job/dossieres?ref=x") == "dossieres"
    assert parsers.slug_from("dossieres") == "dossieres"


def test_search_parse():
    r = parsers.parse_search_json(SEARCH)
    assert r["total"] == 398 and r["paginas"] == 20
    p = r["proyectos"][0]
    assert p["titulo"] == "Desarrollo de Plataforma de Marketing Digital con Ia para Pymes"
    assert p["propuestas"] == 18
    assert p["presupuesto"]["por_hora"] and p["presupuesto"]["max"] == 45
    assert p["cliente"]["pais"] == "Brasil" and p["cliente"]["codigo"] == "BR"
    assert "React.js" in p["skills"]
    assert "Categoría" not in p["descripcion"]
    assert r["proyectos"][2]["cliente"]["metodo_pago_verificado"] is True


def test_detail_parse():
    d = parsers.parse_project_page(DETAIL, "desarrollo-de-soluciones-de-automatizacion-con-inteligencia-artificial")
    assert d["titulo"].startswith("Desarrollo de Soluciones")
    assert d["estado"] == "Evaluando propuestas"
    assert d["fecha_publicacion"] == "2026-09-30"
    assert d["subcategoria"] == "Inteligencia Artificial"
    assert d["tamano"] == "Medio"
    assert d["plazo"] == "No definido"
    assert d["skills"] == ["Machine Learning", "Python", "Node.js"]
    assert d["propuestas"] == 31 and d["freelancers_interesados"] == 40
    c = d["cliente"]
    assert c["nombre"] == "T. E." and c["calificacion"] == 5.0 and c["codigo_pais"] == "ES"
    assert c["proyectos_publicados"] == 8 and c["proyectos_pagados"] == 1
    assert c["miembro_desde"] == "2024-02"
    assert d["otros_proyectos_del_cliente"][0]["slug"] == "dossieres"


def test_merge_and_evaluate():
    listing = parsers.parse_search_json(SEARCH)["proyectos"][2]
    page = parsers.parse_project_page(DETAIL, listing["slug"])
    m = server._merge(listing, page)
    assert m["presupuesto"]["max"] == 3000
    assert m["cliente"]["metodo_pago_verificado"] is True and m["cliente"]["proyectos_pagados"] == 1
    ev = analysis.evaluate(m)
    assert 0 <= ev["puntaje"] <= 100
    assert any("gratis" in a for a in ev["alertas"])
    assert "Node.js" in ev["skills"]["coinciden"]


def test_red_flag_whatsapp():
    p = parsers.parse_search_json(SEARCH)["proyectos"][1]
    ev = analysis.evaluate(p)
    assert any("fuera de Workana" in a for a in ev["alertas"])


def test_stack_scores_higher():
    items = parsers.parse_search_json(SEARCH)["proyectos"]
    react = analysis.evaluate(items[0])["skills"]["puntos"]
    ml = analysis.evaluate(items[2])["skills"]["puntos"]
    assert react > ml


def test_url():
    u = build_search_url(texto="dashboard", skills=["React", "node.js", "typescript"], publicados="24h",
                         modalidad="precio_fijo", pocas_propuestas=True, pais_cliente="ar", pagina=2)
    assert "skills=react-js%2Cnode-js%2Ctypescript" in u
    for part in ("query=dashboard", "category=it-programming", "language=es", "agreement=fixed",
                 "publication=1d", "has_few_bids=1", "country=AR", "page=2"):
        assert part in u, part
    assert "language=xx" in build_search_url(idioma="todos")


def test_tools_registered():
    tools = asyncio.run(server.mcp.list_tools())
    names = {t.name for t in tools}
    assert names == {"workana_buscar_proyectos", "workana_ver_proyecto", "workana_evaluar_proyecto",
                     "workana_mejores_oportunidades"}
    assert all(t.annotations.readOnlyHint for t in tools)


def _fake_workana(dataset):
    """Imita a Workana sin sesión: devuelve el total real pero solo 7 de cada 20 resultados por página."""
    from urllib.parse import parse_qs, urlparse

    async def fake(url, headers=None):
        q = {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}
        rows = dataset
        if "skills" in q:
            want = set(q["skills"].split(","))
            rows = [r for r in rows if want & set(r["sk"])]
        if "agreement" in q:
            rows = [r for r in rows if r["ag"] == q["agreement"]]
        if "has_few_bids" in q:
            rows = [r for r in rows if (r["bids"] <= 4) == (q["has_few_bids"] == "1")]
        if "subcategory" in q:
            rows = [r for r in rows if r["sub"] == q["subcategory"]]
        page = int(q.get("page", 1))
        chunk = rows[(page - 1) * 20:(page - 1) * 20 + 7]
        return json.dumps({"results": {
            "resultDescription": {"count": len(rows)},
            "results": [{"slug": r["slug"], "title": r["slug"], "budget": "USD 100 - 250", "isHourly": r["ag"] == "hourly",
                         "totalBids": f"Propuestas: {r['bids']}", "skills": [{"anchorText": s} for s in r["sk"]]} for r in chunk],
            "pagination": {"total": len(rows), "page": page, "pages": max(1, -(-len(rows) // 20))}}})
    return fake


def test_search_all_uncovers_hidden_results():
    import random
    from workana_mcp.client import SUBCATEGORIES, WorkanaClient
    rnd = random.Random(1)
    subs = list(SUBCATEGORIES.values())
    data = [{"slug": f"p{i}", "sk": rnd.sample(["react-js", "node-js", "typescript"], rnd.randint(1, 2)),
             "ag": rnd.choice(["fixed", "hourly"]), "bids": rnd.randint(0, 40), "sub": rnd.choice(subs)} for i in range(60)]
    c = WorkanaClient()
    c.get_text = _fake_workana(data)
    res = asyncio.run(c.search_all(max_consultas=60, skills=["react-js", "node-js", "typescript"], categoria="programacion"))
    assert res["total"] == 60
    assert len(res["proyectos"]) == 60, len(res["proyectos"])
    # con presupuesto pequeño devuelve lo que pudo y lo marca como incompleto
    c2 = WorkanaClient()
    c2.get_text = _fake_workana(data)
    res2 = asyncio.run(c2.search_all(max_consultas=3, skills=["react-js", "node-js", "typescript"]))
    assert res2["incompleto"] and res2["consultas"] == 3 and 7 <= len(res2["proyectos"]) < 60


if __name__ == "__main__":
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("ok  ", name)
            except Exception as e:  # noqa: BLE001
                fails += 1
                print("FAIL", name, repr(e))
    sys.exit(1 if fails else 0)
