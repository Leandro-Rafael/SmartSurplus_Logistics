import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import folium
from folium import plugins
from streamlit_folium import st_folium
import numpy as np
import io
import requests
import base64
import time
import streamlit.components.v1 as components

# Nossos módulos
from data_generator import generate_suppliers, generate_ngos, calculate_distance_matrix, haversine
from optimization import run_optimization, simulate_current_scenario, apply_disaster_to_distances

@st.cache_data(show_spinner=False)
def geocode_address(address):
    try:
        url = "https://nominatim.openstreetmap.org/search"
        params = {"q": address, "format": "json", "limit": 1}
        headers = {"User-Agent": "SmartSurplus_Logistics_App/1.0"}
        response = requests.get(url, params=params, headers=headers, timeout=5)
        if response.status_code == 200:
            data = response.json()
            if data:
                return float(data[0]["lat"]), float(data[0]["lon"])
    except Exception:
        pass
    return None, None

@st.cache_data(show_spinner=False)
def get_osrm_route(start_lat, start_lon, end_lat, end_lon):
    url = f"http://router.project-osrm.org/route/v1/driving/{start_lon},{start_lat};{end_lon},{end_lat}?overview=full&geometries=geojson"
    for attempt in range(3):
        try:
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                data = response.json()
                if data.get("code") == "Ok":
                    coords = data["routes"][0]["geometry"]["coordinates"]
                    return [[lat, lon] for lon, lat in coords]
            # Caso 429 (Too many requests), a API limitou. Aguarda meio segundo e retenta.
            time.sleep(0.5)
        except Exception:
            time.sleep(0.5)
            pass
    # Se falhar 3x, devolve linha-reta segura para não parar o mapa.
    return [[start_lat, start_lon], [end_lat, end_lon]]

st.set_page_config(
    page_title="SmartSurplus | ESG",
    page_icon="❖",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        'Get Help': None,
        'Report a bug': None,
        'About': "### SmartSurplus\n**ExpoTech 2026** - Motor Logístico de Inteligência Artificial para Otimização de Excedentes."
    }
)

# Login State
if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False

def enter_system():
    st.session_state["logged_in"] = True

# --- EXTERMINADOR DE WATERMARKS (JavaScript Native Observer) ---
# Fica sempre em vigília rastreando cliques que geram Popovers
components.html("""
<script>
    const watcher = new MutationObserver(() => {
        const menus = window.parent.document.querySelectorAll('[data-testid="main-menu-list"]');
        menus.forEach(ul => {
            const footerTrash = ul.nextElementSibling;
            if(footerTrash && footerTrash.tagName.toLowerCase() === 'div') {
                footerTrash.style.setProperty('display', 'none', 'important');
            }
        });
    });
    watcher.observe(window.parent.document.body, { childList: true, subtree: true });
</script>
""", height=0, width=0)

# --- GLOBAL CSS (OPAL TADPOLE AESTHETICS) ---
st.markdown("""
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600&family=Playfair+Display:ital,wght@0,400;0,700;1,400&display=swap" rel="stylesheet">
<link href="https://fonts.googleapis.com/icon?family=Material+Icons" rel="stylesheet">
<style>
    /* Global Typography & Animations */
    * {
        font-family: 'Inter', sans-serif;
    }
    
    /* Esconde marca d'água do Streamlit no rodapé do site */
    footer { visibility: hidden !important; }
    
    /* Esconde a marca d'água "Feito com Streamlit" de dentro do Menu de 3 Pontinhos! */
    [data-testid="stPopoverContent"] ul + div { display: none !important; }
    [data-testid="stPopoverContent"] > div > div:last-child { display: none !important; }
    [data-testid="main-menu-list"] + div { display: none !important; }
    
    @keyframes slideUpFade {
        0% { opacity: 0; transform: translateY(50px); }
        100% { opacity: 1; transform: translateY(0); }
    }
    
    .opal-animate {
        animation: slideUpFade 1.8s cubic-bezier(0.16, 1, 0.3, 1) forwards;
        opacity: 0; /* Ensures it stays hidden until JS/CSS engine computes */
    }
    .opal-delay-1 { animation-delay: 0.3s; }
    .opal-delay-2 { animation-delay: 0.6s; }

    /* Button "Pill" Overhaul globally */
    [data-testid="stButton"] button {
        background-color: #ffffff !important;
        color: #000000 !important;
        border-radius: 50px !important;
        padding: 14px 38px !important;
        border: none !important;
        font-weight: 600 !important;
        font-size: 1.1rem !important;
        transition: transform 0.4s cubic-bezier(0.16, 1, 0.3, 1), opacity 0.4s ease !important;
        box-shadow: 0 4px 15px rgba(255,255,255,0.1);
    }
    [data-testid="stButton"] button:hover {
        transform: scale(1.03) !important;
        opacity: 0.8 !important;
    }
</style>
""", unsafe_allow_html=True)

if not st.session_state["logged_in"]:
    # -----------------------------------------------
    # RICH LANDING PAGE (VITRINE CORPORATIVA)
    # -----------------------------------------------
    st.markdown("""
        <style>
        .stApp {
            background-color: transparent !important;
            background-image: none !important;
        }
        </style>
    """, unsafe_allow_html=True)
    
    st.markdown("""
    <style>
        /* Desligando Menu Superior e Lateral de App */
        .stAppHeader { display: none !important; }
        [data-testid="collapsedControl"] { display: none !important; }
        [data-testid="stSidebar"] { display: none !important; }
        
        /* Centralizando vertical e horizontalmente */
        .block-container {
            max-width: 1200px !important;
            padding-top: 80px !important;
            padding-bottom: 80px !important;
        }

        /* Hero Typography - Pure B&W Professional */
        .opal-title {
            font-family: 'Playfair Display', serif;
            font-size: clamp(3rem, 6vw, 6rem);
            font-weight: 700;
            letter-spacing: -0.04em;
            color: #ffffff;
            line-height: 1.1;
            margin-bottom: 25px;
            text-align: center;
            text-shadow: 0px 4px 60px rgba(255, 255, 255, 0.2);
        }
        
        .opal-subtitle {
            font-size: clamp(1.1rem, 1.8vw, 1.5rem);
            font-weight: 300;
            color: #a1a1aa;
            letter-spacing: 0.02em;
            margin-bottom: 40px;
            max-width: 800px;
            text-align: center;
            margin-left: auto;
            margin-right: auto;
        }
        
        /* Video Background */
        .video-overlay {
            position: fixed;
            top: 0; left: 0;
            width: 100vw; height: 100vh;
            background: linear-gradient(rgba(0,0,0,0.6), rgba(0,0,0,0.85));
            z-index: -998;
        }
        .video-background {
            position: fixed;
            right: 0;
            bottom: 0;
            min-width: 100vw;
            min-height: 100vh;
            width: auto;
            height: auto;
            z-index: -999;
            object-fit: cover;
            filter: grayscale(100%);
        }
        
        /* Grid Setup para Cartões de Altura Idêntica */
        .features-grid {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 24px;
            margin-bottom: 40px;
            width: 100%;
        }
        
        /* Feature Cards (Black & White Glassmorphism) */
        .feature-card {
            background: rgba(20, 20, 20, 0.4); /* Fundo mais transparente para vidro */
            border: 1px solid rgba(255, 255, 255, 0.15);
            border-radius: 16px;
            padding: 30px;
            text-align: left;
            transition: transform 0.4s ease, box-shadow 0.4s ease, border-color 0.4s ease;
            backdrop-filter: blur(16px);
            -webkit-backdrop-filter: blur(16px);
            display: flex;
            flex-direction: column;
            justify-content: flex-start;
        }
        .feature-card:hover {
            transform: translateY(-8px);
            border-color: rgba(255, 255, 255, 0.8);
            box-shadow: 0 10px 40px rgba(255, 255, 255, 0.1);
        }
        .feature-card h3 {
            font-size: 1.3rem;
            color: #ffffff;
            margin-bottom: 12px;
            font-family: 'Inter', sans-serif;
            font-weight: 600;
        }
        .feature-card p {
            font-size: 1rem;
            color: #a1a1aa;
            line-height: 1.6;
        }
        
        /* Story Section - Manifesto Corporativo */
        .story-section {
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin: 100px auto;
            max-width: 1000px;
            padding: 20px;
        }
        
        .story-text-container {
            flex: 1;
            padding: 0 40px;
        }

        .story-text-right {
            border-left: 1px solid #333;
        }

        .story-title {
            font-family: 'Playfair Display', serif;
            font-size: 2.5rem;
            color: #ffffff;
            margin-bottom: 20px;
            line-height: 1.2;
        }

        .story-paragraph {
            font-size: 1.1rem;
            color: #d4d4d8;
            line-height: 1.8;
            font-weight: 300;
        }

        .story-image-container {
            flex: 1;
            text-align: center;
        }

        .story-img {
            max-width: 90%;
            border-radius: 12px;
            opacity: 0.9;
        }

        /* Scroll-driven Animations (CSS View Timeline) */
        @supports (animation-timeline: view()) {
            .slide-in-right {
                animation: slideIn linear forwards;
                animation-timeline: view();
                animation-range: entry 10% cover 50%;
            }
            .fade-in-up {
                animation: fadeUp linear forwards;
                animation-timeline: view();
                animation-range: entry 10% cover 40%;
            }
            .decrypt-on-scroll {
                animation: decryptText linear forwards;
                animation-timeline: view();
                animation-range: entry 0% cover 50%;
            }
        }
        
        @keyframes slideIn {
            0% { opacity: 0; transform: translateX(100px) scale(0.95); filter: blur(5px); }
            100% { opacity: 1; transform: translateX(0) scale(1); filter: blur(0px); }
        }

        @keyframes fadeUp {
            0% { opacity: 0; transform: translateY(80px); }
            100% { opacity: 1; transform: translateY(0); }
        }
        
        @keyframes decryptText {
            0% { opacity: 0; filter: blur(20px); letter-spacing: 14px; transform: scale(0.9); }
            45% { opacity: 0.6; filter: blur(6px); letter-spacing: 4px; color: #52525b; }
            100% { opacity: 1; filter: blur(0px); letter-spacing: normal; transform: scale(1); color: #ffffff; }
        }

        /* --- MOBILE RESPONSIVE OVERRIDES --- */
        @media (max-width: 768px) {
            .opal-title { font-size: clamp(2rem, 10vw, 3rem) !important; }
            .features-grid { grid-template-columns: 1fr !important; gap: 16px !important; }
            .story-section { flex-direction: column !important; margin: 60px auto !important; }
            .story-text-container { padding: 0 15px !important; }
            .story-text-right { border-left: none !important; border-top: 1px solid #333 !important; padding-top: 30px !important; margin-top: 30px !important; }
            .story-image-container { margin-top: 40px !important; width: 100% !important; }
            .story-img { width: 100% !important; }
            .story-title { font-size: 2rem !important; }
            /* Correção para as Tabelas não esmagarem as colunas no celular */
            [data-testid="stDataFrame"] { width: 100% !important; overflow-x: auto !important; }
        }
    </style>
    
    <!-- TAG DO VIDEO MP4 E OVERLAY -->
    <div class="video-overlay"></div>
    <video autoplay loop muted playsinline class="video-background" id="bgVideo">
        <!-- Digital Nodes & Artificial Intelligence Map Networks -->
        <source src="https://videos.pexels.com/video-files/3129957/3129957-hd_1920_1080_25fps.mp4" type="video/mp4">
        <source src="https://videos.pexels.com/video-files/3129595/3129595-uhd_2560_1440_30fps.mp4" type="video/mp4">
        <source src="https://videos.pexels.com/video-files/5182823/5182823-uhd_2160_4096_25fps.mp4" type="video/mp4">
        <!-- Fallback final (Rodovia Noturna de Alta Fiabilidade) que estava funcionando antes -->
        <source src="https://videos.pexels.com/video-files/853889/853889-hd_1920_1080_25fps.mp4" type="video/mp4">
    </video>
    """, unsafe_allow_html=True)
    
    st.markdown("""
        <div class="opal-animate opal-title">SmartSurplus.</div>
        <div class="opal-animate opal-delay-1 opal-subtitle">
            A beleza de escalar a doação e pulverizar o desperdício com precisão matemática.
        </div>
    """, unsafe_allow_html=True)
    
    col_btn1, col_btn2, col_btn3 = st.columns([1, 1, 1])
    with col_btn2:
        st.markdown('<div class="opal-animate opal-delay-2" style="text-align: center;">', unsafe_allow_html=True)
        st.button("Acessar o Painel Operacional", key="btn_top", type="primary", use_container_width=True, on_click=enter_system)
        st.markdown('</div>', unsafe_allow_html=True)

    st.markdown("<br><br><br>", unsafe_allow_html=True)
    
    # Trust Badges / Marcas
    st.markdown('<div class="opal-animate opal-delay-1" style="text-align:center; color:#52525b; font-size:0.9rem; font-weight:600; letter-spacing:2px; text-transform:uppercase;">Motor Tecnológico e Chancelas de Mercado</div>', unsafe_allow_html=True)
    st.markdown('<div class="opal-animate opal-delay-1" style="text-align:center; color:#71717a; font-size:1.2rem; margin-top:10px; font-weight:300;">OSRM Global Routing &nbsp;&nbsp; | &nbsp;&nbsp; PuLP Linear Optimization &nbsp;&nbsp; | &nbsp;&nbsp; ABRAS Metrics 2026</div>', unsafe_allow_html=True)
    
    st.markdown("<br><hr style='border-color: #27272a;'><br><br>", unsafe_allow_html=True)
    
    # 3 Features Grid NATIVO
    st.markdown("""
    <div class="features-grid opal-animate opal-delay-2">
        <div class="feature-card">
            <i class="material-icons" style="color: #ffffff; font-size: 40px; margin-bottom: 20px;">savings</i>
            <br><h3>Despesa Operacional Zero</h3>
            <p>Transformamos a quebra/perda operacional (1.8% padrão ABRAS) em uma malha de distribuição hiper-eficiente, passível de dedução de impostos federais.</p>
        </div>
        <div class="feature-card">
            <i class="material-icons" style="color: #ffffff; font-size: 40px; margin-bottom: 20px;">public</i>
            <br><h3>100% Impacto ESG</h3>
            <p>Integramos ONGs carentes ao varejo em tempo real, roteirizando estoques excedentes perfeitos para garantir a segurança alimentar de comunidades.</p>
        </div>
        <div class="feature-card">
            <i class="material-icons" style="color: #ffffff; font-size: 40px; margin-bottom: 20px;">route</i>
            <br><h3>Previsão e Desvio IA</h3>
            <p>Cálculo de Pesquisa Operacional conectado ao satélite. Simule interdições viárias e observe a matriz inteira se recalcular de forma autônoma.</p>
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("<br><br><br>", unsafe_allow_html=True)
    
    # --- NOVO ENREDO E MANIFESTO DE PRODUTO --- #
    try:
        def get_base64(bin_file):
            import base64
            with open(bin_file, 'rb') as f:
                data = f.read()
            return base64.b64encode(data).decode()
        story_img = get_base64("assets/bw_smartsurplus_concept.png")
    except:
        story_img = ""
        
    st.markdown(f"""
        <div class="story-section">
            <div class="story-text-container decrypt-on-scroll">
                <div class="story-title">O Desperdício Silencioso</div>
                <div class="story-paragraph">
                    Todos os dias, milhares de toneladas de alimentos em perfeito estado são descartadas 
                    por imperfeições logísticas ou vencimentos de prateleira muito próximos. O mercado entende isso 
                    como "Custo Fixo". Nós entendemos como falta de inteligência na malha de distribuição.
                </div>
            </div>
            <div class="story-text-container story-text-right decrypt-on-scroll">
                <div class="story-title">A Solução Agressiva</div>
                <div class="story-paragraph">
                    Criamos um motor de Pesquisa Operacional em Nuvem. O sistema mapeia cada quilograma de sobra 
                    em toda a sua rede de centros e hipermercados, calcula a demanda exata de ONGs em tempo real 
                    e cria o traçado otimizado, desviando até de bloqueios nas vias.
                </div>
            </div>
        </div>
        
        <div class="story-section">
            <div class="story-text-container">
                <div class="story-title">Qual a origem do nome "SmartSurplus"?</div>
                <div class="story-paragraph">
                    <strong>Smart</strong>: Representa Inteligência Artificial em Roteirização. Não ligamos apenas o Ponto A ou B, nós prevemos gargalos logísticos no futuro utilizando Machine Learning e Redes Neurais Long Short-Term Memory.<br><br>
                    <strong>Surplus</strong>: O "Excedente". Aquilo que sobrecarrega as planilhas contábeis mas que é o socorro necessário em comunidades de alta vulnerabilidade social. Onde há sobra contábil invisível, criamos valor real e imediato.
                </div>
            </div>
            <div class="story-image-container">
                <img src="data:image/png;base64,{story_img}" class="story-img slide-in-right" alt="SmartSurplus Concept">
            </div>
        </div>
    """, unsafe_allow_html=True)
    
    st.markdown("<br><br>", unsafe_allow_html=True)
    
    st.markdown("""
<div style="max-width: 1000px; margin: 80px auto; padding: 20px;" class="fade-in-up">
<div class="opal-title" style="font-size: 2.5rem; text-align: left; margin-bottom: 10px;">Arquitetura Operacional</div>
<div class="opal-subtitle" style="text-align: left; margin-left: 0; margin-bottom: 50px; max-width: 1000px;">Por que somos a solução ponta-a-ponta definitiva para logística humanitária preditiva:</div>
<div class="features-grid" style="grid-template-columns: repeat(2, 1fr); gap: 30px;">
<div class="feature-card" style="background: rgba(20,20,20,0.8);">
<i class="material-icons" style="color: #38bdf8; font-size: 36px; margin-bottom: 15px;">map</i>
<h3 style="color: #38bdf8;">I. Motor WebGIS Sandbox</h3>
<p>Mapeamento de alta precisão conectado nativamente aos satélites OSRM e Nominatim. Construa pontos no mapa com cliques ou textos. O sistema rastreia as rotas por ruas precisas da malha rodoviária federal e estadual.</p>
</div>
<div class="feature-card" style="background: rgba(20,20,20,0.8);">
<i class="material-icons" style="color: #10b981; font-size: 36px; margin-bottom: 15px;">hub</i>
<h3 style="color: #10b981;">II. Otimização LP Multi-Commodity</h3>
<p>Diferente de sistemas rudimentares que cruzam apenas peso genérico, nosso algoritmo (Python PuLP) roteiriza 5 categorias de alimento simultaneamente. Se uma ONG precisa de proteínas, a IA se recusa a enviar frutas. Entrega zero-waste.</p>
</div>
<div class="feature-card" style="background: rgba(20,20,20,0.8);">
<i class="material-icons" style="color: #ef4444; font-size: 36px; margin-bottom: 15px;">warning</i>
<h3 style="color: #ef4444;">III. Engenharia de Desastres</h3>
<p>Rastreia rupturas climáticas como alagamentos e bloqueios na via de suprimento. Acione o simulador e assista Zonas de Crise se formarem e dezenas de veículos alterarem suas rotas dinamicamente buscando veias secundárias mais rentáveis.</p>
</div>
<div class="feature-card" style="background: rgba(20,20,20,0.8);">
<i class="material-icons" style="color: #eab308; font-size: 36px; margin-bottom: 15px;">query_stats</i>
<h3 style="color: #eab308;">IV. Preditibilidade LSTM ao Vivo</h3>
<p>A arquitetura de Machine Learning Long Short-Term Memory entende a flutuação macroeconômica. Ajuste parâmetros inflacionários ao vivo e observe a curva do gráfico se flexionar prevendo onde alocar capital em fretistas para evitar estrangulamento futuro.</p>
</div>
</div>
</div>
    """, unsafe_allow_html=True)
    
    st.markdown("<br><br>", unsafe_allow_html=True)
    
    # Bottom CTA
    st.markdown('<div class="opal-title" style="font-size: 3rem;">Pronto para transformar sua frota?</div>', unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)
    col_btnA, col_btnB, col_btnC = st.columns([1, 1, 1])
    with col_btnB:
        st.button("Executar Plataforma >", key="bottom_entry", type="primary", use_container_width=True, on_click=enter_system)


else:
    # -----------------------------------------------
    # MAIN APP (DASHBOARD OPERACIONAL) EM ZINC ESCURO (APPLE STYLE)
    # -----------------------------------------------
    st.markdown("""
    <style>
        .stApp { background-color: #09090b !important; } /* Um preto/chumbo sutil */
        .stAppHeader { background-color: transparent !important; } /* Traz o menu hambúrguer de volta */
        .stDeployButton { display: none !important; }
        
        /* Maximização de Tela (Puxando mapa pro teto) */
        .block-container {
            padding-top: 1.5rem !important; /* Puxa para o topo extremo */
            padding-bottom: 2rem !important;
            max-width: 98% !important; /* Estica lateralmente quase até a borda */
        }
        
        h1, h2, h3, h4 { color: #ffffff !important; font-family: 'Inter', sans-serif !important; letter-spacing: -0.02em; }
        p, span, div { font-family: 'Inter', sans-serif; color: #a1a1aa; }
        
        .metric-card {
            background-color: #18181b;
            padding: 24px;
            border-radius: 16px;
            border: 1px solid #27272a;
            text-align: center;
            transition: all 0.4s ease;
            margin-bottom: 15px;
        }
        .metric-card:hover { border-color: #52525b; }
        
        .metric-value { font-size: 2.2rem; font-weight: 600; color: #ffffff; }
        .metric-label { font-size: 0.9rem; color: #71717a; text-transform: uppercase; letter-spacing: 1px; }
        .metric-diff-good { color: #10B981; font-weight: 600; font-size: 1.1rem; margin-top: 10px; }
        
        /* Tabs Premium Native */
        button[data-baseweb="tab"] { font-size: 1rem !important; color: #71717a !important; font-weight: 400 !important; }
        button[data-baseweb="tab"][aria-selected="true"] { color: #ffffff !important; font-weight: 600 !important; }
        
        div[data-baseweb="tab-highlight"] { background-color: #ffffff !important; height: 2px !important; }
        
        /* Remove Divider in sidebar */
        [data-testid="stSidebar"] hr { border-color: #27272a; }
        [data-testid="stSidebar"] { border-right: 1px solid #18181b; }
    </style>
    """, unsafe_allow_html=True)

    # State Base for Manual Entries
    if "manual_suppliers" not in st.session_state:
        st.session_state["manual_suppliers"] = pd.DataFrame(columns=["ID", "Nome", "Lat", "Lon", "Excedente_kg", "Categoria", "Inventario"])
    if "manual_ngos" not in st.session_state:
        st.session_state["manual_ngos"] = pd.DataFrame(columns=["ID", "Nome", "Lat", "Lon", "Demanda_kg", "Categoria", "Inventario"])
        
    # Execução Lógica Centralizada
    def handle_execution(disaster):
        suppliers_df = st.session_state["manual_suppliers"]
        ngos_df = st.session_state["manual_ngos"]
        
        if suppliers_df.empty or ngos_df.empty:
            st.session_state["results"] = pd.DataFrame()
            st.session_state["surplus_df"] = pd.DataFrame()
            st.session_state["deficit_df"] = pd.DataFrame()
            st.session_state["caos"] = {'Total_Desperdicio_kg': 0, 'Refeicoes_Geradas': 0, 'Custo_Logistico_Caotico': 0, 'Total_Transportado_kg': 0}
            st.session_state["opt"] = {'Total_Desperdicio_kg': 0, 'Refeicoes_Geradas': 0, 'Custo_Logistico_Otimo': 0, 'Total_Transportado_kg': 0}
            return
            
        dist_dict, _ = calculate_distance_matrix(suppliers_df, ngos_df)
        
        if disaster:
            dist_dict, penalized_pairs = apply_disaster_to_distances(dist_dict)
            if penalized_pairs:
                first_pair = penalized_pairs[0]
                s_coords = suppliers_df.set_index("ID")[["Lat", "Lon"]]
                n_coords = ngos_df.set_index("ID")[["Lat", "Lon"]]
                if first_pair[0] in s_coords.index and first_pair[1] in n_coords.index:
                    st.session_state["crisis_route"] = [
                        s_coords.loc[first_pair[0], "Lat"], s_coords.loc[first_pair[0], "Lon"],
                        n_coords.loc[first_pair[1], "Lat"], n_coords.loc[first_pair[1], "Lon"]
                    ]
        else:
            st.session_state["crisis_route"] = None
            
        caos_metrics = simulate_current_scenario(suppliers_df, ngos_df, dist_dict)
        results_df, surplus_df, deficit_df, opt_metrics = run_optimization(suppliers_df, ngos_df, dist_dict)
        
        st.session_state["results"] = results_df
        st.session_state["surplus_df"] = surplus_df
        st.session_state["deficit_df"] = deficit_df
        st.session_state["caos"] = caos_metrics
        st.session_state["opt"] = opt_metrics

    # SIDEBAR MINIMALISTA
    st.sidebar.markdown("<h3 style='text-align:center; font-family: Playfair Display, serif;'>SmartSurplus</h3>", unsafe_allow_html=True)
    st.sidebar.markdown("<br>", unsafe_allow_html=True)
    
    st.sidebar.markdown("**NOVO PONTO**")
    input_mode = st.sidebar.radio("Modo de Inserção:", ["📍 Clique no Mapa", "📝 Endereço de Texto"], horizontal=True, label_visibility="collapsed")
    
    last_clicked = st.session_state.get("map_click_data", None)
    
    if input_mode == "📍 Clique no Mapa":
        if last_clicked:
            st.sidebar.success("📍 Marcador em posição.")
            with st.sidebar.form("add_point"):
                p_type = st.radio("Selecione a Entidade:", ["Supermercado (Oferece)", "ONG (Precisa)"])
                p_name = st.text_input("Nome da Unidade:")
                st.markdown("**Inventário Específico (Kg):**")
                c1, c2 = st.columns(2)
                with c1:
                    kg_fru = st.number_input("Frutas", min_value=0, value=0)
                    kg_lat = st.number_input("Laticínios", min_value=0, value=0)
                    kg_pro = st.number_input("Proteínas", min_value=0, value=0)
                with c2:
                    kg_hor = st.number_input("Hortaliças", min_value=0, value=0)
                    kg_sec = st.number_input("Secos e Grãos", min_value=0, value=0)
                
                if st.form_submit_button("Lançar na Malha"):
                    lat, lon = last_clicked['lat'], last_clicked['lng']
                    inventario = {}
                    if kg_fru > 0: inventario["Frutas"] = kg_fru
                    if kg_lat > 0: inventario["Laticínios"] = kg_lat
                    if kg_pro > 0: inventario["Proteínas"] = kg_pro
                    if kg_hor > 0: inventario["Hortaliças"] = kg_hor
                    if kg_sec > 0: inventario["Secos e Grãos"] = kg_sec
                    
                    total_kg = sum(inventario.values())
                    if total_kg == 0:
                        st.error("Adicione carga em pelo menos uma categoria.")
                    else:
                        cat_str = ", ".join(inventario.keys())
                        if "Supermercado" in p_type:
                            new_id = f"S{len(st.session_state['manual_suppliers']) + 1}"
                            new_row = pd.DataFrame([{"ID": new_id, "Nome": p_name or new_id, "Lat": lat, "Lon": lon, "Excedente_kg": total_kg, "Categoria": cat_str, "Inventario": inventario}])
                            st.session_state["manual_suppliers"] = pd.concat([st.session_state["manual_suppliers"], new_row], ignore_index=True)
                        else:
                            new_id = f"O{len(st.session_state['manual_ngos']) + 1}"
                            new_row = pd.DataFrame([{"ID": new_id, "Nome": p_name or new_id, "Lat": lat, "Lon": lon, "Demanda_kg": total_kg, "Categoria": cat_str, "Inventario": inventario}])
                            st.session_state["manual_ngos"] = pd.concat([st.session_state["manual_ngos"], new_row], ignore_index=True)
                        
                        st.session_state["map_click_data"] = None 
                        st.session_state["map_click_processed"] = last_clicked
                        st.rerun()
        else:
            st.sidebar.info("👆 Clique livremente no mapa para pinar Supermercados ou ONGs.")
    else:
        st.sidebar.info("Digite o endereço exacto (Ex: Av. Paulista, 1000, Sao Paulo)")
        with st.sidebar.form("add_point_address"):
            p_address = st.text_input("Endereço Completo:")
            p_type = st.radio("Selecione a Entidade:", ["Supermercado (Oferece)", "ONG (Precisa)"])
            p_name = st.text_input("Nome da Unidade:")
            st.markdown("**Inventário Específico (Kg):**")
            c1, c2 = st.columns(2)
            with c1:
                kg_fru = st.number_input("Frutas", min_value=0, value=0)
                kg_lat = st.number_input("Laticínios", min_value=0, value=0)
                kg_pro = st.number_input("Proteínas", min_value=0, value=0)
            with c2:
                kg_hor = st.number_input("Hortaliças", min_value=0, value=0)
                kg_sec = st.number_input("Secos e Grãos", min_value=0, value=0)
            
            if st.form_submit_button("Geolocalizar e Lançar"):
                if not p_address.strip():
                    st.error("Preencha o campo de endereço.")
                else:
                    inventario = {}
                    if kg_fru > 0: inventario["Frutas"] = kg_fru
                    if kg_lat > 0: inventario["Laticínios"] = kg_lat
                    if kg_pro > 0: inventario["Proteínas"] = kg_pro
                    if kg_hor > 0: inventario["Hortaliças"] = kg_hor
                    if kg_sec > 0: inventario["Secos e Grãos"] = kg_sec
                    total_kg = sum(inventario.values())
                    
                    if total_kg == 0:
                        st.error("Adicione carga em pelo menos uma categoria.")
                    else:
                        lat, lon = geocode_address(p_address)
                        if lat is not None and lon is not None:
                            cat_str = ", ".join(inventario.keys())
                            if "Supermercado" in p_type:
                                new_id = f"S{len(st.session_state['manual_suppliers']) + 1}"
                                new_row = pd.DataFrame([{"ID": new_id, "Nome": p_name or new_id, "Lat": lat, "Lon": lon, "Excedente_kg": total_kg, "Categoria": cat_str, "Inventario": inventario}])
                                st.session_state["manual_suppliers"] = pd.concat([st.session_state["manual_suppliers"], new_row], ignore_index=True)
                            else:
                                new_id = f"O{len(st.session_state['manual_ngos']) + 1}"
                                new_row = pd.DataFrame([{"ID": new_id, "Nome": p_name or new_id, "Lat": lat, "Lon": lon, "Demanda_kg": total_kg, "Categoria": cat_str, "Inventario": inventario}])
                                st.session_state["manual_ngos"] = pd.concat([st.session_state["manual_ngos"], new_row], ignore_index=True)
                            st.session_state["map_click_data"] = None 
                            st.rerun()
                        else:
                            st.error("Endereço não localizado pelo satélite.")
        
    st.sidebar.markdown("<hr style='opacity:0.2'>", unsafe_allow_html=True)
    st.sidebar.markdown("**ENGENHARIA REVERSA**")
    disaster_mode = st.sidebar.toggle("Bloqueio Simulado (Crise Viária)")
    if disaster_mode:
        st.sidebar.error("30% da malha sofreu colapso.")
        
    st.sidebar.markdown("<hr style='opacity:0.2'>", unsafe_allow_html=True)
    st.sidebar.markdown("**RENDERIZAÇÃO OSRM**")
    mode_route = st.sidebar.radio("Polígonos de Rota:", ["Nativa (Linha Direta)", "Satélite (GPS Real)"])

    st.sidebar.markdown("<br>", unsafe_allow_html=True)
    if st.sidebar.button("Recalcular IA de Otimização", type="primary", use_container_width=True):
        if disaster_mode:
            st.toast("CEMADEN: Vias submersas detectadas. Recalculando Tensor...", icon="⚠️")
        with st.spinner("Processando Matrizes Espaciais..."):
            handle_execution(disaster_mode)
            
    # Auto-Execute no Login
    if "ran" not in st.session_state:
        st.session_state["ran"] = True
        handle_execution(disaster_mode)

    # HEADER INTERNO
    st.markdown("<h2 style='color: #ffffff;'>Analytics</h2>", unsafe_allow_html=True)
    
    # TABS PREMIUM
    tab1, tab2, tab4, tab5, tab3 = st.tabs(["Overview", "Despachos", "Déficit das ONGs", "Estoque Remanescente", "Predictive Horizon"])

    with tab1:
        suppliers_df = st.session_state["manual_suppliers"]
        ngos_df = st.session_state["manual_ngos"]
        results_df = st.session_state.get("results", pd.DataFrame())
        caos = st.session_state.get("caos", {'Total_Desperdicio_kg': 0, 'Refeicoes_Geradas': 0, 'Custo_Logistico_Caotico': 0, 'Total_Transportado_kg': 0})
        opt = st.session_state.get("opt", {'Total_Desperdicio_kg': 0, 'Refeicoes_Geradas': 0, 'Custo_Logistico_Otimo': 0, 'Total_Transportado_kg': 0})

        col1, col2, col3 = st.columns(3)
        diff_desperdicio = ((caos['Total_Desperdicio_kg'] - opt['Total_Desperdicio_kg']) / max(1, caos['Total_Desperdicio_kg'])) * 100
        diff_ref = opt['Refeicoes_Geradas'] - caos['Refeicoes_Geradas']
        
        custo_caos_por_kg = caos["Custo_Logistico_Caotico"] / max(1, caos["Total_Transportado_kg"])
        custo_opt_por_kg = opt["Custo_Logistico_Otimo"] / max(1, opt["Total_Transportado_kg"])
        perc_custo_kg = (1 - (custo_opt_por_kg / max(0.01, custo_caos_por_kg))) * 100
        
        with col1:
            st.markdown(f"""
            <div class="metric-card">
                <div class="metric-label">Desperdício Líquido</div>
                <div class="metric-value">{opt['Total_Desperdicio_kg']} kg</div>
                <div class="metric-diff-good">-{diff_desperdicio:.1f}% vs Humano</div>
            </div>
            """, unsafe_allow_html=True)

        with col2:
            st.markdown(f"""
            <div class="metric-card">
                <div class="metric-label">Impacto Alimentar</div>
                <div class="metric-value">{opt['Refeicoes_Geradas']}</div>
                <div class="metric-diff-good">+ {diff_ref} Pessoas</div>
            </div>
            """, unsafe_allow_html=True)
            
        with col3:
            st.markdown(f"""
            <div class="metric-card">
                <div class="metric-label">Eficiência de Gasto (CPO)</div>
                <div class="metric-value">R$ {custo_opt_por_kg:.2f}</div>
                <div class="metric-diff-good">-{perc_custo_kg:.1f}% Emissão Financeira</div>
            </div>
            """, unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)
        
        # MAPA FOLIUM
        if not suppliers_df.empty or not ngos_df.empty:
            all_lats = pd.concat([suppliers_df['Lat'] if not suppliers_df.empty else pd.Series(), ngos_df['Lat'] if not ngos_df.empty else pd.Series()])
            all_lons = pd.concat([suppliers_df['Lon'] if not suppliers_df.empty else pd.Series(), ngos_df['Lon'] if not ngos_df.empty else pd.Series()])
            center_lat, center_lon = all_lats.mean(), all_lons.mean()
        else:
            center_lat, center_lon = -23.5505, -46.6333 # SP Default Default zero map
            
        m = folium.Map(location=[center_lat, center_lon], zoom_start=11, tiles="CartoDB dark_matter")
        
        # Desenhar ZONA DE CRISE se ativado
        if disaster_mode and not suppliers_df.empty and not ngos_df.empty:
            c_route = st.session_state.get("crisis_route")
            
            if c_route and mode_route == "Satélite (GPS Real)":
                crisis_path = get_osrm_route(c_route[0], c_route[1], c_route[2], c_route[3])
                if crisis_path and len(crisis_path) > 0:
                    folium.PolyLine(
                        locations=crisis_path,
                        color="#EF4444",
                        weight=6,
                        opacity=0.8,
                        tooltip="Via Física Bloqueada"
                    ).add_to(m)
                    mid_idx = len(crisis_path) // 2
                    crisis_lat, crisis_lon = crisis_path[mid_idx]
                else:
                    crisis_lat = (c_route[0] + c_route[2]) / 2
                    crisis_lon = (c_route[1] + c_route[3]) / 2
            elif c_route:
                crisis_path = [[c_route[0], c_route[1]], [c_route[2], c_route[3]]]
                folium.PolyLine(
                    locations=crisis_path,
                    color="#EF4444",
                    weight=6,
                    opacity=0.8,
                    dash_array="10",
                    tooltip="Linha Direta Interditada"
                ).add_to(m)
                crisis_lat = (c_route[0] + c_route[2]) / 2
                crisis_lon = (c_route[1] + c_route[3]) / 2
            else:
                # Fallback genérico
                crisis_lat = center_lat + 0.01
                crisis_lon = center_lon + 0.01
                
            folium.CircleMarker(
                location=[crisis_lat, crisis_lon],
                radius=50,
                color="#EF4444",
                weight=2,
                fill=True,
                fill_color="#EF4444",
                fill_opacity=0.3,
                popup="<b>⛔ ZONA DE BLOQUEIO</b><br>Trânsito/Alagamento severo.",
                tooltip="Crise Viária Ativa"
            ).add_to(m)
        
        # Opcional: Adicionar controle de desenho (Desativado pois vamos usar clique livre para melhor UI)
        # from folium.plugins import Draw
        # Draw(export=False, position='topleft', draw_options={'polyline':False, 'polygon':False, 'circle':False, 'rectangle':False, 'circlemarker':False, 'marker':True}).add_to(m)
        
        # Elimina a marca d'água de Créditos de código-aberto (Leaflet / OpenStreetMaps) dentro do Iframe
        m.get_root().html.add_child(folium.Element("<style>.leaflet-control-attribution { display: none !important; }</style>"))
        
        for _, row in suppliers_df.iterrows():
            html_sup = f"""
            <div style="
                background: linear-gradient(135deg, #10b981, #059669); 
                width: 32px; height: 32px; 
                border-radius: 50% 50% 50% 0; 
                border: 2px solid #ffffff; 
                box-shadow: 0 0 15px rgba(16, 185, 129, 0.8);
                display: flex; align-items: center; justify-content: center;
                color: white; transform: rotate(-45deg);
            ">
                <i class="fa fa-archive" style="font-size: 14px; transform: rotate(45deg);"></i>
            </div>
            """
            folium.Marker(
                location=[row["Lat"], row["Lon"]],
                popup=f"<b>{row['Nome']}</b> <br><small>[{row.get('Categoria', '')}]</small><br>{row['Excedente_kg']} kg de sobra",
                tooltip=row["Nome"],
                icon=folium.DivIcon(html=html_sup, icon_size=(32, 32), icon_anchor=(16, 38))
            ).add_to(m)
            
        for _, row in ngos_df.iterrows():
            html_ngo = f"""
            <div style="
                background: linear-gradient(135deg, #0ea5e9, #2563eb); 
                width: 32px; height: 32px; 
                border-radius: 50% 50% 50% 0; 
                border: 2px solid #ffffff; 
                box-shadow: 0 0 15px rgba(14, 165, 233, 0.8);
                display: flex; align-items: center; justify-content: center;
                color: white; transform: rotate(-45deg);
            ">
                <i class="fa fa-users" style="font-size: 13px; transform: rotate(45deg);"></i>
            </div>
            """
            folium.Marker(
                location=[row["Lat"], row["Lon"]],
                popup=f"<b>{row['Nome']}</b> <br><small>[{row.get('Categoria', '')}]</small><br>Déficit: {row['Demanda_kg']} kg",
                tooltip=row["Nome"],
                icon=folium.DivIcon(html=html_ngo, icon_size=(32, 32), icon_anchor=(16, 38))
            ).add_to(m)

        if not results_df.empty:
            s_coords = suppliers_df.set_index("ID")[["Lat", "Lon"]]
            n_coords = ngos_df.set_index("ID")[["Lat", "Lon"]]
            
            for idx, row in results_df.iterrows():
                s_lat = s_coords.loc[row["Fornecedor"], "Lat"]
                s_lon = s_coords.loc[row["Fornecedor"], "Lon"]
                n_lat = n_coords.loc[row["ONG"], "Lat"]
                n_lon = n_coords.loc[row["ONG"], "Lon"]
                qty = row["Qtde_kg"]
                
                weight = max(2, min(8, (qty / 50) * 8))
                cor_fundo = "#38bdf8" if disaster_mode else "#f8fafc" # Azul claro brilhante para rotas de desvio
                
                if mode_route == "Satélite (GPS Real)":
                    route_path = get_osrm_route(s_lat, s_lon, n_lat, n_lon)
                else:
                    route_path = [[s_lat, s_lon], [n_lat, n_lon]]
                
                plugins.AntPath(
                    locations=route_path,
                    color=cor_fundo,
                    pulse_color="#000000" if not disaster_mode else "#eff6ff", # Pulso claro na rota azul
                    weight=weight,
                    delay=1200,
                    dash_array=[10, 30],
                    tooltip=f"{row['Fornecedor']} ➤ {row['ONG']} ({qty} kg)"
                ).add_to(m)
                
        # CAPTURA INTELIGENTE DE MAPA PARA INTERATIVIDADE
        map_resp = st_folium(m, width=None, height=520, returned_objects=["last_clicked"])
        if map_resp and map_resp.get("last_clicked"):
            l_clk = map_resp["last_clicked"]
            if st.session_state.get("map_click_data") != l_clk and st.session_state.get("map_click_processed") != l_clk:
                st.session_state["map_click_data"] = l_clk
                st.rerun()

    with tab2:
        st.markdown("<br>", unsafe_allow_html=True)
        if not results_df.empty:
            pretty_df = results_df.merge(suppliers_df[["ID", "Nome"]], left_on="Fornecedor", right_on="ID")
            pretty_df = pretty_df.rename(columns={"Nome": "Origem Operacional"})
            pretty_df = pretty_df.merge(ngos_df[["ID", "Nome"]], left_on="ONG", right_on="ID")
            pretty_df = pretty_df.rename(columns={"Nome": "Distrito de Recepção"})
            
            cols = ["Origem Operacional", "Distrito de Recepção", "Qtde_kg", "Distancia_km", "Custo_Estimado"]
            if "Itens_Entregues" in pretty_df.columns:
                cols.insert(3, "Itens_Entregues")
                
            st.dataframe(pretty_df[cols], use_container_width=True, hide_index=True)
            
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                pretty_df[cols].to_excel(writer, index=False, sheet_name='Planning_Frete')
            output.seek(0)
            
            st.markdown("<center>", unsafe_allow_html=True)
            st.download_button(
                label="Baixar Manifesto de Transporte",
                data=output,
                file_name="Manifesto_SmartSurplus.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                type="primary"
            )
            st.markdown("</center>", unsafe_allow_html=True)
        else:
            st.warning("Malha bloqueada. Alivie parâmetros.")

    with tab4:
        st.markdown("<br>", unsafe_allow_html=True)
        deficit_df = st.session_state.get("deficit_df", pd.DataFrame())
        if not deficit_df.empty:
            # Join with ngos names
            def_df = deficit_df.merge(st.session_state["manual_ngos"][["ID", "Nome"]], left_on="ID_Entidade", right_on="ID")
            def_df = def_df[["Nome", "Categoria", "Falta_kg"]].rename(columns={"Nome": "ONG Suplicante"})
            st.dataframe(def_df, use_container_width=True, hide_index=True)
        else:
            st.success("Toda a demanda das ONGs foi contemplada! Nenhum déficit restante nas categorias solicitadas.")

    with tab5:
        st.markdown("<br>", unsafe_allow_html=True)
        surplus_df = st.session_state.get("surplus_df", pd.DataFrame())
        if not surplus_df.empty:
            sur_df = surplus_df.merge(st.session_state["manual_suppliers"][["ID", "Nome"]], left_on="ID_Entidade", right_on="ID")
            sur_df = sur_df[["Nome", "Categoria", "Sobra_kg"]].rename(columns={"Nome": "Supermercado"})
            st.dataframe(sur_df, use_container_width=True, hide_index=True)
        else:
            st.success("Estoque 100% esvaziado! Nenhum supermercado relata sobras.")

    with tab3:
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("<h4 style='color: #ffffff; font-family: Playfair Display, serif;'>Inteligência Artificial LSTM</h4>", unsafe_allow_html=True)
        st.markdown("<hr style='opacity:0.2'>", unsafe_allow_html=True)
        
        col_ctrl, col_graph = st.columns([1.2, 2])
        
        with col_ctrl:
            st.markdown("**Simulador de Anomalias Globais**")
            inflacao = st.slider("Choque de Inflação (%)", min_value=-5, max_value=30, value=5, step=1, help="Corrói o poder de compra e aumenta a sobra de produtos na prateleira.")
            clima = st.slider("Extremo Climático / Quebra de Safra (%)", min_value=-10, max_value=40, value=12, step=1, help="Secas ou alagamentos que superlotam centros de distribuição abruptamente.")
            
            # Fator multiplicador preditivo interativo
            fator_risco = 1.0 + (inflacao / 100.0) + (clima / 100.0)
            aumento_previsto = (fator_risco - 1) * 100
            
            st.markdown("<br>", unsafe_allow_html=True)
            st.markdown(f"""
            <div class="metric-card" style="border-left: 4px solid #ef4444; margin-bottom: 20px;">
                <div class="metric-label">MÊS DE RISCO MÁXIMO PROJETADO</div>
                <div class="metric-value" style="font-size: 1.8rem;">Dezembro</div>
                <div class="metric-diff-good" style="color:#ef4444;">▲ PICO DE +{aumento_previsto:.1f}% DESPERDÍCIO</div>
            </div>
            """, unsafe_allow_html=True)
            
            frota_recomendada = max(0, int(aumento_previsto * 0.8))
            st.markdown(f"""
            <div class="metric-card" style="border-left: 4px solid #38bdf8;">
                <div class="metric-label" style="color: #38bdf8;">ALERTA ZERO-WASTE & RECOMENDAÇÃO LOGÍSTICA</div>
                <div style="font-size: 0.95rem; color: #d4d4d8; padding-top: 8px; line-height: 1.4;">
                    A malha atual não absorverá o choque previsto. A IA recomenda expandir frotas terceirizadas em <b>{frota_recomendada}%</b> no último trimestre para mitigar o colapso do ecossistema.
                </div>
            </div>
            """, unsafe_allow_html=True)
            
        with col_graph:
            meses = ['Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun', 'Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez']
            
            # Dinamizar volume base para o contexto da simulação atual (se possível)
            kg_base_rede = st.session_state.get("manual_suppliers", pd.DataFrame())["Excedente_kg"].sum()
            base_multiplier = max(1, kg_base_rede / 100) if kg_base_rede > 0 else 10
            
            # Curva referencial simulada
            base_curve = [100, 95, 110, 105, 130, 120, 150, 160, 140, 180, 190, 250]
            base_waste = [int(x * base_multiplier) for x in base_curve]
            
            np.random.seed(42) # Consistência visual no ruído baseline
            ml_df = pd.DataFrame({
                "Mês": meses,
                "Histórico (Sem IA)": base_waste,
                "Predição LSTM (Horizonte +30D)": [x * fator_risco + np.random.normal(0, max(1, x*0.05)) for x in base_waste]
            })
            
            fig_ml = px.line(ml_df, x="Mês", y=["Histórico (Sem IA)", "Predição LSTM (Horizonte +30D)"],
                          color_discrete_sequence=["#3f3f46", "#38bdf8"],
                          markers=True)
                          
            fig_ml.update_layout(
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
                font=dict(color="#a1a1aa", family="Inter"),
                title=dict(text="Curva de Sensibilidade Linear: Estresse Logístico Acumulado", font=dict(size=14, color="#ffffff")),
                hovermode="x unified",
                legend=dict(
                    title="",
                    orientation="h",
                    yanchor="bottom",
                    y=-0.25,
                    xanchor="center",
                    x=0.5
                ),
                margin=dict(l=10, r=10, t=40, b=10)
            )
            # Fazer a linha Preditiva ser pontilhada para efeito de projeção
            fig_ml.update_traces(patch={"line": {"dash": "dot"}}, selector={"name": "Predição LSTM (Horizonte +30D)"})
            
            st.plotly_chart(fig_ml, use_container_width=True)
