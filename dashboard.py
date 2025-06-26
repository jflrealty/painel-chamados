# dashboard.py  – Painel JFL Comercial
import os, io, re, json, datetime as dt
import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
from sqlalchemy import create_engine
from utils.slack import get_nome_real

st.set_page_config(page_title="Painel JFL", layout="wide")

# ----------------------------- UI STYLE ---------------------------------
st.markdown("""
<style>
  .main  { background:#F5F5F5 }
  .title { font-size:32px;font-weight:bold;color:#003366 }
  .sub   { font-size:16px;color:#666 }
  .card  { background:#fff;padding:20px;border-radius:12px;
           box-shadow:0 2px 6px rgba(0,0,0,.1);text-align:center }
</style>""", unsafe_allow_html=True)

st.markdown("<div class='title'>🏢 JFL | Painel Gerencial de Chamados</div>", True)
st.markdown("<div class='sub'>Monitoramento em tempo real • Base comercial</div>", True)
st.markdown("---")

# ------------------------- HELPERS --------------------------------------
def parse_reaberturas(txt: str, os_id: int, resp: str, data_abertura):
    """Converte “[2025-06-26] Fulano reabriu …” → dicts."""
    if not txt:
        return []
    pat = re.compile(r"\[(\d{4}-\d{2}-\d{2})]\s+(.+?)\s+(.*)")
    out = []
    for l in filter(None, (x.strip() for x in txt.splitlines())):
        if m := pat.match(l):
            data, quem, desc = m.groups()
            out.append(
                dict(id=os_id,
                     quando=pd.to_datetime(data, errors="coerce"),
                     quem=quem, descricao=desc,
                     campo="reabertura", de="-", para="-",
                     responsavel_nome=resp, data_abertura=data_abertura))
    return out

# ---------- LOAD DATA ---------------------------------------------------
@st.cache_data(show_spinner=False)
def carregar_dados() -> tuple[pd.DataFrame, pd.DataFrame]:
    url = os.getenv("DATA_PUBLIC_URL")
    if not url:
        st.error("❌ Variável DATA_PUBLIC_URL não definida.")
        return pd.DataFrame(), pd.DataFrame()

    try:
        # 1) cria o engine normalmente
        engine = create_engine(url, connect_args={"sslmode": "require"})

        # 2) usa o raw_connection (DB-API) p/ evitar o bug do .cursor
        with engine.raw_connection() as raw_conn:
            df = pd.read_sql("SELECT * FROM ordens_servico", con=raw_conn)

    except Exception as e:
        st.error(f"❌ Erro ao ler banco: {e}")
        return pd.DataFrame(), pd.DataFrame()

    if df.empty:
        return df, pd.DataFrame()

    # ---------- GARANTE COLUNAS ----------
    obrigatorias = [
        "responsavel", "solicitante", "capturado_por",
        "data_abertura", "data_fechamento",
        "log_edicoes", "historico_reaberturas", "status",
        "data_ultima_edicao", "ultimo_editor"
    ]
    for col in obrigatorias:
        if col not in df.columns:
            df[col] = None

    # ---------- NOMES REAIS ----------
    df["responsavel_nome"] = df["responsavel"].apply(get_nome_real)
    df["solicitante_nome"] = df["solicitante"].apply(get_nome_real)
    df["capturado_nome"] = df["capturado_por"].apply(get_nome_real)

    # ---------- DATAS & SLA ----------
    df["data_abertura"] = pd.to_datetime(df["data_abertura"], errors="coerce")
    df["data_fechamento"] = pd.to_datetime(df["data_fechamento"], errors="coerce")
    df["dias_para_fechamento"] = (df["data_fechamento"] - df["data_abertura"]).dt.days

    # ---------- df_alt: ALTERAÇÕES & REABERTURAS ----------
    registros = []
    for _, r in df.iterrows():
        # edições
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

        # reaberturas
        registros += parse_reaberturas(
            r.get("historico_reaberturas"), r["id"],
            r["responsavel_nome"], r["data_abertura"]
        )

    df_alt = pd.DataFrame(registros)
    if not df_alt.empty and "quando" in df_alt.columns:
        df_alt = df_alt.sort_values("quando", ascending=False)

    return df, df_alt

df, df_alt = carregar_dados()
if df.empty:
    st.info("📭 Nenhum chamado encontrado.")
    st.stop()

# -------------------------- SIDEBAR -------------------------------------
st.sidebar.markdown("## 🎛️ Filtros")
# datas válidas
valid = df["data_abertura"].dropna()
min_d, max_d = valid.min().date(), valid.max().date()
ini, fim = st.sidebar.date_input("🗓️ Período:", [min_d, max_d])

# ⟹ Sempre filtre comparando date × date
mask = df["data_abertura"].dt.date.between(ini, fim)
df = df[mask]
df_alt = df_alt[df_alt["data_abertura"].dt.date.between(ini, fim)]

resp_sel = st.sidebar.multiselect("🧑‍💼 Responsável:",
                                  sorted(df["responsavel_nome"].dropna().unique()))
if resp_sel:
    df = df[df["responsavel_nome"].isin(resp_sel)]
    df_alt = df_alt[df_alt["responsavel_nome"].isin(resp_sel)]

# ------------------------- METRICS --------------------------------------
c1,c2,c3,c4,c5 = st.columns(5)
c1.markdown(f"<div class='card'><h3>{len(df)}</h3><p>Total</p></div>", True)
em_at = df["status"].isin(["aberto","em analise"]).sum()
c2.markdown(f"<div class='card'><h3>{em_at}</h3><p>Em Atendimento</p></div>", True)
c3.markdown(f"<div class='card'><h3>{df['data_fechamento'].notna().sum()}</h3><p>Finalizados</p></div>", True)
c4.markdown(f"<div class='card'><h3>{(df['dias_para_fechamento']<=2).sum()}</h3><p>Dentro SLA</p></div>", True)
c5.markdown(f"<div class='card'><h3>{(df['dias_para_fechamento']>2).sum()}</h3><p>Fora SLA</p></div>", True)

st.markdown("---")

# -------------------------- GRÁFICOS ------------------------------------
st.subheader("📊 Distribuição de Chamados")
if "tipo_ticket" in df.columns and not df.empty:
    fig, ax = plt.subplots(figsize=(6,3))
    df["tipo_ticket"].value_counts().plot.bar(ax=ax, color="#3E84F4")
    ax.set_ylabel("Qtd"); st.pyplot(fig)

fech = df[df["data_fechamento"].notna()]
st.metric("🗓️ Tempo médio de fechamento",
          f"{fech['dias_para_fechamento'].mean():.1f} dias" if not fech.empty else "-")

if not fech.empty:
    fig2, ax2 = plt.subplots(figsize=(6,3))
    fech["dias_para_fechamento"].hist(ax=ax2, bins=10, color="#34A853")
    ax2.set_xlabel("Dias"); ax2.set_ylabel("Chamados")
    st.pyplot(fig2)

# ---------------------- ALTERAÇÕES --------------------------------------
st.markdown("## 🔄 Alterações (edições + reaberturas)")
if df_alt.empty:
    st.info("Não há alterações para o filtro atual.")
else:
    vis = (df_alt[["id","quando","quem","descricao"]]
           .rename(columns={"id":"OS","quando":"Data",
                            "quem":"Usuário","descricao":"Alteração"}))
    st.dataframe(vis, use_container_width=True)

    top = (df_alt["quem"].value_counts().head(10)
           .rename_axis("Usuário").reset_index(name="Qtd"))
    fig3, ax3 = plt.subplots(figsize=(6,3))
    top.plot.barh(x="Usuário", y="Qtd", ax=ax3, color="#FF7043")
    ax3.invert_yaxis(); ax3.set_xlabel("Alterações")
    st.pyplot(fig3)

# --------------------------- EXPORT -------------------------------------
st.subheader("📦 Exportar")
csv_main = df.to_csv(index=False).encode()
csv_alt  = df_alt.to_csv(index=False).encode()

b1,b2,b3,b4 = st.columns(4)
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
