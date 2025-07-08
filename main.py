import os, psycopg2, datetime as dt, pytz
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from utils.slack_helpers import get_real_name

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
    todos_responsaveis = sorted(set(ch["responsavel"] for ch in chamados if ch["responsavel"]))
    todos_capturadores = sorted(set(ch["capturado_por"] for ch in chamados if ch["capturado_por"] and ch["capturado_por"] != "<não capturado>"))

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
                "user": get_real_name(m.get("user") or ""),
                "text": m.get("text", ""),
                "ts": dt.datetime.fromtimestamp(float(m["ts"]), tz=dt.timezone.utc).astimezone(pytz.timezone("America/Sao_Paulo")).strftime("%d/%m/%Y às %Hh%M")
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

    q = """SELECT id,tipo_ticket,status,responsavel,canal_id,thread_ts,
                   data_abertura,data_fechamento,sla_status,
                   capturado_por,log_edicoes,historico_reaberturas
            FROM ordens_servico WHERE true"""
    pr = []

    if status and status.lower() != "todos":
        q += " AND status = %s"; pr.append(status)
    if resp_nome and resp_nome.lower() != "todos":
        q += " AND responsavel = %s"; pr.append(resp_nome)
    if d_ini:
        q += " AND data_abertura >= %s"; pr.append(d_ini)
    if d_fim:
        q += " AND data_abertura <= %s"; pr.append(d_fim)
    if capturado and capturado.lower() != "todos":
        q += " AND capturado_por = %s"; pr.append(capturado)
    if mudou_tipo == "sim":
        q += " AND (log_edicoes IS NOT NULL AND log_edicoes <> '')"
    elif mudou_tipo == "nao":
        q += " AND (log_edicoes IS NULL OR log_edicoes = '')"

    q += " ORDER BY id DESC"

    try:
        with psycopg2.connect(url) as conn, conn.cursor() as cur:
            cur.execute(q, tuple(pr))
            rows = cur.fetchall()
    except Exception as e:
        print("⚠️ banco:", e); return []

    fmt = lambda d: d.astimezone(pytz.timezone("America/Sao_Paulo")).strftime("%d/%m/%Y às %Hh%M") if d else "-"
    format_user = lambda uid: get_real_name(uid) or "<não capturado>"

    return [
        {
            "id": r[0],
            "tipo_ticket": r[1],
            "status": r[2].lower(),
            "responsavel": get_real_name(r[3]) or r[3],
            "canal_id": r[4],
            "thread_ts": r[5],
            "abertura": fmt(r[6]),
            "fechamento": fmt(r[7]),
            "sla": r[8] or "-",
            "capturado_por": format_user(r[9]),
            "mudou_tipo": bool(r[10]) or bool(r[11])
        }
        for r in rows
    ]

def calcular_metricas(ch):
    return {
        "total": len(ch),
        "em_atendimento": sum(c["status"] in ("aberto", "em atendimento") for c in ch),
        "finalizados": sum(c["status"] in ("fechado", "finalizado") for c in ch),
        "fora_sla": sum(c["sla"] == "fora" for c in ch),
        "mudaram_tipo": sum(c["mudou_tipo"] for c in ch)
    }
