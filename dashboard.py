import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import io
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
        df["dias_para_fechamento"] = (df["data_fechamento"] - df["data_abertura"]).dt.days

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
col1.markdown(f"<div class='card'><h3>{len(df)}</h3><p>Total de Chamados</p></div>", unsafe_allow_html=True)
col2.markdown(f"<div class='card'><h3>{len(df[df.status.isin(['aberto', 'em analise'])])}</h3><p>Em Atendimento</p></div>", unsafe_allow_html=True)
col3.markdown(f"<div class='card'><h3>{len(df[df['data_fechamento'].notnull()])}</h3><p>Finalizados</p></div>", unsafe_allow_html=True)
col4.markdown(f"<div class='card'><h3>{len(df[df['dias_para_fechamento'] <= 2])}</h3><p>Dentro do SLA</p></div>", unsafe_allow_html=True)
col5.markdown(f"<div class='card'><h3>{len(df[df['dias_para_fechamento'] > 2])}</h3><p>Fora do SLA</p></div>", unsafe_allow_html=True)

st.markdown("---")

# ====== 📊 GRÁFICOS ======
st.subheader("📊 Distribuição de Chamados")

# Gráfico de Tipo de Ticket
if "tipo_ticket" in df.columns:
    tipo_counts = df["tipo_ticket"].value_counts()
    fig1, ax1 = plt.subplots()
    tipo_counts.plot(kind="bar", color="#3E84F4", ax=ax1)
    ax1.set_title("Chamados por Tipo de Ticket")
    ax1.set_ylabel("Quantidade")
    st.pyplot(fig1)

# Gráfico Tempo Médio de Fechamento
fechados = df[df["data_fechamento"].notnull()]
tempo_medio = fechados["dias_para_fechamento"].mean()
st.metric("📅 Tempo médio de fechamento", f"{tempo_medio:.1f} dias")

# Histograma (opcional)
fig2, ax2 = plt.subplots()
fechados["dias_para_fechamento"].dropna().hist(bins=10, color="#34A853", ax=ax2)
ax2.set_title("Distribuição dos Dias para Fechamento")
ax2.set_xlabel("Dias")
ax2.set_ylabel("Chamados")
st.pyplot(fig2)

# ====== 📤 EXPORTAÇÃO ======
st.subheader("📤 Exportar dados filtrados")

col_exp1, col_exp2, col_exp3 = st.columns(3)

# CSV
csv = df.to_csv(index=False).encode("utf-8")
col_exp1.download_button("⬇️ Exportar CSV", csv, "chamados.csv", "text/csv")

# Excel
excel_buffer = io.BytesIO()
df.to_excel(excel_buffer, index=False, engine='xlsxwriter')
col_exp2.download_button("📊 Exportar Excel", excel_buffer.getvalue(), "chamados.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# PDF (deixo para próxima etapa se quiser com logo, tabelado etc.)

st.markdown("---")

# ====== TABELA ======
st.dataframe(df, use_container_width=True)
