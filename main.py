import os
import psycopg2
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from utils.slack_helpers import get_real_name  # ⬅️ IMPORTAÇÃO DO NOME REAL

app = FastAPI()
templates = Jinja2Templates(directory="templates")

# Slack Client a partir da variável do Railway
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
slack_client = WebClient(token=SLACK_BOT_TOKEN)

@app.get("/painel", response_class=HTMLResponse)
async def painel(
    request: Request,
    status: str = None,
    responsavel: str = None,
    data_ini: str = None,
    data_fim: str = None
):
    chamados = carregar_chamados_do_banco(status, responsavel, data_ini, data_fim)
    totais = calcular_metricas(chamados)
    return templates.TemplateResponse("painel.html", {
        "request": request,
        "chamados": chamados,
        "totais": totais
    })

@app.post("/thread", response_class=HTMLResponse)
async def show_thread(
    request: Request,
    canal_id: str = Form(...),
    thread_ts: str = Form(...)
):
    try:
        resp = slack_client.conversations_replies(
            channel=canal_id,
            ts=thread_ts,
            limit=200
        )
        messages = [
            {
                "user": get_real_name(m.get("user", "desconhecido")),  # ⬅️ Nome real
                "text": m.get("text", ""),
                "ts": m.get("ts")
            }
            for m in resp.get("messages", [])
        ]
    except SlackApiError as e:
        return templates.TemplateResponse("thread.html", {
            "request": request,
            "messages": [],
            "error": str(e)
        })

    return templates.TemplateResponse("thread.html", {
        "request": request,
        "messages": messages,
        "canal": canal_id,
        "thread": thread_ts
    })

def carregar_chamados_do_banco(status=None, responsavel=None, data_ini=None, data_fim=None):
    DATABASE_URL = os.environ.get("DATABASE_PUBLIC_URL")

    if not DATABASE_URL:
        return []

    if DATABASE_URL.startswith("postgresql://"):
        DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgres://", 1)

    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()

        query = """
            SELECT id, tipo_ticket, status, responsavel, canal_id, thread_ts, data_abertura, data_fechamento, sla_status
            FROM ordens_servico
            WHERE 1=1
        """
        params = []

        if status:
            query += " AND status = %s"
            params.append(status)
        if responsavel:
            query += " AND responsavel = %s"
            params.append(responsavel)
        if data_ini:
            query += " AND data_abertura >= %s"
            params.append(data_ini)
        if data_fim:
            query += " AND data_abertura <= %s"
            params.append(data_fim)

        query += " ORDER BY id DESC LIMIT 100"

        cur.execute(query, tuple(params))
        rows = cur.fetchall()
        chamados = []
        for r in rows:
            chamados.append({
                "id": r[0],
                "tipo_ticket": r[1],
                "status": r[2],
                "responsavel": get_real_name(r[3]),
                "canal_id": r[4],
                "thread_ts": r[5],
                "data_abertura": r[6],
                "data_fechamento": r[7],
                "sla_status": r[8]
            })
        cur.close()
        conn.close()
        return chamados
    except Exception as e:
        print(f"❌ ERRO ao conectar ao banco: {e}")
        return []
