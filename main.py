# main.py – Painel de Chamados v6 (estável + rápido)
import os, math, datetime as dt, pytz
from urllib.parse import urlencode

from fastapi import FastAPI, Request, Depends
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from slack_sdk import WebClient, errors as slack_err

from auth import router as auth_router, require_login
from export import export_router
from utils.db_helpers import (
    carregar_chamados,
    contar_chamados,
    listar_responsaveis,
    listar_capturadores,
    listar_tipos,
)
from utils.slack_helpers import get_real_name, formatar_texto_slack

# ── App e Middleware ────────────────────────────────────────────
app = FastAPI()

app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SESSION_SECRET_KEY", "3fa85f64-5717-4562-b3fc-2c963f66afa6")
)

app.include_router(auth_router)
app.include_router(export_router)

templates = Jinja2Templates(directory="templates")
templates.env.globals.update(get_real_name=get_real_name, max=max, min=min)
PER_PAGE = 20

# ── Slack client ────────────────────────────────────────────────
slack_client = WebClient(token=os.getenv("SLACK_BOT_TOKEN", ""))


# ═════════════════════════ ROTAS ════════════════════════════════
from fastapi import Depends
from auth import require_login

@app.get("/painel", response_class=HTMLResponse)
async def painel(request: Request,
                 user: dict = Depends(require_login),
                 status: str = "Todos",
                 responsavel: str = "Todos",
                 capturado: str = "Todos",
                 mudou_tipo: str = "Todos",
                 data_ini: str = None,
                 data_fim: str = None,
                 sla: str = "Todos",
                 tipo: str = "Todos",
                 page: int = 1):

    # Mapeamento visual → real
    status_map = {
        "Aberto": "aberto",
        "Em Atendimento": "em análise",
        "Finalizado": "fechado",
        "Cancelado": "cancelado",
        "Todos": None
    }

    # filtros preparados
    filtros = {
        "status":      status_map.get(status),
        "resp":        None if responsavel in ("Todos", "") else responsavel,
        "capturado":   None if capturado in ("Todos", "") else capturado,
        "mudou_tipo":  None if mudou_tipo == "Todos" else mudou_tipo,
        "sla":         None if sla == "Todos" else sla,
        "tipo_ticket": None if tipo == "Todos" else tipo,
    }

    if data_ini:
        try: filtros["d_ini"] = dt.datetime.strptime(data_ini, "%Y-%m-%d")
        except: filtros["d_ini"] = None

    if data_fim:
        try: filtros["d_fim"] = dt.datetime.strptime(data_fim, "%Y-%m-%d") + dt.timedelta(days=1)
        except: filtros["d_fim"] = None

    filtros_sem_status = {k: v for k, v in filtros.items()
                          if k not in ("status", "sla", "mudou_tipo")}

    total = contar_chamados(**filtros)
    paginas_totais = max(1, math.ceil(total / PER_PAGE))
    page = max(1, min(page, paginas_totais))
    ini, fim = (page - 1) * PER_PAGE, page * PER_PAGE
    chamados = carregar_chamados(limit=PER_PAGE, offset=ini, **filtros)

    fs = dict(filtros_sem_status)  # evitar duplicação

    fs.pop("status", None)
    fs.pop("sla", None)
    fs.pop("mudou_tipo", None)

    metricas = {
        "total":          total,
        "em_atendimento": contar_chamados(status="em análise", **fs),
        "finalizados":    contar_chamados(**fs, status="fechado"),
        "fora_sla":       contar_chamados(sla="fora", **fs),
        "mudaram_tipo":   contar_chamados(**fs, mudou_tipo="sim"),
    }

    filtros_dict = {
        "status": status, "responsavel": responsavel,
        "capturado": capturado, "mudou_tipo": mudou_tipo,
        "data_ini": data_ini, "data_fim": data_fim,
        "sla": sla, "tipo": tipo
    }
    filtros_qs = urlencode({k: v for k, v in filtros_dict.items() if v and v != "Todos"})

    return templates.TemplateResponse(
        "painel.html",
        {
            "request":        request,
            "chamados":       chamados,
            "metricas":       metricas,
            "pagina_atual":   page,
            "paginas_totais": paginas_totais,
            "url_paginacao":  f"/painel?{filtros_qs}",
            "filtros":        filtros_dict,
            "responsaveis":   listar_responsaveis(),
            "capturadores":   listar_capturadores(),
            "tipos":          listar_tipos(),
            "filtros_as_query": filtros_qs,
        },
    )

@app.get("/dashboards", response_class=HTMLResponse)
async def dashboards(request: Request, user: dict = Depends(require_login)):
    from utils.db_helpers import carregar_chamados
    import datetime as dt

    # pega filtros da query string (vêm do JS via form)
    data_ini = request.query_params.get("data_ini")
    data_fim = request.query_params.get("data_fim")
    responsavel = request.query_params.get("responsavel")

    filtros = {}

    if data_ini:
        try:
            filtros["d_ini"] = dt.datetime.strptime(data_ini, "%Y-%m-%d")
        except:
            pass

    if data_fim:
        try:
            filtros["d_fim"] = dt.datetime.strptime(data_fim, "%Y-%m-%d") + dt.timedelta(days=1)
        except:
            pass

    if responsavel and responsavel != "Todos":
        filtros["resp"] = responsavel

    # aplica limit só se nenhum filtro for usado
    usar_limit = not filtros
    dados = carregar_chamados(limit=200 if usar_limit else None, **filtros)

    # conserta datas para o frontend (caso venha datetime puro)
    for c in dados:
        for campo in ("abertura_raw", "captura_raw", "fechamento_raw"):
            if isinstance(c.get(campo), dt.datetime):
                c[campo] = c[campo].isoformat()

    return templates.TemplateResponse(
        "dashboards.html",
        {
            "request": request,
            "dados": dados
        }
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
