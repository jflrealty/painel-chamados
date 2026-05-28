# main.py – Painel de Chamados v6 (estável + rápido)
import os, math, datetime as dt, pytz
from pathlib import Path
from urllib.parse import urlencode

from fastapi import FastAPI, Request, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from jinja2 import Environment, FileSystemLoader
from starlette.middleware.sessions import SessionMiddleware
from slack_sdk import WebClient, errors as slack_err

from auth import router as auth_router, require_login
from export import export_router
from utils import db_helpers, db_financeiro

from utils.db_helpers import (
    carregar_chamados,
    contar_chamados,
    listar_responsaveis,
    listar_capturadores,
    listar_tipos,
)
from utils.slack_helpers import get_real_name, formatar_texto_slack

# ── App e Middleware ────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent

app = FastAPI()

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SESSION_SECRET_KEY", "3fa85f64-5717-4562-b3fc-2c963f66afa6")
)

app.include_router(auth_router)
app.include_router(export_router)

jinja_env = Environment(loader=FileSystemLoader(str(BASE_DIR / "templates")))
jinja_env.globals.update(get_real_name=get_real_name, max=max, min=min)
templates = Jinja2Templates(env=jinja_env)

PER_PAGE = 20

# ── Slack client ────────────────────────────────────────────────
slack_client = WebClient(token=os.getenv("SLACK_BOT_TOKEN", ""))


# ═════════════════════════ ROTAS ════════════════════════════════

@app.get("/")
async def root():
    return RedirectResponse(url="/painel")


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

    status_map = {
        "Aberto": "aberto",
        "Em Atendimento": "em análise",
        "Finalizado": "fechado",
        "Cancelado": "cancelado",
        "Todos": None
    }

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

    fs = dict(filtros_sem_status)
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
        request,
        "painel.html",
        {
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

@app.get("/painel-financeiro", response_class=HTMLResponse)
async def painel_financeiro(request: Request,
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

    status_map = {
        "Aberto": "aberto",
        "Em Atendimento": "em atendimento",
        "Finalizado": "finalizado",
        "Cancelado": "cancelado",
        "Todos": None
    }

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

    total = db_financeiro.contar_chamados(**filtros)
    paginas_totais = max(1, math.ceil(total / PER_PAGE))
    page = max(1, min(page, paginas_totais))
    ini, fim = (page - 1) * PER_PAGE, page * PER_PAGE
    chamados = db_financeiro.carregar_chamados(limit=PER_PAGE, offset=ini, **filtros)

    fs = dict(filtros_sem_status)

    metricas = {
        "total":          db_financeiro.contar_chamados(**filtros),
        "em_atendimento": db_financeiro.contar_chamados(**fs, status="em atendimento"),
        "finalizados":    db_financeiro.contar_chamados(**fs, status="finalizado"),
        "fora_sla":       db_financeiro.contar_chamados(**fs, sla="fora"),
        "mudaram_tipo":   db_financeiro.contar_chamados(**fs, mudou_tipo="sim"),
    }

    filtros_dict = {
        "status": status, "responsavel": responsavel,
        "capturado": capturado, "mudou_tipo": mudou_tipo,
        "data_ini": data_ini, "data_fim": data_fim,
        "sla": sla, "tipo": tipo
    }
    filtros_qs = urlencode({k: v for k, v in filtros_dict.items() if v and v != "Todos"})

    return templates.TemplateResponse(
        request,
        "painel_financeiro.html",
        {
            "chamados":       chamados,
            "metricas":       metricas,
            "pagina_atual":   page,
            "paginas_totais": paginas_totais,
            "url_paginacao":  f"/painel-financeiro?{filtros_qs}",
            "filtros":        filtros_dict,
            "responsaveis":   db_financeiro.listar_responsaveis(),
            "capturadores":   db_financeiro.listar_capturadores(),
            "tipos":          db_financeiro.listar_tipos(),
            "filtros_as_query": filtros_qs,
        },
    )

@app.get("/dashboards", response_class=HTMLResponse)
async def dashboards(request: Request, user: dict = Depends(require_login)):
    import datetime as dt

    data_ini = request.query_params.get("data_ini")
    data_fim = request.query_params.get("data_fim")
    responsavel = request.query_params.get("responsavel")
    status = request.query_params.get("status")
    tipo = request.query_params.get("tipo")

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

    if status and status != "Todos":
        filtros["status"] = status

    if tipo and tipo != "Todos":
        filtros["tipo_ticket"] = tipo

    filtros_ativos = any([
        filtros.get("d_ini"),
        filtros.get("d_fim"),
        filtros.get("resp"),
        filtros.get("status"),
        filtros.get("tipo_ticket")
    ])

    usar_limit = not filtros_ativos
    print("usar_limit:", usar_limit)

    dados = carregar_chamados(**({} if usar_limit else filtros))

    for c in dados:
        for campo in ("abertura_raw", "captura_raw", "fechamento_raw"):
            valor = c.get(campo)
            if valor:
                if isinstance(valor, dt.datetime):
                    c[campo] = valor.isoformat()
                elif isinstance(valor, str):
                    try:
                        c[campo] = dt.datetime.fromisoformat(valor).isoformat()
                    except:
                        c[campo] = None

    return templates.TemplateResponse(
        request,
        "dashboards.html",
        {"dados": dados},
    )

# ───────────────────────── THREAD ───────────────────────────────
@app.post("/thread")
async def thread(request: Request):
    form      = await request.form()
    canal_id  = form["canal_id"]
    thread_ts = form["thread_ts"]

    mensagens = []
    try:
        from utils.slack_helpers import get_slack_client
        client = get_slack_client(canal_id)
        resp = client.conversations_replies(channel=canal_id, ts=thread_ts, limit=200)
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

    return templates.TemplateResponse(
        request,
        "thread.html",
        {"mensagens": mensagens},
    )
