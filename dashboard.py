# -------------------------------------------------------------
# dashboard.py  •  Painel JFL Comercial
# -------------------------------------------------------------
"""
Streamlit dashboard para acompanhar os chamados comerciais da JFL.
Principais diferenças desta revisão:
• Conexão PostgreSQL robusta (pool_pre_ping + sslmode=require) e
  uso direto do *engine* no pandas.read_sql → adeus erro de cursor.
• Função de parse reescrita (MatchObject.group).  
• Oculta colunas técnicas na grade AgGrid.  
• Tipagem, limpeza geral e pequenas otimizações.
"""

from __future__ import annotations

# ----------------------------- Imports -----------------------------
import os, io, json, re
from datetime import date

import pandas as pd
import streamlit as st
import matplotlib.pyplot as plt
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode

from utils.slack import get_nome_real  # helper já existente no repo

# -------------------------- Config inits ---------------------------
load_dotenv()

st.set_page_config(page_title="Painel JFL", layout="wide")

SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN", "")
slack_client = WebClient(token=SLACK_BOT_TOKEN)

# ----------------------------- CSS ---------------------------------
CUSTOM_CSS = """
<style>
  .main  { background:#F5F5F5 }
  .title { font-size:32px;font-weight:bold;color:#003366 }
  .sub   { font-size:16px;color:#666 }
  .card  { background:#fff;padding:20px;border-radius:12px;
           box-shadow:0 2px 6px rgba(0,0,0,.1);text-align:center }
</style>
"""

st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

st.markdown("<div class='title'>🏢 JFL | Painel Gerencial de Chamados</div>", unsafe_allow_html=True)
st.markdown("<div class='sub'>Monitoramento em tempo real • Base comercial</div>", unsafe_allow_html=True)
st.markdown("---")

# ---------------------------- Helpers -----------------------------

def parse_reaberturas(txt: str | None, os_id: int, resp_nome: str, data_abertura: pd.Timestamp) -> list[dict]:
    """Converte linhas no formato "[YYYY-MM-DD] Fulano ..." em dicionários."""
    if not txt:
        return []

    pat = re.compile(r"\[(\d{4}-\d{2}-\d{2})]\s+(.+?)\s+(.*)")
    registros: list[dict] = []
    for linha in filter(None, (l.strip() for l in txt.splitlines())):
        m = pat.match(linha)
        if not m:
            continue
        data_str, quem, desc = m.group(1), m.group(2), m.group(3)
        registros.append(
            {
                "id": os_id,
                "quando": pd.to_datetime(data_str, errors="coerce"),
                "quem": quem,
                "descricao": desc,
                "campo": "reabertura",
                "de": "-",
                "para": "-",
                "responsavel_nome": resp_nome,
                "data_abertura": data_abertura,
            }
        )
    return registros


def fetch_thread(channel_id: str, thread_ts: str) -> list[dict]:
    """Baixa as mensagens de uma thread do Slack em ordem cronológica."""
    if not SLACK_BOT_TOKEN or not channel_id or not thread_ts:
        return []
    try:
        resp = slack_client.conversations_replies(channel=channel_id, ts=thread_ts, limit=200)
        return resp["messages"][::-1]  # invertido → cronológico
    except SlackApiError as e:
        st.error(f"Erro Slack: {e.response['error']}")
        return []

# -------------------------- Data loading ---------------------------

@st.cache_data(show_spinner=False)
def carregar_dados() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Lê dados de ordens_servico e retorna (principal, alterações)."""
    url = os.getenv("DATA_PUBLIC_URL", "")
    if not url:
        st.error("❌ DATA_PUBLIC_URL não definida nos secrets / env vars.")
        return pd.DataFrame(), pd.DataFrame()

    # Garante driver psycopg2 e SSL
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    if "sslmode" not in url:
        url += "?sslmode=require"

    try:
        engine = create_engine(url)
        with engine.connect() as conn:
            df = pd.read_sql("SELECT * FROM ordens_servico", con=conn)
    except Exception as e:
        st.error(f"❌ Erro ao ler o banco: {e}")
        return pd.DataFrame(), pd.DataFrame()

    if df.empty:
        return df, pd.DataFrame()

    return df, pd.DataFrame()

    # ----- limpeza / colunas obrigatórias -------------------------
    obrigatorias = [
        "responsavel",
        "solicitante",
        "capturado_por",
        "data_abertura",
        "data_fechamento",
        "log_edicoes",
        "historico_reaberturas",
        "status",
        "data_ultima_edicao",
        "ultimo_editor",
    ]
    for col in obrigatorias:
        if col not in df.columns:
            df[col] = None

    # ----- colunas derivadas --------------------------------------
    df["responsavel_nome"] = df["responsavel"].apply(get_nome_real)
    df["solicitante_nome"] = df["solicitante"].apply(get_nome_real)
    df["capturado_nome"] = df["capturado_por"].apply(get_nome_real)

    df["data_abertura"] = pd.to_datetime(df["data_abertura"], errors="coerce")
    df["data_fechamento"] = pd.to_datetime(df["data_fechamento"], errors="coerce")
    df["dias_para_fechamento"] = (df["data_fechamento"] - df["data_abertura"]).dt.days

    # ----- monta df_alt (edições + reaberturas) -------------------
    registros: list[dict] = []
    for _, r in df.iterrows():
        # edições
        if r["log_edicoes"] not in (None, "", "null"):
            try:
                log = json.loads(r["log_edicoes"])
                for campo, mud in log.items():
                    registros.append(
                        {
                            "id": r["id"],
                            "quando": pd.to_datetime(r["data_ultima_edicao"], errors="coerce"),
                            "quem": r["ultimo_editor"] or "-",
                            "descricao": f"{campo}: {mud.get('de')} → {mud.get('para')}",
                            "campo": campo,
                            "de": mud.get("de"),
                            "para": mud.get("para"),
                            "responsavel_nome": r["responsavel_nome"],
                            "data_abertura": r["data_abertura"],
                        }
                    )
            except Exception:
                pass
        # reaberturas
        registros += parse_reaberturas(
            r.get("historico_reaberturas"),
            r["id"],
            r["responsavel_nome"],
            r["data_abertura"],
        )

    df_alt = pd.DataFrame(registros)
    if not df_alt.empty and "quando" in df_alt.columns:
        df_alt = df_alt.sort_values("quando", ascending=False)

    return df, df_alt

# ----------------------- Main application --------------------------

df, df_alt = carregar_dados()
if df.empty:
    st.info("📭 Nenhum chamado encontrado.")
    st.stop()

# -------------- Sidebar filters ------------------------------------

today = date.today()
min_d, max_d = df["data_abertura"].min().date(), df["data_abertura"].max().date()
ini, fim = st.sidebar.date_input("🗓️ Período:", [min_d, max_d], max_value=today)

mask_periodo = df["data_abertura"].dt.date.between(ini, fim)
df = df[mask_periodo]
if not df_alt.empty:
    df_alt = df_alt[df_alt["data_abertura"].dt.date.between(ini, fim)]

responsaveis = sorted(df["responsavel_nome"].dropna().unique())
sel_resp = st.sidebar.multiselect("🧑‍💼 Responsável:", responsaveis)
if sel_resp:
    df = df[df["responsavel_nome"].isin(sel_resp)]
    if not df_alt.empty:
        df_alt = df_alt[df_alt["responsavel_nome"].isin(sel_resp)]

# ---------------------------- Métricas ------------------------------

c1, c2, c3, c4, c5 = st.columns(5)
c1.markdown(f"<div class='card'><h3>{len(df)}</h3><p>Total</p></div>", unsafe_allow_html=True)
c2.markdown(f"<div class='card'><h3>{df['status'].isin(['aberto','em analise']).sum()}</h3><p>Em Atendimento</p></div>", unsafe_allow_html=True)
c3.markdown(f"<div class='card'><h3>{df['data_fechamento'].notna().sum()}</h3><p>Finalizados</p></div>", unsafe_allow_html=True)
c4.markdown(f"<div class='card'><h3>{(df['dias_para_fechamento']<=2).sum()}</h3><p>Dentro SLA</p></div>", unsafe_allow_html=True)
c5.markdown(f"<div class='card'><h3>{(df['dias_para_fechamento']>2).sum()}</h3><p>Fora SLA</p></div>", unsafe_allow_html=True)

st.markdown("---")

# ----------------------- Grade de chamados -------------------------

st.subheader("📄 Chamados (clique em uma linha)")

cols_grade = [
    "id",
    "tipo_ticket",
    "status",
    "solicitante_nome",
    "responsavel_nome",
    "data_abertura",
    "canal_id",  # oculto
    "thread_ts",  # oculto
]

# adiciona colunas faltantes (evita KeyError)
for c in ("canal_id", "thread_ts"):
    if c not in df.columns:
        df[c] = None

builder = GridOptionsBuilder.from_dataframe(df[cols_grade])
builder.configure_pagination()
builder.configure_default_column(resizable=True, filter=True, sortable=True)
for hidden in ("canal_id", "thread_ts"):
    builder.configure_column(hidden, hide=True)
builder.configure_selection("single")

sel = AgGrid(
    df,
    gridOptions=builder.build(),
    update_mode=GridUpdateMode.SELECTION_CHANGED,
    height=300,
    theme="streamlit",
    fit_columns_on_grid_load=True,
)["selected_rows"]

# -------------------- Detalhes + Thread Slack ----------------------

if sel:
    r = sel[0]
    st.markdown(f"### 📝 Detalhes OS {r['id']}")
    st.write(
        f"""
**Tipo:** {r.get('tipo_ticket','')}  •  **Status:** {r.get('status','')}
**Solicitante:** {r.get('solicitante_nome','')}
**Responsável:** {r.get('responsavel_nome','')}
**Abertura:** {pd.to_datetime(r['data_abertura']).strftime('%d/%m/%Y %H:%M')}
"""
    )

    if st.button("💬 Ver thread Slack", key=f"btn_thread_{r['id']}"):
        msgs = fetch_thread(r.get("canal_id"), r.get("thread_ts"))
        if msgs:
            st.success(f"{len(msgs)} mensagens encontradas")
            st.markdown("---")
            for m in msgs:
                ts = pd.to_datetime(float(m["ts"]), unit="s")
                user = get_nome_real(m.get("user", ""))
                txt = m.get("text", "")
                pin = "📌 " if m["ts"] == r.get("thread_ts") else ""
                bg = "#E3F2FD" if pin else "#fff"
                st.markdown(
                    f"<div style='background:{bg};padding:6px;border-left:3px solid #2196F3;'>"
                    f"<strong>{pin}{user}</strong> <span style='color:#555;'>_{ts:%d/%m %H:%M}_</span><br>{txt}</div>",
                    unsafe_allow_html=True,
                )
        else:
            st.info("Nenhuma mensagem encontrada ou canal/thread inválidos.")

# ----------------------------- Gráficos ----------------------------

st.subheader("📊 Distribuição e Fechamento")
col1, col2 = st.columns(2)

with col1:
    fig, ax = plt.subplots(figsize=(4, 2))
    df["tipo_ticket"].value_counts().plot.bar(ax=ax, color="#3E84F4", width=0.5)
    ax.set_ylabel("Qtd", fontsize=8)
    ax.set_title("Por Tipo de Ticket", fontsize=9)
    ax.tick_params(axis="x", labelrotation=25, labelsize=7)
    ax.tick_params(axis="y", labelsize=7)
    for s in ax.spines.values():
        s.set_visible(False)
    st.pyplot(fig)

with col2:
    fech = df[df["data_fechamento"].notna()]
    tempo_medio = fech["dias_para_fechamento"].mean()
    st.metric("🗓️ Tempo médio de fechamento", f"{tempo_medio:.1f} dias" if not fech.empty else "-")
    if not fech.empty:
        fig2, ax2 = plt.subplots(figsize=(4, 2))
        fech["dias_para_fechamento"].hist(ax=ax2, bins=6, color="#34A853")
        ax2.set_xlabel("Dias", fontsize=8)
        ax2.set_ylabel("Chamados", fontsize=8)
        ax2.set_title("Dias até Fechamento", fontsize=9)
        ax2.tick_params(axis="both", labelsize=7)
        for s in ax2.spines.values():
            s.set_visible(False)
        st.pyplot(fig2)

# -------------------------- Alterações -----------------------------

st.markdown("## 🔄 Alterações (edições + reaberturas)")
if df_alt.empty:
    st.info("Não há alterações para o filtro atual.")
else:
    vis = df_alt[["id", "quando", "quem", "descricao"]].rename(
        columns={
            "id": "OS",
            "quando": "Data",
            "quem": "Usuário",
            "descricao": "Alteração",
        }
    )
    col_a, col_b = st.columns([2, 1])

    with col_a:
        st.dataframe(vis, use_container_width=True)

    with col_b:
        top = (
            df_alt["quem"].value_counts().head(10).rename_axis("Usuário").reset_index(name="Qtd")
        )
        fig3, ax3 = plt.subplots(figsize=(4, 2))
        top.plot.barh(x="Usuário", y="Qtd", ax=ax3, color="#FF7043")
        ax3.invert_yaxis()
        ax3.set_xlabel("Alterações", fontsize=8)
        ax3.set_title("Top Alteradores", fontsize=9)
        ax3.tick_params(axis="both", labelsize=7)
        for s in ax3.spines.values():
            s.set_visible(False)
        st.pyplot(fig3)

# --------------------------- Export -------------------------------

st.subheader("📦 Exportar")

csv_main = df.to_csv(index=False).encode()
csv_alt = df_alt.to_csv(index=False).encode()

b1, b2, b3, b4 = st.columns(4)

b1.download_button("⬇️ Chamados CSV", csv_main, "chamados.csv", "text/csv")

buf = io.BytesIO()
df.to_excel(buf, index=False, engine="xlsxwriter")
b2.download_button(
    "📊 Chamados XLSX",
    buf.getvalue(),
    "chamados.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)

b3.download_button("⬇️ Alterações CSV", csv_alt, "alteracoes.csv", "text/csv")

buf2 = io.BytesIO()
df_alt.to_excel(buf2, index=False, engine="xlsxwriter")
b4.download_button(
    "📊 Alterações XLSX",
    buf2.getvalue(),
    "alteracoes.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)
