"""
Acesso central ao Postgres – consultas enxutas.
"""
import os, psycopg2, pytz
from utils.slack_helpers import get_real_name
from datetime import datetime

_TZ = pytz.timezone("America/Sao_Paulo")
_URL = os.getenv("DATABASE_PUBLIC_URL", "").replace("postgresql://", "postgres://", 1)

# ── helpers internos ───────────────────────────────────────────
def _fmt(dt_obj):            # datetime → string local
    return dt_obj.astimezone(_TZ).strftime("%d/%m/%Y %H:%M") if dt_obj else "-"

def _user(uid: str):         # UID → nome real / placeholder
    nome = get_real_name(uid)
    return "<não capturado>" if not nome or nome.startswith(("U", "B", "W", "S")) else nome

def _base_sql():
    return """SELECT id,tipo_ticket,status,responsavel,canal_id,thread_ts,
                     data_abertura,data_fechamento,sla_status,
                     capturado_por,solicitante,log_edicoes,historico_reaberturas,
                     data_captura
              FROM ordens_servico WHERE true"""

def _apply_filters(q: str, pr: list,
                   *, status=None, resp=None, d_ini=None, d_fim=None,
                   capturado=None, mudou_tipo=None, sla=None, tipo_ticket=None):
    if status:     q += " AND LOWER(status) = %s";  pr.append(status.lower())
    if resp:       q += " AND responsavel=%s";      pr.append(resp)
    if d_ini:      q += " AND data_abertura >= %s"; pr.append(d_ini)
    if d_fim:      q += " AND data_abertura <= %s"; pr.append(d_fim)
    if capturado:  q += " AND capturado_por=%s";    pr.append(capturado)
    if sla == "fora": q += " AND sla_status='fora'"
    if tipo_ticket: q += " AND tipo_ticket=%s"; pr.append(tipo_ticket)
    if mudou_tipo == "sim":
        q += (" AND ( (log_edicoes IS NOT NULL AND log_edicoes <> '') "
               "OR (historico_reaberturas IS NOT NULL AND historico_reaberturas <> '') )")
    elif mudou_tipo == "nao":
        q += (" AND ( (log_edicoes IS NULL OR log_edicoes = '') "
               "AND (historico_reaberturas IS NULL OR historico_reaberturas = '') )")
    return q, pr

# ── API pública ────────────────────────────────────────────────
def contar_chamados(**filtros) -> int:
    q = "SELECT COUNT(*) FROM ordens_servico WHERE true"
    q, pr = _apply_filters(q, [], **filtros)
    try:
        with psycopg2.connect(_URL) as conn, conn.cursor() as cur:
            cur.execute(q, pr)
            return cur.fetchone()[0] or 0
    except Exception as e:
        print("DB ERRO (contar):", e)
        return 0

def carregar_chamados(*, limit=None, offset=None, **filtros):
    q, pr = _apply_filters(_base_sql(), [], **filtros)
    q += " ORDER BY id DESC"
    if limit:  q += f" LIMIT {limit}"
    if offset: q += f" OFFSET {offset}"
    try:
        with psycopg2.connect(_URL) as conn, conn.cursor() as cur:
            cur.execute(q, pr)
            rows = cur.fetchall()
    except Exception as e:
        print("DB ERRO (fetch):", e); return []

    return [{
        "id": r[0],
        "tipo_ticket": r[1],
        "status": r[2].lower(),
        "responsavel_uid": r[3],
        "responsavel": _user(r[3]),
        "canal_id": r[4],
        "thread_ts": r[5],

        # Datas para exibição formatada
        "abertura": _fmt(r[6]),
        "fechamento": _fmt(r[7]),

        # Datas cruas para dashboards (formatadas ISO)
        "abertura_raw": r[6].isoformat() if r[6] else None,
        "fechamento_raw": r[7].isoformat() if r[7] else None,

        # SLA
        "sla": (r[8] or "-").lower(),

        # Captura
        "capturado_uid": r[9],
        "capturado_por": _user(r[9]),
        "captura_raw": (
            datetime.fromisoformat(r[13]).isoformat()
            if isinstance(r[13], str)
            else r[13].isoformat() if r[13] else None
        ),

        # Solicitante e tipo
        "solicitante": _user(r[10]),
        "mudou_tipo": bool(r[10]) or bool(r[11]),
    } for r in rows]

def listar_responsaveis(**filtros):
    q, pr = _apply_filters("SELECT DISTINCT responsavel FROM ordens_servico WHERE true", [], **filtros)
    try:
        with psycopg2.connect(_URL) as conn, conn.cursor() as cur:
            cur.execute(q, pr)
            return sorted({r[0] for r in cur.fetchall() if r[0]})
    except Exception: return []

def listar_capturadores(**filtros):
    q, pr = _apply_filters("SELECT DISTINCT capturado_por FROM ordens_servico WHERE true", [], **filtros)
    try:
        with psycopg2.connect(_URL) as conn, conn.cursor() as cur:
            cur.execute(q, pr)
            return sorted({r[0] for r in cur.fetchall() if r[0]})
    except Exception: return []

def listar_tipos(**filtros):
    q, pr = _apply_filters("SELECT DISTINCT tipo_ticket FROM ordens_servico WHERE true", [], **filtros)
    try:
        with psycopg2.connect(_URL) as conn, conn.cursor() as cur:
            cur.execute(q, pr)
            return sorted({r[0] for r in cur.fetchall() if r[0]})
    except Exception: return []
