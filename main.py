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
async def painel(request: Request):
    chamados = carregar_chamados_do_banco()
    return templates.TemplateResponse("painel.html", {
        "request": request,
        "chamados": chamados
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

def carregar_chamados_do_banco():
    DATABASE_URL = os.environ.get("DATABASE_PUBLIC_URL")

    print("🔍 DATABASE_PUBLIC_URL =", DATABASE_URL)

    if not DATABASE_URL:
        print("❌ ERRO: DATABASE_PUBLIC_URL não está definida.")
        return []

    if DATABASE_URL.startswith("postgresql://"):
        DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgres://", 1)

    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        cur.execute("""
            SELECT id, tipo_ticket, status, responsavel, canal_id, thread_ts
            FROM ordens_servico
            ORDER BY id DESC
            LIMIT 100
        """)
        rows = cur.fetchall()
        chamados = []
        for r in rows:
            chamados.append({
                "id": r[0],
                "tipo_ticket": r[1],
                "status": r[2],
                "responsavel": get_real_name(r[3]),
                "canal_id": r[4],
                "thread_ts": r[5]
            })
        cur.close()
        conn.close()
        return chamados
    except Exception as e:
        print(f"❌ ERRO ao conectar ao banco: {e}")
        return []
