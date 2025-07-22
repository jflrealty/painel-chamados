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
                 status: Optional[str] = None,
                 responsavel: Optional[str] = None,
                 capturado: Optional[str] = None,
                 mudou_tipo: Optional[str] = None,
                 data_ini: Optional[str] = None,
                 data_fim: Optional[str] = None,
                 page: int = 1):

    # Normalizar filtros
    filtros_dict = {}

    if status and status != "Todos":
        if status == "Em Atendimento":
            filtros_dict["status"] = "aberto"
        elif status == "Finalizados":
            filtros_dict["status"] = "fechado"
        else:
            filtros_dict["status"] = status

    if responsavel and responsavel != "Todos":
        filtros_dict["responsavel"] = responsavel

    if capturado and capturado != "Todos":
        filtros_dict["capturado"] = capturado

    if mudou_tipo and mudou_tipo != "Todos":
        filtros_dict["mudou_tipo"] = mudou_tipo

    if data_ini:
        filtros_dict["data_ini"] = data_ini

    if data_fim:
        filtros_dict["data_fim"] = data_fim

    # Paginação
    chamados, total_paginas = carregar_chamados(page=page, **filtros_dict)

    # Cards de métricas
    try:
        total = contar_chamados(**filtros_dict)
        em_atendimento = contar_chamados(status="aberto", **{k: v for k, v in filtros_dict.items() if k != "status"})
        finalizados = contar_chamados(status="fechado", **{k: v for k, v in filtros_dict.items() if k != "status"})
        fora_sla = contar_chamados(sla="fora", **filtros_dict)
        alteraram_tipo = contar_chamados(mudou_tipo="sim", **filtros_dict)
    except Exception as e:
        print("ERRO NAS MÉTRICAS:", e)
        total = em_atendimento = finalizados = fora_sla = alteraram_tipo = 0

    return templates.TemplateResponse("painel.html", {
        "request": request,
        "chamados": chamados,
        "pagina": page,
        "total_paginas": total_paginas,
        "filtros": filtros_dict,
        "cards": {
            "total": total,
            "em_atendimento": em_atendimento,
            "finalizados": finalizados,
            "fora_sla": fora_sla,
            "alteraram_tipo": alteraram_tipo,
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
