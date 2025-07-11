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
async def painel(
    request:      Request,
    page:         int  | None = 1,
    status:       str  | None = None,
    responsavel:  str  | None = None,
    data_ini:     str  | None = None,
    data_fim:     str  | None = None,
    capturado:    str  | None = None,
    mudou_tipo:   str  | None = None,
    sla:          str  | None = None,
    # atalhos dos cards
    so_ema: bool | None = None,
    so_fin: bool | None = None,
    so_sla: bool | None = None,
    so_mud: bool | None = None,
):
    # ── filtros disparados pelos cards ──
    if so_ema:  status, sla,  mudou_tipo = "Em Atendimento", None, None
    if so_fin:  status, sla,  mudou_tipo = "Finalizado",     None, None
    if so_sla:  sla,    status           = "fora",           None
    if so_mud:  mudou_tipo, status       = "sim",            None

    base_filtros = dict(
        status=status, resp=responsavel,
        d_ini=data_ini, d_fim=data_fim,
        capturado=capturado, mudou_tipo=mudou_tipo, sla=sla
    )

    # ── paginação ───────────────────────────────────────────────
    PER_PAGE       = 20
    total          = contar_chamados(**base_filtros)
    paginas_totais = max(1, math.ceil(total / PER_PAGE))
    page           = max(1, min(page, paginas_totais))
    offset         = (page - 1) * PER_PAGE

    chamados = carregar_chamados(limit=PER_PAGE, offset=offset, **base_filtros)

    # ── combos para filtros ─────────────────────────────────────
    responsaveis = listar_responsaveis(**base_filtros)
    capturadores = listar_capturadores(**base_filtros)

    # ── métricas globais ───────────────────────────────────────────
    filtros_para_metricas = {k: v for k, v in base_filtros.items()
                         if k not in ("status", "sla", "mudou_tipo")}

    metricas = {
        "total": contar_chamados(**base_filtros),
        "em_atendimento": contar_chamados(status="aberto", **filtros_para_metricas),
        "finalizados":    contar_chamados(status="fechado", **filtros_para_metricas),
        "fora_sla":       contar_chamados(sla="fora", **filtros_para_metricas),
        "mudaram_tipo":   contar_chamados(mudou_tipo="sim", **filtros_para_metricas),
    }

    # ── query-string p/ links & export ──────────────────────────
    filtros_qs = urlencode({k: v for k, v in {
        "status": status, "responsavel": responsavel,
        "data_ini": data_ini, "data_fim": data_fim,
        "capturado": capturado, "mudou_tipo": mudou_tipo,
        "sla": sla
    }.items() if v})

    return templates.TemplateResponse(
        "painel.html",
        {
            "request":        request,
            "chamados":       chamados,
            "metricas":       metricas,
            "pagina_atual":   page,
            "paginas_totais": paginas_totais,
            "url_paginacao":  f"/painel?{filtros_qs}",
            "filtros": {
                "status": status, "responsavel": responsavel,
                "data_ini": data_ini, "data_fim": data_fim,
                "capturado": capturado, "mudou_tipo": mudou_tipo,
                "sla": sla
            },
            "responsaveis":   responsaveis,
            "capturadores":   capturadores,
            "filtros_as_query": filtros_qs,
        },
    )

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
