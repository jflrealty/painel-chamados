import os
import json
import psycopg2
import json
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from pathlib import Path

app = FastAPI()
templates = Jinja2Templates(directory="templates")

# Token direto das variáveis do Railway (sem .env)
SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN")
slack_client = WebClient(token=SLACK_BOT_TOKEN)

@app.get("/", response_class=HTMLResponse)
async def painel(request: Request):
    chamados = []
    path = Path("chamados.json")
    if path.exists():
        with open(path, "r") as f:
            chamados = json.load(f)

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
                "user": m.get("user", "desconhecido"),
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
