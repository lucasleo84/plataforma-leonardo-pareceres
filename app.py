
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
ADMIN_CODE = st.secrets.get("ADMIN_CODE", "leonardo2025")

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

