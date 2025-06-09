import streamlit as st
from db.comercial import get_chamados_comercial
from utils.slack import get_nome_real

st.set_page_config(page_title="Painel de Chamados", layout="wide")

st.title("📊 Painel de Administração dos Bots")

bot = st.radio("Selecione o Bot", ["Comercial", "Financeiro"])

if bot == "Comercial":
    df = get_chamados_comercial()

    for col in ["responsavel", "solicitante", "ultimo_editor", "capturado_por"]:
        if col in df.columns:
            df[col] = df[col].apply(get_nome_real)

    colunas_ocultas = [
        "responsavel_id",
        "thread_ts",
        "historico_reaberturas",
        "ultimo_editor",
        "canal_id"
    ]
    df = df.drop(columns=[col for col in colunas_ocultas if col in df.columns])

    st.dataframe(df)
else:
    st.info("📌 Conexão com Financeiro ainda não implementada.")
