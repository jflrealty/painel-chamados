import streamlit as st
from db.comercial import get_chamados_comercial
from utils.slack import get_nome_real

st.set_page_config(page_title="Painel de Chamados", layout="wide")

st.title("📊 Painel de Administração dos Bots")

bot = st.radio("Selecione o Bot", ["Comercial", "Financeiro"])

if bot == "Comercial":
    df = get_chamados_comercial()

    # Traduz colunas específicas
    for col in ["responsavel", "solicitante", "ultimo_editor", "capturado_por"]:
        if col in df.columns:
            df[col] = df[col].apply(get_nome_real)

    st.dataframe(df)
else:
    st.info("📌 Conexão com Financeiro ainda não implementada.")
