import os, psycopg2, datetime as dt
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from utils.slack_helpers import get_real_name  # função já criada

app = FastAPI()
templates = Jinja2Templates(directory="templates")

# ─────────── Slack ───────────
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN", "")
slack_client = WebClient(token=SLACK_BOT_TOKEN)

# ─────────── Rotas ───────────
@app.get("/painel", response_class=HTMLResponse)
async def painel(
    request: Request,
    status: str | None = None,
    responsavel: str | None = None,
    data_ini: str | None = None,
    data_fim: str | None = None,
    capturado: str | None = None,
    mudou_tipo: str | None = None
):
    chamados = carregar_chamados_do_banco(status, responsavel, data_ini, data_fim, capturado, mudou_tipo)
    metricas = calcular_metricas(chamados)

    # listas únicas
    todos_responsaveis = sorted(set(ch["responsavel"] for ch in chamados if ch["responsavel"]))
    todos_capturadores = sorted(set(ch["capturado_por"] for ch in chamados if ch["capturado_por"]))

    return templates.TemplateResponse(
        "painel.html",
        {
            "request": request,
            "chamados": chamados,
            "metricas": metricas,
            "filtros": {
                "status": status,
                "responsavel": responsavel,
                "data_ini": data_ini,
                "data_fim": data_fim,
                "capturado": capturado,
                "mudou_tipo": mudou_tipo
            },
            "responsaveis": todos_responsaveis,
            "capturadores": todos_capturadores
        }
    )

@app.post("/thread", response_class=HTMLResponse)
async def thread(request: Request, canal_id: str = Form(...), thread_ts: str = Form(...)):
    try:
        resp = slack_client.conversations_replies(channel=canal_id, ts=thread_ts, limit=200)
        msgs = [
            {
                "user": get_real_name(m.get("user") or "BOT"),  # Se não tiver user, exibe "BOT"
                "text": m.get("text", ""),
                "ts": dt.datetime.fromtimestamp(float(m["ts"])).strftime("%d/%m/%Y às %Hh%M")
            }
            for m in resp.get("messages", [])
        ]
    except SlackApiError as e:
        msgs, canal_id = [], f"Erro Slack: {e.response['error']}"
    return templates.TemplateResponse("thread.html", {"request": request, "msgs": msgs})

# ─────────── Helpers ───────────
def carregar_chamados_do_banco(status=None, resp_nome=None, d_ini=None, d_fim=None, capturado=None, mudou_tipo=None):
    url = os.getenv("DATABASE_PUBLIC_URL", "")
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgres://", 1)

    q = """SELECT id, tipo_ticket, status, responsavel, canal_id, thread_ts,
                  data_abertura, data_fechamento, sla_status,
                  capturado_por, log_edicoes, historico_reaberturas
           FROM ordens_servico WHERE true"""
    pr = []

    if status and status.lower() != "todos":
        q += " AND status = %s"; pr.append(status)
    if resp_nome and resp_nome.lower() != "todos":
        q += " AND responsavel = %s"; pr.append(resp_nome)
    if capturado and capturado.lower() != "todos":
        q += " AND capturado_por = %s"; pr.append(capturado)
    if d_ini:
        q += " AND data_abertura >= %s"; pr.append(d_ini)
    if d_fim:
        q += " AND data_abertura <= %s"; pr.append(d_fim)

    q += " ORDER BY id DESC"

    try:
        with psycopg2.connect(url) as conn, conn.cursor() as cur:
            cur.execute(q, tuple(pr))
            rows = cur.fetchall()
    except Exception as e:
        print("⚠️ banco:", e)
        return []

    fmt = lambda d: d.strftime("%d/%m/%Y às %Hh%M") if d else "-"
    chamados = []

    for r in rows:
        capturador = get_real_name(r[9]) or "<não capturado>"

        # Detecta se houve alteração de tipo ou reabertura
        log = r[10] or ""
        hist = r[11] or ""
        mudou = ("alterou tipo_ticket" in log.lower()) or ("reabriu" in hist.lower())

        chamados.append({
            "id": r[0],
            "tipo_ticket": r[1],
            "status": r[2],
            "responsavel": get_real_name(r[3]) or r[3],
            "canal_id": r[4],
            "thread_ts": r[5],
            "abertura": fmt(r[6]),
            "fechamento": fmt(r[7]),
            "sla": r[8] or "-",
            "capturado_por": capturador,
            "mudou_tipo": mudou
        })

    # Filtro de mudança de tipo
    if mudou_tipo == "sim":
        chamados = [c for c in chamados if c["mudou_tipo"]]
    elif mudou_tipo == "nao":
        chamados = [c for c in chamados if not c["mudou_tipo"]]

    return chamados

def calcular_metricas(ch):
    return {
        "total": len(ch),
        "em_atendimento": sum(c["status"].lower() == "em atendimento" for c in ch),
        "finalizados":    sum(c["status"].lower() == "finalizado" for c in ch),
        "fora_sla":       sum(c["sla"].lower() == "fora do sla" for c in ch),
        "mudaram_tipo":   sum(c.get("mudou_tipo") for c in ch if isinstance(c.get("mudou_tipo"), bool))
    }
