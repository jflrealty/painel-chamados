import streamlit as st

st.set_page_config(page_title="Painel de Chamados", layout="wide")

st.title("📊 Painel de Administração dos Bots")

bot = st.radio("Selecione o Bot", ["Comercial", "Financeiro"])

st.write(f"Você selecionou: {bot}")
