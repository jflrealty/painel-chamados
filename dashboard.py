import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import io, json, os
from utils.slack import get_nome_real
from sqlalchemy import create_engine

st.set_page_config(page_title="Painel JFL", layout="wide")

# ---------- ESTILO ----------
st.markdown(
    """
    <style>
        .main { background-color: #F5F5F5; }
        .title { font-size: 32px; font-weight: bold; color: #003366; }
        .sub { font-size: 16px; color: #666666; }
        .card {
            background-color: white;
            padding: 20px;
            border-radius: 12px;
            box-shadow: 0 2px 6px rgba(0,0,0,0.1);
            text-align: center;
        }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown("<div class='title'>🏢 JFL | Painel Gerencial de Chamados</div>", unsafe_allow_html=True)
st.markdown("<div class='sub'>Monitoramento em tempo real • Base comercial</div>", unsafe_allow_html=True)
st.markdown("---")

# ---------- LOAD DATA ----------
@st.cache_data
def carregar_dados():
    url = os.getenv("DATA_PUBLIC_URL")
    if not url:
        st.error("❌ Variável DATA_PUBLIC_URL não encontrada.")
        return pd.DataFrame(), pd.DataFrame()

    try:
        engine = create_engine(url, connect_args={"sslmode": "require"})
        with engine.connect() as conn:
            df = pd.read_sql("SELECT * FROM ordens_servico", con=conn)
    except Exception as e:
        st.error(f"❌ Erro ao ler dados do banco: {e}")
        return pd.DataFrame(), pd.DataFrame()

    if df.empty:
        return df, pd.DataFrame()

    # Proteção para colunas ausentes
    for col in ["responsavel", "solicitante", "capturado_por", "data_abertura", "data_fechamento", "log_edicoes"]:
        if col not in df.columns:
            df[col] = None

    # Aplicar nomes reais
    df["responsavel_nome"] = df["responsavel"].apply(get_nome_real)
    df["solicitante_nome"] = df["solicitante"].apply(get_nome_real)
    df["capturado_nome"]  = df["capturado_por"].apply(get_nome_real)

    # Datas e SLA
    df["data_abertura"]   = pd.to_datetime(df["data_abertura"],  errors="coerce")
    df["data_fechamento"] = pd.to_datetime(df["data_fechamento"], errors="coerce")
    df["dias_para_fechamento"] = (df["data_fechamento"] - df["data_abertura"]).dt.days

    # Processar log_edicoes
    registros = []
    for _, row in df.iterrows():
        if row.get("log_edicoes") not in [None, "", "null"]:
            try:
                log = json.loads(row["log_edicoes"])
                for campo, mudanca in log.items():
                    registros.append({
                        "id": row.get("id"),
                        "campo": campo,
                        "de": str(mudanca.get("de")),
                        "para": str(mudanca.get("para")),
                        "responsavel_nome": row.get("responsavel_nome", ""),
                        "data_abertura": row.get("data_abertura"),
                    })
            except Exception as e:
                print("Erro ao processar log_edicoes:", e)

    df_alt = pd.DataFrame(registros)
    return df, df_alt

# ===== CHAMAR E VERIFICAR DADOS =====
df, df_alt = carregar_dados()

if df.empty:
    st.warning("📭 Nenhum dado encontrado. Verifique a conexão ou os filtros aplicados.")
    st.stop()
    
# ---------- SIDEBAR FILTERS ----------
if not df.empty:
    st.sidebar.markdown("## 🎛️ Filtros")

    min_d, max_d = df["data_abertura"].min(), df["data_abertura"].max()
    d_ini, d_fim = st.sidebar.date_input("🗓️ Intervalo de abertura:", [min_d, max_d])
    if d_ini and d_fim:
        df = df[df["data_abertura"].between(pd.to_datetime(d_ini), pd.to_datetime(d_fim))]
        if not df_alt.empty and "data_abertura" in df_alt.columns:
            df_alt = df_alt[df_alt["data_abertura"].between(pd.to_datetime(d_ini), pd.to_datetime(d_fim))]

    resp_opts = sorted(df["responsavel_nome"].dropna().unique())
    resp_sel = st.sidebar.multiselect("🧝 Responsável:", resp_opts)
    if resp_sel:
        df = df[df["responsavel_nome"].isin(resp_sel)]
        if not df_alt.empty and "responsavel_nome" in df_alt.columns:
            df_alt = df_alt[df_alt["responsavel_nome"].isin(resp_sel)]

    if not df_alt.empty and "campo" in df_alt.columns:
        campo_opts = sorted(df_alt["campo"].unique())
        campo_sel = st.sidebar.multiselect("📝 Campo alterado:", campo_opts)
        if campo_sel:
            df_alt = df_alt[df_alt["campo"].isin(campo_sel)]

# ---------- METRIC CARDS ----------
col1, col2, col3, col4, col5 = st.columns(5)
col1.markdown(f"<div class='card'><h3>{len(df)}</h3><p>Total de Chamados</p></div>", unsafe_allow_html=True)
em_analise = len(df[df["status"].isin(["aberto", "em analise"])]) if "status" in df.columns else 0
col2.markdown(f"<div class='card'><h3>{em_analise}</h3><p>Em Atendimento</p></div>", unsafe_allow_html=True)
finalizados = len(df[df["data_fechamento"].notna()]) if "data_fechamento" in df.columns else 0
col3.markdown(f"<div class='card'><h3>{finalizados}</h3><p>Finalizados</p></div>", unsafe_allow_html=True)
sla_ok = len(df[df["dias_para_fechamento"] <= 2]) if "dias_para_fechamento" in df.columns else 0
col4.markdown(f"<div class='card'><h3>{sla_ok}</h3><p>Dentro do SLA</p></div>", unsafe_allow_html=True)
sla_nok = len(df[df["dias_para_fechamento"] > 2]) if "dias_para_fechamento" in df.columns else 0
col5.markdown(f"<div class='card'><h3>{sla_nok}</h3><p>Fora do SLA</p></div>", unsafe_allow_html=True)

st.markdown("---")

# ---------- CHARTS ----------
st.subheader("📊 Distribuição de Chamados")
if "tipo_ticket" in df.columns and not df.empty:
    fig1, ax1 = plt.subplots(figsize=(6,3))
    df["tipo_ticket"].value_counts().plot.bar(color="#3E84F4", ax=ax1)
    ax1.set_title("Chamados por Tipo de Ticket")
    ax1.set_ylabel("Quantidade")
    st.pyplot(fig1)

fechados = df[df["data_fechamento"].notna()]
tempo_medio = fechados["dias_para_fechamento"].mean()
st.metric("🗓️ Tempo médio de fechamento", f"{tempo_medio:.1f} dias" if pd.notna(tempo_medio) else "-")

if not fechados.empty:
    fig2, ax2 = plt.subplots(figsize=(6,3))
    fechados["dias_para_fechamento"].hist(bins=10, color="#34A853", ax=ax2)
    ax2.set_title("Distribuição dos Dias para Fechamento")
    ax2.set_xlabel("Dias")
    ax2.set_ylabel("Chamados")
    st.pyplot(fig2)

# ---------- ALTERAÇÕES ----------
st.markdown("## 🔄 Alterações nos Chamados")
if df_alt.empty:
    st.info("📭 Nenhuma alteração encontrada com os filtros atuais.")
else:
    st.dataframe(df_alt, use_container_width=True)

    top_alt = (
        df_alt.groupby(["campo", "de", "para"])
              .size()
              .reset_index(name="qtd")
              .sort_values("qtd", ascending=False)
    )

    st.markdown("### 📊 Top alterações")
    fig3, ax3 = plt.subplots(figsize=(8,4))
    top_alt.head(10).plot(kind="bar", x="para", y="qtd", color="#FF7043", ax=ax3)
    ax3.set_xlabel("Para")
    ax3.set_ylabel("Quantidade")
    ax3.set_title("Top 10 alterações (campo/de → para)")
    st.pyplot(fig3)

# ---------- EXPORT ----------
st.subheader("📄 Exportar dados filtrados")

csv_main  = df.to_csv(index=False).encode("utf-8")
csv_alt   = df_alt.to_csv(index=False).encode("utf-8")

c1, c2, c3, c4 = st.columns(4)
c1.download_button("⬇️ Chamados (CSV)", csv_main, "chamados.csv", "text/csv")

excel_buf = io.BytesIO()
df.to_excel(excel_buf, index=False, engine="xlsxwriter")
c2.download_button("📊 Chamados (XLSX)", excel_buf.getvalue(), "chamados.xlsx",
                   "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

c3.download_button("⬇️ Alterações (CSV)", csv_alt, "alteracoes.csv", "text/csv")

excel_alt = io.BytesIO()
df_alt.to_excel(excel_alt, index=False, engine="xlsxwriter")
c4.download_button("📊 Alterações (XLSX)", excel_alt.getvalue(), "alteracoes.xlsx",
                   "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

st.markdown("---")
st.dataframe(df, use_container_width=True)
