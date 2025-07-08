# =======================
# 📁 db_helpers.py – Painel de Chamados
# =======================
import os, psycopg2, pytz
from utils.slack_helpers import get_real_name

_TZ = pytz.timezone("America/Sao_Paulo")

def _fmt(dt_obj):
    return dt_obj.astimezone(_TZ).strftime("%d/%m/%Y %H:%M") if dt_obj else "-"

def _user(uid: str) -> str:
    nome = get_real_name(uid)
    if not nome or nome.startswith(("U", "B", "W", "S")):
        return "<não capturado>"
    return nome

def _base_sql():
    return """SELECT id,tipo_ticket,status,responsavel,canal_id,thread_ts,
                     data_abertura,data_fechamento,sla_status,
                     capturado_por,log_edicoes,historico_reaberturas
              FROM ordens_servico WHERE true"""

def _apply_filters(q: str, pr: list, *,
                   status=None, resp=None, d_ini=None, d_fim=None,
                   capturado=None, mudou_tipo=None, sla=None) -> tuple[str, list]:
    if status:     q += " AND status = %s";          pr.append(status)
    if resp:       q += " AND responsavel = %s";     pr.append(resp)
    if d_ini:      q += " AND data_abertura >= %s";  pr.append(d_ini)
    if d_fim:      q += " AND data_abertura <= %s";  pr.append(d_fim)
    if capturado:  q += " AND capturado_por = %s";   pr.append(capturado)
    if sla == "fora": q += " AND sla_status = 'fora'"
    if mudou_tipo == "sim":
        q += (" AND ( (log_edicoes IS NOT NULL AND log_edicoes <> '') "
               "OR (historico_reaberturas IS NOT NULL AND historico_reaberturas <> '') )")
    elif mudou_tipo == "nao":
        q += (" AND ( (log_edicoes IS NULL OR log_edicoes = '') "
               "AND (historico_reaberturas IS NULL OR historico_reaberturas = '') )")
    return q, pr

def contar_chamados(**filtros) -> int:
    q, pr = _apply_filters(_base_sql().replace("*", "COUNT(*)"), [], **filtros)
    url = os.getenv("DATABASE_PUBLIC_URL", "").replace("postgresql://", "postgres://", 1)
    try:
        with psycopg2.connect(url) as conn, conn.cursor() as cur:
            cur.execute(q, pr)
            return cur.fetchone()[0]
    except Exception as e:
        print("DB ERRO (contagem):", e)
        return 0

def carregar_chamados(*, limit: int | None = None, offset: int | None = None, **filtros):
    q, pr = _apply_filters(_base_sql(), [], **filtros)
    q += " ORDER BY id DESC"
    if limit: q += f" LIMIT {limit}"
    if offset: q += f" OFFSET {offset}"

    url = os.getenv("DATABASE_PUBLIC_URL", "").replace("postgresql://", "postgres://", 1)
    try:
        with psycopg2.connect(url) as conn, conn.cursor() as cur:
            cur.execute(q, pr)
            rows = cur.fetchall()
    except Exception as e:
        print("DB ERRO (fetch):", e)
        return []

    return [
        {
            "id": r[0],
            "tipo_ticket": r[1],
            "status": r[2].lower(),
            "responsavel": _user(r[3]),
            "canal_id": r[4],
            "thread_ts": r[5],
            "abertura": _fmt(r[6]),
            "fechamento": _fmt(r[7]),
            "sla": (r[8] or "-").lower(),
            "capturado_por": _user(r[9]),
            "mudou_tipo": bool(r[10]) or bool(r[11]),
        }
        for r in rows
    ]

def listar_responsaveis(**filtros) -> list[str]:
    q = "SELECT DISTINCT responsavel FROM ordens_servico WHERE true"
    q, pr = _apply_filters(q, [], **filtros)
    url = os.getenv("DATABASE_PUBLIC_URL", "").replace("postgresql://", "postgres://", 1)
    try:
        with psycopg2.connect(url) as conn, conn.cursor() as cur:
            cur.execute(q, pr)
            return sorted({_user(r[0]) for r in cur.fetchall()})
    except Exception:
        return []

def listar_capturadores(**filtros) -> list[str]:
    q = "SELECT DISTINCT capturado_por FROM ordens_servico WHERE true"
    q, pr = _apply_filters(q, [], **filtros)
    url = os.getenv("DATABASE_PUBLIC_URL", "").replace("postgresql://", "postgres://", 1)
    try:
        with psycopg2.connect(url) as conn, conn.cursor() as cur:
            cur.execute(q, pr)
            return sorted({_user(r[0]) for r in cur.fetchall() if _user(r[0]) != "<não capturado>"})
    except Exception:
        return []
