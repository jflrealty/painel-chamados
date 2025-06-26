import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import io, json, os
from utils.slack import get_nome_real
from sqlalchemy import create_engine

st.set_page_config(page_title="Painel JFL", layout="wide")

# ---------- ESTILO ----------
st.markdown("""
<style>
    .main { background-color:#F5F5F5; }
    .title{ font-size:32px;font-weight:bold;color:#003366; }
    .sub  { font-size:16px;color:#666666; }
    .card { background:#FFF;padding:20px;border-radius:12px;
            box-shadow:0 2px 6px rgba(0,0,0,.1);text-align:center;}
    .hist-card{background:#FFF;padding:10px;border:1px solid #ECECEC;
               border-radius:6px;margin-bottom:4px;}
</style>
""", unsafe_allow_html=True)

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

    engine = create_engine(url, connect_args={"sslmode": "require"})
    try:
        with engine.raw_connection() as con:
            df = pd.read_sql("SELECT * FROM ordens_servico", con=con)
    except Exception as e:
        st.error(f"❌ Erro ao ler dados do banco: {e}")
        return pd.DataFrame(), pd.DataFrame()

    if df.empty:
        return df, pd.DataFrame()

    # ---- Normalizações ----
    df["responsavel_nome"]  = df["responsavel"].apply(get_nome_real)
    df["solicitante_nome"]  = df["solicitante"].apply(get_nome_real)
    df["capturado_nome"]    = df["capturado_por"].apply(get_nome_real)
    df["data_abertura"]     = pd.to_datetime(df["data_abertura"],  errors="coerce")
    df["data_fechamento"]   = pd.to_datetime(df["data_fechamento"], errors="coerce")
    df["dias_para_fechamento"] = (df["data_fechamento"] - df["data_abertura"]).dt.days

    # ---- Explode log_edicoes ----
    registros = []
    for _, row in df.iterrows():
        raw = row.get("log_edicoes")
        if pd.isna(raw) or raw == "":
            continue
        try:
            log = json.loads(raw)
            # log nesse formato: {campo:{"de": "...", "para":"..."}, ...}
            for campo, mud in log.items():
                registros.append({
                    "id": row["id"],
                    "campo": campo,
                    "de":   str(mud.get("de")),
                    "para": str(mud.get("para")),
                    "responsavel_nome": row["responsavel_nome"],
                    "data_abertura":   row["data_abertura"],
                })
        except Exception as e:
            print("Erro parseando log_edicoes:", e)

    df_alt = pd.DataFrame(registros)
    return df, df_alt

df, df_alt = carregar_dados()

# ---------- SIDEBAR FILTERS ----------
if not df.empty:
    st.sidebar.markdown("## 🎛️ Filtros")

    min_d, max_d = df["data_abertura"].min(), df["data_abertura"].max()
    d_ini, d_fim = st.sidebar.date_input("📅 Intervalo de abertura:", [min_d, max_d])

    if d_ini and d_fim:
        mask = df["data_abertura"].between(pd.to_datetime(d_ini), pd.to_datetime(d_fim))
        df = df[mask]
        if not df_alt.empty:
            df_alt = df_alt[df_alt["data_abertura"].between(pd.to_datetime(d_ini), pd.to_datetime(d_fim))]

    resp_opts = sorted(df["responsavel_nome"].dropna().unique())
    sel_resp  = st.sidebar.multiselect("🧍 Responsável:", resp_opts)

    if sel_resp:
        df = df[df["responsavel_nome"].isin(sel_resp)]
        if not df_alt.empty:
            df_alt = df_alt[df_alt["responsavel_nome"].isin(sel_resp)]

    if not df_alt.empty:
        campo_opts = sorted(df_alt["campo"].unique())
        sel_campo  = st.sidebar.multiselect("📝 Campo alterado:", campo_opts)
        if sel_campo:
            df_alt = df_alt[df_alt["campo"].isin(sel_campo)]

# ---------- METRIC CARDS ----------
col1, col2, col3, col4, col5 = st.columns(5)
col1.markdown(f"<div class='card'><h3>{len(df)}</h3><p>Total de Chamados</p></div>", unsafe_allow_html=True)
col2.markdown(f"<div class='card'><h3>{len(df[df.status.isin(['aberto','em analise'])])}</h3><p>Em Atendimento</p></div>", unsafe_allow_html=True)
col3.markdown(f"<div class='card'><h3>{len(df[df['data_fechamento'].notna()])}</h3><p>Finalizados</p></div>", unsafe_allow_html=True)
col4.markdown(f"<div class='card'><h3>{len(df[df['dias_para_fechamento']<=2])}</h3><p>Dentro do SLA</p></div>", unsafe_allow_html=True)
col5.markdown(f"<div class='card'><h3>{len(df[df['dias_para_fechamento']>2])}</h3><p>Fora do SLA</p></div>",  unsafe_allow_html=True)

st.markdown("---")

# ---------- CHARTS ----------
st.subheader("📊 Distribuição de Chamados")
if "tipo_ticket" in df.columns and not df.empty:
    fig1, ax1 = plt.subplots()
    df["tipo_ticket"].value_counts().plot.bar(color="#3E84F4", ax=ax1)
    ax1.set_title("Chamados por Tipo de Ticket")
    ax1.set_ylabel("Quantidade")
    st.pyplot(fig1)

fechados = df[df["data_fechamento"].notna()]
tempo_medio = fechados["dias_para_fechamento"].mean()
st.metric("📅 Tempo médio de fechamento",
          f"{tempo_medio:.1f} dias" if pd.notna(tempo_medio) else "-")

if not fechados.empty:
    fig2, ax2 = plt.subplots()
    fechados["dias_para_fechamento"].hist(bins=10, color="#34A853", ax=ax2)
    ax2.set_title("Distribuição dos Dias para Fechamento")
    ax2.set_xlabel("Dias")
    ax2.set_ylabel("Chamados")
    st.pyplot(fig2)

# ---------- ALTERAÇÕES ----------
st.markdown("## 🔄 Alterações nos Chamados")
if df_alt.empty:
    st.info("Nenhuma alteração encontrada com os filtros atuais.")
else:
    st.dataframe(df_alt, use_container_width=True)

    # Top 10
    top_alt = (df_alt.groupby(["campo","de","para"])
                      .size()
                      .reset_index(name="qtd")
                      .sort_values("qtd", ascending=False))

    st.markdown("### 📊 Top 10 alterações")
    fig3, ax3 = plt.subplots(figsize=(8,4))
    top_alt.head(10).plot(kind="bar", x="para", y="qtd", color="#FF7043", ax=ax3)
    ax3.set_xlabel("Para")
    ax3.set_ylabel("Qtd")
    st.pyplot(fig3)

# ---------- TABELA COM EXPANDER DE HISTÓRICO ----------
st.markdown("## 📝 Chamados Detalhados")
if df.empty:
    st.warning("Nenhum chamado encontrado.")
else:
    # Ordene como preferir
    df_view = df.sort_values("data_abertura", ascending=False)

    for _, row in df_view.iterrows():
        colA, colB = st.columns([4,1])
        with colA:
            st.markdown(
                f"**ID {row['id']}** | {row['tipo_ticket']} | "
                f"{row['empreendimento']} | Resp: {row['responsavel_nome']} | "
                f"Status: {row['status']}"
            )
        with colB:
            with st.expander("🔍 Histórico"):
                historico = row.get("log_edicoes")
                if not historico or historico in ["", "null", None]:
                    st.write("Sem edições registradas.")
                else:
                    try:
                        obj = json.loads(historico)
                        for campo, mud in obj.items():
                            st.markdown(
                                f"<div class='hist-card'>**{campo}**<br>"
                                f"<span style='color:#888'>de:</span> {mud.get('de','-')}<br>"
                                f"<span style='color:#888'>para:</span> {mud.get('para','-')}</div>",
                                unsafe_allow_html=True)
                    except Exception as e:
                        st.write("Formato inválido:", e)

        st.markdown("---")

# ---------- EXPORT ----------
st.subheader("📤 Exportar dados filtrados")
csv_main = df.to_csv(index=False).encode("utf-8")
csv_alt  = df_alt.to_csv(index=False).encode("utf-8")

c1,c2,c3,c4 = st.columns(4)
c1.download_button("⬇️ Chamados CSV", csv_main, "chamados.csv", mime="text/csv")

buf_main = io.BytesIO(); df.to_excel(buf_main,index=False,engine="xlsxwriter")
c2.download_button("📊 Chamados XLSX", buf_main.getvalue(), "chamados.xlsx",
                   mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

c3.download_button("⬇️ Alterações CSV", csv_alt, "alteracoes.csv", mime="text/csv")

buf_alt  = io.BytesIO(); df_alt.to_excel(buf_alt,index=False,engine="xlsxwriter")
c4.download_button("📊 Alterações XLSX", buf_alt.getvalue(), "alteracoes.xlsx",
                   mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
