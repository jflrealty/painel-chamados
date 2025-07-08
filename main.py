# main.py – Painel de Chamados (FastAPI) ✔️
import os, psycopg2, datetime as dt, json
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from utils.slack_helpers import get_real_name   # ⇽ já criado

app = FastAPI()
templates = Jinja2Templates(directory="templates")

# ─────────── Slack ───────────
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN", "")
slack_client    = WebClient(token=SLACK_BOT_TOKEN)

# ─────────── ROTA PRINCIPAL ───────────
@app.get("/painel", response_class=HTMLResponse)
async def painel(
    request: Request,
    status:       str | None = None,
    responsavel:  str | None = None,
    capturado:    str | None = None,
    historico:    str | None = None,          # novo filtro
    data_ini:     str | None = None,
    data_fim:     str | None = None,
):
    chamados = carregar_chamados_do_banco(status, responsavel,
                                          capturado, historico,
                                          data_ini,  data_fim)
    metricas = calcular_metricas(chamados)

    # Combos
    lista_resp  = sorted({c["responsavel"]   for c in chamados if c["responsavel"]})
    lista_capt  = sorted({c["capturado_por"] for c in chamados if c["capturado_por"]})

    return templates.TemplateResponse(
        "painel.html",
        {
            "request":      request,
            "chamados":     chamados,
            "metricas":     metricas,
            "responsaveis": lista_resp,
            "capturadores": lista_capt,
            "filtros": {
                "status": status, "responsavel": responsavel,
                "capturado": capturado, "historico": historico,
                "data_ini": data_ini,   "data_fim":  data_fim,
            },
        },
    )

# ─────────── THREAD ───────────
@app.post("/thread", response_class=HTMLResponse)
async def thread(request: Request,
                 canal_id: str = Form(...),
                 thread_ts: str = Form(...)):
    try:
        resp  = slack_client.conversations_replies(
                    channel=canal_id, ts=thread_ts, limit=200)
        msgs = [
            {
                "user": get_real_name(m.get("user") or ""),
                "text": m.get("text", ""),
                "ts":   dt.datetime.fromtimestamp(float(m["ts"]))
                        .strftime("%d/%m/%Y às %Hh%M"),
            }
            for m in resp.get("messages", [])
        ]
    except SlackApiError as e:
        msgs, canal_id = [], f"Erro Slack: {e.response['error']}"

    return templates.TemplateResponse("thread.html",
                                      {"request": request, "msgs": msgs})

# ─────────── HELPERS ───────────
def tem_historico(log_edicoes: str | None, reab: str | None) -> bool:
    log = (log_edicoes or "").lower()
    return ("alterou o tipo" in log) or bool((reab or "").strip())

def carregar_chamados_do_banco(st=None, resp=None,
                               capt=None, hist=None,
                               d_ini=None, d_fim=None):
    url = os.getenv("DATABASE_PUBLIC_URL", "")
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgres://", 1)

    q = """
        SELECT id,tipo_ticket,status,responsavel,canal_id,thread_ts,
               data_abertura,data_fechamento,sla_status,capturado_por,
               log_edicoes,historico_reaberturas
        FROM ordens_servico
        WHERE true
    """
    pr = []

    if st:
        q += " AND status = %s";            pr.append(st)
    if resp:
        q += " AND responsavel = %s";       pr.append(resp)
    if capt:
        q += " AND capturado_por = %s";     pr.append(capt)
    if d_ini:
        q += " AND data_abertura >= %s";    pr.append(d_ini)
    if d_fim:
        q += " AND data_abertura <= %s";    pr.append(d_fim)

    q += " ORDER BY id DESC"

    try:
        with psycopg2.connect(url) as conn, conn.cursor() as cur:
            cur.execute(q, tuple(pr))
            rows = cur.fetchall()
    except Exception as e:
        print("⚠️ banco:", e); return []

    fmt = lambda d: d.strftime("%d/%m/%Y às %Hh%M") if d else "-"

    dados = []
    for r in rows:
        historico = tem_historico(r[10], r[11])
        dados.append({
            "id":           r[0],
            "tipo_ticket":  r[1],
            "status":       r[2],
            "responsavel":  get_real_name(r[3]) or r[3],
            "canal_id":     r[4],
            "thread_ts":    r[5],
            "abertura":     fmt(r[6]),
            "fechamento":   fmt(r[7]),
            "sla":          r[8] or "-",
            "capturado_por":get_real_name(r[9]) or r[9],
            "mudou_tipo":  "alterou o tipo" in (r[10] or "").lower(),
            "reabriu":      bool((r[11] or "").strip()),
            "historico":    historico,
        })

    # filtro final “historico”
    if hist == "sim":
        dados = [d for d in dados if d["historico"]]
    elif hist == "nao":
        dados = [d for d in dados if not d["historico"]]

    return dados

def calcular_metricas(ch):
    return {
        "total":          len(ch),
        "em_atendimento": sum(c["status"] == "Em Atendimento" for c in ch),
        "finalizados":    sum(c["status"] == "Finalizado"     for c in ch),
        "fora_sla":       sum(c["sla"].lower().startswith("fora") for c in ch),
        "com_historico":  sum(c["historico"] for c in ch),
    }
