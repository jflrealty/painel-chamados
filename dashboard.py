import json
import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import re, json, io, os, datetime as dt
from sqlalchemy import create_engine                      
from utils.slack import get_nome_real                     

st.set_page_config(page_title="Painel JFL", layout="wide")

# ---------- ESTILO ----------
st.markdown("""
<style>
  .main  { background:#F5F5F5; }
  .title { font-size:32px;font-weight:bold;color:#003366; }
  .sub   { font-size:16px;color:#666; }
  .card  { background:#fff;padding:20px;border-radius:12px;
           box-shadow:0 2px 6px rgba(0,0,0,.1);text-align:center; }
</style>
""", unsafe_allow_html=True)

st.markdown("<div class='title'>🏢 JFL | Painel Gerencial de Chamados</div>", unsafe_allow_html=True)
st.markdown("<div class='sub'>Monitoramento em tempo real • Base comercial</div>", unsafe_allow_html=True)
st.markdown("---")

# ---------- HELPERS ----------
def parse_reaberturas(txt: str, os_id: int, resp: str, data_abertura):
    """Extrai '[YYYY-MM-DD] Fulano ...' → dicts."""
    if not txt:
        return []
    pattern = re.compile(r"\[(\d{4}-\d{2}-\d{2})\]\s+(.+?)\s+(.*)")
    registros = []
    for line in (l.strip() for l in txt.splitlines() if l.strip()):
        m = pattern.match(line)
        if m:
            data, quem, desc = m.groups()
            registros.append({
                "id": os_id,
                "quando": pd.to_datetime(data, errors="coerce"),
                "quem": quem,
                "descricao": desc,
                "campo": "reabertura",
                "de": "-",
                "para": "-",
                "responsavel_nome": resp,
                "data_abertura": data_abertura,
            })
    return registros


# ---------- LOAD DATA ----------
@st.cache_data(show_spinner=False)
def carregar_dados():
    url = os.getenv("DATA_PUBLIC_URL")
    if not url:
        st.error("❌ Variável DATA_PUBLIC_URL não definida.")
        return pd.DataFrame(), pd.DataFrame()

    try:
        engine = create_engine(url, connect_args={"sslmode": "require"})
        # ▶️  Use diretamente o engine (resolve o erro de cursor)
        df = pd.read_sql("SELECT * FROM ordens_servico", con=engine)
    except Exception as e:
        st.error(f"❌ Erro ao ler dados do banco: {e}")
        return pd.DataFrame(), pd.DataFrame()

    if df.empty:
        return df, pd.DataFrame()

    # garante colunas
    need = ["responsavel","solicitante","capturado_por",
            "data_abertura","data_fechamento",
            "log_edicoes","historico_reaberturas","status",
            "data_ultima_edicao","ultimo_editor"]
    for c in need:
        if c not in df.columns:
            df[c] = None

    # nomes reais
    df["responsavel_nome"] = df["responsavel"].apply(get_nome_real)
    df["solicitante_nome"] = df["solicitante"].apply(get_nome_real)
    df["capturado_nome"]   = df["capturado_por"].apply(get_nome_real)

    # datas & SLA
    df["data_abertura"]    = pd.to_datetime(df["data_abertura"], errors="coerce")
    df["data_fechamento"]  = pd.to_datetime(df["data_fechamento"], errors="coerce")
    df["dias_para_fechamento"] = (df["data_fechamento"] - df["data_abertura"]).dt.days

    # ---------- df_alt ----------
    registros = []
    for _, r in df.iterrows():
        # log_edicoes JSON
        if r["log_edicoes"] not in [None, "", "null"]:
            try:
                log = json.loads(r["log_edicoes"])
                for campo, mud in log.items():
                    registros.append({
                        "id": r["id"],
                        "quando": pd.to_datetime(r["data_ultima_edicao"], errors="coerce"),
                        "quem": r["ultimo_editor"] or "-",
                        "descricao": f"{campo}: {mud.get('de')} → {mud.get('para')}",
                        "campo": campo,
                        "de": mud.get("de"), "para": mud.get("para"),
                        "responsavel_nome": r["responsavel_nome"],
                        "data_abertura": r["data_abertura"]
                    })
            except Exception as e:
                print("⚠️ log_edicoes mal-formado:", e)

        # histórico de reaberturas
        registros += parse_reaberturas(
            r.get("historico_reaberturas"), r["id"],
            r["responsavel_nome"], r["data_abertura"]
        )

    df_alt = pd.DataFrame(registros)
    if not df_alt.empty and "quando" in df_alt.columns:
        df_alt = df_alt.sort_values("quando", ascending=False)

    return df, df_alt


# ---------- LEITURA -----------
df, df_alt = carregar_dados()
if df.empty:
    st.warning("📭 Nenhum dado encontrado.")
    st.stop()

# ---------- SIDEBAR -----------
st.sidebar.markdown("## 🎛️ Filtros")

# 1) converter coluna para datetime sem timezone
df["data_abertura"] = pd.to_datetime(df["data_abertura"], errors="coerce").dt.tz_localize(None)
if not df_alt.empty:
    df_alt["data_abertura"] = pd.to_datetime(df_alt["data_abertura"], errors="coerce").dt.tz_localize(None)

# 2) valores válidos para filtro
valid_dates = df["data_abertura"].dropna()
if valid_dates.empty:
    st.warning("📭 Nenhuma data de abertura válida encontrada.")
    st.stop()

min_d = valid_dates.min().date()
max_d = valid_dates.max().date()

# 3) widget de seleção de datas
date_range = st.sidebar.date_input("🗓️ Período:", [min_d, max_d])

# 4) garantir datetime64[ns] sem timezone
if isinstance(date_range, (list, tuple)) and len(date_range) == 2:
    d_ini = pd.Timestamp(date_range[0]).replace(tzinfo=None)
    d_fim = pd.Timestamp(date_range[1]).replace(tzinfo=None)
else:
    d_ini = pd.Timestamp(date_range).replace(tzinfo=None)
    d_fim = d_ini

# 5) aplicar filtros com segurança
df = df[df["data_abertura"].between(d_ini, d_fim)]
if not df_alt.empty:
    df_alt = df_alt[df_alt["data_abertura"].between(d_ini, d_fim)]

# 6) filtro por responsável
resp_sel = st.sidebar.multiselect("🧑‍💼 Responsável:", sorted(df["responsavel_nome"].dropna().unique()))
if resp_sel:
    df = df[df["responsavel_nome"].isin(resp_sel)]
    if not df_alt.empty:
        df_alt = df_alt[df_alt["responsavel_nome"].isin(resp_sel)]
# ---------- METRIC CARDS -------
col1, col2, col3, col4, col5 = st.columns(5)
col1.markdown(f"<div class='card'><h3>{len(df)}</h3><p>Total</p></div>", unsafe_allow_html=True)
col2.markdown(f"<div class='card'><h3>{len(df[df['status'].isin(['aberto','em analise'])])}</h3><p>Em Atendimento</p></div>", unsafe_allow_html=True)
col3.markdown(f"<div class='card'><h3>{df['data_fechamento'].notna().sum()}</h3><p>Finalizados</p></div>", unsafe_allow_html=True)
col4.markdown(f"<div class='card'><h3>{(df['dias_para_fechamento']<=2).sum()}</h3><p>Dentro do SLA</p></div>", unsafe_allow_html=True)
col5.markdown(f"<div class='card'><h3>{(df['dias_para_fechamento']>2).sum()}</h3><p>Fora do SLA</p></div>", unsafe_allow_html=True)

st.markdown("---")

# ---------- GRÁFICOS ----------
st.subheader("📊 Distribuição de Chamados")
if "tipo_ticket" in df.columns and not df.empty:
    fig1, ax1 = plt.subplots(figsize=(6,3))
    df["tipo_ticket"].value_counts().plot.bar(ax=ax1, color="#3E84F4")
    ax1.set_ylabel("Qtd")
    st.pyplot(fig1)

fech = df[df["data_fechamento"].notna()]
st.metric("🗓️ Tempo médio de fechamento",
          f"{fech['dias_para_fechamento'].mean():.1f} dias" if not fech.empty else "-")

if not fech.empty:
    fig2, ax2 = plt.subplots(figsize=(6,3))
    fech["dias_para_fechamento"].hist(ax=ax2, bins=10, color="#34A853")
    ax2.set_xlabel("Dias"); ax2.set_ylabel("Chamados")
    st.pyplot(fig2)

# ---------- ALTERAÇÕES ----------
st.markdown("## 🔄 Alterações (edições + reaberturas)")
if df_alt.empty:
    st.info("Não há alterações para os filtros selecionados.")
else:
    vis = df_alt[["id","quando","quem","descricao"]].rename(
        columns={"id":"OS","quando":"Data","quem":"Usuário","descricao":"Alteração"})
    st.dataframe(vis, use_container_width=True)

    top = (df_alt["quem"].value_counts()
                      .head(10)
                      .rename_axis("Usuário")
                      .reset_index(name="Qtd"))
    fig3, ax3 = plt.subplots(figsize=(6,3))
    top.plot.barh(x="Usuário", y="Qtd", ax=ax3, color="#FF7043")
    ax3.invert_yaxis(); ax3.set_xlabel("Alterações")
    st.pyplot(fig3)

# ---------- EXPORT ----------
st.subheader("📦 Exportar")
csv_main = df.to_csv(index=False).encode()
csv_alt  = df_alt.to_csv(index=False).encode()

b1, b2, b3, b4 = st.columns(4)
b1.download_button("⬇️ Chamados CSV", csv_main, "chamados.csv", "text/csv")

buf = io.BytesIO(); df.to_excel(buf, index=False, engine="xlsxwriter")
b2.download_button("📊 Chamados XLSX", buf.getvalue(), "chamados.xlsx",
                   "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

b3.download_button("⬇️ Alterações CSV", csv_alt, "alteracoes.csv", "text/csv")

buf2 = io.BytesIO(); df_alt.to_excel(buf2, index=False, engine="xlsxwriter")
b4.download_button("📊 Alterações XLSX", buf2.getvalue(), "alteracoes.xlsx",
                   "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

st.markdown("---")
st.dataframe(df, use_container_width=True)
