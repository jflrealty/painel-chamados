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
import io, json, re
from datetime import date

import pandas as pd
import streamlit as st
import matplotlib.pyplot as plt
from sqlalchemy import create_engine, text
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode

from utils.slack import get_nome_real  # helper de nomes reais

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

def parse_reaberturas(txt: str | None, os_id: int, resp_nome: str, data_abertura):
    """Extrai texto de reaberturas → lista de dicionários"""
    if not txt:
        return []
    regs = []
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
    """Busca mensagens da thread no Slack."""
    if not (channel_id and thread_ts and SLACK_BOT_TOKEN):
        return []
    try:
        resp = slack_client.conversations_replies(channel=channel_id, ts=thread_ts, limit=200)
        return resp["messages"][::-1]  # ordem cronológica
    except SlackApiError as e:
        st.error(f"Erro Slack: {e.response['error']}")
        return []

def safe_get(row: dict, col: str, default="-"):
    return row.get(col, default) if isinstance(row, dict) else default

# ═══════════════ Carregamento base ════════════════════════
@st.cache_data(show_spinner=False)
def carregar_dados():
    url = DATA_PUBLIC_URL.replace("postgres://", "postgresql+psycopg2://")
    if "sslmode" not in url:
        url += "?sslmode=require"

    try:
        engine = create_engine(url, pool_pre_ping=True, future=True)
        with engine.connect() as conn:
            df = pd.read_sql(text("SELECT * FROM ordens_servico"), conn)
    except Exception as e:
        st.error(f"❌ Erro ao ler o banco: {e}")
        return pd.DataFrame(), pd.DataFrame()

    if df.empty:
        return df, pd.DataFrame()

    # Campos obrigatórios faltantes → None
    obrig = [
        "responsavel", "solicitante", "capturado_por", "status",
        "data_abertura", "data_fechamento", "log_edicoes",
        "historico_reaberturas", "data_ultima_edicao", "ultimo_editor",
    ]
    for col in obrig:
        if col not in df.columns:
            df[col] = None

    # Nomes legíveis
    df["responsavel_nome"] = df["responsavel"].apply(get_nome_real)
    df["solicitante_nome"] = df["solicitante"].apply(get_nome_real)

    # Datas
    df["data_abertura"]   = pd.to_datetime(df["data_abertura"], errors="coerce")
    df["data_fechamento"] = pd.to_datetime(df["data_fechamento"], errors="coerce")
    df["dias_para_fechamento"] = (df["data_fechamento"] - df["data_abertura"]).dt.days

    # df_alt (edições + reaberturas)
    regs = []
    for _, r in df.iterrows():
        # edições
        if r["log_edicoes"]:
            try:
                for campo, mud in json.loads(r["log_edicoes"]).items():
                    regs.append(
                        dict(
                            id=r["id"],
                            quando=pd.to_datetime(r["data_ultima_edicao"], errors="coerce"),
                            quem=r.get("ultimo_editor") or "-",
                            descricao=f"{campo}: {mud.get('de')} → {mud.get('para')}",
                            campo=campo,
                            de=mud.get("de"), para=mud.get("para"),
                            responsavel_nome=r["responsavel_nome"],
                            data_abertura=r["data_abertura"],
                        )
                    )
            except Exception:
                pass
        # reaberturas
        regs += parse_reaberturas(
            r.get("historico_reaberturas"),
            r["id"],
            r["responsavel_nome"],
            r["data_abertura"],
        )

    df_alt = pd.DataFrame(regs).sort_values("quando", ascending=False) if regs else pd.DataFrame()
    return df, df_alt

# ═══════════════ Main =================================================
df, df_alt = carregar_dados()
if df.empty:
    st.info("📭 Nenhum chamado encontrado.")
    st.stop()

# ─── Filtros laterais ───
today = date.today()
min_d, max_d = df["data_abertura"].min().date(), df["data_abertura"].max().date()
ini, fim = st.sidebar.date_input("🗓️ Período:", [min_d, max_d], max_value=today)

mask = df["data_abertura"].dt.date.between(ini, fim)
df = df[mask]
if not df_alt.empty:
    df_alt = df_alt[df_alt["data_abertura"].dt.date.between(ini, fim)]

resp_opts = sorted(df["responsavel_nome"].dropna().unique())
sel_resp = st.sidebar.multiselect("🧑‍💼 Responsável:", resp_opts)
if sel_resp:
    df = df[df["responsavel_nome"].isin(sel_resp)]
    if not df_alt.empty:
        df_alt = df_alt[df_alt["responsavel_nome"].isin(sel_resp)]

# ─── Métricas ───
c1, c2, c3, c4, c5 = st.columns(5)
c1.markdown(f"<div class='card'><h3>{len(df)}</h3><p>Total</p></div>", True)
c2.markdown(f"<div class='card'><h3>{df['status'].isin(['aberto','em analise']).sum()}</h3><p>Em Atendimento</p></div>", True)
c3.markdown(f"<div class='card'><h3>{df['data_fechamento'].notna().sum()}</h3><p>Finalizados</p></div>", True)
c4.markdown(f"<div class='card'><h3>{(df['dias_para_fechamento']<=2).sum()}</h3><p>Dentro SLA</p></div>", True)
c5.markdown(f"<div class='card'><h3>{(df['dias_para_fechamento']>2).sum()}</h3><p>Fora SLA</p></div>", True)
st.markdown("---")

# ───────────── Grade ─────────────
st.subheader("📄 Chamados")

grid_cols = [
    "id", "tipo_ticket", "status",
    "solicitante_nome", "responsavel_nome",
    "data_abertura", "canal_id", "thread_ts",
]
df_grid = df.reindex(columns=grid_cols)

gb = GridOptionsBuilder.from_dataframe(df_grid)
gb.configure_pagination()
gb.configure_default_column(resizable=True, filter=True, sortable=True)
gb.configure_column("canal_id", hide=True)
gb.configure_column("thread_ts", hide=True)
gb.configure_selection("single")

sel_result = AgGrid(
    df_grid,
    gridOptions=gb.build(),
    update_mode=GridUpdateMode.SELECTION_CHANGED,
    height=300,
    theme="streamlit",
    fit_columns_on_grid_load=True,
).get("selected_rows", [])

# ─── Detalhes + Thread ───
if isinstance(sel_result, list) and len(sel_result) > 0 and isinstance(sel_result[0], dict):
    r = sel_result[0]
    st.markdown(f"### 📝 Detalhes OS {safe_get(r, 'id')}")

    try:
        abertura_fmt = pd.to_datetime(safe_get(r, "data_abertura")).strftime("%d/%m/%Y %H:%M")
    except Exception:
        abertura_fmt = "-"

    st.write(f"""**Tipo:** {safe_get(r,'tipo_ticket')}
**Status:** {safe_get(r,'status')}
**Solicitante:** {safe_get(r,'solicitante_nome')}
**Responsável:** {safe_get(r,'responsavel_nome')}
**Abertura:** {abertura_fmt}""")

    # POP-UP (expander) com a thread
    with st.expander("💬 Ver Thread Slack"):
        canal = str(safe_get(r, "canal_id"))
        ts    = str(safe_get(r, "thread_ts"))
        if canal and ts and ts.replace(".", "", 1).isdigit():
            msgs = fetch_thread(canal, ts)
            if msgs:
                st.success(f"{len(msgs)} mensagens na thread")
                for m in msgs:
                    ts_msg = pd.to_datetime(float(m["ts"]), unit="s")
                    user = get_nome_real(m.get("user", ""))
                    txt  = m.get("text", "")
                    pin  = "📌 " if m["ts"] == ts else ""
                    bg   = "#E3F2FD" if pin else "#fff"
                    st.markdown(
                        f"<div style='background:{bg};padding:6px;border-left:3px solid #2196F3;'>"
                        f"<strong>{pin}{user}</strong> "
                        f"<span style='color:#555;'>_{ts_msg:%d/%m %H:%M}_</span><br>{txt}</div>",
                        unsafe_allow_html=True,
                    )
            else:
                st.warning("⚠️ Nenhuma mensagem encontrada ou canal inválido.")
        else:
            st.error("❌ Canal ou thread inválidos.")
else:
    st.info("📌 Selecione um chamado para visualizar os detalhes.")

# ─── Gráficos ───
st.subheader("📊 Distribuição e Fechamento")
g1, g2 = st.columns(2)

with g1:
    fig, ax = plt.subplots(figsize=(4, 2))
    df["tipo_ticket"].value_counts().plot.bar(ax=ax, color="#3E84F4", width=0.5)
    ax.set_ylabel("Qtd", fontsize=8)
    ax.set_title("Por Tipo de Ticket", fontsize=9)
    ax.tick_params(axis="x", labelrotation=25, labelsize=7)
    ax.tick_params(axis="y", labelsize=7)
    ax.spines[['top','right','left','bottom']].set_visible(False)
    st.pyplot(fig)

with g2:
    fech = df[df["data_fechamento"].notna()]
    st.metric("🗓️ Tempo médio de fechamento",
              f"{fech['dias_para_fechamento'].mean():.1f} dias" if not fech.empty else "-")
    if not fech.empty:
        fig2, ax2 = plt.subplots(figsize=(4, 2))
        fech["dias_para_fechamento"].hist(ax=ax2, bins=6, color="#34A853")
        ax2.set_xlabel("Dias", fontsize=8)
        ax2.set_ylabel("Chamados", fontsize=8)
        ax2.set_title("Dias até Fechamento", fontsize=9)
        ax2.tick_params(axis="both", labelsize=7)
        ax2.spines[['top','right','left','bottom']].set_visible(False)
        st.pyplot(fig2)

# ─── Alterações / Export ───
st.markdown("## 🔄 Alterações (edições + reaberturas)")
if df_alt.empty:
    st.info("Não há alterações para o filtro atual.")
else:
    vis = df_alt.rename(columns={"id": "OS", "quando": "Data", "quem": "Usuário"})
    a, b = st.columns([2,1])

    with a:
        st.dataframe(vis, use_container_width=True)

    with b:
        top = (
            vis["Usuário"]
            .value_counts()
            .head(10)
            .rename_axis("Usuário")
            .reset_index(name="Qtd")
        )
        fig3, ax3 = plt.subplots(figsize=(4, 2))
        top.plot.barh(x="Usuário", y="Qtd", ax=ax3, color="#FF7043")
        ax3.invert_yaxis()
        ax3.set_xlabel("Alterações", fontsize=8)
        ax3.set_title("Top Alteradores", fontsize=9)
        ax3.tick_params(axis="both", labelsize=7)
        ax3.spines[['top','right','left','bottom']].set_visible(False)
        st.pyplot(fig3)

# Exportações
st.subheader("📦 Exportar")
csv_main = df.to_csv(index=False).encode()
csv_alt  = df_alt.to_csv(index=False).encode()

c_csv, c_xlsx, a_csv, a_xlsx = st.columns(4)

c_csv.download_button("⬇️ Chamados CSV", csv_main, "chamados.csv", "text/csv")

buf = io.BytesIO(); df.to_excel(buf, index=False, engine="xlsxwriter")
c_xlsx.download_button("📊 Chamados XLSX", buf.getvalue(), "chamados.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

a_csv.download_button("⬇️ Alterações CSV", csv_alt, "alteracoes.csv", "text/csv")

buf2 = io.BytesIO(); df_alt.to_excel(buf2, index=False, engine="xlsxwriter")
a_xlsx.download_button("📊 Alterações XLSX", buf2.getvalue(), "alteracoes.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
