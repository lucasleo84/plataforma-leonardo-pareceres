import json
import streamlit as st
import pandas as pd
import networkx as nx
from pyvis.network import Network
import community.community_louvain as community_louvain
from pathlib import Path
import base64

# -----------------------------------------------------------
# Configuração geral
# -----------------------------------------------------------
st.set_page_config(
    page_title="Rede das Lutas, Brincadeiras e Habilidades",
    page_icon="🥋",
    layout="wide"
)
st.markdown(
    "<style> .stButton>button { font-weight:600 } </style>",
    unsafe_allow_html=True
)

BASE_DIR = Path(__file__).parent
ARQ_DADOS = BASE_DIR / "dados.json"
ARQ_TEC_OF  = BASE_DIR / "habilidades_tecnicas_ofensivas.txt"
ARQ_TEC_DEF = BASE_DIR / "habilidades_tecnicas_defensivas.txt"
ARQ_TAC     = BASE_DIR / "habilidades_taticas.txt"

# Cores
COR_LUTA, COR_BRINCADEIRA, COR_TECNICA, COR_TATICA = (
    "#1f77b4", "#2ca02c", "#ff7f0e", "#9467bd"
)

# -----------------------------------------------------------
# Utilidades
# -----------------------------------------------------------
def _ler_lista(arquivo: Path, fallback: list[str]) -> list[str]:
    if arquivo.exists():
        linhas = [l.strip() for l in arquivo.read_text(encoding="utf-8").splitlines()]
        return [l for l in linhas if l]
    return fallback

def carregar_habilidades_catalogo():
    return {
        "tecnicas_of": _ler_lista(ARQ_TEC_OF, ["projetar", "chutar", "golpear", "derrubar"]),
        "tecnicas_def": _ler_lista(ARQ_TEC_DEF, ["bloquear", "imobilizar", "defender", "segurar"]),
        "taticas": _ler_lista(ARQ_TAC, ["feintar", "marcação", "cobertura", "pressão"])
    }

def carregar_dados():
    if ARQ_DADOS.exists():
        try:
            return json.loads(ARQ_DADOS.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []

def salvar_dados(registros):
    ARQ_DADOS.write_text(json.dumps(registros, ensure_ascii=False, indent=2), encoding="utf-8")

def init_state():
    if "view" not in st.session_state:
        st.session_state.view = "A"
    if "filters" not in st.session_state:
        st.session_state.filters = {"LB": True, "BH": True, "LH": True}

# -----------------------------------------------------------
# Construção da Rede
# -----------------------------------------------------------
def build_graph_full(registros):
    G = nx.Graph()
    for r in registros:
        luta = r["luta"].strip()
        brinc = r["brincadeira"].strip()
        G.add_node(luta, tipo="luta", label=luta)
        G.add_node(brinc, tipo="brincadeira", label=brinc)
        G.add_edge(luta, brinc, rel="LB")
        grupos = [
            ("tecnica", r["hab_tecnicas_of"]),
            ("tecnica", r["hab_tecnicas_def"]),
            ("tatica", r["hab_taticas"])
        ]
        for sub_tipo, lista in grupos:
            for h in lista:
                nome = h.strip()
                if not nome:
                    continue
                G.add_node(nome, tipo="habilidade", sub_tipo=sub_tipo, label=nome)
                G.add_edge(brinc, nome, rel="BH")
                G.add_edge(luta, nome, rel="LH")
    return G

def subgraph_for_relation(G_full, show_LB, show_BH, show_LH):
    allowed = set()
    if show_LB: allowed.add("LB")
    if show_BH: allowed.add("BH")
    if show_LH: allowed.add("LH")
    H = nx.Graph()
    for u, v, attrs in G_full.edges(data=True):
        if attrs.get("rel") in allowed:
            if u not in H: H.add_node(u, **G_full.nodes[u])
            if v not in H: H.add_node(v, **G_full.nodes[v])
            H.add_edge(u, v, **attrs)
    return H

def color_and_size_for_node(G, n):
    attrs = G.nodes[n]
    t = attrs.get("tipo", "")
    deg = G.degree(n)
    size = max(10, 10 + 4 * deg)
    if t == "luta": color = COR_LUTA
    elif t == "brincadeira": color = COR_BRINCADEIRA
    elif t == "habilidade":
        color = COR_TECNICA if attrs.get("sub_tipo") == "tecnica" else COR_TATICA
    else: color = "#888888"
    return {"color": color, "size": size, "title": f"{t} • grau: {deg}"}

def render_pyvis(G, view="A", partition=None, height="720px"):
    net = Network(height=height, width="100%", notebook=False, directed=False, bgcolor="#ffffff")
    net.set_options('''
    {
      "nodes": {"shape": "dot", "scaling": {"min":10,"max":45}, "font": {"size":18}},
      "edges": {"smooth": false, "color": {"inherit": true}},
      "physics": {
        "enabled": true,
        "repulsion": {"centralGravity": 0.2, "springLength": 200, "springConstant": 0.03, "nodeDistance": 200, "damping": 0.09},
        "solver": "repulsion"
      },
      "interaction": {"hover": true,"zoomView": true,"dragNodes": true}
    }
    ''')
    if view == "A":
        for n in G.nodes():
            sty = color_and_size_for_node(G, n)
            net.add_node(str(n), label=str(G.nodes[n].get("label", n)),
                         color=sty["color"], size=sty["size"], title=sty["title"])
        for u, v, attrs in G.edges(data=True):
            net.add_edge(str(u), str(v))
    else:
        part = partition or {n: 0 for n in G.nodes()}
        palette = ["#1f77b4","#ff7f0e","#2ca02c","#d62728","#9467bd","#8c564b","#e377c2","#7f7f7f","#bcbd22","#17becf"]
        for n in G.nodes():
            deg = G.degree(n)
            size = max(10, 10 + 4 * deg)
            g = part.get(n, 0)
            color = palette[g % len(palette)]
            net.add_node(str(n), label=str(G.nodes[n].get("label", n)),
                         color=color, size=size, title=f"grau: {deg}")
        for u, v, attrs in G.edges(data=True):
            net.add_edge(str(u), str(v))
    return net.generate_html(notebook=False)

# -----------------------------------------------------------
# Área dos Alunos (simplificada)
# -----------------------------------------------------------
def pagina_insercao():
    st.header("Área dos Alunos – Inserção")
    cat = carregar_habilidades_catalogo()
    registros = carregar_dados()

    luta = st.text_input("Nome da Luta")
    brinc = st.text_input("Nome da Brincadeira")
    tec_of  = st.multiselect("Técnicas Ofensivas",  options=cat["tecnicas_of"])
    tec_def = st.multiselect("Técnicas Defensivas", options=cat["tecnicas_def"])
    taticas = st.multiselect("Habilidades Táticas", options=cat["taticas"])

    if st.button("Adicionar Brincadeira", type="primary"):
        if not luta.strip() or not brinc.strip():
            st.error("Informe Luta e Brincadeira.")
        elif len(tec_of + tec_def + taticas) == 0:
            st.error("Selecione pelo menos uma habilidade.")
        else:
            novo = {"luta": luta.strip(),"brincadeira": brinc.strip(),
                    "hab_tecnicas_of": tec_of,"hab_tecnicas_def": tec_def,"hab_taticas": taticas}
            registros.append(novo)
            salvar_dados(registros)
            st.success(f"Brincadeira **{brinc}** adicionada à luta **{luta}**.")
            st.balloons()

    st.subheader("📋 Registros atuais")
    if registros:
        df = pd.DataFrame(registros)
        for k in ["hab_tecnicas_of","hab_tecnicas_def","hab_taticas"]:
            df[k]=df[k].apply(lambda x:", ".join(x))
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.info("Nenhum registro ainda.")

# -----------------------------------------------------------
# Área do Professor
# -----------------------------------------------------------
def pagina_visualizacao():
    st.header("Área do Professor – Visualização e Controles")
    with st.sidebar:
        st.subheader("Filtros de Visualização")
        f = st.session_state.filters
        f["LB"] = st.checkbox("Luta → Brincadeira", value=f["LB"])
        f["BH"] = st.checkbox("Brincadeira → Habilidade", value=f["BH"])
        f["LH"] = st.checkbox("Luta → Habilidade", value=f["LH"])
        st.divider(); st.subheader("Legenda")
        st.markdown("- 🔵 **Lutas**\n- 🟢 **Brincadeiras**\n- 🟠 **Técnicas (Of/Def)**\n- 🟣 **Táticas**")
        st.divider()
        if st.button("♻️ Limpar Rede", type="secondary"):
            salvar_dados([]); st.toast("Rede limpa.", icon="✅")

    registros = carregar_dados()
    if not registros:
        st.warning("Sem registros ainda. Peça aos alunos para adicionar em `?page=insercao`.")
        return

    c1, c2 = st.columns([1,1])
    with c1:
        if st.button("🟦 Visualização A", use_container_width=True): st.session_state.view="A"
    with c2:
        if st.button("🌈 Visualização B", use_container_width=True): st.session_state.view="B"

    G_full=build_graph_full(registros)
    G=subgraph_for_relation(G_full,f["LB"],f["BH"],f["LH"])
    if G.number_of_nodes()==0:
        st.warning("Nenhum nó com os filtros atuais."); return

    if st.session_state.view=="A":
        html=render_pyvis(G,"A")
    else:
        part=community_louvain.best_partition(G) if G.number_of_edges()>0 else {n:0 for n in G.nodes()}
        html=render_pyvis(G,"B",part)

    st.components.v1.html(html,height=720,scrolling=True)

    # botão download HTML
    b64 = base64.b64encode(html.encode()).decode()
    href = f'<a href="data:text/html;base64,{b64}" download="rede_lutas.html">💾 Baixar Rede (HTML)</a>'
    st.markdown(href, unsafe_allow_html=True)

# -----------------------------------------------------------
# Navegação
# -----------------------------------------------------------
init_state()
params = st.query_params
page = params.get("page", "visualizacao").lower()

if page == "insercao":
    pagina_insercao()
else:
    pagina_visualizacao()
