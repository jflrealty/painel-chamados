# main.py – Painel de Chamados v6 (estável + rápido)
import os, math, datetime as dt, pytz
from urllib.parse import urlencode

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from slack_sdk import WebClient, errors as slack_err

from export import export_router
from utils.db_helpers import (
    carregar_chamados,
    contar_chamados,
    listar_responsaveis,
    listar_capturadores,
)
from utils.slack_helpers import get_real_name, formatar_texto_slack

# ── FastAPI / templates ─────────────────────────────────────────
app = FastAPI()
app.include_router(export_router)

templates = Jinja2Templates(directory="templates")
templates.env.globals.update(get_real_name=get_real_name, max=max, min=min)

# ── Slack client ────────────────────────────────────────────────
slack_client = WebClient(token=os.getenv("SLACK_BOT_TOKEN", ""))

# ═════════════════════════ ROTAS ════════════════════════════════
@app.get("/painel", response_class=HTMLResponse)
async def painel(request: Request,
                 status: str = "Todos",
                 responsavel: str = "Todos",
                 capturado: str = "Todos",
                 mudou_tipo: str = "Todos",
                 data_ini: str = None,
                 data_fim: str = None,
                 page: int = 1):

    # Filtros gerais
    filtros = {}
    if responsavel != "Todos": filtros["resp"] = responsavel
    if capturado != "Todos": filtros["capturado"] = capturado
    if mudou_tipo != "Todos": filtros["mudou_tipo"] = mudou_tipo
    if data_ini: filtros["d_ini"] = data_ini
    if data_fim: filtros["d_fim"] = data_fim

    # Status filtrado diretamente
    status_card = status
    if status == "Em Atendimento": filtros["status"] = "aberto"
    elif status == "Finalizados": filtros["status"] = "fechado"
    elif status not in ["Todos", "", None]: filtros["status"] = status

    # Paginação
    total = contar_chamados(**filtros)
    paginas_totais = max(1, math.ceil(total / PER_PAGE))
    page = max(1, min(page, paginas_totais))
    offset = (page - 1) * PER_PAGE

    chamados = carregar_chamados(limit=PER_PAGE, offset=offset, **filtros)

    # Cards superiores
    try:
        filtros_sem_status = {k: v for k, v in filtros.items() if k != "status"}
        cards = {
            "total": contar_chamados(**filtros_sem_status),
            "em_atendimento": contar_chamados(status="aberto", **filtros_sem_status),
            "finalizados": contar_chamados(status="fechado", **filtros_sem_status),
            "fora_sla": contar_chamados(sla="fora", **filtros),
            "alteraram_tipo": contar_chamados(mudou_tipo="sim", **filtros),
        }
    except Exception as e:
        print("ERRO CARDS:", e)
        cards = {"total": 0, "em_atendimento": 0, "finalizados": 0, "fora_sla": 0, "alteraram_tipo": 0}

    return templates.TemplateResponse("painel.html", {
        "request": request,
        "chamados": chamados,
        "pagina": page,
        "total_paginas": paginas_totais,
        "cards": cards,
        "filtros": {
            "status": status_card,
            "responsavel": responsavel,
            "capturado": capturado,
            "mudou_tipo": mudou_tipo,
            "data_ini": data_ini,
            "data_fim": data_fim
        }
    })

# ───────────────────────── THREAD ───────────────────────────────
@app.post("/thread")
async def thread(request: Request):
    form      = await request.form()
    canal_id  = form["canal_id"]
    thread_ts = form["thread_ts"]

    mensagens = []
    try:
        resp = slack_client.conversations_replies(channel=canal_id, ts=thread_ts, limit=200)
        tz   = pytz.timezone("America/Sao_Paulo")
        for i, m in enumerate(resp.get("messages", [])):
            mensagens.append({
                "texto": formatar_texto_slack(m.get("text", "")),
                "ts": dt.datetime.fromtimestamp(float(m["ts"]))
                      .astimezone(tz).strftime("%d/%m/%Y %H:%M"),
                "user": get_real_name(m.get("user")) or "<não capturado>",
                "orig": i == 0
            })
    except slack_err.SlackApiError as e:
        print("Slack API:", e.response["error"])

    return templates.TemplateResponse("thread.html",
                                      {"request": request, "mensagens": mensagens})
