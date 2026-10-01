"""Convierte las respuestas de Workana (JSON del listado y HTML de un proyecto) en dicts limpios."""

from __future__ import annotations

import html as htmllib
import re
from typing import Any

from bs4 import BeautifulSoup

BASE = "https://www.workana.com"


# ---------------------------------------------------------------------------
# utilidades
# ---------------------------------------------------------------------------

def strip_html(s: str | None) -> str:
    if not s:
        return ""
    s = re.sub(r"<br\s*/?>", "\n", s, flags=re.I)
    s = re.sub(r"</p>|</li>", "\n", s, flags=re.I)
    s = re.sub(r"<[^>]+>", "", s)
    s = htmllib.unescape(s)
    s = re.sub(r"[ \t\r\f\v\xa0]+", " ", s)
    s = "\n".join(line.strip() for line in s.split("\n"))
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def _int(s: Any) -> int | None:
    if s is None:
        return None
    m = re.search(r"\d[\d.,]*", str(s))
    if not m:
        return None
    return int(re.sub(r"[.,]", "", m.group(0)))


def _money(s: str) -> float:
    """'1.000' -> 1000 ; '15' -> 15 ; '1,5' -> 1.5 (Workana usa punto como separador de miles)."""
    s = s.strip()
    if re.fullmatch(r"\d{1,3}(\.\d{3})+", s):
        return float(s.replace(".", ""))
    return float(s.replace(".", "").replace(",", "."))


def parse_budget(text: str | None) -> dict:
    """Interpreta textos como 'USD 100 - 250', 'USD 15 - 45 / hora', 'Menos de USD 50',
    'Más de USD 3.000', 'Menos de USD 15 / hora', 'Abierto'."""
    t = (text or "").strip()
    out: dict[str, Any] = {"texto": t or None, "moneda": None, "min": None, "max": None, "por_hora": None}
    if not t:
        return out
    low = t.lower()
    out["por_hora"] = ("hora" in low) or ("/ h" in low) or ("hour" in low)
    m = re.search(r"\b(USD|US\$|BRL|R\$|EUR|ARS|MXN|COP|CLP)\b", t)
    out["moneda"] = m.group(1) if m else ("USD" if "$" in t else None)
    nums = [_money(x) for x in re.findall(r"\d[\d.,]*", t)]
    if not nums:
        return out
    if re.search(r"menos de|less than|at[eé] |hasta", low):
        out["min"], out["max"] = 0.0, nums[0]
    elif re.search(r"m[aá]s de|more than|over|acima de|mais de", low):
        out["min"], out["max"] = nums[0], None
    elif len(nums) >= 2:
        out["min"], out["max"] = nums[0], nums[1]
    else:
        out["min"] = out["max"] = nums[0]
    return out


_UNITS_H = {
    "segundo": 1 / 3600, "minuto": 1 / 60, "hora": 1, "día": 24, "dia": 24,
    "semana": 24 * 7, "mes": 24 * 30, "meses": 24 * 30, "año": 24 * 365, "ano": 24 * 365,
    "minute": 1 / 60, "hour": 1, "day": 24, "week": 24 * 7, "month": 24 * 30, "year": 24 * 365,
}


def hours_ago(text: str | None) -> float | None:
    """'Hace 13 horas' -> 13 ; 'Hace 11 minutos' -> 0.18 ; 'Hace 2 días' -> 48 ; 'há 1 hora' -> 1."""
    if not text:
        return None
    low = text.lower()
    if re.search(r"ahora|agora|just now|reci[eé]n", low):
        return 0.0
    m = re.search(r"(\d+|un|una|uma|um|an|a)\s+([a-záéíóúñç]+)", low)
    if not m:
        if "ayer" in low or "ontem" in low or "yesterday" in low:
            return 24.0
        return None
    n_raw, unit = m.group(1), m.group(2)
    n = int(n_raw) if n_raw.isdigit() else 1
    for key, h in _UNITS_H.items():
        if unit.startswith(key[:4]) or unit.startswith(key):
            return round(n * h, 2)
    return None


def slug_from(url_or_slug: str) -> str:
    s = (url_or_slug or "").strip()
    m = re.search(r"/job/(?:insight/)?([a-z0-9\-]+)", s)
    if m:
        return m.group(1)
    s = s.strip("/").split("?")[0].split("#")[0]
    if not re.fullmatch(r"[a-z0-9\-]+", s):
        raise ValueError("No reconozco el proyecto. Pasa la URL completa (https://www.workana.com/job/...) o el slug.")
    return s


def project_url(slug: str) -> str:
    return f"{BASE}/job/{slug}"


# ---------------------------------------------------------------------------
# listado (/jobs con X-Requested-With -> JSON)
# ---------------------------------------------------------------------------

def _country(html_: str | None) -> dict:
    if not html_:
        return {"pais": None, "codigo": None}
    code = re.search(r"country=([A-Z]{2})", html_)
    name = re.search(r'title="([^"]+)"', html_)
    if not name:
        name_txt = strip_html(html_)
    else:
        name_txt = htmllib.unescape(name.group(1))
    return {"pais": name_txt or None, "codigo": code.group(1) if code else None}


def parse_search_item(r: dict) -> dict:
    title = r.get("title") or ""
    m = re.search(r'title="([^"]+)"', title)
    title_txt = htmllib.unescape(m.group(1)) if m else strip_html(title)
    rating = r.get("rating") or {}
    try:
        rating_v = float(rating.get("value")) if rating.get("value") not in (None, "") else None
    except (TypeError, ValueError):
        rating_v = None
    desc = strip_html(r.get("description"))
    # el listado añade "Categoría: X / Subcategoría: Y" al final de la descripción
    extra = dict(re.findall(r"^(Categor[ií]a|Subcategor[ií]a|[¿?][^:\n]+[?]):\s*(.+)$", desc, flags=re.M))
    desc_clean = re.split(r"\n\s*Categor[ií]a:", desc)[0].strip()
    budget = parse_budget(r.get("budget"))
    if budget["por_hora"] is None and r.get("isHourly") is not None:
        budget["por_hora"] = bool(r.get("isHourly"))
    return {
        "slug": r.get("slug"),
        "titulo": title_txt,
        "url": project_url(r.get("slug") or ""),
        "publicado": r.get("postedDate"),
        "horas_desde_publicacion": hours_ago(r.get("postedDate")),
        "presupuesto": budget,
        "modalidad": "por_hora" if r.get("isHourly") else "precio_fijo",
        "propuestas": _int(r.get("totalBids")),
        "skills": [s.get("anchorText") for s in (r.get("skills") or []) if s.get("anchorText")],
        "cliente": {
            "nombre": r.get("authorName"),
            **_country(r.get("country")),
            "calificacion": rating_v,
            "metodo_pago_verificado": bool(r.get("hasVerifiedPaymentMethod")),
            "plan": r.get("projectClientPlanLabel"),
            "es_empresa": bool(r.get("isCompany")),
        },
        "urgente": bool(r.get("isUrgent")),
        "destacado": bool(r.get("isSearchFeatured")),
        "ultimo_mensaje_cliente": r.get("lastEmployerMessage"),
        "descripcion": desc_clean,
        "extra": {k: v for k, v in extra.items()} or None,
    }


def parse_search_json(data: dict) -> dict:
    res = (data or {}).get("results") or {}
    items = res.get("results") or []
    pag = res.get("pagination") or {}
    total = (res.get("resultDescription") or {}).get("count")
    return {
        "total": total if total is not None else pag.get("total"),
        "pagina": pag.get("page"),
        "paginas": pag.get("pages"),
        "proyectos": [parse_search_item(x) for x in items if x.get("slug")],
    }


# ---------------------------------------------------------------------------
# página de un proyecto (/job/<slug>)
# ---------------------------------------------------------------------------

_MONTHS = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6, "julio": 7,
    "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
}


def _date_es(text: str) -> str | None:
    m = re.search(r"(\d{1,2})\s+([A-Za-zé]+),?\s+(\d{4})", text or "")
    if not m:
        return None
    mon = _MONTHS.get(m.group(2).lower())
    if not mon:
        return None
    return f"{int(m.group(3)):04d}-{mon:02d}-{int(m.group(1)):02d}"


def _member_since(text: str) -> str | None:
    m = re.search(r"([A-Za-zé]+),?\s+(\d{4})", text or "")
    if not m:
        return None
    mon = _MONTHS.get(m.group(1).lower())
    return f"{m.group(2)}-{mon:02d}" if mon else m.group(2)


def is_blocked_page(text: str) -> bool:
    head = text[:20000]
    return ("cf-chl" in head or "challenge-platform" in head or "Just a moment..." in head
            or "Attention Required! | Cloudflare" in head)


def parse_project_page(page: str, slug: str | None = None) -> dict:
    soup = BeautifulSoup(page, "html.parser")
    root = soup.select_one("section.project-view-v3") or soup
    h1 = root.select_one("h1")
    if not h1:
        raise ValueError("La página no parece un proyecto de Workana (¿cambió el HTML o el proyecto no existe?).")
    status = root.select_one("header .label")
    header_p = root.select_one("header p")
    header_txt = header_p.get_text(" ", strip=True) if header_p else ""
    cat_hidden = root.select_one("h2.hidden")
    cat_slug, subcat_slug = None, None
    if cat_hidden and "/" in cat_hidden.get_text():
        cat_slug, subcat_slug = [x.strip() for x in cat_hidden.get_text().split("/", 1)]
    budget_el = root.select_one("h4.budget")
    budget_txt = budget_el.get_text(" ", strip=True) if budget_el else None

    desc_el = root.select_one(".block-detail .expander") or root.select_one(".specification")
    desc = strip_html(desc_el.decode_contents()) if desc_el else ""

    # "Categoría X / Subcategoría Y / Tamaño del proyecto Z / ¿Cuál es el alcance...? W"
    fields: dict[str, str] = {}
    for p in root.select(".block-detail p.mt20"):
        for b in p.find_all("b"):
            label_parts = []
            prev = b.previous_sibling
            while prev is not None and getattr(prev, "name", None) not in ("br", "b"):
                label_parts.insert(0, prev if isinstance(prev, str) else prev.get_text(" "))
                prev = prev.previous_sibling
            label = " ".join(x.strip() for x in label_parts if x and x.strip()).strip()
            if label:
                fields[label] = b.get_text(" ", strip=True)
        txt = p.get_text(" ", strip=True)
        m = re.match(r"(Plazo de Entrega|Duraci[oó]n del proyecto)\s*:?\s*(.+)", txt)
        if m:
            fields[m.group(1)] = m.group(2)

    skills = [a.get_text(" ", strip=True) for a in root.select(".block-detail .skills a.skill")]

    # cliente
    aside = root.select_one("aside") or root
    name_el = aside.select_one(".wk-user-info .user-name")
    profile_href = name_el.get("href") if name_el else None
    stars = aside.select_one(".stars-fill")
    rating = None
    if stars and stars.get("style"):
        m = re.search(r"width:\s*([\d.]+)%", stars["style"])
        if m:
            rating = round(float(m.group(1)) / 20, 2)
    flag = aside.select_one(".country .flag")
    country_code = None
    if flag:
        for c in flag.get("class", []):
            if c.startswith("flag-"):
                country_code = c[5:].upper()
    stats: dict[str, str] = {}
    for item in aside.select(".item-data"):
        ps = item.find_all("p")
        if len(ps) >= 2:
            stats[ps[1].get_text(" ", strip=True).lower()] = ps[0].get_text(" ", strip=True)
        elif len(ps) == 1:
            t = ps[0].get_text(" ", strip=True)
            if ":" in t:
                k, v = t.split(":", 1)
                stats[k.strip().lower()] = v.strip()

    other = []
    for li in root.select(".client-projects li"):
        a = li.select_one("a[href*='/job/']")
        if not a:
            continue
        spans = [s.get_text(" ", strip=True) for s in li.select("p span")]
        lab = li.select_one(".label")
        other.append({
            "titulo": a.get_text(" ", strip=True),
            "slug": slug_from(a.get("href", "")),
            "estado": lab.get_text(" ", strip=True) if lab else None,
            "detalle": " · ".join(s for s in spans if s),
        })

    return {
        "slug": slug,
        "url": project_url(slug) if slug else None,
        "titulo": h1.get_text(" ", strip=True),
        "estado": status.get_text(" ", strip=True) if status else None,
        "fecha_publicacion": _date_es(header_txt),
        "categoria": fields.get("Categoría") or cat_slug,
        "subcategoria": fields.get("Subcategoría") or subcat_slug,
        "categoria_slug": cat_slug,
        "subcategoria_slug": subcat_slug,
        "presupuesto_pagina": budget_txt,
        "tamano": fields.get("Tamaño del proyecto"),
        "alcance": next((v for k, v in fields.items() if "alcance" in k.lower()), None),
        "plazo": fields.get("Plazo de Entrega") or fields.get("Duración del proyecto") or fields.get("Duracion del proyecto"),
        "otros_campos": {k: v for k, v in fields.items() if k not in (
            "Categoría", "Subcategoría", "Tamaño del proyecto", "Plazo de Entrega", "Duración del proyecto")
            and "alcance" not in k.lower()} or None,
        "descripcion": desc,
        "skills": skills,
        "propuestas": _int(stats.get("propuestas")),
        "freelancers_interesados": _int(stats.get("freelancers interesados")),
        "cliente": {
            "nombre": name_el.get_text(" ", strip=True) if name_el else None,
            "perfil_url": (BASE + profile_href) if profile_href and profile_href.startswith("/") else profile_href,
            "calificacion": rating,
            "codigo_pais": country_code,
            "proyectos_publicados": _int(stats.get("proyectos publicados")),
            "proyectos_pagados": _int(stats.get("proyectos pagos")),
            "miembro_desde": _member_since(stats.get("miembro desde", "")),
        },
        "otros_proyectos_del_cliente": other,
    }
