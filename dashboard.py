import streamlit as st
from db.comercial import get_chamados_comercial

st.set_page_config(page_title="Painel de Chamados", layout="wide")

st.title("📊 Painel de Administração dos Bots")

bot = st.radio("Selecione o Bot", ["Comercial", "Financeiro"])

if bot == "Comercial":
    df = get_chamados_comercial()
    st.dataframe(df)
else:
    st.info("📌 Conexão com Financeiro ainda não implementada.")
