import os, psycopg2, pytz
from utils.slack_helpers import get_real_name
from datetime import datetime
from dateutil.parser import parse as parse_dt

_TZ = pytz.timezone("America/Sao_Paulo")
_URL = "postgres://postgres:yZybXyL...@shortline.proxy.rlwy.net:17741/railway"  # URL do banco FINANCEIRO

# Reaproveita os mesmos helpers do db_helpers, mas renomeia a base
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
