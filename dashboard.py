import streamlit as st
import pandas as pd
from utils.slack import get_nome_real

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
    from sqlalchemy import create_engine
    import os

    # Pega a string completa já formatada com driver psycopg2
    url = os.getenv("DATA_PUBLIC_URL")

    if not url:
        st.error("❌ Variável DATA_PUBLIC_URL não encontrada.")
        return pd.DataFrame()

    # Cria engine corretamente
    engine = create_engine(url, connect_args={"sslmode": "require"})

    try:
        df = pd.read_sql("SELECT * FROM ordens_servico", con=engine)
    except Exception as e:
        st.error(f"❌ Erro ao ler dados do banco: {e}")
        return pd.DataFrame()

    # Traduz nomes
    if not df.empty:
        df["responsavel_nome"] = df["responsavel"].apply(get_nome_real)
        df["solicitante_nome"] = df["solicitante"].apply(get_nome_real)
        df["capturado_nome"] = df["capturado_por"].apply(get_nome_real)

        # Oculta colunas
        colunas_ocultas = [
            "responsavel", "solicitante", "capturado_por",
            "responsavel_id", "thread_ts", "historico_reaberturas",
            "ultimo_editor", "canal_id"
        ]
        df = df.drop(columns=[c for c in colunas_ocultas if c in df.columns])

    return df

    # Traduzir IDs para nomes reais
    df["responsavel_nome"] = df["responsavel"].apply(get_nome_real)
    df["solicitante_nome"] = df["solicitante"].apply(get_nome_real)
    df["capturado_nome"] = df["capturado_por"].apply(get_nome_real)

    # Ocultar colunas indesejadas
    colunas_ocultas = [
        "responsavel", "solicitante", "capturado_por",
        "responsavel_id", "thread_ts", "historico_reaberturas",
        "ultimo_editor", "canal_id"
    ]
    return df.drop(columns=[c for c in colunas_ocultas if c in df.columns])

df = carregar_dados()

# ====== METRIC CARDS ======
col1, col2, col3 = st.columns(3)
col1.markdown(f"<div class='card'><h3>{len(df)}</h3><p>Total de Chamados</p></div>", unsafe_allow_html=True)
col2.markdown(f"<div class='card'><h3>{len(df[df.status == 'em atendimento'])}</h3><p>Em Atendimento</p></div>", unsafe_allow_html=True)
col3.markdown(f"<div class='card'><h3>{len(df[df.status == 'finalizado'])}</h3><p>Finalizados</p></div>", unsafe_allow_html=True)

st.markdown("---")

# ====== TABELA (apenas visual por enquanto) ======
st.dataframe(df, use_container_width=True)
