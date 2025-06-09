import streamlit as st
import pandas as pd
from utils.slack import get_nome_real
from sqlalchemy import create_engine

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
    import os

    url = os.getenv("DATA_PUBLIC_URL")
    if not url:
        st.error("❌ Variável DATA_PUBLIC_URL não encontrada.")
        return pd.DataFrame()

    try:
        engine = create_engine(url)
        conn = engine.raw_connection()
        df = pd.read_sql("SELECT * FROM ordens_servico", con=conn)
        conn.close()
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

    return df

df = carregar_dados()

# ====== METRIC CARDS COM ÍCONES COLORIDOS ======

def bolinha(cor):
    cores = {
        "verde": "#28a745",
        "vermelho": "#dc3545",
        "cinza": "#6c757d"
    }
    return f"<span style='color:{cores[cor]}; font-size:24px;'>●</span>"

total_chamados = len(df)
em_atendimento = len(df[df["status"] == "em atendimento"])
encerrados = len(df[df["data_fechamento"].notna()])
dentro_sla = len(df[df["sla_status"] == "dentro do prazo"])
fora_sla = len(df[df["sla_status"] == "fora do prazo"])

col1, col2, col3, col4, col5 = st.columns(5)

col1.markdown(f"<div class='card'>{bolinha('cinza')}<h3>{total_chamados}</h3><p>Total de Chamados</p></div>", unsafe_allow_html=True)
col2.markdown(f"<div class='card'>{bolinha('cinza')}<h3>{em_atendimento}</h3><p>Em Atendimento</p></div>", unsafe_allow_html=True)
col3.markdown(f"<div class='card'>{bolinha('cinza')}<h3>{encerrados}</h3><p>Encerrados</p></div>", unsafe_allow_html=True)
col4.markdown(f"<div class='card'>{bolinha('verde')}<h3>{dentro_sla}</h3><p>Dentro do SLA</p></div>", unsafe_allow_html=True)
col5.markdown(f"<div class='card'>{bolinha('vermelho')}<h3>{fora_sla}</h3><p>Fora do SLA</p></div>", unsafe_allow_html=True)
# ====== TABELA ======
st.dataframe(df, use_container_width=True)
