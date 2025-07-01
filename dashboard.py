# -------------------------------------------------------------
# dashboard.py  •  Painel JFL Comercial
# -------------------------------------------------------------
"""
Painel Streamlit para acompanhar chamados comerciais JFL
• Conexão PostgreSQL (SQLAlchemy ≥2)                         ✔️
• Variáveis SLACK_BOT_TOKEN / DATA_PUBLIC_URL tratadas       ✔️
• Thread Slack integrada + métricas, filtros, exportações    ✔️
"""

from __future__ import annotations

# ═══════════════════════ Imports ═══════════════════════════
import os, io, json, re
from datetime import date

import pandas as pd
import streamlit as st
import matplotlib.pyplot as plt
from sqlalchemy import create_engine, text
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode

from utils.slack import get_nome_real

# ═══════════════ Ambiente / tokens ═════════════════════════
SLACK_BOT_TOKEN = st.secrets.get("SLACK_BOT_TOKEN", "")
DATA_PUBLIC_URL = st.secrets.get("DATA_PUBLIC_URL", "")

if not DATA_PUBLIC_URL:
    st.error("❌ DATA_PUBLIC_URL não definida.")
    st.stop()

if not SLACK_BOT_TOKEN:
    st.warning("⚠️ SLACK_BOT_TOKEN não definida – nomes de usuários podem aparecer como “–”.")

st.set_page_config(page_title="Painel JFL", layout="wide")
slack_client = WebClient(token=SLACK_BOT_TOKEN)

# ═══════════════ Estilo básico ═════════════════════════════
st.markdown(
    """
    <style>
      .main  { background:#F5F5F5 }
      .title { font-size:32px;font-weight:bold;color:#003366 }
      .sub   { font-size:16px;color:#666 }
      .card  { background:#fff;padding:20px;border-radius:12px;
               box-shadow:0 2px 6px rgba(0,0,0,.1);text-align:center }
    </style>
    """,
    unsafe_allow_html=True,
)
st.markdown("<div class='title'>🏢 JFL | Painel Gerencial de Chamados</div>", True)
st.markdown("<div class='sub'>Monitoramento em tempo real • Base comercial</div>", True)
st.markdown("---")

# ═══════════════ Helpers ══════════════════════════════════
_reab = re.compile(r"\[(\d{4}-\d{2}-\d{2})]\s+(.+?)\s+(.*)")

def parse_reaberturas(txt: str | None, os_id: int, resp_nome: str, data_abertura: pd.Timestamp):
    if not txt:
        return []
    regs: list[dict] = []
    for linha in filter(None, map(str.strip, txt.splitlines())):
        m = _reab.match(linha)
        if m:
            data_str, quem, desc = m.groups()
            regs.append(
                dict(
                    id=os_id,
                    quando=pd.to_datetime(data_str, errors="coerce"),
                    quem=quem,
                    descricao=desc,
                    campo="reabertura",
                    de="-",
                    para="-",
                    responsavel_nome=resp_nome,
                    data_abertura=data_abertura,
                )
            )
    return regs

def fetch_thread(channel_id: str | None, thread_ts: str | None):
    if not (channel_id and thread_ts and SLACK_BOT_TOKEN):
        return []
    try:
        resp = slack_client.conversations_replies(channel=channel_id, ts=thread_ts, limit=200)
        return resp["messages"][::-1]
    except SlackApiError as e:
        st.error(f"Erro Slack: {e.response['error']}")
        return []

def safe_get(row: dict, col: str, default="-"):
    return row.get(col, default) if isinstance(row, dict) else default

# ═══════════════ Teste Slack isolado ANTES DE TUDO ══════════════════════
st.subheader("🧪 Teste Isolado da API do Slack")
if st.button("Ver Thread de Teste"):
    canal = "C06TTKNEBHA"
    ts = "1749246526.039919"
    msgs = fetch_thread(canal, ts)
    if msgs:
        st.success(f"{len(msgs)} mensagens encontradas")
        for m in msgs:
            ts_msg = pd.to_datetime(float(m["ts"]), unit="s")
            user = get_nome_real(m.get("user", ""))
            txt = m.get("text", "")
            st.markdown(
                f"<div style='background:#F4F6F7;padding:8px;border-left:4px solid #3E84F4;'>"
                f"<strong>{user}</strong> "
                f"<span style='color:#777;'>_{ts_msg:%d/%m %H:%M}_</span><br>{txt}</div>",
                unsafe_allow_html=True,
            )
    else:
        st.warning("⚠️ Nenhuma mensagem encontrada ou canal inválido.")
