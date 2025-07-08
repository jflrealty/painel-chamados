# main.py  – Painel de Chamados v2
import os, psycopg2, datetime as dt, pytz, math
from urllib.parse import urlencode

from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from utils.slack_helpers import get_real_name          # sua função já pronta

# ──────────────────────────── FastAPI / Templates ────────────────────────────
app = FastAPI()
templates = Jinja2Templates(directory="templates")
templates.env.globals["get_real_name"] = get_real_name  # p/ usar no Jinja

# ──────────────────────────── Slack Client ────────────────────────────
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN", "")
slack_client     = WebClient(token=SLACK_BOT_TOKEN)

# ═════════════════════════════ Rotas ══════════════════════════════════
@app.get("/painel", response_class=HTMLResponse)
async def painel(
    request: Request,
    page:        int  | None = 1,            # ← paginação
    status:      str | None = None,
    responsavel: str | None = None,
    data_ini:    str | None = None,
    data_fim:    str | None = None,
    capturado:   str | None = None,
    mudou_tipo:  str | None = None,
    sla:         str | None = None           # “fora” vindo do card
):
    # ---- consulta completa (sem corte) ----
    chamados_full = carregar_chamados_do_banco(
        status, responsavel, data_ini, data_fim, capturado, mudou_tipo, sla
    )

    # ---- métricas (antes do corte) ----
    metricas = calcular_metricas(chamados_full)

    # ---- paginação ----------------------------------------------------
    PER_PAGE = 50
    total    = len(chamados_full)
    total_pg = max(1, math.ceil(total / PER_PAGE))
    page     = max(1, min(page, total_pg))                 # clamp
    ini, fim = (page - 1) * PER_PAGE, page * PER_PAGE
    chamados = chamados_full[ini:fim]

    # ---- selects ------------------------------------------------------
    todos_resp  = sorted({c["responsavel"]    for c in chamados_full if c["responsavel"]})
    todos_capts = sorted({c["capturado_por"]  for c in chamados_full
                          if c["capturado_por"] and c["capturado_por"] != "<não capturado>"})

    # ---- rebuild query-string (sem page) ----
    filtros = {
        "status": status, "responsavel": responsavel,
        "data_ini": data_ini, "data_fim": data_fim,
        "capturado": capturado, "mudou_tipo": mudou_tipo,
        "sla": sla
    }
    filtros_qs = urlencode({k: v for k, v in filtros.items() if v})

    return templates.TemplateResponse(
        "painel.html",
        {
            "request": request,
            "chamados": chamados,
            "metricas": metricas,
            "page": page,
            "total_pages": total_pg,
            "filtros_as_query": filtros_qs,
            "filtros": filtros,
            "responsaveis": todos_resp,
            "capturadores": todos_capts
        }
    )

# ---------------------- thread (inalterada – apenas formatação) ------------
@app.post("/thread")
async def thread(request: Request):
    form       = await request.form()
    canal_id   = form["canal_id"]
    thread_ts  = form["thread_ts"]

    mensagens = []
    try:
        print(f"🔎 Buscando thread: canal={canal_id}, ts={thread_ts}")
        resp = slack_client.conversations_replies(channel=canal_id, ts=thread_ts, limit=200)
        mensagens = resp.get("messages", [])
        print(f"✅ {len(mensagens)} mensagens encontradas")
    except SlackApiError as e:
        print("❌ Slack API:", e.response["error"])
    except Exception as e:
        print("❌ Erro inesperado:", e)

    return templates.TemplateResponse("thread.html", {
        "request": request,
        "mensagens": mensagens
    })

# ═════════════════════ Helpers DB / Métricas ═════════════════════════
def carregar_chamados_do_banco(
    status=None, resp_nome=None, d_ini=None, d_fim=None,
    capturado=None, mudou_tipo=None, sla=None
):
    url = os.getenv("DATABASE_PUBLIC_URL", "")
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgres://", 1)

    q = """SELECT id,tipo_ticket,status,responsavel,canal_id,thread_ts,
                  data_abertura,data_fechamento,sla_status,
                  capturado_por,log_edicoes,historico_reaberturas
           FROM ordens_servico WHERE true"""
    pr = []

    if status:                    q += " AND status = %s";             pr.append(status)
    if resp_nome:                 q += " AND responsavel = %s";        pr.append(resp_nome)
    if d_ini:                     q += " AND data_abertura >= %s";     pr.append(d_ini)
    if d_fim:                     q += " AND data_abertura <= %s";     pr.append(d_fim)
    if capturado:                 q += " AND capturado_por = %s";      pr.append(capturado)
    if sla == "fora":             q += " AND sla_status = 'fora'"
    if mudou_tipo == "sim":       q += " AND log_edicoes IS NOT NULL AND log_edicoes <> ''"
    elif mudou_tipo == "nao":     q += " AND (log_edicoes IS NULL OR log_edicoes = '')"

    q += " ORDER BY id DESC"

    try:
        with psycopg2.connect(url) as conn, conn.cursor() as cur:
            cur.execute(q, tuple(pr))
            rows = cur.fetchall()
    except Exception as e:
        print("⚠️ banco:", e); return []

    tz  = pytz.timezone("America/Sao_Paulo")
    fmt = lambda d: d.astimezone(tz).strftime("%d/%m/%Y às %Hh%M") if d else "-"
    user = lambda uid: get_real_name(uid) or "<não capturado>"

    return [
        {
            "id": r[0],
            "tipo_ticket": r[1],
            "status": r[2].lower(),
            "responsavel": get_real_name(r[3]) or r[3],
            "canal_id": r[4], "thread_ts": r[5],
            "abertura": fmt(r[6]), "fechamento": fmt(r[7]),
            "sla": r[8] or "-",
            "capturado_por": user(r[9]),
            "mudou_tipo": bool(r[10]) or bool(r[11]),
        }
        for r in rows
    ]

def calcular_metricas(ch):
    return {
        "total":          len(ch),
        "em_atendimento": sum(c["status"] in ("aberto", "em atendimento") for c in ch),
        "finalizados":    sum(c["status"] in ("fechado", "finalizado")    for c in ch),
        "fora_sla":       sum(c["sla"] == "fora"                          for c in ch),
        "mudaram_tipo":   sum(c["mudou_tipo"]                             for c in ch)
    }
