
import os
from datetime import datetime
import pandas as pd
import streamlit as st

# ========== CONFIGURAÇÕES ==========
st.set_page_config(page_title="Pareceres - Plataforma Leonardo", layout="wide")
ARQ_DISTRIB = "distribuicao_pareceres.xlsx"         # planilha com a distribuição
PASTA_SUBMISSOES = "submissoes"                     # onde salvar os arquivos
ARQ_LOG = os.path.join(PASTA_SUBMISSOES, "log_submissoes.csv")   # log das submissões
ADMIN_CODE = st.secrets.get("ADMIN_CODE", "leonardo2025")        # defina em .streamlit/secrets.toml

os.makedirs(PASTA_SUBMISSOES, exist_ok=True)

# ========== FUNÇÕES AUXILIARES ==========
@st.cache_data
def carregar_distribuicao(caminho: str) -> pd.DataFrame:
    df = pd.read_excel(caminho)
    cols_map = {
        "Aluno (Avaliador)": "aluno",
        "Câmara": "camara",
        "Perfil": "perfil",
        "Projeto recebido (Autor)": "autor",
        "Câmara do Autor": "camara_autor",
    }
    df = df.rename(columns=cols_map)
    for c in ["aluno", "camara", "perfil", "autor", "camara_autor"]:
        if c in df.columns:
            df[c] = df[c].astype(str).str.strip()
    return df

def carregar_log() -> pd.DataFrame:
    if os.path.exists(ARQ_LOG):
        df = pd.read_csv(ARQ_LOG)
        if "timestamp" in df.columns:
            df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
        return df
    else:
        return pd.DataFrame(columns=[
            "timestamp", "aluno", "camara", "perfil", "autor",
            "camara_autor", "parecer_texto", "nota", "arquivos"
        ])

def salvar_log(df: pd.DataFrame):
    df.to_csv(ARQ_LOG, index=False)

def salvar_uploads(aluno: str, arquivos):
    paths = []
    if not arquivos:
        return paths
    pasta_aluno = os.path.join(PASTA_SUBMISSOES, aluno.replace(" ", "_"))
    os.makedirs(pasta_aluno, exist_ok=True)
    for f in arquivos:
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        fname = f"{ts}__{f.name}".replace("/", "_").replace("\\", "_")
        destino = os.path.join(pasta_aluno, fname)
        with open(destino, "wb") as out:
            out.write(f.getbuffer())
        paths.append(destino)
    return paths

def escrever_card_projeto(row):
    st.markdown(f"**Você deve avaliar o projeto de:** `{row['autor']}`")
    st.caption(f"Câmara do autor: {row['camara_autor']} • Seu perfil: {row['perfil']}")

# ========== CARGAS INICIAIS ==========
if not os.path.exists(ARQ_DISTRIB):
    st.error(f"Arquivo de distribuição não encontrado: {ARQ_DISTRIB}")
    st.stop()

dist = carregar_distribuicao(ARQ_DISTRIB)
log_df = carregar_log()

# ========== SIDEBAR ==========
st.sidebar.title("Pareceres - Plataforma Leonardo")
modo = st.sidebar.radio("Selecione o modo:", ["Aluno", "Admin"])

# ========== MODO ALUNO ==========
if modo == "Aluno":
    st.header("Envio de Parecer")
    st.write("Preencha os campos abaixo para enviar seu parecer sobre o projeto designado.")

    alunos = sorted(dist["aluno"].unique())
    aluno_sel = st.selectbox("Seu nome (Avaliador)", alunos)

    reg = dist[dist["aluno"] == aluno_sel].head(1)
    if reg.empty:
        st.warning("Aluno não encontrado na distribuição.")
        st.stop()
    row = reg.iloc[0]

    with st.expander("Detalhes da sua designação", expanded=True):
        escrever_card_projeto(row)

    with st.form("form_parecer"):
        parecer_texto = st.text_area(
            "Parecer (texto)",
            placeholder="Descreva seu parecer aqui... (ABNT / critérios da disciplina)",
            height=200
        )
        nota = st.number_input("Nota (opcional)", min_value=0.0, max_value=10.0, step=0.1, format="%.1f")

        uploads = st.file_uploader(
            "Anexos (PDF/DOCX/ZIP) — opcional",
            type=["pdf", "docx", "zip"],
            accept_multiple_files=True
        )

        concordo = st.checkbox("Declaro que li as instruções e estou enviando meu parecer.")
        submit = st.form_submit_button("Enviar Parecer ✅")

    if submit:
        if not parecer_texto and not uploads:
            st.error("Envie ao menos o texto do parecer OU um anexo.")
        elif not concordo:
            st.error("Marque a declaração para prosseguir.")
        else:
            paths = salvar_uploads(aluno_sel, uploads)
            novo = {
                "timestamp": datetime.now().isoformat(),
                "aluno": aluno_sel,
                "camara": row["camara"],
                "perfil": row["perfil"],
                "autor": row["autor"],
                "camara_autor": row["camara_autor"],
                "parecer_texto": parecer_texto,
                "nota": nota if pd.notna(nota) else "",
                "arquivos": "|".join(paths) if paths else "",
            }
            log_df = pd.concat([log_df, pd.DataFrame([novo])], ignore_index=True)
            salvar_log(log_df)
            st.success("Parecer enviado com sucesso! 🎉")
            if paths:
                st.caption(f"Arquivos salvos: {len(paths)}")
            st.balloons()

# ========== MODO ADMIN ==========
else:
    st.header("Administração / Acompanhamento")

    codigo = st.text_input("Código de acesso (Admin)", type="password")
    if codigo != ADMIN_CODE:
        st.info("Insira o código de acesso para visualizar os dados.")
        st.stop()

    col1, col2, col3 = st.columns(3)
    with col1:
        total_alunos = dist["aluno"].nunique()
        st.metric("Alunos designados", total_alunos)
    with col2:
        total_submissoes = len(log_df)
        st.metric("Submissões recebidas", total_submissoes)
    with col3:
        taxa = (log_df["aluno"].nunique() / total_alunos * 100) if total_alunos else 0
        st.metric("Cobertura (alunos que já enviaram)", f"{taxa:.0f}%")

    camaras = ["(todas)"] + sorted(dist["camara"].unique())
    cam_sel = st.selectbox("Filtrar por câmara", camaras)
    autor_opts = ["(todos)"] + sorted(dist["autor"].unique())
    autor_sel = st.selectbox("Filtrar por autor do projeto", autor_opts)

    df_view = log_df.copy()
    if cam_sel != "(todas)":
        df_view = df_view[df_view["camara"] == cam_sel]
    if autor_sel != "(todos)":
        df_view = df_view[df_view["autor"] == autor_sel]

    st.subheader("Submissões")
    if df_view.empty:
        st.warning("Nenhuma submissão com esses filtros.")
    else:
        cols_ordem = ["timestamp", "aluno", "camara", "perfil", "autor", "camara_autor", "nota", "parecer_texto", "arquivos"]
        cols_exist = [c for c in cols_ordem if c in df_view.columns]
        st.dataframe(df_view[cols_exist], use_container_width=True)

    from io import BytesIO
    output = BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        log_df.to_excel(writer, index=False, sheet_name="submissoes")
        dist.to_excel(writer, index=False, sheet_name="distribuicao")
    output.seek(0)
    st.download_button(
        "⬇️ Baixar log de submissões (XLSX)",
        data=output,
        file_name=f"submissoes_{datetime.now().strftime('%Y%m%d-%H%M')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="dl_xlsx_final"
    )

    with st.expander("Notas e boas práticas"):
        st.markdown(
            "- Defina `ADMIN_CODE` em `.streamlit/secrets.toml`.\n"
            "- Os arquivos enviados ficam em `submissoes/<aluno>/`.\n"
            "- O log CSV é `submissoes/log_submissoes.csv`.\n"
        )
