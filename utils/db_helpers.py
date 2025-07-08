"""
Centraliza tudo que é ‘dados do banco’, para evitar import circular.
"""
import os, psycopg2, pytz, datetime as dt
from utils.slack_helpers import get_real_name

TZ = pytz.timezone("America/Sao_Paulo")

def _fmt(dt_obj):
    return dt_obj.astimezone(TZ).strftime("%d/%m/%Y às %Hh%M") if dt_obj else "-"

def _u(uid):
    nome = get_real_name(uid)
    # se ainda parece um UID ou falhou:
    if not nome or nome.startswith(("U0", "U1", "W0", "B0", "S0")):
        return "<não capturado>"
    return nome

def carregar_chamados(status=None, resp_nome=None, d_ini=None, d_fim=None,
                      capturado=None, mudou_tipo=None, sla=None,
                      limit=None, offset=None):
    url = os.getenv("DATABASE_PUBLIC_URL", "").replace("postgresql://", "postgres://", 1)
    q  = """SELECT id,tipo_ticket,status,responsavel,canal_id,thread_ts,
                   data_abertura,data_fechamento,sla_status,
                   capturado_por,log_edicoes,historico_reaberturas
            FROM ordens_servico WHERE true"""
    pr = []
    if status:               q += " AND status = %s";              pr.append(status)
    if resp_nome:            q += " AND responsavel = %s";         pr.append(resp_nome)
    if d_ini:                q += " AND data_abertura >= %s";      pr.append(d_ini)
    if d_fim:                q += " AND data_abertura <= %s";      pr.append(d_fim)
    if capturado:            q += " AND capturado_por = %s";       pr.append(capturado)
    if sla == "fora":        q += " AND sla_status = 'fora'"
    if mudou_tipo == "sim":
        q += " AND ( (log_edicoes IS NOT NULL AND log_edicoes <> '') \
                     OR (historico_reaberturas IS NOT NULL AND historico_reaberturas <> '') )"
    elif mudou_tipo == "nao":
        q += " AND ( (log_edicoes IS NULL OR log_edicoes = '') \
                     AND (historico_reaberturas IS NULL OR historico_reaberturas = '') )"
    q += " ORDER BY id DESC"

    if limit is not None:
        q += " LIMIT %s"
        pr.append(limit)
    if offset is not None:
        q += " OFFSET %s"
        pr.append(offset)

    try:
        with psycopg2.connect(url) as conn, conn.cursor() as cur:
            cur.execute(q, tuple(pr)); rows = cur.fetchall()
    except Exception as e:
        print("DB ERRO:", e); return []

    tz  = pytz.timezone("America/Sao_Paulo")
    fmt = lambda d: d.astimezone(tz).strftime("%d/%m/%Y %H:%M") if d else "-"
    return [{
        "id": r[0], "tipo_ticket": r[1], "status": r[2].lower(),
        "responsavel": traduzir_usuario(r[3]),
        "canal_id": r[4], "thread_ts": r[5],
        "abertura": fmt(r[6]), "fechamento": fmt(r[7]),
        "sla": (r[8] or "-").lower(),
        "capturado_por": traduzir_usuario(r[9]),
        "mudou_tipo": bool(r[10]) or bool(r[11]),
    } for r in rows]
