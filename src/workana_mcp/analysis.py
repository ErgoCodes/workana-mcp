"""Puntaje de oportunidad (0-100) para decidir a qué proyectos de Workana vale la pena postularse."""

from __future__ import annotations

import os
import re
from datetime import date

DEFAULT_PROFILE = [
    "React.js", "Node.js", "TypeScript", "JavaScript", "Next.js", "Express.js", "NestJS",
    "HTML", "CSS", "HTML5", "CSS3", "API", "REST API", "MongoDB", "MySQL", "SQL", "Database",
    "Git", "Responsive Web Design", "Firebase",
]
# skills "fuertes" (pesan más que las genéricas como HTML/CSS/API)
CORE = {"react", "node", "typescript", "next", "express", "nest", "javascript"}

TEXT_KEYWORDS = {  # si aparecen en título/descripción cuentan como encaje aunque no estén en los tags
    "react": r"\breact(\.js|js)?\b(?!\s*native)",
    "node": r"\bnode(\.js|js)?\b",
    "typescript": r"\btypescript\b|\bTS\b",
    "next": r"\bnext(\.js|js)\b",
    "express": r"\bexpress(\.js|js)?\b",
    "nest": r"\bnest(\.js|js)\b",
    "mern": r"\bmern\b",
    "fullstack": r"full[\s-]?stack",
}

RED_FLAGS = [
    (r"(fuera de (la )?(plataforma|workana))|(por fuera de workana)|(pago directo)|(transferencia directa)",
     15, "Pide trabajar o pagar fuera de Workana (pierdes la protección de pago)."),
    (r"\b(whats?app|wpp|telegram|t\.me/|skype)\b.{0,40}\b(\+?\d[\d\s-]{6,}|contact|escr[ií]b|agr[eé]g)",
     10, "Intenta llevar el contacto a WhatsApp/Telegram."),
    (r"[\w.+-]+@[\w-]+\.[\w.]+", 8, "Incluye un e-mail en la descripción (contacto fuera de la plataforma)."),
    (r"prueba (gratis|gratuita|sin (pago|costo))|trabajo de prueba sin|test (gratis|sin pago)|free test|teste gr[aá]tis",
     12, "Pide trabajo o prueba gratis antes de contratar."),
    (r"\b(porcentaje|comisi[oó]n|equity|participaci[oó]n|socio)\b.{0,50}\b(ganancia|venta|empresa|proyecto)",
     8, "Ofrece pagar con porcentaje/participación en lugar de dinero."),
    (r"presupuesto (muy )?(bajo|limitado|ajustado)|(algo|muy|lo m[aá]s) (econ[oó]mico|barato)|low budget|poco presupuesto",
     6, "Avisa que el presupuesto es bajo."),
    (r"clon(ar|e|ación)? (de|tipo|como) (uber|airbnb|facebook|instagram|amazon|netflix|tiktok|bolt|rappi)|similar a (uber|bolt|airbnb|netflix|instagram|tiktok|rappi)",
     5, "Pide un 'clon' de una plataforma grande: suele tener presupuesto irreal para el alcance."),
]
POSITIVE = [
    (r"largo plazo|long term|a futuro m[aá]s proyectos|relaci[oó]n continua|trabajo continuo|mensual", "Posible relación a largo plazo."),
    (r"(ya|actualmente) (tenemos|contamos con|existe)|proyecto existente|c[oó]digo existente|mantenimiento", "Proyecto existente: alcance más acotado."),
    (r"requisitos|especificaci[oó]n|figma|mockup|documentaci[oó]n", "El cliente tiene requisitos/diseños definidos."),
]


def profile_skills(custom: list[str] | None = None) -> list[str]:
    if custom:
        return custom
    env = os.environ.get("WORKANA_MIS_SKILLS")
    if env:
        return [s.strip() for s in env.split(",") if s.strip()]
    return DEFAULT_PROFILE


def _norm(s: str) -> str:
    s = s.lower().strip()
    s = re.sub(r"\.?js$", "", s)
    s = re.sub(r"[^a-z0-9]+", " ", s).strip()
    return {"nestj": "nest", "nestjs": "nest", "reactjs": "react", "nodejs": "node", "nextjs": "next"}.get(s, s)


def skill_match(project_skills: list[str], text: str, mine: list[str]) -> dict:
    mine_n = {_norm(s) for s in mine}
    proj_n = [_norm(s) for s in project_skills]
    matched = [s for s, n in zip(project_skills, proj_n) if n in mine_n]
    missing = [s for s, n in zip(project_skills, proj_n) if n not in mine_n]
    in_text = [k for k, rx in TEXT_KEYWORDS.items() if re.search(rx, text or "", re.I)]
    core_hits = {_norm(s) for s in matched} & CORE | (set(in_text) & (CORE | {"mern", "fullstack"}))
    ratio = len(matched) / len(project_skills) if project_skills else 0.0
    pts = 0.0
    pts += min(len(core_hits), 3) / 3 * 18       # hasta 18 por tecnologías fuertes
    pts += ratio * 12                              # hasta 12 por % de skills cubiertas
    return {
        "puntos": round(min(pts, 30), 1),
        "coinciden": matched,
        "no_tengo": missing,
        "en_texto": in_text,
        "porcentaje_cubierto": round(ratio * 100),
    }


def _competition_pts(bids: int | None) -> float:
    if bids is None:
        return 12
    for limit, pts in ((4, 25), (9, 20), (19, 13), (34, 7)):
        if bids <= limit:
            return pts
    return 2


def _budget_pts(b: dict | None) -> tuple[float, str]:
    if not b or (b.get("min") is None and b.get("max") is None):
        return 8, "Presupuesto no visible o 'abierto'."
    top = b.get("max") if b.get("max") is not None else (b.get("min") or 0) * 1.5
    if b.get("por_hora"):
        for lim, pts in ((45, 20), (25, 15), (15, 10)):
            if top >= lim:
                return pts, f"Hasta {top:g} USD/h."
        return 4, f"Tarifa baja (hasta {top:g} USD/h)."
    for lim, pts in ((1000, 20), (500, 16), (250, 12), (100, 7)):
        if top >= lim:
            return pts, f"Hasta {top:g} USD."
    return 3, f"Presupuesto bajo (hasta {top:g} USD)."


def _freshness_pts(h: float | None) -> float:
    if h is None:
        return 4
    for lim, pts in ((6, 10), (24, 8), (72, 5), (168, 2)):
        if h <= lim:
            return pts
    return 0


def _client_pts(c: dict) -> tuple[float, list[str], list[str]]:
    pts, pros, cons = 0.0, [], []
    if c.get("metodo_pago_verificado"):
        pts += 5
        pros.append("Método de pago verificado.")
    elif c.get("metodo_pago_verificado") is False:
        cons.append("Método de pago NO verificado todavía.")
    r = c.get("calificacion")
    if r and r >= 4.5:
        pts += 4
        pros.append(f"Cliente con calificación {r:g}/5.")
    elif r and r > 0:
        pts += 2
    paid = c.get("proyectos_pagados")
    pub = c.get("proyectos_publicados")
    if paid:
        pts += 4 if paid >= 2 else 3
        pros.append(f"Ya pagó {paid} proyecto(s) en Workana.")
    elif paid == 0:
        cons.append("Nunca ha pagado un proyecto en Workana (cliente sin historial).")
    if pub and pub >= 3:
        pts += 2
    if pub and paid is not None and pub >= 5 and paid == 0:
        cons.append(f"Publicó {pub} proyectos y no pagó ninguno: puede publicar sin contratar.")
    ms = c.get("miembro_desde")
    if ms and re.match(r"\d{4}-\d{2}", ms):
        y, m = map(int, ms.split("-")[:2])
        today = date.today()
        if (today.year - y) * 12 + today.month - m <= 1:
            cons.append("Cuenta de cliente creada este mes.")
    return min(pts, 15), pros, cons


def evaluate(project: dict, mine: list[str] | None = None) -> dict:
    """project: dict combinado de listado y/o página (ver server._merge)."""
    mine = profile_skills(mine)
    text = f"{project.get('titulo', '')}\n{project.get('descripcion', '')}"
    sm = skill_match(project.get("skills") or [], text, mine)
    comp = _competition_pts(project.get("propuestas"))
    bud, bud_note = _budget_pts(project.get("presupuesto"))
    fresh = _freshness_pts(project.get("horas_desde_publicacion"))
    cli, pros, cons = _client_pts(project.get("cliente") or {})

    alerts, penalty = [], 0
    for rx, pen, msg in RED_FLAGS:
        if re.search(rx, text, re.I | re.S):
            alerts.append(msg)
            penalty += pen
    for rx, msg in POSITIVE:
        if re.search(rx, text, re.I):
            pros.append(msg)

    if project.get("urgente"):
        cons.append("Marcado como urgente: responde rápido o no postules.")
    if (project.get("estado") or "").lower() not in ("", "evaluando propuestas", "avaliando propostas", "open", "abierto"):
        cons.append(f"Estado del proyecto: {project.get('estado')}.")
        penalty += 30
    if sm["puntos"] < 6:
        cons.append("Poco encaje con tu stack.")

    total = sm["puntos"] + comp + bud + fresh + cli - penalty
    total = max(0, min(100, round(total)))
    nivel = "alta" if total >= 65 else "media" if total >= 45 else "baja"
    bids = project.get("propuestas")
    return {
        "puntaje": total,
        "prioridad": nivel,
        "desglose": {
            "encaje_skills_(30)": sm["puntos"],
            "competencia_(25)": comp,
            "presupuesto_(20)": bud,
            "cliente_(15)": cli,
            "frescura_(10)": fresh,
            "penalizaciones": -penalty,
        },
        "skills": sm,
        "presupuesto_nota": bud_note,
        "a_favor": pros,
        "en_contra": cons,
        "alertas": alerts,
        "consejos": _tips(project, sm, bids),
    }


def _tips(p: dict, sm: dict, bids: int | None) -> list[str]:
    tips = []
    h = p.get("horas_desde_publicacion")
    if bids is not None and bids <= 9 and (h is None or h <= 24):
        tips.append("Pocas propuestas y reciente: postula hoy, las primeras propuestas se leen más.")
    elif bids is not None and bids >= 35:
        tips.append("Mucha competencia: solo vale la pena si tu propuesta es muy específica (demo, pregunta técnica concreta).")
    if sm["coinciden"] or sm["en_texto"]:
        stack = ", ".join(sm["coinciden"][:4] or sm["en_texto"][:4])
        tips.append(f"Abre la propuesta mencionando experiencia concreta con {stack} y un proyecto parecido.")
    if sm["no_tengo"]:
        tips.append(f"Skills que no tienes en tu perfil: {', '.join(sm['no_tengo'][:5])}. Aclara cómo lo cubrirías o descártalo.")
    b = p.get("presupuesto") or {}
    if b.get("min") is not None and b.get("max") and not b.get("por_hora"):
        mid = (b["min"] + b["max"]) / 2
        tips.append(f"Rango del cliente {b['min']:g}-{b['max']:g} USD: una oferta cerca de {mid:.0f} USD con alcance por etapas suele funcionar.")
    tips.append("Haz 1-2 preguntas sobre el alcance para iniciar conversación; no prometas plazos sin ver requisitos.")
    return tips
