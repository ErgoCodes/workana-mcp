"""Cliente HTTP para Workana: construcción de URLs, límite de frecuencia y caché.

Solo LEE páginas públicas (las mismas que ve cualquiera sin iniciar sesión).
No inicia sesión, no envía propuestas ni mensajes.
"""

from __future__ import annotations

import asyncio
import heapq
import json
import os
import time
from urllib.parse import urlencode

from . import parsers

BASE = parsers.BASE
LANG_PATH = os.environ.get("WORKANA_LOCALE", "es")  # es | pt | en -> textos de la web en ese idioma

BASE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/128.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-ES,es;q=0.9,pt;q=0.8,en;q=0.7",
}
JSON_HEADERS = {"Accept": "application/json, text/plain, */*", "X-Requested-With": "XMLHttpRequest"}

MIN_INTERVAL_S = 1.2   # pausa mínima entre peticiones (sé amable con Workana)
CACHE_TTL_S = 300      # 5 minutos
TIMEOUT_S = 25

CATEGORIES = {
    "programacion": "it-programming",
    "diseno": "design-multimedia",
    "redaccion": "writing-translation",
    "marketing": "sales-marketing",
    "soporte": "admin-support",
    "legal": "legal",
    "finanzas": "finance-management",
    "ingenieria": "engineering-manufacturing",
}
SUBCATEGORIES = {  # de it-programming
    "web": "web-development",
    "diseno_web": "web-design",
    "ecommerce": "e-commerce",
    "wordpress": "wordpress-1",
    "apps_moviles": "mobile-development",
    "data_science": "data-science-1",
    "escritorio": "desktop-apps",
    "inteligencia_artificial": "artificial-intelligence-1",
    "otros": "others-5",
}
PUBLICATION = {"24h": "1d", "3d": "3d", "semana": "1w", "cualquiera": None}
# slugs verificados en workana.com (hay proyectos con cada uno)
KNOWN_SKILLS = {
    "react": "react-js", "react.js": "react-js", "reactjs": "react-js",
    "node": "node-js", "node.js": "node-js", "nodejs": "node-js",
    "typescript": "typescript", "ts": "typescript",
    "javascript": "javascript", "js": "javascript",
    "next": "next-js", "next.js": "next-js", "nextjs": "next-js",
    "react native": "react-native", "react-native": "react-native",
    "vue": "vue-js", "vue.js": "vue-js", "angular": "angular",
    "express": "express-js", "express.js": "express-js",
    "nest": "nest-js", "nestjs": "nest-js", "nest.js": "nest-js",
    "mongodb": "mongodb", "mysql": "mysql", "sql": "sql", "database": "database",
    "html": "html", "css": "css", "html5": "html5", "css3": "css3",
    "firebase": "firebase", "graphql": "graphql", "rest api": "rest-api", "api": "api",
    "docker": "docker", "python": "python", "php": "php", "laravel": "laravel",
    "wordpress": "wordpress", "shopify": "shopify", "web scraping": "web-scraping",
    "chatbot": "chatbot", "flutter": "flutter", "git": "git",
    "inteligencia artificial": "artificial-intelligence",
}
DEFAULT_SKILLS = ["react-js", "node-js", "typescript", "next-js", "express-js", "nest-js"]


class WorkanaError(Exception):
    pass


def skill_slug(s: str) -> str:
    k = s.strip().lower()
    if k in KNOWN_SKILLS:
        return KNOWN_SKILLS[k]
    return k.replace(".", "-").replace(" ", "-")


def build_search_url(
    texto: str | None = None,
    skills: list[str] | None = None,
    categoria: str | None = "programacion",
    subcategoria: str | None = None,
    idioma: str | None = "es",
    modalidad: str | None = None,
    publicados: str | None = None,
    pocas_propuestas: bool = False,
    propuestas: str | None = None,
    pais_cliente: str | None = None,
    pagina: int = 1,
) -> str:
    params: list[tuple[str, str]] = []
    if texto:
        params.append(("query", texto))
    if categoria and categoria != "todas":
        params.append(("category", CATEGORIES.get(categoria, categoria)))
    if subcategoria:
        params.append(("subcategory", SUBCATEGORIES.get(subcategoria, subcategoria)))
    if skills:
        params.append(("skills", ",".join(dict.fromkeys(skill_slug(s) for s in skills))))
    if idioma:  # sin parámetro Workana usa el idioma de la web; "xx" = todos
        params.append(("language", "xx" if idioma == "todos" else idioma))
    if modalidad in ("precio_fijo", "fixed"):
        params.append(("agreement", "fixed"))
    elif modalidad in ("por_hora", "hourly"):
        params.append(("agreement", "hourly"))
    pub = PUBLICATION.get(publicados or "cualquiera", publicados)
    if pub:
        params.append(("publication", pub))
    if pocas_propuestas or propuestas == "pocas":
        params.append(("has_few_bids", "1"))
    elif propuestas == "muchas":
        params.append(("has_few_bids", "2"))
    if pais_cliente:
        params.append(("country", pais_cliente.upper()))
    if pagina and pagina > 1:
        params.append(("page", str(pagina)))
    return f"{BASE}/{LANG_PATH}/jobs" + ("?" + urlencode(params) if params else "")


class WorkanaClient:
    def __init__(self) -> None:
        self._last = 0.0
        self._lock = asyncio.Lock()
        self._cache: dict[str, tuple[float, str]] = {}
        self._session = None
        self._backend = None

    async def _get_session(self):
        if self._session is not None:
            return self._session
        try:  # curl_cffi imita la huella TLS de Chrome -> menos bloqueos de Cloudflare
            from curl_cffi.requests import AsyncSession  # type: ignore

            self._session = AsyncSession(impersonate="chrome", timeout=TIMEOUT_S)
            self._backend = "curl_cffi"
        except Exception:  # pragma: no cover
            import httpx

            self._session = httpx.AsyncClient(headers=BASE_HEADERS, follow_redirects=True, timeout=TIMEOUT_S)
            self._backend = "httpx"
        return self._session

    async def _throttle(self) -> None:
        async with self._lock:
            wait = MIN_INTERVAL_S - (time.monotonic() - self._last)
            if wait > 0:
                await asyncio.sleep(wait)
            self._last = time.monotonic()

    async def get_text(self, url: str, headers: dict | None = None) -> str:
        key = url + ("|json" if headers and "X-Requested-With" in headers else "")
        now = time.time()
        if key in self._cache and now - self._cache[key][0] < CACHE_TTL_S:
            return self._cache[key][1]
        session = await self._get_session()
        await self._throttle()
        hdrs = {k: v for k, v in BASE_HEADERS.items() if not (self._backend == "curl_cffi" and k == "User-Agent")}
        hdrs["Referer"] = f"{BASE}/{LANG_PATH}/jobs"
        if headers:
            hdrs.update(headers)
        try:
            if self._backend == "curl_cffi":
                r = await session.get(url, headers=hdrs, allow_redirects=True)
            else:
                r = await session.get(url, headers=hdrs)
        except Exception as e:
            raise WorkanaError(f"Error de red al acceder a Workana ({type(e).__name__}: {e}). Revisa tu conexión.") from e
        status, text = r.status_code, r.text
        if parsers.is_blocked_page(text) or status in (403, 429, 503):
            raise WorkanaError(
                f"Workana rechazó la petición (HTTP {status}, posible verificación anti-bot o demasiadas consultas). "
                "Espera unos minutos y prueba con menos páginas. Si persiste, abre workana.com en tu navegador."
            )
        if status in (404, 410):
            raise WorkanaError("El proyecto no existe o fue eliminado (404).")
        if status >= 400:
            raise WorkanaError(f"HTTP {status} al acceder a {url}.")
        self._cache[key] = (now, text)
        return text

    # ------------------------------------------------------------------
    async def search(self, url: str) -> dict:
        txt = await self.get_text(url, headers=JSON_HEADERS)
        try:
            data = json.loads(txt)
        except json.JSONDecodeError as e:
            raise WorkanaError(
                "Workana devolvió HTML en lugar de JSON en la búsqueda (puede haber cambiado su web)."
            ) from e
        out = parsers.parse_search_json(data)
        out["url_busqueda"] = url.replace(f"/{LANG_PATH}/jobs", "/jobs")
        return out

    async def search_all(self, max_consultas: int = 15, **filtros) -> dict:
        """Sin sesión Workana solo muestra 7 de cada 20 resultados por página (el resto queda oculto
        para empujar el registro). Para verlos todos, cuando una búsqueda tiene más resultados de los
        visibles se divide en búsquedas más pequeñas (por skill, modalidad, nº de propuestas y
        subcategoría) y se unen los resultados. Como último recurso se leen más páginas."""
        filtros = {k: v for k, v in filtros.items() if v is not None}
        found: dict[str, dict] = {}
        state = {"n": 0, "incompleto": False}

        async def run(f: dict) -> dict | None:
            f = {k: v for k, v in f.items() if not k.startswith("_")}
            if state["n"] >= max_consultas:
                state["incompleto"] = True
                return None
            state["n"] += 1
            res = await self.search(build_search_url(**f))
            for p in res["proyectos"]:
                found.setdefault(p["slug"], p)
            return res

        def splits(f: dict) -> list[dict]:
            # primero particiones disjuntas (no repiten proyectos), al final skills (se solapan)
            if not f.get("modalidad"):
                return [{**f, "modalidad": m} for m in ("precio_fijo", "por_hora")]
            if not f.get("pocas_propuestas") and not f.get("propuestas"):
                return [{**f, "propuestas": x} for x in ("pocas", "muchas")]
            if f.get("categoria", "programacion") == "programacion" and not f.get("subcategoria"):
                return [{**f, "subcategoria": x} for x in SUBCATEGORIES]
            sk = f.get("skills") or []
            if len(sk) > 1:
                return [{**f, "skills": [x]} for x in sk]
            pages = min(f.get("_paginas") or 1, 50)  # último recurso: más páginas (7 visibles de cada 20)
            if not f.get("pagina") and pages > 1:
                return [{**f, "pagina": n} for n in range(2, pages + 1)]
            return []

        # cola por prioridad: primero la búsqueda con más resultados ocultos
        queue: list[tuple[int, int, dict]] = []
        counter = 0

        def push(f: dict, res: dict) -> None:
            nonlocal counter
            hidden = (res["total"] or 0) - len(res["proyectos"])
            if hidden > 0 and not f.get("pagina"):
                counter += 1
                heapq.heappush(queue, (-hidden, counter, {**f, "_paginas": res.get("paginas")}))

        async def explore() -> None:
            while queue:
                _, _, f = heapq.heappop(queue)
                for sub in splits(f):
                    sub = {k: v for k, v in sub.items() if k != "_paginas"}
                    r = await run(sub)
                    if r is None:
                        return
                    push(sub, r)

        first = await run(dict(filtros))
        url = first["url_busqueda"] if first else None
        if first:
            push(dict(filtros), first)
            await explore()
        return {
            "total": first["total"] if first else 0,
            "proyectos": list(found.values()),
            "consultas": state["n"],
            "incompleto": state["incompleto"],
            "url_busqueda": url,
        }

    async def project(self, url_or_slug: str) -> dict:
        slug = parsers.slug_from(url_or_slug)
        page = await self.get_text(f"{BASE}/{LANG_PATH}/job/{slug}")
        try:
            return parsers.parse_project_page(page, slug)
        except ValueError as e:
            raise WorkanaError(str(e)) from e

    async def find_in_search(self, slug: str, title: str) -> dict | None:
        """La página del proyecto (sin sesión) no muestra presupuesto, país ni pago verificado;
        esos datos salen del listado. Busca el proyecto por su título y lo empareja por slug."""
        for idioma in ("todos",):
            url = build_search_url(texto=title[:80], categoria=None, idioma=idioma)
            try:
                res = await self.search(url)
            except WorkanaError:
                return None
            for p in res["proyectos"]:
                if p["slug"] == slug:
                    return p
        return None

    async def aclose(self) -> None:
        if self._session is not None:
            try:
                if self._backend == "curl_cffi":
                    await self._session.close()
                else:
                    await self._session.aclose()
            except Exception:
                pass
