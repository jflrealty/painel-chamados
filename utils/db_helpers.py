"""
Acesso central ao Postgres – consultas enxutas.
"""
import os, psycopg2, pytz
from utils.slack_helpers import get_real_name

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
                     capturado_por,log_edicoes,historico_reaberturas
              FROM ordens_servico WHERE true"""

def _apply_filters(q: str, pr: list,
                   *, status=None, resp=None, d_ini=None, d_fim=None,
                   capturado=None, mudou_tipo=None, sla=None):
    if status:     q += " AND status=%s";           pr.append(status)
    if resp:       q += " AND responsavel=%s";      pr.append(resp)
    if d_ini:      q += " AND data_abertura >= %s"; pr.append(d_ini)
    if d_fim:      q += " AND data_abertura <= %s"; pr.append(d_fim)
    if capturado:  q += " AND capturado_por=%s";    pr.append(capturado)
    if sla == "fora": q += " AND sla_status='fora'"
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
        "id": r[0], "tipo_ticket": r[1], "status": r[2].lower(),
        "responsavel": _user(r[3]), "canal_id": r[4], "thread_ts": r[5],
        "abertura": _fmt(r[6]), "fechamento": _fmt(r[7]),
        "sla": (r[8] or "-").lower(),
        "capturado_por": _user(r[9]),
        "mudou_tipo": bool(r[10]) or bool(r[11]),
    } for r in rows]

def listar_responsaveis(**filtros):
    q, pr = _apply_filters("SELECT DISTINCT responsavel FROM ordens_servico WHERE true", [], **filtros)
    try:
        with psycopg2.connect(_URL) as conn, conn.cursor() as cur:
            cur.execute(q, pr)
            return sorted({_user(r[0]) for r in cur.fetchall()})
    except Exception: return []

def listar_capturadores(**filtros):
    q, pr = _apply_filters("SELECT DISTINCT capturado_por FROM ordens_servico WHERE true", [], **filtros)
    try:
        with psycopg2.connect(_URL) as conn, conn.cursor() as cur:
            cur.execute(q, pr)
            return sorted({u for u in (_user(r[0]) for r in cur.fetchall()) if u != "<não capturado>"})
    except Exception: return []
