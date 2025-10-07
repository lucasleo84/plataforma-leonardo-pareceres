
import os
from datetime import datetime, timedelta, timezone
import pandas as pd
import streamlit as st

# ========== CONFIGURAÇÕES ==========
st.set_page_config(page_title="Pareceres - Plataforma Leonardo", layout="wide")

ARQ_DISTRIB = "distribuicao_pareceres.xlsx"               # planilha com a distribuição
PASTA_SUBMISSOES = "submissoes"                           # onde salvar os arquivos enviados
PASTA_PROJETOS = "projetos"                               # onde ficam os PDFs dos projetos (opcional p/ links)
ARQ_LOG = os.path.join(PASTA_SUBMISSOES, "log_submissoes.csv")
# defina no secrets: [general] ADMIN_CODE="..."  (em produção use segredo forte)
# Lê a senha do secrets tanto na raiz quanto dentro de [general]
def _get_admin_code():
    try:
        s = st.secrets
        if "ADMIN_CODE" in s:                       # caso: ADMIN_CODE na raiz
            return str(s["ADMIN_CODE"])
        if "general" in s and "ADMIN_CODE" in s["general"]:   # caso: [general] ADMIN_CODE="..."
            return str(s["general"]["ADMIN_CODE"])
    except Exception:
        pass
    return "leonardo2025"  # troque por "" se quiser obrigar uso do Secrets

ADMIN_CODE = _get_admin_code()

os.makedirs(PASTA_SUBMISSOES, exist_ok=True)
os.makedirs(PASTA_PROJETOS, exist_ok=True)

# ========== CONTROLE DE ACESSO / SESSÃO ==========
def _now_utc():
    return datetime.now(timezone.utc)

def is_admin_session() -> bool:
    exp = st.session_state.get("admin_until")
    return isinstance(exp, datetime) and _now_utc() < exp

def login_admin(code: str) -> bool:
    ok = bool(code) and (code == ADMIN_CODE)
    if ok:
        # sessão admin válida por 6 horas
        st.session_state["admin_until"] = _now_utc() + timedelta(hours=6)
        st.session_state["is_admin"] = True
    return ok

def logout_admin():
    for k in ["admin_until", "is_admin", "last_mode"]:
        st.session_state.pop(k, None)

def require_admin():
    if not is_admin_session():
        st.warning("Acesso restrito à Administração. Faça login para continuar.")
        st.stop()

# ========== FUNÇÕES AUXILIARES ==========
@st.cache_data(show_spinner=False)
def carregar_distribuicao(caminho: str, _sig: float) -> pd.DataFrame:
    """
    Lê a planilha e normaliza colunas.
    _sig = assinatura do cache (mtime do arquivo).
    """
    df = pd.read_excel(caminho)

    cols_map = {
        "Aluno (Avaliador)": "aluno",
        "Câmara": "camara",
        "Perfil": "perfil",
        "Projeto recebido (Autor)": "autor",
        "Câmara do Autor": "camara_autor",
        # aceita qualquer um desses nomes para o PDF do projeto
        "PDF do Projeto": "pdf",
        "PDF do Autor": "pdf",
        "Link do Projeto (PDF)": "pdf",
    }
    df = df.rename(columns={k: v for k, v in cols_map.items() if k in df.columns})

    for c in ["aluno", "camara", "perfil", "autor", "camara_autor", "pdf"]:
        if c not in df.columns:
            df[c] = ""
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
            "timestamp", "aluno", "camara", "perfil", "autor", "camara_autor", "arquivos"
        ])

def salvar_log(df: pd.DataFrame):
    df.to_csv(ARQ_LOG, index=False)

def salvar_uploads(aluno: str, arquivos):
    """Salva uploads do aluno em subpasta específica; retorna lista de caminhos."""
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

def mostrar_pdf_projeto(row):
    """Exibe botão para abrir/baixar o PDF do projeto, se configurado na planilha."""
    pdf_val = str(row.get("pdf", "")).strip()
    if not pdf_val or pdf_val.lower() == "nan":
        st.info("Sem PDF do projeto cadastrado para este autor. Preencha a coluna **PDF do Projeto** (ou **PDF do Autor** / **Link do Projeto (PDF)**) na planilha.")
        return

    st.subheader("Projeto (PDF) do autor")
    is_url = pdf_val.lower().startswith(("http://", "https://"))

    if is_url:
        st.link_button("🔗 Abrir projeto em nova aba", pdf_val)
    else:
        caminho = pdf_val
        if not os.path.isabs(caminho):
            caminho = os.path.join(PASTA_PROJETOS, pdf_val)
        if os.path.exists(caminho):
            with open(caminho, "rb") as f:
                st.download_button(
                    "⬇️ Baixar PDF do projeto",
                    data=f.read(),
                    file_name=os.path.basename(caminho),
                    mime="application/pdf",
                    key=f"baixar_pdf_{row['autor']}"
                )
        else:
            st.warning("PDF do projeto não foi encontrado. Verifique o nome/caminho na planilha ou faça upload em 'projetos/'.")

# ========== CARGAS INICIAIS ==========
if not os.path.exists(ARQ_DISTRIB):
    st.error(f"Arquivo de distribuição não encontrado: {ARQ_DISTRIB}")
    st.stop()

mtime = os.path.getmtime(ARQ_DISTRIB)  # assinatura sensível a mudanças no arquivo
dist = carregar_distribuicao(ARQ_DISTRIB, mtime)
log_df = carregar_log()

# ========== SIDEBAR ==========
st.sidebar.title("Pareceres - Plataforma Leonardo")

# Login/Admin na sidebar
if is_admin_session():
    st.sidebar.success("Você está logado como Admin ✅")
    if st.sidebar.button("Sair (logout)"):
        logout_admin()
        st.rerun()
else:
    with st.sidebar.expander("Acesso Admin", expanded=False):
        code = st.text_input("Código de acesso", type="password", key="admin_code_in")
        if st.button("Entrar", key="admin_login_btn"):
            if login_admin(code):
                st.sidebar.success("Login efetuado!")
                st.rerun()
            else:
                st.sidebar.error("Código incorreto.")

# O usuário só pode escolher 'Admin' se estiver logado
if is_admin_session():
    modo = st.sidebar.radio("Selecione o modo:", ["Aluno", "Admin"], index=1 if st.session_state.get("last_mode") == "Admin" else 0)
else:
    modo = "Aluno"
    st.sidebar.info("Área Admin protegida. Faça login para habilitar.")
st.session_state["last_mode"] = modo

# Botão de recarregar distribuição: só para Admin
if is_admin_session() and st.sidebar.button("🔄 Recarregar distribuição"):
    st.cache_data.clear()
    st.rerun()

# ========== MODO ALUNO ==========
if modo == "Aluno":
    st.header("Envio de Parecer (Anexo)")

    alunos = sorted(dist["aluno"].unique())
    aluno_sel = st.selectbox("Seu nome (Avaliador)", alunos)

    reg = dist[dist["aluno"] == aluno_sel].head(1)
    if reg.empty:
        st.warning("Aluno não encontrado na distribuição.")
        st.stop()
    row = reg.iloc[0]

    with st.expander("Detalhes da sua designação", expanded=True):
        escrever_card_projeto(row)
        mostrar_pdf_projeto(row)

    with st.form("form_parecer_anexo"):
        uploads = st.file_uploader(
            "Envie seu parecer (PDF, DOCX ou ZIP) somente após a reunião da Câmara",
            type=["pdf", "docx", "zip"],
            accept_multiple_files=True
        )
        concordo = st.checkbox("Declaro que estou enviando meu parecer apenas APÓS a reunião da Câmara.")
        submit = st.form_submit_button("Enviar Parecer ✅")

    if submit:
        if not uploads:
            st.error("Envie ao menos um arquivo (PDF, DOCX ou ZIP).")
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
                "arquivos": "|".join(paths) if paths else "",
            }
            log_df = pd.concat([log_df, pd.DataFrame([novo])], ignore_index=True)
            salvar_log(log_df)
            st.success("Parecer enviado com sucesso! 🎉")
            st.caption(f"Arquivos salvos: {len(paths)}")
            st.balloons()

# ========== MODO ADMIN ==========
else:
    require_admin()  # guarda de segurança

    st.header("Administração / Acompanhamento")

    # ===== AÇÕES DE EDIÇÃO (somente Admin) =====
    st.subheader("Ações de edição")

    # Substituir a planilha de distribuição no servidor do app
    with st.expander("Atualizar planilha de distribuição (substituir .xlsx)", expanded=True):
        up = st.file_uploader(
            "Selecione a nova planilha .xlsx",
            type=["xlsx"],
            key="upl_dist_admin2"
        )

        # Info do arquivo atual
        try:
            from datetime import datetime
            mtime = os.path.getmtime(ARQ_DISTRIB)
            st.caption(f"Arquivo atual: **{ARQ_DISTRIB}** — última modificação: {datetime.fromtimestamp(mtime).strftime('%d/%m/%Y %H:%M')}")
        except Exception:
            st.caption(f"Arquivo atual: **{ARQ_DISTRIB}**")

        if up is not None:
            try:
                with open(ARQ_DISTRIB, "wb") as f:
                    f.write(up.getbuffer())
                st.success("Distribuição atualizada com sucesso.")
                st.cache_data.clear()
                st.rerun()
            except Exception as e:
                st.error(f"Falha ao atualizar a planilha: {e}")
    
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

    # ===== AÇÕES DE EDIÇÃO (somente Admin) =====
    st.subheader("Ações de edição")
    with st.expander("Atualizar planilha de distribuição (substituir .xlsx)", expanded=False):
        up = st.file_uploader("Nova planilha .xlsx", type=["xlsx"], key="upl_dist_admin")
        if st.button("Substituir distribuição", disabled=up is None, key="btn_subs_dist"):
            try:
                with open(ARQ_DISTRIB, "wb") as f:
                    f.write(up.getbuffer())
                st.success("Distribuição atualizada com sucesso.")
                st.cache_data.clear()
                st.rerun()
            except Exception as e:
                st.error(f"Falha ao atualizar: {e}")

    with st.expander("Gerenciar log de submissões", expanded=False):
        c1, c2 = st.columns(2)
        with c1:
            if st.button("🗑️ Limpar log", key="btn_clear_log"):
                try:
                    if os.path.exists(ARQ_LOG):
                        os.remove(ARQ_LOG)
                    st.success("Log apagado.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro ao apagar log: {e}")
        with c2:
            from io import BytesIO
            output = BytesIO()
            with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
                log_df.to_excel(writer, index=False, sheet_name="submissoes")
                dist.to_excel(writer, index=False, sheet_name="distribuicao")
            output.seek(0)
            st.download_button(
                "⬇️ Baixar log + distribuição (XLSX)",
                data=output,
                file_name=f"submissoes_{datetime.now().strftime('%Y%m%d-%H%M')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="dl_xlsx_final"
            )

    # ===== VISUALIZAÇÃO E FILTROS (Admin) =====
    st.subheader("Submissões")
    camaras = ["(todas)"] + sorted(dist["camara"].unique())
    cam_sel = st.selectbox("Filtrar por câmara", camaras)
    autor_opts = ["(todos)"] + sorted(dist["autor"].unique())
    autor_sel = st.selectbox("Filtrar por autor do projeto", autor_opts)

    df_view = carregar_log()
    if cam_sel != "(todas)":
        df_view = df_view[df_view["camara"] == cam_sel]
    if autor_sel != "(todos)":
        df_view = df_view[df_view["autor"] == autor_sel]

    if df_view.empty:
        st.warning("Nenhuma submissão com esses filtros.")
    else:
        cols_ordem = ["timestamp", "aluno", "camara", "perfil", "autor", "camara_autor", "arquivos"]
        cols_exist = [c for c in cols_ordem if c in df_view.columns]
        st.dataframe(df_view[cols_exist], use_container_width=True)

    with st.expander("Notas e boas práticas"):
        st.markdown(
            "- **Área Admin protegida por sessão de 6h** (logout disponível na barra lateral).\n"
            "- Defina `ADMIN_CODE` em `.streamlit/secrets.toml`.\n"
            "- Arquivos enviados ficam em `submissoes/<aluno>/`.\n"
            "- Para disponibilizar PDFs aos avaliadores, use a coluna **PDF do Projeto** (ou **PDF do Autor**/**Link do Projeto (PDF)**) na planilha."
        )
