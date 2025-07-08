# main.py  – Painel de Chamados (FastAPI)
import os, psycopg2, datetime as dt
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from utils.slack_helpers import get_real_name          # função já criada

app = FastAPI()
templates = Jinja2Templates(directory="templates")

# ─────────── Slack ───────────
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN", "")
slack_client     = WebClient(token=SLACK_BOT_TOKEN)

# ─────────── Rotas ───────────
@app.get("/painel", response_class=HTMLResponse)
async def painel(
    request: Request,
    status: str | None = None,
    responsavel: str | None = None,             # agora vem o nome
    data_ini: str | None = None,
    data_fim: str | None = None
):
    chamados = carregar_chamados_do_banco(status, responsavel, data_ini, data_fim)
    metricas = calcular_metricas(chamados)
    return templates.TemplateResponse(
        "painel.html",
        {"request": request, "chamados": chamados, "metricas": metricas}
    )

@app.post("/thread", response_class=HTMLResponse)
async def thread(request: Request, canal_id: str = Form(...), thread_ts: str = Form(...)):
    try:
        resp = slack_client.conversations_replies(channel=canal_id, ts=thread_ts, limit=200)
        msgs = [
            {
                "user": get_real_name(m.get("user") or ""),
                "text": m.get("text", ""),
                "ts": dt.datetime.fromtimestamp(float(m["ts"])).strftime("%d/%m/%Y às %Hh%M")
            }
            for m in resp.get("messages", [])
        ]
    except SlackApiError as e:
        msgs, canal_id = [], f"Erro Slack: {e.response['error']}"
    return templates.TemplateResponse("thread.html", {"request": request, "msgs": msgs})

# ─────────── Helpers ───────────
def carregar_chamados_do_banco(status=None, resp_nome=None, d_ini=None, d_fim=None):
    url = os.getenv("DATABASE_PUBLIC_URL", "")
    if url.startswith("postgresql://"):                      # adaptação p/ psycopg2
        url = url.replace("postgresql://", "postgres://", 1)

    q  = """SELECT id,tipo_ticket,status,responsavel,canal_id,thread_ts,
                   data_abertura,data_fechamento,sla_status
            FROM ordens_servico WHERE true"""
    pr = []

    if status and status.lower() != "todos":
        q += " AND status = %s";               pr.append(status)
    if resp_nome and resp_nome.lower() != "todos":
        q += " AND responsavel = %s";          pr.append(resp_nome)
    if d_ini:
        q += " AND data_abertura >= %s";       pr.append(d_ini)
    if d_fim:
        q += " AND data_abertura <= %s";       pr.append(d_fim)

    q += " ORDER BY id DESC"                   # sem LIMIT → traz tudo

    try:
        with psycopg2.connect(url) as conn, conn.cursor() as cur:
            cur.execute(q, tuple(pr))
            rows = cur.fetchall()
    except Exception as e:
        print("⚠️ banco:", e); return []

    fmt = lambda d: d.strftime("%d/%m/%Y às %Hh%M") if d else "-"
    return [
        {
            "id": r[0], "tipo_ticket": r[1], "status": r[2],
            "responsavel": get_real_name(r[3]) or r[3],
            "canal_id": r[4], "thread_ts": r[5],
            "abertura": fmt(r[6]), "fechamento": fmt(r[7]),
            "sla": r[8] or "-"
        } for r in rows
    ]

def calcular_metricas(ch):
    return {
        "total": len(ch),
        "em_atendimento": sum(c["status"] == "aberto"  for c in ch),
        "finalizados":    sum(c["status"] == "fechado" for c in ch),
        "fora_sla":       sum(c["sla"]   == "fora"     for c in ch)
    }
