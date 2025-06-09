import streamlit as st
import pandas as pd
from utils.slack import get_nome_real
from sqlalchemy import create_engine
import os

st.set_page_config(page_title="Painel JFL", layout="wide")

# ====== HEADER ======
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
    unsafe_allow_html=True
)

st.markdown("<div class='title'>🏢 JFL | Painel Gerencial de Chamados</div>", unsafe_allow_html=True)
st.markdown("<div class='sub'>Monitoramento em tempo real • Base comercial</div>", unsafe_allow_html=True)
st.markdown("---")

# ====== LER DADOS ======
@st.cache_data
def carregar_dados():
    url = os.getenv("DATA_PUBLIC_URL")
    if not url:
        st.error("❌ Variável DATA_PUBLIC_URL não encontrada.")
        return pd.DataFrame()

    engine = create_engine(url, connect_args={"sslmode": "require"})

    try:
        connection = engine.raw_connection()
        df = pd.read_sql("SELECT * FROM ordens_servico", con=connection)
        connection.close()
    except Exception as e:
        st.error(f"❌ Erro ao ler dados do banco: {e}")
        return pd.DataFrame()

    if not df.empty:
        df["responsavel_nome"] = df["responsavel"].apply(get_nome_real)
        df["solicitante_nome"] = df["solicitante"].apply(get_nome_real)
        df["capturado_nome"] = df["capturado_por"].apply(get_nome_real)

        colunas_ocultas = [
            "responsavel", "solicitante", "capturado_por",
            "responsavel_id", "thread_ts", "historico_reaberturas",
            "ultimo_editor", "canal_id"
        ]
        df = df.drop(columns=[c for c in colunas_ocultas if c in df.columns])

        df["data_abertura"] = pd.to_datetime(df["data_abertura"], errors='coerce')
        df["data_fechamento"] = pd.to_datetime(df["data_fechamento"], errors='coerce')

    return df

df = carregar_dados()

# ====== APLICAR FILTROS ======
if not df.empty:
    st.sidebar.markdown("## 🎛️ Filtros")

    # Filtro por data
    min_date = df["data_abertura"].min()
    max_date = df["data_abertura"].max()
    data_inicial, data_final = st.sidebar.date_input("📅 Intervalo de abertura:", [min_date, max_date])

    if data_inicial and data_final:
        df = df[df["data_abertura"].between(pd.to_datetime(data_inicial), pd.to_datetime(data_final))]

    # Filtro por responsável
    responsaveis_unicos = sorted(df["responsavel_nome"].dropna().unique().tolist())
    responsaveis = st.sidebar.multiselect("🧍 Responsável:", options=responsaveis_unicos)

    if responsaveis:
        df = df[df["responsavel_nome"].isin(responsaveis)]

# ====== METRIC CARDS ======
col1, col2, col3, col4, col5 = st.columns(5)

# Dash 1 - Total
col1.markdown(f"<div class='card'><h3>{len(df)}</h3><p>Total de Chamados</p></div>", unsafe_allow_html=True)

# Dash 2 - Em Atendimento (status aberto ou em análise)
em_atendimento = df[df["status"].isin(["aberto", "em analise"])]
col2.markdown(f"<div class='card'><h3>{len(em_atendimento)}</h3><p>Em Atendimento</p></div>", unsafe_allow_html=True)

# Dash 3 - Finalizados (data_fechamento preenchida)
finalizados = df[df["data_fechamento"].notnull()]
col3.markdown(f"<div class='card'><h3>{len(finalizados)}</h3><p>Finalizados</p></div>", unsafe_allow_html=True)

# Dash 4 - Dentro do SLA (exemplo: <= 2 dias úteis)
sla_dias = 2
df["dias_para_fechamento"] = (df["data_fechamento"] - df["data_abertura"]).dt.days
dentro_sla = df[df["dias_para_fechamento"] <= sla_dias]
col4.markdown(f"<div class='card'><h3>{len(dentro_sla)}</h3><p>Dentro do SLA</p></div>", unsafe_allow_html=True)

# Dash 5 - Fora do SLA
fora_sla = df[df["dias_para_fechamento"] > sla_dias]
col5.markdown(f"<div class='card'><h3>{len(fora_sla)}</h3><p>Fora do SLA</p></div>", unsafe_allow_html=True)

st.markdown("---")

# ====== TABELA VISUAL ======
st.dataframe(df, use_container_width=True)
