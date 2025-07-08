# main.py – Painel de Chamados (FastAPI)
import os, json, psycopg2, datetime as dt
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from utils.slack_helpers import get_real_name          # mesma helper de antes

app        = FastAPI()
templates  = Jinja2Templates(directory="templates")
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN", "")
slack_client    = WebClient(token=SLACK_BOT_TOKEN)

# ────────────────────────────── ROTAS ──────────────────────────────
@app.get("/painel", response_class=HTMLResponse)
async def painel(
    request: Request,
    status:       str | None = None,
    responsavel:  str | None = None,          # nome legível
    capturado:    str | None = None,          # nome legível
    mudou_tipo:   str | None = None,          # "sim"/"nao"/None
    data_ini:     str | None = None,
    data_fim:     str | None = None
):
    chamados = carregar_chamados_do_banco(status, responsavel,
                                          capturado, mudou_tipo,
                                          data_ini, data_fim)
    metricas = calcular_metricas(chamados)

    lista_resp  = sorted({c["responsavel"]   for c in chamados if c["responsavel"]})
    lista_cap   = sorted({c["capturado_por"] for c in chamados if c["capturado_por"]})

    return templates.TemplateResponse(
        "painel.html",
        {
            "request":     request,
            "chamados":    chamados,
            "metricas":    metricas,
            "filtros": {
                "status": status, "responsavel": responsavel,
                "capturado": capturado, "mudou_tipo": mudou_tipo,
                "data_ini": data_ini, "data_fim": data_fim
            },
            "responsaveis": lista_resp,
            "capturadores": lista_cap
        }
    )

@app.post("/thread", response_class=HTMLResponse)
async def thread(request: Request,
                 canal_id: str = Form(...),
                 thread_ts: str = Form(...)):
    try:
        resp = slack_client.conversations_replies(channel=canal_id,
                                                  ts=thread_ts,
                                                  limit=200)
        msgs = [{
            "user": get_real_name(m.get("user") or ""),
            "text": m.get("text", ""),
            "ts"  : dt.datetime.fromtimestamp(float(m["ts"]))
                    .strftime("%d/%m/%Y às %Hh%M")
        } for m in resp.get("messages", [])]
    except SlackApiError as e:
        msgs = [{"user":"-", "text":f"Erro Slack: {e.response['error']}", "ts":""}]

    return templates.TemplateResponse("thread.html",
                                      {"request": request, "msgs": msgs})

# ────────────────────────────── HELPERS ──────────────────────────────
def carregar_chamados_do_banco(st=None, resp=None, cap=None,
                               mudou=None, d_ini=None, d_fim=None):
    url = os.getenv("DATABASE_PUBLIC_URL", "")
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgres://", 1)

    q = """SELECT id,tipo_ticket,status,responsavel,canal_id,thread_ts,
                  data_abertura,data_fechamento,sla_status,
                  capturado_por,log_edicoes
           FROM ordens_servico WHERE true"""
    pr = []

    if st       and st.lower() != "todos": q += " AND status = %s";       pr.append(st)
    if resp     and resp.lower() != "todos":
        # banco guarda UID; convertemos p/ UID via sub-consulta
        q += " AND responsavel = (SELECT %s)"; pr.append(resp)
    if cap      and cap.lower()  != "todos":
        q += " AND capturado_por = (SELECT %s)"; pr.append(cap)
    if d_ini:  q += " AND data_abertura >= %s"; pr.append(d_ini)
    if d_fim:  q += " AND data_abertura <= %s"; pr.append(d_fim)

    q += " ORDER BY id DESC"

    try:
        with psycopg2.connect(url) as conn, conn.cursor() as cur:
            cur.execute(q, tuple(pr))
            rows = cur.fetchall()
    except Exception as e:
        print("⚠️ banco:", e); return []

    chamados = []
    for r in rows:
        (cid,tipo,status,uid,cid_slk,ts,a_d,a_f,sla,cap_uid,log) = r

        # detectou mudança no tipo?
        mudou_tipo = False
        if log:
            try:
                edits = json.loads(log)
                if "tipo_ticket" in edits: mudou_tipo = True
            except Exception:
                pass

        chamados.append({
            "id": cid,
            "tipo_ticket": tipo,
            "status": status,
            "responsavel": get_real_name(uid) or uid,
            "canal_id": cid_slk,
            "thread_ts": ts,
            "abertura": _fmt(a_d),
            "fechamento": _fmt(a_f),
            "sla": sla or "-",
            "mudou_tipo": mudou_tipo,
            "capturado_por": get_real_name(cap_uid) or cap_uid
        })

    # aplica filtro “mudou_tipo” depois; é bool
    if mudou == "sim":
        chamados = [c for c in chamados if c["mudou_tipo"]]
    elif mudou == "nao":
        chamados = [c for c in chamados if not c["mudou_tipo"]]

    return chamados

def calcular_metricas(ch):
    return {
        "total"        : len(ch),
        "em_atendimento": sum(c["status"] == "aberto"   for c in ch),
        "finalizados"  : sum(c["status"] == "fechado" for c in ch),
        "fora_sla"     : sum(c["sla"].lower().startswith("fora") for c in ch),
        "mudaram_tipo" : sum(c["mudou_tipo"] for c in ch)
    }

_fmt = lambda d: d.strftime("%d/%m/%Y às %Hh%M") if d else "-"
