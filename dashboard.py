# dashboard.py  •  Painel JFL Comercial
# -------------------------------------------------------------
# Executar local:  streamlit run dashboard.py
# -------------------------------------------------------------
from dotenv import load_dotenv
load_dotenv()

import os, io, re, json
import pandas as pd
import streamlit as st
import matplotlib.pyplot as plt
from sqlalchemy import create_engine               # para conexão segura
from utils.slack import get_nome_real              # helper de nomes reais
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode

# -------------------------------------------------------------
# CONFIG STREAMLIT  +  SLACK CLIENT
# -------------------------------------------------------------
st.set_page_config(page_title="Painel JFL", layout="wide")
slack_client = WebClient(token=os.getenv("SLACK_BOT_TOKEN"))

# -------------------------------------------------------------
# CSS RÁPIDO (cards, títulos…)
# -------------------------------------------------------------
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

# -------------------------------------------------------------
# HELPERS
# -------------------------------------------------------------

def parse_reaberturas(txt: str, os_id: int, resp_nome: str, data_abertura):
    """Extrai linhas “[YYYY-MM-DD] Fulano …” em dicionários."""
    if not txt:
        return []

    pat = re.compile(r"\[(\d{4}-\d{2}-\d{2})]\s+(.+?)\s+(.*)")
    regs = []
    for linha in filter(None, (l.strip() for l in txt.splitlines())):
        m = pat.match(linha)
        if m:
            data, quem, desc = m.groups()
            regs.append(
                {
                    "id": os_id,
                    "quando": pd.to_datetime(data, errors="coerce"),
                    "quem": quem,
                    "descricao": desc,
                    "campo": "reabertura",
                    "de": "-",
                    "para": "-",
                    "responsavel_nome": resp_nome,
                    "data_abertura": data_abertura,
                }
            )
    return regs


def fetch_thread(channel_id: str, thread_ts: str) -> list[dict]:
    """Baixa as mensagens de uma thread do Slack (ordem cronológica)."""
    try:
        resp = slack_client.conversations_replies(channel=channel_id, ts=thread_ts, limit=200)
        return resp["messages"][::-1]      # inverte → cronológica
    except SlackApiError as e:
        st.error(f"Erro Slack: {e.response['error']}")
        return []

# -------------------------------------------------------------
# LOAD DATA (com cache)
# -------------------------------------------------------------

@st.cache_data(show_spinner=False)
def carregar_dados() -> tuple[pd.DataFrame, pd.DataFrame]:
    url = os.getenv("DATA_PUBLIC_URL")
    if not url:
        st.error("❌ Variável DATA_PUBLIC_URL não definida.")
        return pd.DataFrame(), pd.DataFrame()

    try:
        engine = create_engine(url, connect_args={"sslmode": "require"})
        with engine.connect() as conn:  # ← aqui é a correção
            df = pd.read_sql("SELECT * FROM ordens_servico", conn)
    except Exception as e:
        st.error(f"❌ Erro ao ler o banco: {e}")
        return pd.DataFrame(), pd.DataFrame()

    if df.empty:
        return df, pd.DataFrame()

    obrigatorias = [
        "responsavel", "solicitante", "capturado_por",
        "data_abertura", "data_fechamento",
        "log_edicoes", "historico_reaberturas", "status",
        "data_ultima_edicao", "ultimo_editor",
    ]
    for col in obrigatorias:
        if col not in df.columns:
            df[col] = None

    # nomes + datas + SLA
    df["responsavel_nome"] = df["responsavel"].apply(get_nome_real)
    df["solicitante_nome"] = df["solicitante"].apply(get_nome_real)
    df["capturado_nome"]  = df["capturado_por"].apply(get_nome_real)

    df["data_abertura"]   = pd.to_datetime(df["data_abertura"], errors="coerce")
    df["data_fechamento"] = pd.to_datetime(df["data_fechamento"], errors="coerce")
    df["dias_para_fechamento"] = (df["data_fechamento"] - df["data_abertura"]).dt.days

    # ---- df_alt  (edições + reaberturas) ----
    regs: list[dict] = []
    for _, r in df.iterrows():
        # edições
        if r["log_edicoes"] not in (None, "", "null"):
            try:
                log = json.loads(r["log_edicoes"])
                for campo, mud in log.items():
                    regs.append(
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
        regs += parse_reaberturas(
            r.get("historico_reaberturas"), r["id"], r["responsavel_nome"], r["data_abertura"]
        )

    df_alt = pd.DataFrame(regs)
    if not df_alt.empty and "quando" in df_alt.columns:
        df_alt = df_alt.sort_values("quando", ascending=False)

    return df, df_alt

# -------------------------------------------------------------
# 🔄 FLUXO PRINCIPAL
# -------------------------------------------------------------

df, df_alt = carregar_dados()
if df.empty:
    st.info("📭 Nenhum chamado encontrado.")
    st.stop()

# ---- SIDEBAR / FILTROS -------------------------------------
st.sidebar.markdown("## 🎛️ Filtros")

valid_dates = df["data_abertura"].dropna()
min_d, max_d = valid_dates.min().date(), valid_dates.max().date()
ini, fim = st.sidebar.date_input("🗓️ Período:", [min_d, max_d])

mask_main = df["data_abertura"].dt.date.between(ini, fim)
df = df[mask_main]
if not df_alt.empty:
    df_alt = df_alt[df_alt["data_abertura"].dt.date.between(ini, fim)]

responsaveis = sorted(df["responsavel_nome"].dropna().unique())
sel_resp = st.sidebar.multiselect("🧑‍💼 Responsável:", responsaveis)
if sel_resp:
    df = df[df["responsavel_nome"].isin(sel_resp)]
    if not df_alt.empty:
        df_alt = df_alt[df_alt["responsavel_nome"].isin(sel_resp)]

# ---- MÉTRICAS ------------------------------------------------
c1, c2, c3, c4, c5 = st.columns(5)
c1.markdown(f"<div class='card'><h3>{len(df)}</h3><p>Total</p></div>", True)
c2.markdown(
    f"<div class='card'><h3>{df['status'].isin(['aberto','em analise']).sum()}</h3><p>Em Atendimento</p></div>",
    True,
)
c3.markdown(f"<div class='card'><h3>{df['data_fechamento'].notna().sum()}</h3><p>Finalizados</p></div>", True)
c4.markdown(f"<div class='card'><h3>{(df['dias_para_fechamento']<=2).sum()}</h3><p>Dentro SLA</p></div>", True)
c5.markdown(f"<div class='card'><h3>{(df['dias_para_fechamento']>2).sum()}</h3><p>Fora SLA</p></div>", True)

st.markdown("---")

# -------------------------------------------------------------
# 📄 GRADE DE CHAMADOS + THREAD ▸ colocar DEPOIS das métricas
# -------------------------------------------------------------
st.subheader("📄 Chamados (clique em uma linha)")

cols_grade = [
    "id", "tipo_ticket", "status",
    "solicitante_nome", "responsavel_nome",
    "data_abertura",
    "canal_id",   # ocultos na grade mas úteis
    "thread_ts"
]

gb = GridOptionsBuilder.from_dataframe(df[cols_grade])
gb.configure_pagination()
gb.configure_default_column(resizable=True, filter=True, sortable=True)
gb.configure_column("canal_id", hide=True)
gb.configure_column("thread_ts", hide=True)
gb.configure_selection("single")
grid_resp = AgGrid(
        df,
        gridOptions=gb.build(),
        update_mode=GridUpdateMode.SELECTION_CHANGED,
        height=300,
        theme="streamlit",
        fit_columns_on_grid_load=True)

sel = grid_resp["selected_rows"]

if sel:
    r = sel[0]
    os_id     = r["id"]
    canal_id  = r.get("canal_id")
    thread_ts = r.get("thread_ts")

    st.markdown(f"### 📝 Detalhes OS {os_id}")
    st.write(f"""
    **Tipo:** {r.get('tipo_ticket','')}  •  **Status:** {r.get('status','')}
    **Solicitante:** {r.get('solicitante_nome','')}
    **Responsável:** {r.get('responsavel_nome','')}
    **Abertura:** {pd.to_datetime(r['data_abertura']).strftime('%d/%m/%Y %H:%M')}
    """)

    # ------- Botão de ver thread -------
    if st.button("💬 Ver thread Slack", key=f"btn_thread_{os_id}"):
        if canal_id and thread_ts:
            msgs = fetch_thread(canal_id, thread_ts)
            if msgs:
                st.success(f"{len(msgs)} mensagens encontradas")
                st.markdown("---")
                for m in msgs:
                    ts   = pd.to_datetime(float(m["ts"]), unit="s")
                    user = get_nome_real(m.get("user", ""))
                    txt  = m.get("text", "")
                    pin  = "📌 " if m["ts"] == thread_ts else ""
                    bg   = "#E3F2FD" if pin else "#FFFFFF"
                    st.markdown(
                        f"<div style='background:{bg};padding:6px;border-left:3px solid #2196F3;'>"
                        f"<strong>{pin}{user}</strong> "
                        f"<span style='color:#555;'>_{ts:%d/%m %H:%M}_</span><br>{txt}</div>",
                        unsafe_allow_html=True)
            else:
                st.info("Nenhuma mensagem encontrada.")
        else:
            st.warning("Sem canal/thread cadastrados para esta OS.")

# ---- GRÁFICOS ----------------------------------------------
st.subheader("📊 Distribuição e Fechamento")

g1, g2 = st.columns(2)

with g1:
    if "tipo_ticket" in df.columns and not df.empty:
        fig, ax = plt.subplots(figsize=(4, 2))
        df["tipo_ticket"].value_counts().plot.bar(ax=ax, color="#3E84F4", width=0.5)
        ax.set_ylabel("Qtd", fontsize=8)
        ax.set_title("Por Tipo de Ticket", fontsize=9)
        ax.tick_params(axis="x", labelrotation=25, labelsize=7)
        ax.tick_params(axis="y", labelsize=7)
        for s in ax.spines.values():
            s.set_visible(False)
        st.pyplot(fig)

with g2:
    fech = df[df["data_fechamento"].notna()]
    st.metric(
        "🗓️ Tempo médio de fechamento",
        f"{fech['dias_para_fechamento'].mean():.1f} dias" if not fech.empty else "-",
    )
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

# -------------------------------------------------------------
# 🔄 ALTERAÇÕES
# -------------------------------------------------------------
st.markdown("## 🔄 Alterações (edições + reaberturas)")
if df_alt.empty:
    st.info("Não há alterações para o filtro atual.")
else:
    vis = df_alt[["id", "quando", "quem", "descricao"]].rename(
        columns={"id": "OS", "quando": "Data", "quem": "Usuário", "descricao": "Alteração"}
    )
    st.dataframe(vis, use_container_width=True)

    top = df_alt["quem"].value_counts().head(10).rename_axis("Usuário").reset_index(name="Qtd")
    fig3, ax3 = plt.subplots(figsize=(4, 2))
    top.plot.barh(x="Usuário", y="Qtd", ax=ax3, color="#FF7043")
    ax3.invert_yaxis()
    ax3.set_xlabel("Alterações", fontsize=8)
    ax3.set_title("Top Alteradores", fontsize=9)
    ax3.tick_params(axis="both", labelsize=7)
    for s in ax3.spines.values():
        s.set_visible(False)
    st.pyplot(fig3)

# -------------------------------------------------------------
# 📦 EXPORTAR
# -------------------------------------------------------------
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
