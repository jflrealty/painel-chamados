import os, psycopg2, pytz
from utils.slack_helpers import get_real_name
from datetime import datetime
from dateutil.parser import parse as parse_dt

_TZ = pytz.timezone("America/Sao_Paulo")
_URL = os.getenv("DATABASE_PUBLIC_URL_FINANCEIRO")

# ── Helpers ─────────────────────────────────────────────
def _fmt(dt_obj):
    return dt_obj.astimezone(_TZ).strftime("%d/%m/%Y %H:%M") if dt_obj else "-"

def _user(uid: str):
    nome = get_real_name(uid)
    return "<não capturado>" if not nome or nome.startswith(("U", "B", "W", "S")) else nome

def _to_iso(dt):
    try:
        if isinstance(dt, datetime):
            return dt.astimezone(_TZ).isoformat()
        elif isinstance(dt, str) and dt:
            return parse_dt(dt).astimezone(_TZ).isoformat()
    except:
        return None

def _base_sql():
    return """SELECT id,tipo_ticket,status,responsavel,canal_id,thread_ts,
                     data_abertura,data_fechamento,sla_status,
                     capturado_por,solicitante,log_edicoes,historico_reaberturas,
                     data_captura
              FROM ordens_servico_financeiro WHERE true"""

def _apply_filters(q: str, pr: list,
                   *, status=None, resp=None, d_ini=None, d_fim=None,
                   capturado=None, mudou_tipo=None, sla=None, tipo_ticket=None):
    if status:
        q += " AND LOWER(status) = LOWER(%s)"
        pr.append(status)
    if resp:
        q += " AND responsavel=%s"
        pr.append(resp)
    if d_ini:
        q += " AND data_abertura >= %s"
        pr.append(d_ini)
    if d_fim:
        q += " AND data_abertura <= %s"
        pr.append(d_fim)
    if capturado:
        q += " AND capturado_por=%s"
        pr.append(capturado)
    if sla == "fora":
        q += " AND sla_status='fora'"
    if tipo_ticket:
        q += " AND tipo_ticket=%s"
        pr.append(tipo_ticket)
    if mudou_tipo == "sim":
        q += (" AND ( (log_edicoes IS NOT NULL AND log_edicoes <> '') "
               "OR (historico_reaberturas IS NOT NULL AND historico_reaberturas <> '') )")
    elif mudou_tipo == "nao":
        q += (" AND ( (log_edicoes IS NULL OR log_edicoes = '') "
               "AND (historico_reaberturas IS NULL OR historico_reaberturas = '') )")
    return q, pr

# ── API pública ─────────────────────────────────────────
def contar_chamados(**filtros) -> int:
    q = "SELECT COUNT(*) FROM ordens_servico_financeiro WHERE true"
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
    if limit is not None:
        q += f" LIMIT {limit}"
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

        "abertura": _fmt(r[6]),
        "fechamento": _fmt(r[7]),
        "abertura_raw": _to_iso(r[6]),
        "fechamento_raw": _to_iso(r[7]),
        "captura_raw": _to_iso(r[13]),

        "sla": (r[8] or "-").lower(),
        "capturado_uid": r[9],
        "capturado_por": _user(r[9]),
        "solicitante": _user(r[10]),
        "mudou_tipo": bool(r[11]) or bool(r[12]),
    } for r in rows]

def listar_responsaveis(**filtros):
    q, pr = _apply_filters("SELECT DISTINCT responsavel FROM ordens_servico_financeiro WHERE true", [], **filtros)
    try:
        with psycopg2.connect(_URL) as conn, conn.cursor() as cur:
            cur.execute(q, pr)
            return sorted({r[0] for r in cur.fetchall() if r[0]})
    except Exception:
        return []

def listar_capturadores(**filtros):
    q, pr = _apply_filters("SELECT DISTINCT capturado_por FROM ordens_servico_financeiro WHERE true", [], **filtros)
    try:
        with psycopg2.connect(_URL) as conn, conn.cursor() as cur:
            cur.execute(q, pr)
            return sorted({r[0] for r in cur.fetchall() if r[0]})
    except Exception:
        return []

def listar_tipos(**filtros):
    q, pr = _apply_filters("SELECT DISTINCT tipo_ticket FROM ordens_servico_financeiro WHERE true", [], **filtros)
    try:
        with psycopg2.connect(_URL) as conn, conn.cursor() as cur:
            cur.execute(q, pr)
            return sorted({r[0] for r in cur.fetchall() if r[0]})
    except Exception:
        return []
