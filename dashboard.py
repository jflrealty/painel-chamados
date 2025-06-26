import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import io, json, os, re
from utils.slack import get_nome_real
from sqlalchemy import create_engine

st.set_page_config(page_title="Painel JFL", layout="wide")

# ---------- ESTILO ----------
st.markdown("""
<style>
  .main { background-color:#F5F5F5; }
  .title{ font-size:32px;font-weight:bold;color:#003366; }
  .sub  { font-size:16px;color:#666; }
  .card { background:#fff;padding:20px;border-radius:12px;
          box-shadow:0 2px 6px rgba(0,0,0,.1);text-align:center;}
</style>
""", unsafe_allow_html=True)

st.markdown("<div class='title'>🏢 JFL | Painel Gerencial de Chamados</div>", unsafe_allow_html=True)
st.markdown("<div class='sub'>Monitoramento em tempo real • Base comercial</div>", unsafe_allow_html=True)
st.markdown("---")

# ---------- FUNÇÃO AUXILIAR ----------
def parse_historico(hist: str, os_id: int, resp_nome: str, data_abertura):
    """
    Transforma texto do tipo:
      [2025-06-26] Gabriela reabriu para *Reserva*
    em dicts → lista.
    """
    registros = []
    linhas = [l.strip() for l in hist.splitlines() if l.strip()]
    padrao = re.compile(r"\[(\d{4}-\d{2}-\d{2})\]\s+([^ ]+.*?)\s+(.*)")
    for ln in linhas:
        m = padrao.match(ln)
        if m:
            quando, quem, desc = m.groups()
            registros.append({
                "id": os_id,
                "quando": pd.to_datetime(quando, errors="coerce"),
                "quem": quem,
                "descricao": desc,
                "campo": "reabertura",
                "de": "-",         # não se aplica
                "para": "-",       # não se aplica
                "responsavel_nome": resp_nome,
                "data_abertura": data_abertura,
            })
    return registros

# ---------- LOAD DATA ----------
@st.cache_data
def carregar_dados():
    url = os.getenv("DATA_PUBLIC_URL")
    if not url:
        st.error("❌ Variável DATA_PUBLIC_URL não encontrada.")
        return pd.DataFrame(), pd.DataFrame()

    try:
        engine = create_engine(url, connect_args={"sslmode": "require"})
        df = pd.read_sql("SELECT * FROM ordens_servico", con=engine)
    except Exception as e:
        st.error(f"❌ Erro ao ler dados do banco: {e}")
        return pd.DataFrame(), pd.DataFrame()

    if df.empty:
        return df, pd.DataFrame()

    # Garantir colunas
    for col in ["responsavel", "solicitante", "capturado_por",
                "data_abertura", "data_fechamento",
                "log_edicoes", "historico_reaberturas"]:
        df.setdefault(col, None)

    # Nomes legíveis
    df["responsavel_nome"] = df["responsavel"].apply(get_nome_real)
    df["solicitante_nome"] = df["solicitante"].apply(get_nome_real)
    df["capturado_nome"]   = df["capturado_por"].apply(get_nome_real)

    # Datas
    df["data_abertura"]   = pd.to_datetime(df["data_abertura"],  errors="coerce")
    df["data_fechamento"] = pd.to_datetime(df["data_fechamento"], errors="coerce")
    df["dias_para_fechamento"] = (df["data_fechamento"] - df["data_abertura"]).dt.days

    # ---- LOG DE EDIÇÕES + REABERTURAS ----
    registros = []

    for _, row in df.iterrows():
        # log_edicoes (JSON)
        if row.get("log_edicoes") not in [None, "", "null"]:
            try:
                log = json.loads(row["log_edicoes"])
                for campo, mudanca in log.items():
                    registros.append({
                        "id": row["id"],
                        "quando": row.get("data_ultima_edicao"),
                        "quem": row.get("ultimo_editor"),
                        "descricao": f"{campo}: {mudanca.get('de')} → {mudanca.get('para')}",
                        "campo": campo,
                        "de": mudanca.get("de"),
                        "para": mudanca.get("para"),
                        "responsavel_nome": row.get("responsavel_nome",""),
                        "data_abertura": row.get("data_abertura"),
                    })
            except Exception as e:
                print("⚠️ Erro JSON log_edicoes:", e)

        # historico_reaberturas (texto)
        if row.get("historico_reaberturas") not in [None, "", "null"]:
            registros += parse_historico(
                row["historico_reaberturas"],
                row["id"],
                row.get("responsavel_nome",""),
                row.get("data_abertura")
            )

    df_alt = pd.DataFrame(registros)

    # Ordenar por data (quand o existir)
    if "quando" in df_alt.columns:
        df_alt = df_alt.sort_values("quando", ascending=False)

    return df, df_alt

# ===== CHAMAR E VERIFICAR DADOS =====
df, df_alt = carregar_dados()

if df.empty:
    st.warning("📭 Nenhum dado encontrado. Verifique a conexão ou os filtros aplicados.")
    st.stop()

# ---------- SIDEBAR FILTERS ----------
st.sidebar.markdown("## 🎛️ Filtros")

min_d, max_d = df["data_abertura"].min(), df["data_abertura"].max()
d_ini, d_fim = st.sidebar.date_input("🗓️ Intervalo de abertura:", [min_d, max_d])

if d_ini and d_fim:
    df = df[df["data_abertura"].between(pd.to_datetime(d_ini), pd.to_datetime(d_fim))]
    if not df_alt.empty:
        df_alt = df_alt[df_alt["data_abertura"].between(pd.to_datetime(d_ini), pd.to_datetime(d_fim))]

resp_sel = st.sidebar.multiselect("🧝 Responsável:",
                                  sorted(df["responsavel_nome"].dropna().unique()))
if resp_sel:
    df = df[df["responsavel_nome"].isin(resp_sel)]
    if not df_alt.empty:
        df_alt = df_alt[df_alt["responsavel_nome"].isin(resp_sel)]

# ---------- METRIC CARDS ----------
col1, col2, col3, col4, col5 = st.columns(5)
col1.markdown(f"<div class='card'><h3>{len(df)}</h3><p>Total de Chamados</p></div>", unsafe_allow_html=True)
col2.markdown(f"<div class='card'><h3>{len(df[df['status'].isin(['aberto','em analise'])])}</h3><p>Em Atendimento</p></div>", unsafe_allow_html=True)
col3.markdown(f"<div class='card'><h3>{df['data_fechamento'].notna().sum()}</h3><p>Finalizados</p></div>", unsafe_allow_html=True)
col4.markdown(f"<div class='card'><h3>{(df['dias_para_fechamento']<=2).sum()}</h3><p>Dentro do SLA</p></div>", unsafe_allow_html=True)
col5.markdown(f"<div class='card'><h3>{(df['dias_para_fechamento']>2).sum()}</h3><p>Fora do SLA</p></div>", unsafe_allow_html=True)

st.markdown("---")

# ---------- CHARTS ----------
st.subheader("📊 Distribuição de Chamados")
if "tipo_ticket" in df.columns and not df.empty:
    fig1, ax1 = plt.subplots(figsize=(6,3))
    df["tipo_ticket"].value_counts().plot.bar(color="#3E84F4", ax=ax1)
    ax1.set_ylabel("Qtd")
    st.pyplot(fig1)

fechados = df[df["data_fechamento"].notna()]
tempo_medio = fechados["dias_para_fechamento"].mean()
st.metric("🗓️ Tempo médio de fechamento", f"{tempo_medio:.1f} dias" if pd.notna(tempo_medio) else "-")

if not fechados.empty:
    fig2, ax2 = plt.subplots(figsize=(6,3))
    fechados["dias_para_fechamento"].hist(bins=10, color="#34A853", ax=ax2)
    ax2.set_xlabel("Dias")
    ax2.set_ylabel("Chamados")
    st.pyplot(fig2)

# ---------- ALTERAÇÕES ----------
st.markdown("## 🔄 Alterações (edições + reaberturas)")
if df_alt.empty:
    st.info("📭 Nenhuma alteração encontrada com os filtros atuais.")
else:
    mostrar = df_alt[["id","quando","quem","descricao"]].rename(columns={
        "id":"OS","quando":"Data","quem":"Usuário","descricao":"Alteração"
    })
    st.dataframe(mostrar, use_container_width=True)

    # Top quem mais reabre / edita
    top_alt = (df_alt["quem"].value_counts().head(10)).rename_axis("Usuário").reset_index(name="Qtd")
    fig3, ax3 = plt.subplots(figsize=(6,3))
    top_alt.plot(kind="barh", x="Usuário", y="Qtd", color="#FF7043", ax=ax3)
    ax3.invert_yaxis()
    ax3.set_xlabel("Alterações")
    st.pyplot(fig3)

# ---------- EXPORT ----------
st.subheader("📄 Exportar dados filtrados")

csv_main = df.to_csv(index=False).encode("utf-8")
csv_alt  = df_alt.to_csv(index=False).encode("utf-8")

c1, c2, c3, c4 = st.columns(4)
c1.download_button("⬇️ Chamados (CSV)", csv_main, "chamados.csv", "text/csv")

buf_main = io.BytesIO(); df.to_excel(buf_main, index=False, engine="xlsxwriter")
c2.download_button("📊 Chamados (XLSX)", buf_main.getvalue(), "chamados.xlsx",
                   "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

c3.download_button("⬇️ Alterações (CSV)", csv_alt, "alteracoes.csv", "text/csv")

buf_alt = io.BytesIO(); df_alt.to_excel(buf_alt, index=False, engine="xlsxwriter")
c4.download_button("📊 Alterações (XLSX)", buf_alt.getvalue(), "alteracoes.xlsx",
                   "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

st.markdown("---")
st.dataframe(df, use_container_width=True)
