# workana-mcp

An MCP server that lets Claude **find and score freelance projects on Workana**, so you spend your time on proposals that can actually win.

## Why I built it

Most Workana projects are a poor fit: dozens of proposals already in, tiny budgets, clients who never paid anyone, or requests to move the conversation to WhatsApp. Checking each one by hand every day took longer than writing the proposals. This tool does the filtering and tells me which handful are worth my time.

It is **read-only by design**. Workana has no public API, so the server reads the same public pages you see in the browser **without logging in**. It never touches your account, never sends proposals or messages. You decide where to apply and send the proposal yourself.

## Tools

| Tool | What it does |
|---|---|
| `workana_buscar_proyectos` | Search with filters: text, skills, category/subcategory, language, fixed price or hourly, age (24h/3d/week), few proposals only, client country, minimum budget, minimum rate, maximum proposals. Sort by opportunity, date or fewest proposals. |
| `workana_ver_proyecto` | Full project page: complete description, skills, budget, proposals, interested freelancers and the client (country, rating, projects posted and paid, member since, verified payment, their other projects). |
| `workana_evaluar_proyecto` | Opportunity score 0–100 with a breakdown, alerts, pros and cons, and tips for the proposal. |
| `workana_mejores_oportunidades` | Daily workflow: searches recent projects for your stack, drops the bad ones, deep-analyzes the best N and ranks them. |

### How the score (0–100) works

- **Stack fit (30):** strong technologies (React, Node, TypeScript, Next, Express, Nest) in the skills or text, plus the % of the project's skills you have.
- **Competition (25):** 0–4 proposals = 25 … 35+ = 2.
- **Budget (20):** fixed price (≥ 1,000 USD = 20) or hourly rate (≥ 45 USD/h = 20).
- **Client (15):** verified payment, rating, projects already paid and how many they posted.
- **Freshness (10):** under 6 h = 10 … over a week = 0.
- **Penalties:** paying or working outside Workana, contact via WhatsApp or Telegram, email in the description, free trial work, payment in equity or percentage, "low" budget, clones of big platforms, closed project.

Priority: **high** from 65, **medium** 45–64, **low** below 45. It's a heuristic to prioritize, not a guarantee.

## The interesting problem: results Workana hides

Logged out, Workana only shows **7 of every 20** results per page and hides the rest to push you to sign up. Instead of logging in (which would put an account at risk), the server notices when a search has hidden results and **splits it into narrower searches** (by pricing model, number of proposals, subcategory, skill and, as a last resort, more pages), then merges and de-duplicates the results. `max_consultas` (default 20, max 30) caps how many requests that costs, and the response says how many projects it saw out of the total Workana reports.

The same idea fills another gap: a logged-out project page doesn't show the budget or verified payment, so the server finds the project in the listings by title and fills those fields in.

Requests go through `curl_cffi` (presenting as Chrome), wait 1.5 s between calls and are cached for 5 minutes.

## Your profile

By default it scores against a fullstack stack: React.js, Node.js, TypeScript, JavaScript, Next.js, Express.js, NestJS, HTML/CSS, API/REST, MongoDB, MySQL/SQL, Git and Firebase. Two ways to change it:

- Per query, with the `mis_skills` parameter.
- Permanently, with the `WORKANA_MIS_SKILLS` variable in the server config (comma-separated).

## Install (Linux)

Register the `run.sh` launcher in Claude Desktop. On first run it installs its dependencies into `.venv` and logs to `install.log`.

1. Claude Desktop → **Settings → Developer → Edit config**.
2. Inside `"mcpServers"`, add:

```json
"workana": {
  "command": "bash",
  "args": ["/PATH/TO/workana-mcp/run.sh"]
}
```

   Optionally, set your skills profile:

```json
"workana": {
  "command": "bash",
  "args": ["/PATH/TO/workana-mcp/run.sh"],
  "env": { "WORKANA_MIS_SKILLS": "React.js,Node.js,TypeScript,Next.js,NestJS,PostgreSQL,Docker" }
}
```

3. Fully restart Claude Desktop. The first start takes a minute or two while it installs. If the `workana_*` tools don't show up, check `install.log`.

## Example prompts

- "Give me today's best Workana opportunities for my stack."
- "Find fixed-price React or Next projects posted in the last 24 hours with few proposals."
- "Evaluate this project: https://www.workana.com/job/…"
- "Find hourly Node.js projects paying at least 20 USD/h from clients in Spain or the US."

> The tool's output is in Spanish, its author's first language.

## Limitations

- If Workana blocks requests, wait a few minutes and use fewer pages.
- If Workana changes its site, `parsers.py` needs updating. The tests (`.venv/bin/python tests/test_all.py`) run against saved real responses and catch it.
- **Personal use, low volume.** Don't use it to scrape at scale or to automate sending proposals: that violates Workana's terms and puts your account at risk.

## License

MIT
