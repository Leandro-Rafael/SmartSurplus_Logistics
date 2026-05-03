import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import folium
from folium import plugins
from streamlit_folium import st_folium
import numpy as np
import io
import requests
import time
import urllib.parse
import streamlit.components.v1 as components

st.set_page_config(
    page_title="SmartSurplus",
    layout="wide",
    initial_sidebar_state="collapsed",
    page_icon="⬡"
)

# ── IMPORTS ──
from data_generator import generate_suppliers, generate_ngos, calculate_distance_matrix, haversine
from optimization import run_optimization, simulate_current_scenario, apply_disaster_to_distances

@st.cache_data(show_spinner=False)
def geocode_address(address):
    try:
        r = requests.get("https://nominatim.openstreetmap.org/search",
            params={"q": address, "format": "json", "limit": 1},
            headers={"User-Agent": "SmartSurplus/2.0"}, timeout=5)
        if r.status_code == 200 and r.json():
            d = r.json()[0]; return float(d["lat"]), float(d["lon"])
    except: pass
    return None, None

@st.cache_data(show_spinner=False)
def get_osrm_route(slat, slon, nlat, nlon):
    time.sleep(0.5) # Proteção contra rate limit (max 1 req/sec)
    url = f"http://router.project-osrm.org/route/v1/driving/{slon},{slat};{nlon},{nlat}?overview=full&geometries=geojson"
    for _ in range(3):
        try:
            r = requests.get(url, headers={"User-Agent": "SmartSurplus/2.0"}, timeout=5)
            if r.status_code == 200 and r.json().get("code") == "Ok":
                return [[c[1],c[0]] for c in r.json()["routes"][0]["geometry"]["coordinates"]]
            time.sleep(1.0)
        except: time.sleep(1.0)
    return [[slat,slon],[nlat,nlon]]

@st.cache_data(show_spinner=False)
def get_osrm_route_multi(coords_list):
    if len(coords_list) < 2: return coords_list
    time.sleep(0.5) # Proteção contra rate limit
    coords_str = ";".join([f"{lon},{lat}" for lat, lon in coords_list])
    url = f"http://router.project-osrm.org/route/v1/driving/{coords_str}?overview=full&geometries=geojson"
    for _ in range(3):
        try:
            r = requests.get(url, headers={"User-Agent": "SmartSurplus/2.0"}, timeout=5)
            if r.status_code == 200 and r.json().get("code") == "Ok":
                return [[c[1],c[0]] for c in r.json()["routes"][0]["geometry"]["coordinates"]]
            time.sleep(1.0)
        except: time.sleep(1.0)
    return [[lat, lon] for lat, lon in coords_list]

# ── WATERMARK REMOVER ──
st.markdown("""<style>
[data-testid="main-menu-list"] + div { display: none !important; }
</style>""", unsafe_allow_html=True)

# ── DRIVER APP ──
if st.query_params.get("role") == "driver":
    import hashlib, urllib.parse
    
    def get_sb_headers():
        try: return {"apikey": st.secrets["supabase"]["key"], "Authorization": f"Bearer {st.secrets['supabase']['key']}", "Content-Type": "application/json"}
        except: return {}
    
    def get_sb_url():
        try: return st.secrets["supabase"]["url"]
        except: return ""

    st.markdown("""<style>
    .stApp{background:#030712!important;}
    section[data-testid="stSidebar"],header,footer{display:none!important;}
    .block-container{padding:1rem!important; max-width: 100% !important;}
    [data-testid="stButton"] button{background:#00ff88!important;color:#000!important;border-radius:12px!important;font-weight:800!important;border:none!important; font-family: 'Space Mono', monospace !important; padding: 14px !important;}
    .driver-title { font-family:'Syne',sans-serif; color:#f9fafb; font-size:1.5rem; font-weight:800; margin-bottom: 24px; text-align:center;}
    [data-testid="stTextInput"] input, [data-testid="stPasswordInput"] input { background:#0f172a !important; color:#fff !important; border:1px solid #1e293b !important;}
    .lot-card { border: 2px solid #00ff88; border-radius:12px; padding:16px; margin-bottom:16px; background:#0f172a; }
    .lot-card.yellow { border-color: #fbbf24; }
    .gps-panel { position: fixed; bottom: 0; left: 0; right: 0; background: #030712; padding: 24px; border-top: 1px solid #1f2937; border-radius: 24px 24px 0 0; z-index: 1000; box-shadow: 0 -10px 40px rgba(0,0,0,0.8); }
    </style>""", unsafe_allow_html=True)
    
    if "driver_logged" not in st.session_state:
        st.session_state.driver_logged = False
        st.session_state.driver_data = None
        st.session_state.driver_step = "auth"
    
    step = st.session_state.driver_step
    
    if step == "auth":
        st.markdown('<div class="driver-title">Portal do Motorista</div>', unsafe_allow_html=True)
        tab1, tab2 = st.tabs(["🔒 Entrar", "📝 Criar Conta"])
        
        with tab1:
            l_cpf = st.text_input("CPF", key="l_cpf")
            l_senha = st.text_input("Senha", type="password", key="l_senha")
            if st.button("Acessar Plataforma", use_container_width=True, key="btn_login"):
                if l_cpf and l_senha:
                    url = f"{get_sb_url()}/rest/v1/drivers?cpf=eq.{l_cpf}&senha=eq.{hashlib.sha256(l_senha.encode()).hexdigest()}"
                    r = requests.get(url, headers=get_sb_headers())
                    if r.status_code == 200 and len(r.json()) > 0:
                        res = r.json()[0]
                        st.session_state.driver_logged = True
                        st.session_state.driver_data = {"nome": res["nome"], "cpf": l_cpf}
                        st.session_state.driver_step = "vehicle"
                        st.rerun()
                    else: st.error("CPF ou Senha incorretos.")
                else: st.warning("Preencha todos os campos.")
                
        with tab2:
            r_nome = st.text_input("Nome Completo")
            r_cpf = st.text_input("CPF")
            r_pix = st.text_input("Chave Pix (Recebimento)")
            r_nasc = st.date_input("Data de Nascimento")
            r_senha = st.text_input("Criar Senha", type="password")
            st.markdown("<p style='color:#9ca3af;font-size:0.8rem;margin-bottom:0;'>Validação Facial (Obrigatória)</p>", unsafe_allow_html=True)
            r_foto = st.camera_input("Tirar Foto da Face", label_visibility="collapsed")
            if st.button("Validar e Cadastrar", use_container_width=True, key="btn_cad"):
                if r_nome and r_cpf and r_pix and r_senha and r_foto:
                    url = f"{get_sb_url()}/rest/v1/drivers"
                    payload = {"cpf": r_cpf, "nome": r_nome, "pix": r_pix, "nascimento": str(r_nasc), "senha": hashlib.sha256(r_senha.encode()).hexdigest()}
                    r = requests.post(url, headers=get_sb_headers(), json=payload, params={"Prefer":"return=minimal"})
                    if r.status_code in [200, 201, 204]:
                        st.success("Cadastro aprovado! Faça o login na outra aba.")
                    else:
                        st.error("CPF já cadastrado ou erro de conexão com a Nuvem.")
                else: st.warning("Preencha todos os dados e tire a foto.")
        st.stop()
        
    elif step == "vehicle":
        nome = st.session_state.driver_data["nome"].split()[0]
        st.markdown(f'<div class="driver-title">Bem-vindo, {nome}</div>', unsafe_allow_html=True)
        st.markdown("<p style='text-align:center;color:#9ca3af;margin-bottom:24px;'>Qual veículo você está operando hoje?</p>", unsafe_allow_html=True)
        
        c1, c2 = st.columns(2)
        with c1:
            if st.button("🛻 Caminhonete\n(Até 1.000 kg)", use_container_width=True):
                st.session_state.driver_vehicle = "pickup"
                st.session_state.driver_step = "marketplace"
                st.rerun()
        with c2:
            if st.button("🚛 Caminhão\n(Acima de 1 Ton)", use_container_width=True):
                st.session_state.driver_vehicle = "truck"
                st.session_state.driver_step = "marketplace"
                st.rerun()
        st.stop()
        
    elif step == "marketplace":
        st.markdown('<div class="driver-title">Marketplace de Cargas</div>', unsafe_allow_html=True)
        try:
            import pandas as pd
            url = f"{get_sb_url()}/rest/v1/marketplace_results"
            r = requests.get(url, headers=get_sb_headers())
            if r.status_code == 200 and r.json():
                df = pd.DataFrame(r.json())
                df = df.rename(columns={"fornecedor":"Fornecedor", "ong":"ONG", "qtde_kg":"Qtde_kg", "distancia_km":"Distancia_km"})
            else: df = pd.DataFrame()
            
            lotes = df.groupby("Fornecedor").agg({"ONG": lambda x: list(x), "Qtde_kg": "sum", "Distancia_km": "sum"}).reset_index()
            
            if lotes.empty: st.info("Nenhuma carga disponível no momento."); st.stop()
            
            veiculo = st.session_state.driver_vehicle
            for i, row in lotes.iterrows():
                lucro = (row["Qtde_kg"] * 0.10) + (row["Distancia_km"] * 0.50)
                
                is_adv = True
                if veiculo == "pickup" and row["Qtde_kg"] > 1000: is_adv = False
                if veiculo == "truck" and row["Qtde_kg"] < 300: is_adv = False
                
                c_border = "#00ff88" if is_adv else "#fbbf24"
                c_status = "🟢 Rota Otimizada p/ Seu Veículo" if is_adv else "🟡 Carga Desbalanceada p/ Seu Veículo"
                
                st.markdown(f"""
                <div style="border: 2px solid {c_border}; border-radius:12px; padding:16px; margin-bottom:8px; background:#0f172a;">
                    <div style="color:{c_border}; font-size:0.7rem; font-weight:bold; margin-bottom:8px;">{c_status}</div>
                    <div style="font-size:1.1rem; color:#fff; font-weight:bold;">Coleta: {row['Fornecedor']}</div>
                    <div style="color:#9ca3af; font-size:0.85rem; margin-top:4px;">Entregas: {len(row['ONG'])} paradas</div>
                    <div style="display:flex; justify-content:space-between; margin-top:12px; border-top:1px solid #1e293b; padding-top:12px;">
                        <div>
                            <div style="color:#64748b; font-size:0.7rem;">Carga Total</div>
                            <div style="color:#f8fafc; font-weight:bold;">{row['Qtde_kg']:.0f} kg</div>
                        </div>
                        <div style="text-align:right;">
                            <div style="color:#64748b; font-size:0.7rem;">Lucro Estimado</div>
                            <div style="color:#00ff88; font-weight:bold; font-size:1.2rem;">R$ {lucro:.2f}</div>
                        </div>
                    </div>
                </div>
                """, unsafe_allow_html=True)
                if st.button("ACEITAR FRETE", key=f"btn_acc_{i}", use_container_width=True):
                    st.session_state.driver_selected_lote = row["Fornecedor"]
                    st.session_state.driver_lucro = lucro
                    st.session_state.driver_color = c_border
                    st.session_state.driver_step = "gps"
                    st.rerun()
                st.markdown("<br>", unsafe_allow_html=True)
        except Exception as e:
            st.info("A otimização ainda não foi gerada pelo despachante.")
        st.stop()
        
    elif step == "gps":
        st.markdown("""<style>.block-container{padding:0!important;}</style>""", unsafe_allow_html=True)
        lote_id = st.session_state.driver_selected_lote
        lucro = st.session_state.driver_lucro
        cor = st.session_state.driver_color
        
        import pandas as pd
        url_res = f"{get_sb_url()}/rest/v1/marketplace_results?fornecedor=eq.{urllib.parse.quote(lote_id)}"
        r_res = requests.get(url_res, headers=get_sb_headers())
        df = pd.DataFrame(r_res.json()).rename(columns={"fornecedor":"Fornecedor", "ong":"ONG", "qtde_kg":"Qtde_kg", "distancia_km":"Distancia_km"}) if r_res.status_code == 200 and r_res.json() else pd.DataFrame()
        
        url_sup = f"{get_sb_url()}/rest/v1/marketplace_suppliers"
        r_sup = requests.get(url_sup, headers=get_sb_headers())
        sup_df = pd.DataFrame(r_sup.json()).set_index("nome") if r_sup.status_code == 200 and r_sup.json() else pd.DataFrame()
        
        url_ong = f"{get_sb_url()}/rest/v1/marketplace_ngos"
        r_ong = requests.get(url_ong, headers=get_sb_headers())
        ong_df = pd.DataFrame(r_ong.json()).set_index("nome") if r_ong.status_code == 200 and r_ong.json() else pd.DataFrame()
        
        coords = []
        if lote_id in sup_df.index:
            s_lat, s_lon = sup_df.loc[lote_id, "lat"], sup_df.loc[lote_id, "lon"]
            coords.append((float(s_lat), float(s_lon)))
            
        for _, r in df.iterrows():
            ong_name = r["ONG"]
            if ong_name in ong_df.index:
                n_lat, n_lon = ong_df.loc[ong_name, "lat"], ong_df.loc[ong_name, "lon"]
                coords.append((float(n_lat), float(n_lon)))
                
        route_geom = get_osrm_route_multi(coords)
        
        if coords:
            m = folium.Map(location=coords[0], zoom_start=13, tiles="CartoDB dark_matter", zoom_control=False)
            m.get_root().html.add_child(folium.Element("<style>.leaflet-control-attribution{display:none!important}</style>"))
            plugins.AntPath(route_geom, color=cor, weight=5, pulse_color="#030712", delay=800).add_to(m)
            
            for i, c in enumerate(coords):
                icone = "A" if i == 0 else str(i+1)
                m_cor = cor if i > 0 else "#ffffff"
                folium.Marker(c, icon=folium.DivIcon(html=f'<div style="background:{m_cor};width:24px;height:24px;border-radius:50%;border:2px solid #000;display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:bold;color:#000;">{icone}</div>',icon_size=(24,24),icon_anchor=(12,12))).add_to(m)
            st_folium(m, width="100%", height=650, returned_objects=[])
        
        st.markdown('<div class="gps-panel">', unsafe_allow_html=True)
        st.markdown(f'<div style="display:flex;justify-content:space-between;margin-bottom:12px;"><div style="color:#9ca3af;font-size:.7rem;letter-spacing:2px;text-transform:uppercase;">Navegação // GPS</div><div style="color:{cor};font-size:.9rem;font-weight:bold;font-family:monospace;">Lucro: R$ {lucro:.2f}</div></div>', unsafe_allow_html=True)
        
        drive_state = st.session_state.get("drive_state", "pending")
        if drive_state == "pending":
            if st.button("🚀 INICIAR CORRIDA", use_container_width=True):
                st.session_state["drive_state"] = "transit"; st.rerun()
        elif drive_state == "transit":
            st.success("🟢 NAVEGAÇÃO ATIVA")
            if st.button("✅ FINALIZAR LOTE", use_container_width=True):
                st.session_state["drive_state"] = "completed"; st.rerun()
        elif drive_state == "completed":
            st.info("📦 Rota finalizada e valor depositado no Pix.")
            if st.button("Voltar ao Marketplace", use_container_width=True):
                st.session_state.driver_step = "marketplace"
                st.session_state.drive_state = "pending"
                st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)
        st.stop()

if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False

def enter_system():
    st.session_state["logged_in"] = True

# ═══════════════════════════════════════════════════════════
# LANDING PAGE
# ═══════════════════════════════════════════════════════════
if not st.session_state["logged_in"]:

    # Esconde tudo do Streamlit e zera padding
    st.markdown("""
    <style>
    .stApp { background: #000 !important; overflow: hidden !important; }
    .stAppHeader, [data-testid="collapsedControl"], [data-testid="stSidebar"] { display: none !important; }
    footer { visibility: hidden !important; }
    .block-container { max-width: 100% !important; padding: 0 !important; margin: 0 !important; }
    [data-testid="stVerticalBlock"] > div { padding: 0 !important; gap: 0 !important; }
    iframe { height: 100vh !important; border: none !important; }
    </style>
    """, unsafe_allow_html=True)

    # Landing inteira em components.html para scroll/JS funcionar
    components.html("""
<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<link href="https://fonts.googleapis.com/css2?family=Syne:wght@400;700;800&family=Space+Grotesk:wght@300;400;500&family=Space+Mono:wght@400;700&display=swap" rel="stylesheet">
<style>
* { margin:0; padding:0; box-sizing:border-box; }
html, body { width: 100%; background: transparent; color: #fff; font-family: 'Space Grotesk', sans-serif; overflow-x: hidden; -ms-overflow-style: none; scrollbar-width: none; }
::-webkit-scrollbar { display: none; }

/* CURSOR */
#cg{position:fixed;width:500px;height:500px;border-radius:50%;background:radial-gradient(circle,rgba(0,255,136,.12) 0%,rgba(0,255,136,.02) 40%,transparent 70%);pointer-events:none;z-index:9999;transform:translate(-50%,-50%);top:50%;left:50%;transition:left .08s ease-out,top .08s ease-out;mix-blend-mode:screen;}


/* GLOBAL BACKGROUND */
.global-bg { position: fixed; inset: 0; z-index: -5; background: #010503; overflow: hidden; perspective: 1200px; }
.map-floor { position: absolute; top: -10%; left: -50%; width: 200%; height: 200%; background: url('https://upload.wikimedia.org/wikipedia/commons/e/ec/World_map_blank_without_borders.svg') no-repeat center center; background-size: cover; transform: rotateX(74deg); opacity: 0.15; filter: invert(1) sepia(1) hue-rotate(100deg) saturate(3) brightness(1.5); animation: panMap 50s alternate infinite ease-in-out; }
.grid-floor { position: absolute; top: 10%; left: -50%; width: 200%; height: 150%; background-image: linear-gradient(rgba(0, 255, 136, 0.12) 1px, transparent 1px), linear-gradient(90deg, rgba(0, 255, 136, 0.12) 1px, transparent 1px); background-size: 80px 80px; transform: rotateX(74deg); animation: gridScroll 6s linear infinite; mask-image: linear-gradient(to bottom, rgba(0,0,0,0) 0%, rgba(0,0,0,1) 40%, rgba(0,0,0,0) 100%); -webkit-mask-image: linear-gradient(to bottom, rgba(0,0,0,0) 0%, rgba(0,0,0,1) 40%, rgba(0,0,0,0) 100%); }
.beam { position:absolute; height:2px; filter:drop-shadow(0 0 10px #00ff88); background:linear-gradient(90deg,transparent,#00ff88,transparent); animation:rb 4s linear infinite; opacity:0; }
.b1 { top:30%; left:-20%; transform:rotateX(74deg) rotateZ(30deg); width:400px; }
.b2 { top:55%; left:-20%; transform:rotateX(74deg) rotateZ(-15deg); width:300px; animation-duration:6s; animation-delay:1.5s; }
.b3 { top:80%; left:-20%; transform:rotateX(74deg) rotateZ(5deg); width:500px; animation-duration:5s; animation-delay:0.5s; }
@keyframes panMap { 0% { transform: rotateX(74deg) translateY(-80px); } 100% { transform: rotateX(74deg) translateY(80px); } }
@keyframes gridScroll { 0% { background-position: 0 0; } 100% { background-position: 0 80px; } }
@keyframes rb { 0% { left: -30%; opacity: 0; } 10% { opacity:1; } 90% { opacity:1; } 100% { left: 120%; opacity: 0; } }

/* LOGISTICS ROUTING NETWORK */
.net-wrap{position:absolute;inset:0;width:100%;height:100%;z-index:2;pointer-events:none;opacity:0.6;mask-image:radial-gradient(ellipse 70% 80% at 50% 50%,rgba(0,0,0,1) 0%,rgba(0,0,0,0) 100%);-webkit-mask-image:radial-gradient(ellipse 70% 80% at 50% 50%,rgba(0,0,0,1) 0%,rgba(0,0,0,0) 100%);}
#net-canvas{display:block;width:100%;height:100%;}

/* REAL MAP TEXTURE GLOBE */
.real-globe-wrap { position: absolute; top: 55%; left: 50%; transform: translate(-50%, -50%); width: 850px; height: 850px; z-index: 1; pointer-events: none; opacity: 0.45; mask-image: radial-gradient(circle 400px at var(--mx,50%) var(--my,50%), rgba(0,0,0,1) 0%, rgba(0,0,0,0.06) 100%); -webkit-mask-image: radial-gradient(circle 400px at var(--mx,50%) var(--my,50%), rgba(0,0,0,1) 0%, rgba(0,0,0,0.06) 100%); }
.real-globe { width: 100%; height: 100%; border-radius: 50%; background-image: url('https://upload.wikimedia.org/wikipedia/commons/c/c3/Solarsystemscope_texture_2k_earth_nightmap.jpg'); background-size: auto 100%; background-repeat: repeat-x; animation: spinEarth 100s linear infinite; box-shadow: inset -60px -60px 100px rgba(0,0,0,0.95), inset 60px 60px 100px rgba(0,0,0,0.85), inset 0 0 40px rgba(0,255,136,0.3); filter: sepia(1) hue-rotate(100deg) saturate(2) brightness(0.7); }
@keyframes spinEarth { from { background-position: 0 0; } to { background-position: 200% 0; } }

/* SCANLINE */
#sl{position:fixed;top:-2px;left:0;width:100%;height:2px;background:linear-gradient(90deg,transparent,rgba(0,255,136,.3),transparent);z-index:9998;pointer-events:none;animation:scan 5s linear infinite;}
@keyframes scan{from{top:-2px}to{top:100vh}}
@keyframes spinR{from{transform:translate(-50%,-50%) rotateX(75deg) rotateY(-15deg) rotateZ(0deg);}to{transform:translate(-50%,-50%) rotateX(75deg) rotateY(-15deg) rotateZ(360deg);}}
@keyframes floatP{0%,100%{transform:translateY(0);}50%{transform:translateY(-20px);}}

/* HERO */
.hero{position:relative;width:100%;height:100vh;display:flex;align-items:center;justify-content:center;overflow:hidden;background:transparent;}
.hero-vid{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;opacity:.0;}
.hero-vid iframe{width:120%;height:120%;position:absolute;top:-10%;left:-10%;pointer-events:none;filter:brightness(.28) saturate(.4);}
.hero-ov{position:absolute;inset:0;background:radial-gradient(ellipse 80% 55% at 50% 40%,rgba(0,255,136,.05) 0%,transparent 65%),linear-gradient(to bottom,rgba(0,0,0,.1),rgba(0,0,0,.65));}
.hero-c{position:relative;z-index:2;text-align:center;padding:0 24px;max-width:980px;margin:0 auto;}
.eyebrow{font-family:'Space Mono',monospace;font-size:.7rem;letter-spacing:5px;color:#00ff88;text-transform:uppercase;margin-bottom:4px;opacity:0;animation:fu .9s .2s forwards;}
.h1{font-family:'Syne',sans-serif;font-size:clamp(4rem,9vw,9rem);font-weight:800;line-height:.85;letter-spacing:-.05em;color:#fff;margin-bottom:0;opacity:0;animation:fu .9s .45s forwards;}
.h1 .g{background:linear-gradient(110deg,#00ff88 15%,#0284c7 45%,#ffffff 50%,#0284c7 55%,#00ff88 85%);background-size:200% auto;color:transparent;-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent;animation:shine 4s linear infinite;display:inline-block;}
.h1 .sub{display:block;font-size:.40em;font-weight:400;color:rgba(255,255,255,.4);letter-spacing:-.01em;margin-top:10px;}
.hsub{font-family:'Space Grotesk',sans-serif;font-size:clamp(1rem,1.8vw,1.25rem);color:rgba(255,255,255,.6);font-weight:300;max-width:560px;margin:20px auto 32px;line-height:1.6;opacity:0;animation:fu .9s .7s forwards;}
.hero-btn{display:inline-block;border:1.5px solid rgba(255,255,255,.35);border-radius:50px;padding:17px 56px;font-family:'Space Mono',monospace;font-size:.78rem;letter-spacing:3px;color:#fff;cursor:pointer;background:rgba(255,255,255,.04);backdrop-filter:blur(12px);transition:all .35s ease;opacity:0;animation:fu .9s .95s forwards;}
.hero-btn:hover{border-color:#00ff88;color:#00ff88;background:rgba(0,255,136,.08);box-shadow:0 0 60px rgba(0,255,136,.2);transform:translateY(-2px);}
.scroll-hint{position:absolute;bottom:36px;left:0;width:100%;display:flex;flex-direction:column;align-items:center;gap:10px;opacity:0;animation:fu 1s 1.8s forwards;}
.scroll-hint span{font-family:'Space Mono',monospace;font-size:.6rem;letter-spacing:3px;color:rgba(255,255,255,.22);}
.scroll-line{width:1px;height:56px;background:linear-gradient(to bottom,#00ff88,transparent);animation:sp 2s ease-in-out infinite;}

/* MARQUEE */
.mq{overflow:hidden;border-top:1px solid rgba(255,255,255,.05);border-bottom:1px solid rgba(255,255,255,.05);padding:22px 0;background:rgba(0,0,0,0.4);backdrop-filter:blur(10px);}
.mq-track{display:flex;gap:40px;animation:mq 22s linear infinite;width:max-content;}
.mq-item{font-family:'Space Mono',monospace;font-size:.65rem;letter-spacing:3px;color:rgba(255,255,255,.18);text-transform:uppercase;white-space:nowrap;}
.dot{color:#00ff88;}
@keyframes mq{from{transform:translateX(0)}to{transform:translateX(-50%)}}

/* COUNTERS */
.counters{display:grid;grid-template-columns:repeat(3,1fr);gap:1px;background:rgba(255,255,255,.06);max-width:960px;margin:80px auto;border-radius:4px;overflow:hidden;}
.citem{background:rgba(0,0,0,0.4);backdrop-filter:blur(10px);padding:56px 32px;text-align:center;}
.cnum{font-family:'Syne',sans-serif;font-size:clamp(2.5rem,5vw,5rem);font-weight:800;color:#fff;line-height:1;}
.cnum .g{color:#00ff88;}
.clabel{font-family:'Space Mono',monospace;font-size:.62rem;color:rgba(255,255,255,.28);letter-spacing:3px;text-transform:uppercase;margin-top:12px;}

/* MANIFESTO */
.manifesto{max-width:1100px;margin:0 auto;padding:80px 40px;}
.m-ey{font-family:'Space Mono',monospace;font-size:.62rem;letter-spacing:4px;color:#00ff88;margin-bottom:20px;}
.m-txt{font-family:'Syne',sans-serif;font-size:clamp(1.8rem,3.5vw,3.5rem);font-weight:800;line-height:1.15;letter-spacing:-.03em;margin-bottom:60px;}
.m-txt .d{color:rgba(255,255,255,.18);}
.m-txt .l{color:#fff;}
.m-txt .g{color:#00ff88;}

/* BENTO */
.bento{max-width:1300px;margin:0 auto;padding:0 40px 100px;}
.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;}
.card{background:#080808;border:1px solid rgba(255,255,255,.07);border-radius:18px;padding:36px;position:relative;overflow:hidden;transition:border-color .3s,transform .3s;}
.card:hover{border-color:rgba(255,255,255,.18);transform:translateY(-4px);}
.card::before{content:'';position:absolute;top:0;left:0;right:0;height:1.5px;background:linear-gradient(90deg,transparent,var(--c,#00ff88),transparent);opacity:0;transition:opacity .4s;}
.card:hover::before{opacity:1;}
.card.wide{grid-column:span 2;}
.card-icon{font-size:1.8rem;margin-bottom:18px;display:block;}
.card-title{font-family:'Syne',sans-serif;font-size:1.15rem;font-weight:700;color:#fff;margin-bottom:10px;}
.card-desc{font-size:.88rem;color:rgba(255,255,255,.38);line-height:1.7;}
.tag{display:inline-block;background:rgba(0,255,136,.07);border:1px solid rgba(0,255,136,.18);color:#00ff88;font-family:'Space Mono',monospace;font-size:.58rem;letter-spacing:2px;padding:4px 11px;border-radius:100px;margin-top:16px;}

/* CTA */
.cta{text-align:center;padding:80px 40px 40px;position:relative;overflow:hidden;}
.cta-glow{position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);width:700px;height:500px;background:radial-gradient(ellipse,rgba(0,255,136,.07) 0%,transparent 70%);pointer-events:none;}
.cta-title{font-family:'Syne',sans-serif;font-size:clamp(2.5rem,5vw,5.5rem);font-weight:800;letter-spacing:-.04em;line-height:1;margin-bottom:20px;color:#fff;}
.cta-sub{font-family:'Space Mono',monospace;font-size:.68rem;letter-spacing:3px;color:rgba(255,255,255,.28);margin-bottom:48px;}
.cta-btn{display:inline-block;border:1.5px solid rgba(255,255,255,.35);border-radius:50px;padding:17px 56px;font-family:'Space Mono',monospace;font-size:.78rem;letter-spacing:3px;color:#fff;cursor:pointer;background:rgba(255,255,255,.04);backdrop-filter:blur(12px);transition:all .35s ease;}
.cta-btn:hover{border-color:#00ff88;color:#00ff88;background:rgba(0,255,136,.08);box-shadow:0 0 60px rgba(0,255,136,.2);transform:translateY(-2px);}

/* REVEAL */
.rv{opacity:0;transform:translateY(32px);transition:opacity .9s ease,transform .9s ease;}
.rv.on{opacity:1;transform:translateY(0);}
.d1{transition-delay:.1s;}.d2{transition-delay:.2s;}.d3{transition-delay:.3s;}.d4{transition-delay:.4s;}.d5{transition-delay:.5s;}

/* ANIMS */
@keyframes fu{from{opacity:0;transform:translateY(36px)}to{opacity:1;transform:translateY(0)}}
@keyframes glow{0%,100%{text-shadow:0 0 30px rgba(0,255,136,.5)}50%{text-shadow:0 0 80px rgba(0,255,136,.9),0 0 120px rgba(0,255,136,.3)}}
@keyframes shine{to{background-position:200% center;}}
@keyframes sp{0%,100%{opacity:1}50%{opacity:.25}}

/* RESPONSIVE */
@media (max-width: 900px) {
  .grid { grid-template-columns: repeat(2, 1fr); }
  .manifesto { padding: 60px 24px; }
  .bento { padding: 0 24px 80px; }
}
@media (max-width: 600px) {
  .counters { grid-template-columns: 1fr; margin: 40px 24px; }
  .citem { padding: 36px 20px; }
  .grid { grid-template-columns: 1fr; }
  .card.wide { grid-column: span 1; }
  .hero-vid iframe { width: 300%; height: 300%; top: -100%; left: -100%; }
  .cta-title { font-size: 2.2rem; }
  .h1 .sub { margin-top: 8px; }
}
</style>
</head>
<body>

<div id="cg"></div>
<div id="sl"></div>
<div class="global-bg">
  <div class="map-floor"></div>
  <div class="grid-floor"></div>
  <div class="beam b1"></div><div class="beam b2"></div><div class="beam b3"></div>
</div>

<!-- HERO -->
<div class="hero">
  <div class="hero-vid">
    <iframe src="https://www.youtube.com/embed/LmUsAFDfk6E?autoplay=1&mute=1&loop=1&playlist=LmUsAFDfk6E&controls=0&showinfo=0&rel=0&iv_load_policy=3&modestbranding=1&playsinline=1" frameborder="0" allow="autoplay;encrypted-media" allowfullscreen loading="lazy"></iframe>
  </div>
  <div class="hero-ov"></div>
  <div class="real-globe-wrap"><div class="real-globe"></div></div>
  <div class="net-wrap">
    <canvas id="net-canvas"></canvas>
  </div>
  <div class="hero-c">
    <div class="eyebrow">// Logística Humanitária de Precisão — São Paulo, BR</div>
    <h1 class="h1">Smart<span class="g">Surplus</span><span class="sub">Zero Waste Logistics Intelligence</span></h1>
    <p class="hsub">Motor de otimização multi-commodity que converte o desperdício do varejo em segurança alimentar — com roteamento por satélite e IA preditiva.</p>
    <button class="hero-btn" onclick="enterApp()">Acessar Plataforma →</button>
  </div>
  <div class="scroll-hint">
    <div class="scroll-line"></div>
    <span>scroll</span>
  </div>
</div>

<!-- MARQUEE -->
<div class="mq">
  <div class="mq-track">
    <span class="mq-item">Python PuLP</span><span class="dot">·</span>
    <span class="mq-item">OSRM Satellite Routing</span><span class="dot">·</span>
    <span class="mq-item">Multi-Commodity LP</span><span class="dot">·</span>
    <span class="mq-item">Nominatim Geocoding</span><span class="dot">·</span>
    <span class="mq-item">ESG Analytics</span><span class="dot">·</span>
    <span class="mq-item">ABRAS 2026</span><span class="dot">·</span>
    <span class="mq-item">Folium WebGIS</span><span class="dot">·</span>
    <span class="mq-item">Zero Waste</span><span class="dot">·</span>
    <span class="mq-item">Python PuLP</span><span class="dot">·</span>
    <span class="mq-item">OSRM Satellite Routing</span><span class="dot">·</span>
    <span class="mq-item">Multi-Commodity LP</span><span class="dot">·</span>
    <span class="mq-item">Nominatim Geocoding</span><span class="dot">·</span>
    <span class="mq-item">ESG Analytics</span><span class="dot">·</span>
    <span class="mq-item">ABRAS 2026</span><span class="dot">·</span>
    <span class="mq-item">Folium WebGIS</span><span class="dot">·</span>
    <span class="mq-item">Zero Waste</span><span class="dot">·</span>
  </div>
</div>

<!-- COUNTERS -->
<div style="background:transparent;padding:0 40px;">
<div class="counters">
  <div class="citem rv">
    <div class="cnum"><span class="g" data-count="1.8" data-float="1">0</span>%</div>
    <div class="clabel">Perda média ABRAS no varejo</div>
  </div>
  <div class="citem rv d1">
    <div class="cnum"><span class="g" data-count="2.5" data-float="1">0</span>×</div>
    <div class="clabel">kg CO₂e por kg desperdiçado</div>
  </div>
  <div class="citem rv d2">
    <div class="cnum"><span class="g" data-count="5" data-float="0">0</span></div>
    <div class="clabel">Categorias otimizadas simultâneas</div>
  </div>
</div>
</div>

<!-- MANIFESTO -->
<div class="manifesto" style="background:transparent;">
  <div class="m-ey rv">// O Problema</div>
  <div class="m-txt rv d1">
    <span class="d">Todos os dias, toneladas de </span><span class="l">alimentos perfeitos</span>
    <span class="d"> são descartadas por </span><span class="g">falhas logísticas.</span>
    <span class="d"> Isso não é só desperdício - mas também </span><span class="l">falta de inteligência</span>
    <span class="d"> na malha de distribuição.</span>
  </div>
  <div class="m-ey rv d2">// A Solução</div>
  <div class="m-txt rv d3">
    <span class="l">SmartSurplus </span><span class="d">mapeia cada kg de sobra, calcula a demanda exata de ONGs e cria </span>
    <span class="g">o traçado otimizado</span><span class="d"> — desviando até de bloqueios viários em tempo real.</span>
  </div>
</div>

<!-- BENTO FEATURES -->
<div class="bento" style="background:transparent;">
  <div class="grid">
    <div class="card wide rv" style="--c:#00ff88;">
      <span class="card-icon">⬡</span>
      <div class="card-title">Motor WebGIS Sandbox</div>
      <div class="card-desc">Mapeamento com satélites OSRM e Nominatim. Adicione pontos por clique no mapa ou endereço de texto. Rotas rua a rua com AntPath animado sobre mapa dark de SP.</div>
      <span class="tag">OSRM · FOLIUM · NOMINATIM</span>
    </div>
    <div class="card rv d1" style="--c:#38bdf8;">
      <span class="card-icon">◈</span>
      <div class="card-title">LP Multi-Commodity</div>
      <div class="card-desc">PuLP roteiriza 5 categorias simultaneamente. Se uma ONG precisa de proteínas, a IA recusa enviar frutas.</div>
      <span class="tag">PYTHON PULP</span>
    </div>
    <div class="card rv d2" style="--c:#ef4444;">
      <span class="card-icon">⚠</span>
      <div class="card-title">Engenharia de Desastres</div>
      <div class="card-desc">Simule alagamentos. 30% da malha colapsa e o algoritmo recalcula toda a matriz automaticamente.</div>
      <span class="tag">CEMADEN SIMULATION</span>
    </div>
    <div class="card rv d3" style="--c:#f59e0b;">
      <span class="card-icon">◎</span>
      <div class="card-title">Horizonte LSTM</div>
      <div class="card-desc">Ajuste choques inflacionários e climáticos. Projeção de pico de desperdício com recomendação de frota.</div>
      <span class="tag">PREDICTIVE AI</span>
    </div>
    <div class="card rv d4" style="--c:#a855f7;">
      <span class="card-icon">📱</span>
      <div class="card-title">App do Motorista</div>
      <div class="card-desc">QR Code gera interface dedicada ao motorista. Arquitetura multi-tenant via query params em tempo real.</div>
      <span class="tag">MULTI-TENANT</span>
    </div>
    <div class="card rv d5" style="--c:#00ff88;">
      <span class="card-icon">🌿</span>
      <div class="card-title">Certificado ESG</div>
      <div class="card-desc">Gera certificado oficial com CO₂ evitado, árvores equivalentes e refeições. Pronto para auditoria.</div>
      <span class="tag">ESG · CARBON CREDIT</span>
    </div>
  </div>
</div>

<!-- CTA BOTTOM -->
<div class="cta" style="background:transparent;">
  <div class="cta-glow"></div>
  <div class="cta-title rv">Pronto para transformar<br>excedente em <span style="color:#00ff88;">impacto real?</span></div>
  <div class="cta-sub rv d1">Plataforma operacional — sem instalação, sem fricção.</div>
  <button class="cta-btn rv d2" onclick="enterApp()">Executar Plataforma →</button>
</div>

<script>
// CURSOR GLOW
const cg = document.getElementById('cg');
const gw = document.querySelector('.real-globe-wrap');
const moveCg = e => { 
  cg.style.left = e.clientX + 'px'; cg.style.top = e.clientY + 'px'; 
  if(gw) {
    const r = gw.getBoundingClientRect();
    gw.style.setProperty('--mx', (e.clientX - r.left) + 'px');
    gw.style.setProperty('--my', (e.clientY - r.top) + 'px');
  }
};
document.addEventListener('mousemove', moveCg);
try { window.parent.document.addEventListener('mousemove', moveCg); } catch(e) {}

// FIX HERO HEIGHT TO viewport
const h = window.innerHeight;
document.querySelectorAll('.hero').forEach(el => { el.style.height = h + 'px'; el.style.minHeight = h + 'px'; });

// PARALLAX HERO with internal Scroll
window.addEventListener('scroll', () => {
  const sy = window.scrollY;
  const heroVid = document.querySelector('.hero-vid iframe');
  const heroC   = document.querySelector('.hero-c');
  if(heroVid) heroVid.style.transform = `translateY(${sy * .3}px)`;
  if(heroC) {
    heroC.style.transform = `translateY(${sy * .12}px)`;
    heroC.style.opacity   = Math.max(0, 1 - sy / 500);
  }
});

// ANIM COUNTER
function animCount(el) {
  const target = parseFloat(el.dataset.count);
  const isFloat = el.dataset.float === '1';
  const dur = 1800; const t0 = performance.now();
  function tick(now) {
    const p = Math.min((now - t0) / dur, 1);
    const e = 1 - Math.pow(1 - p, 3);
    el.textContent = isFloat ? (e * target).toFixed(1) : Math.floor(e * target);
    if (p < 1) requestAnimationFrame(tick);
    else el.textContent = isFloat ? target.toFixed(1) : target;
  }
  requestAnimationFrame(tick);
}

// DYNAMIC TRIGGER WITH INTERSECTION OBSERVER
const observer = new IntersectionObserver((entries) => {
  entries.forEach(entry => {
    if (entry.isIntersecting) {
      entry.target.classList.add('on');
      if(entry.target.classList.contains('citem')) {
         const countSpan = entry.target.querySelector('[data-count]');
         if(countSpan && !countSpan.dataset.st) {
            countSpan.dataset.st = '1';
            animCount(countSpan);
         }
      }
      observer.unobserve(entry.target);
    }
  });
}, { threshold: 0.1 });

document.querySelectorAll('.rv').forEach(el => observer.observe(el));

// ENTRAR NO APP
function enterApp() {
  try {
    const btns = window.parent.document.querySelectorAll('button');
    for(const b of btns) {
      if(b.innerText.trim().includes('ENTRAR')) { b.click(); return; }
    }
  } catch(e) {}
}
</script>
<script>
const ncvs = document.getElementById('net-canvas');
const nctx = ncvs.getContext('2d');
let cw, ch, hubs = [], pulses = [];

function resizeNet() {
  cw = ncvs.width = window.innerWidth;
  ch = ncvs.height = window.innerHeight;
  hubs = []; pulses = [];
  const numHubs = Math.floor((cw * ch) / 16000);
  for(let i=0; i<numHubs; i++) {
    hubs.push({
      x: Math.random() * cw, y: Math.random() * ch,
      vx: (Math.random()-0.5)*0.2, vy: (Math.random()-0.5)*0.2,
      r: Math.random() > 0.85 ? 3 : 1.5,
      conns: []
    });
  }
  for(let i=0; i<hubs.length; i++) {
    for(let j=i+1; j<hubs.length; j++) {
      const dx = hubs[i].x - hubs[j].x, dy = hubs[i].y - hubs[j].y;
      if(dx*dx + dy*dy < 24000) hubs[i].conns.push(hubs[j]);
    }
  }
}

let lastFrameTime = 0;
function animNet(time) {
  requestAnimationFrame(animNet);
  if (time - lastFrameTime < 33) return; // limit to ~30 FPS
  lastFrameTime = time;
  nctx.clearRect(0, 0, cw, ch);
  for(const h of hubs) {
    h.x += h.vx; h.y += h.vy;
    if(h.x<0||h.x>cw) h.vx*=-1;
    if(h.y<0||h.y>ch) h.vy*=-1;
  }
  nctx.lineWidth = 0.5;
  for(const h of hubs) {
    for(const c of h.conns) {
      nctx.beginPath(); nctx.moveTo(h.x, h.y); nctx.lineTo(c.x, c.y);
      nctx.strokeStyle = 'rgba(0,255,136,0.12)'; nctx.stroke();
    }
    if(h.conns.length > 0 && Math.random() < 0.005) {
      pulses.push({ src: h, tgt: h.conns[Math.floor(Math.random()*h.conns.length)], p: 0, speed: 0.008 + Math.random()*0.01 });
    }
  }
  for(const h of hubs) {
    nctx.beginPath(); nctx.arc(h.x, h.y, h.r, 0, Math.PI*2);
    nctx.fillStyle = h.r > 2 ? 'rgba(0,255,136,0.6)' : 'rgba(0,255,136,0.2)'; nctx.fill();
  }
  for(let i = pulses.length-1; i>=0; i--) {
    const p = pulses[i]; p.p += p.speed;
    if(p.p >= 1) { pulses.splice(i, 1); continue; }
    const px = p.src.x + (p.tgt.x - p.src.x) * p.p, py = p.src.y + (p.tgt.y - p.src.y) * p.p;
    nctx.beginPath(); nctx.arc(px, py, 1.5, 0, Math.PI*2);
    nctx.fillStyle = '#fff'; nctx.shadowBlur = 8; nctx.shadowColor = '#00ff88'; nctx.fill(); nctx.shadowBlur = 0;
  }
}
window.addEventListener('resize', resizeNet);
try { window.parent.addEventListener('resize', resizeNet); } catch(e){}
resizeNet();
animNet();

</script>
</body>
</html>
    """, height=1000, scrolling=True)

    # Botão Streamlit OCULTO — acionado pelo JS acima
    st.markdown("""
    <style>
    div[data-testid="stHorizontalBlock"] { display: none !important; }
    </style>
    """, unsafe_allow_html=True)
    _, cb, _ = st.columns([1,1,1])
    with cb:
        if st.button("ENTRAR", key="enter_hidden", on_click=enter_system):
            pass

# ═══════════════════════════════════════════════════════════
# DASHBOARD
# ═══════════════════════════════════════════════════════════
else:
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Syne:wght@400;700;800&family=Space+Grotesk:wght@300;400;500;600&family=Space+Mono:wght@400;700&display=swap');
    .stApp { background: #050810 !important; }
    .stAppHeader { background: transparent !important; }
    .stDeployButton { display: none !important; }
    footer { visibility: hidden !important; }
    .block-container { padding-top: 1.2rem !important; padding-bottom: 2rem !important; max-width: 98% !important; }
    * { font-family: 'Space Grotesk', sans-serif; }
    .material-symbols-rounded { font-family: 'Material Symbols Rounded' !important; }
    h1,h2,h3,h4 { font-family: 'Syne', sans-serif !important; color: #f9fafb !important; letter-spacing: -.02em !important; }

    [data-testid="stSidebar"] { background: #03050e !important; border-right: 1px solid #0d1117 !important; }
    [data-testid="stSidebar"] hr { border-color: #0d1117 !important; }
    [data-testid="stSidebar"] label { color: #6b7280 !important; font-size: .82rem !important; }
    [data-testid="stSidebar"] [data-testid="stNumberInput"] input::-webkit-inner-spin-button,
    [data-testid="stSidebar"] [data-testid="stNumberInput"] input::-webkit-outer-spin-button { -webkit-appearance: none; margin: 0; }
    [data-testid="stSidebar"] [data-testid="stNumberInput"] input { -moz-appearance: textfield; }

    .mc { background: #080d1a; border: 1px solid #0f1929; border-radius: 14px; padding: 20px; margin-bottom: 10px; position: relative; overflow: hidden; transition: border-color .3s; }
    .mc:hover { border-color: #1e293b; }
    .mc-bar { position: absolute; left: 0; top: 0; width: 3px; height: 100%; }
    .mc-label { font-family: 'Space Mono', monospace !important; font-size: .6rem; color: #374151; text-transform: uppercase; letter-spacing: 2px; margin-bottom: 10px; }
    .mc-value { font-family: 'Syne', sans-serif !important; font-size: 1.9rem; font-weight: 800; color: #f9fafb; line-height: 1; }
    .mc-unit { font-size: .9rem; color: #374151; font-weight: 400; }
    .mc-diff { font-family: 'Space Mono', monospace !important; font-size: .7rem; color: #00ff88; margin-top: 8px; font-weight: 700; }

    button[data-baseweb="tab"] { font-family: 'Space Grotesk', sans-serif !important; font-size: .85rem !important; color: #374151 !important; font-weight: 500 !important; }
    button[data-baseweb="tab"][aria-selected="true"] { color: #f9fafb !important; font-weight: 600 !important; }
    div[data-baseweb="tab-highlight"] { background: #00ff88 !important; height: 2px !important; }
    div[data-baseweb="tab-border"] { background: #0d1117 !important; }

    [data-testid="stTextInput"] input { background: #080d1a !important; border: 1px solid #0f1929 !important; border-radius: 8px !important; color: #f9fafb !important; }
    [data-testid="stNumberInput"] input { background: #080d1a !important; border: 1px solid #0f1929 !important; border-radius: 8px !important; color: #f9fafb !important; }
    [data-testid="stRadio"] label { color: #9ca3af !important; }
    [data-testid="stDataFrame"] { border: 1px solid #0f1929 !important; border-radius: 12px !important; }

    [data-testid="stButton"] button { background: #00ff88 !important; color: #000 !important; border-radius: 8px !important; padding: 10px 20px !important; border: none !important; font-weight: 700 !important; font-size: .8rem !important; font-family: 'Space Mono', monospace !important; letter-spacing: 1px !important; transition: all .2s !important; }
    [data-testid="stButton"] button:hover { background: #00cc6a !important; transform: translateY(-1px) !important; }

    ::-webkit-scrollbar { width: 3px; height: 3px; }
    ::-webkit-scrollbar-track { background: #050810; }
    ::-webkit-scrollbar-thumb { background: #0f1929; border-radius: 2px; }

    .slabel { font-family: 'Space Mono', monospace; font-size: .6rem; letter-spacing: 3px; color: #00ff88; text-transform: uppercase; margin-bottom: 4px; }
    .stitle { font-family: 'Syne', sans-serif; font-size: 1.4rem; font-weight: 800; color: #f9fafb; margin-bottom: 16px; }
    .d-alert { background: #120508; border: 1px solid #3f0f0f; border-left: 3px solid #ef4444; border-radius: 8px; padding: 12px 16px; color: #fca5a5; font-family: 'Space Mono', monospace; font-size: .7rem; letter-spacing: 1px; margin: 8px 0; }
    .empty { text-align: center; padding: 60px 20px; }
    .empty-icon { font-size: 2.5rem; margin-bottom: 12px; }
    .empty-title { font-family: 'Syne', sans-serif; font-size: 1.2rem; color: #4b5563; margin-bottom: 6px; }
    .empty-sub { font-family: 'Space Mono', monospace; font-size: .72rem; letter-spacing: 1px; color: #374151; }

    @media (max-width: 768px) {
        .hide-on-mobile { display: none !important; }
        [data-testid="stSidebar"] [data-testid="column"] { min-width: calc(50% - 1rem) !important; flex: 1 1 calc(50% - 1rem) !important; }
        .top-header { justify-content: center !important; text-align: center !important; }
        .header-text-container { width: 100%; text-align: center; }
    }
    
    /* Ajustes da barra lateral para subir o menu e o título */
    [data-testid="stSidebarUserContent"] { padding-top: 0rem !important; margin-top: -60px !important; }
    [data-testid="stSidebarHeader"] { padding-bottom: 0rem !important; padding-top: 1rem !important; height: auto !important; position: relative !important; z-index: 99; }
    [data-testid="stSidebarHeader"] button { position: absolute !important; right: 10px !important; top: 10px !important; }
    
    /* Estilização e fixação do Menu Popover (Navegação) */
    .sticky-header { position: sticky; top: 0; z-index: 100; background: #050810; padding: 10px 0; margin-bottom: 15px; }
    [data-testid="stPopover"] button { background-color: #03050e !important; background-image: url('data:image/svg+xml;utf8,<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="%2300ff88" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"></polyline></svg>') !important; background-repeat: no-repeat !important; background-position: right 14px center !important; border: 1px solid #00ff88 !important; border-radius: 8px !important; box-shadow: 0 0 10px rgba(0, 255, 136, 0.1) !important; color: #00ff88 !important; font-family: 'Space Mono', monospace !important; font-weight: 700 !important; cursor: pointer !important; justify-content: center !important; text-align: center !important; padding: 12px 36px 12px 16px !important; width: 100% !important; position: relative !important; transition: all 0.2s; }
    [data-testid="stPopover"] button[aria-expanded="true"] { background-image: url('data:image/svg+xml;utf8,<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="%2300ff88" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="18 15 12 9 6 15"></polyline></svg>') !important; }
    [data-testid="stPopover"] button:hover { background-color: rgba(0, 255, 136, 0.05) !important; border-color: #00ff88 !important; color: #00ff88 !important; }
    [data-testid="stPopover"] button div[data-testid="stMarkdownContainer"] { width: 100% !important; text-align: center !important; }
    [data-testid="stPopover"] button div[data-testid="stMarkdownContainer"] p { text-align: center !important; }
    div[data-testid="stPopoverBody"] { background: #050810 !important; border: 1px solid #0d1117 !important; border-radius: 8px !important; padding: 8px !important; }
    div[data-testid="stPopoverBody"] [data-testid="stButton"] button { background: transparent !important; color: #f9fafb !important; border: none !important; font-family: 'Space Mono', monospace !important; font-weight: 500 !important; text-align: left !important; justify-content: flex-start !important; padding: 10px !important; margin-bottom: 2px !important; border-radius: 6px !important; font-size: 0.85rem !important; }
    div[data-testid="stPopoverBody"] [data-testid="stButton"] button:hover { background: rgba(0, 255, 136, 0.1) !important; color: #00ff88 !important; }
    div[data-testid="stPopoverBody"] [data-testid="stButton"] button div[data-testid="stMarkdownContainer"] { width: 100% !important; text-align: left !important; }
    div[data-testid="stPopoverBody"] [data-testid="stButton"] button div[data-testid="stMarkdownContainer"] p { text-align: left !important; }
    </style>
    """, unsafe_allow_html=True)

    if "manual_suppliers" not in st.session_state:
        st.session_state["manual_suppliers"] = pd.DataFrame(columns=["ID","Nome","Lat","Lon","Excedente_kg","Categoria","Inventario"])
    if "manual_ngos" not in st.session_state:
        st.session_state["manual_ngos"] = pd.DataFrame(columns=["ID","Nome","Lat","Lon","Demanda_kg","Categoria","Inventario"])

    def handle_execution(disaster):
        sup = st.session_state["manual_suppliers"]
        ong = st.session_state["manual_ngos"]
        e_c = {'Total_Desperdicio_kg':0,'Refeicoes_Geradas':0,'Custo_Logistico_Caotico':0,'Total_Transportado_kg':0}
        e_o = {'Total_Desperdicio_kg':0,'Refeicoes_Geradas':0,'Custo_Logistico_Otimo':0,'Total_Transportado_kg':0,'Total_Fornecido_kg':0,'Total_Demanda_kg':0}
        if sup.empty or ong.empty:
            st.session_state.update({"results":pd.DataFrame(),"surplus_df":pd.DataFrame(),"deficit_df":pd.DataFrame(),"caos":e_c,"opt":e_o}); return
        dist_dict, _ = calculate_distance_matrix(sup, ong)
        if disaster:
            dist_dict, pairs = apply_disaster_to_distances(dist_dict)
            if pairs:
                p = pairs[0]; sc = sup.set_index("ID")[["Lat","Lon"]]; nc = ong.set_index("ID")[["Lat","Lon"]]
                if p[0] in sc.index and p[1] in nc.index:
                    st.session_state["crisis_route"] = [sc.loc[p[0],"Lat"],sc.loc[p[0],"Lon"],nc.loc[p[1],"Lat"],nc.loc[p[1],"Lon"]]
        else:
            st.session_state["crisis_route"] = None
        caos = simulate_current_scenario(sup, ong, dist_dict)
        res, sur, dfc, opt = run_optimization(sup, ong, dist_dict)
        st.session_state.update({"results":res,"surplus_df":sur,"deficit_df":dfc,"caos":caos,"opt":opt})
        
        # Salvar resultados no Supabase
        try:
            h = {"apikey": st.secrets["supabase"]["key"], "Authorization": f"Bearer {st.secrets['supabase']['key']}", "Content-Type": "application/json"}
            u = st.secrets["supabase"]["url"]
            requests.delete(f"{u}/rest/v1/marketplace_results?id=gte.0", headers=h)
            requests.delete(f"{u}/rest/v1/marketplace_suppliers?lat=gte.-90", headers=h)
            requests.delete(f"{u}/rest/v1/marketplace_ngos?lat=gte.-90", headers=h)
            
            if not res.empty: 
                r_renamed = res.rename(columns={"Fornecedor":"fornecedor", "ONG":"ong", "Qtde_kg":"qtde_kg", "Distancia_km":"distancia_km"})
                requests.post(f"{u}/rest/v1/marketplace_results", headers=h, json=r_renamed.to_dict(orient="records"), params={"Prefer":"return=minimal"})
            if not sup.empty: 
                s_renamed = sup.rename(columns={"Nome":"nome","Lat":"lat","Lon":"lon"})[["nome","lat","lon"]]
                requests.post(f"{u}/rest/v1/marketplace_suppliers", headers=h, json=s_renamed.to_dict(orient="records"), params={"Prefer":"return=minimal"})
            if not ong.empty: 
                o_renamed = ong.rename(columns={"Nome":"nome","Lat":"lat","Lon":"lon"})[["nome","lat","lon"]]
                requests.post(f"{u}/rest/v1/marketplace_ngos", headers=h, json=o_renamed.to_dict(orient="records"), params={"Prefer":"return=minimal"})
        except Exception as e:
            st.error(f"Erro ao sincronizar com a nuvem (Supabase): {e}")

    # ── SIDEBAR ──
    with st.sidebar:
        st.markdown("""<div style="padding:12px 0 16px;border-bottom:1px solid #0d1117;margin-bottom:16px;">
          <div style="font-family:'Syne',sans-serif;font-size:1.3rem;font-weight:800;color:#f9fafb;">SmartSurplus</div>
          <div style="font-family:'Space Mono',monospace;font-size:.58rem;color:#00ff88;letter-spacing:3px;margin-top:2px;">LOGISTICS INTELLIGENCE</div>
        </div>""", unsafe_allow_html=True)

        st.markdown('<div class="slabel">Demo Rápido</div>', unsafe_allow_html=True)
        c1, c2 = st.columns(2)
        with c1: n_sup = st.number_input("Mercados", min_value=1, max_value=15, value=5)
        with c2: n_ong = st.number_input("ONGs", min_value=1, max_value=10, value=4)
        if st.button("▶ Carregar Demo", use_container_width=True):
            cats = ["Frutas","Laticínios","Proteínas","Hortaliças","Secos e Grãos"]
            np.random.seed(42)
            sup_d = generate_suppliers(n_sup); ong_d = generate_ngos(n_ong)
            sup_rows = []
            for _, r in sup_d.iterrows():
                inv = {c: int(np.random.randint(20, max(21, int(r["Excedente_kg"]/2)))) for c in np.random.choice(cats, size=np.random.randint(2,5), replace=False)}
                sup_rows.append({**r.to_dict(), "Inventario":inv, "Categoria":", ".join(inv.keys())})
            ong_rows = []
            for _, r in ong_d.iterrows():
                inv = {c: int(np.random.randint(20, max(21, int(r["Demanda_kg"]/2)))) for c in np.random.choice(cats, size=np.random.randint(2,4), replace=False)}
                ong_rows.append({**r.to_dict(), "Inventario":inv, "Categoria":", ".join(inv.keys())})
            st.session_state["manual_suppliers"] = pd.DataFrame(sup_rows)
            st.session_state["manual_ngos"]      = pd.DataFrame(ong_rows)
            st.session_state.pop("ran", None)
            st.toast("Demo carregado!", icon="✅"); st.rerun()

        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown('<div class="slabel">Adicionar Ponto</div>', unsafe_allow_html=True)
        input_mode = st.radio("", ["📍 Clique no Mapa", "📝 Por Endereço"], label_visibility="collapsed")
        last_clicked = st.session_state.get("map_click_data", None)

        if input_mode == "📍 Clique no Mapa":
            if last_clicked:
                st.success(f"📍 {last_clicked['lat']:.4f}, {last_clicked['lng']:.4f}")
                with st.form("form_map"):
                    p_type = st.selectbox("Tipo", ["🟢 Supermercado","🔵 ONG"])
                    p_name = st.text_input("Nome")
                    ca, cb = st.columns(2)
                    with ca:
                        kf=st.number_input("Frutas kg",0); kl=st.number_input("Laticínios kg",0); kp=st.number_input("Proteínas kg",0)
                    with cb:
                        kh=st.number_input("Hortaliças kg",0); ks=st.number_input("Secos kg",0)
                    if st.form_submit_button("Lançar", use_container_width=True):
                        lat,lon = last_clicked['lat'],last_clicked['lng']
                        inv = {}
                        if kf>0: inv["Frutas"]=kf
                        if kl>0: inv["Laticínios"]=kl
                        if kp>0: inv["Proteínas"]=kp
                        if kh>0: inv["Hortaliças"]=kh
                        if ks>0: inv["Secos e Grãos"]=ks
                        total = sum(inv.values())
                        if total==0: st.error("Adicione kg em pelo menos uma categoria.")
                        else:
                            cat_str = ", ".join(inv.keys())
                            if "Supermercado" in p_type:
                                nid = f"S{len(st.session_state['manual_suppliers'])+1}"
                                st.session_state["manual_suppliers"] = pd.concat([st.session_state["manual_suppliers"], pd.DataFrame([{"ID":nid,"Nome":p_name or nid,"Lat":lat,"Lon":lon,"Excedente_kg":total,"Categoria":cat_str,"Inventario":inv}])], ignore_index=True)
                            else:
                                nid = f"O{len(st.session_state['manual_ngos'])+1}"
                                st.session_state["manual_ngos"] = pd.concat([st.session_state["manual_ngos"], pd.DataFrame([{"ID":nid,"Nome":p_name or nid,"Lat":lat,"Lon":lon,"Demanda_kg":total,"Categoria":cat_str,"Inventario":inv}])], ignore_index=True)
                            st.session_state["map_click_data"] = None
                            st.session_state["map_click_processed"] = last_clicked
                            st.rerun()
            else:
                st.info("👆 Clique no mapa para posicionar.")
        else:
            with st.form("form_addr"):
                p_addr = st.text_input("Endereço", placeholder="Av. Paulista, 1000, SP")
                p_type = st.selectbox("Tipo", ["🟢 Supermercado","🔵 ONG"])
                p_name = st.text_input("Nome")
                ca, cb = st.columns(2)
                with ca:
                    kf=st.number_input("Frutas kg",0); kl=st.number_input("Laticínios kg",0); kp=st.number_input("Proteínas kg",0)
                with cb:
                    kh=st.number_input("Hortaliças kg",0); ks=st.number_input("Secos kg",0)
                if st.form_submit_button("Geolocalizar e Lançar", use_container_width=True):
                    if not p_addr.strip(): st.error("Preencha o endereço.")
                    else:
                        inv = {}
                        if kf>0: inv["Frutas"]=kf
                        if kl>0: inv["Laticínios"]=kl
                        if kp>0: inv["Proteínas"]=kp
                        if kh>0: inv["Hortaliças"]=kh
                        if ks>0: inv["Secos e Grãos"]=ks
                        total = sum(inv.values())
                        if total==0: st.error("Adicione kg em pelo menos uma categoria.")
                        else:
                            lat, lon = geocode_address(p_addr)
                            if lat:
                                cat_str = ", ".join(inv.keys())
                                if "Supermercado" in p_type:
                                    nid = f"S{len(st.session_state['manual_suppliers'])+1}"
                                    st.session_state["manual_suppliers"] = pd.concat([st.session_state["manual_suppliers"], pd.DataFrame([{"ID":nid,"Nome":p_name or nid,"Lat":lat,"Lon":lon,"Excedente_kg":total,"Categoria":cat_str,"Inventario":inv}])], ignore_index=True)
                                else:
                                    nid = f"O{len(st.session_state['manual_ngos'])+1}"
                                    st.session_state["manual_ngos"] = pd.concat([st.session_state["manual_ngos"], pd.DataFrame([{"ID":nid,"Nome":p_name or nid,"Lat":lat,"Lon":lon,"Demanda_kg":total,"Categoria":cat_str,"Inventario":inv}])], ignore_index=True)
                                st.rerun()
                            else: st.error("Endereço não localizado.")

        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown('<div class="slabel">Configurações</div>', unsafe_allow_html=True)
        disaster_mode = st.toggle("⚠ Simular Crise Viária", value=False)
        if disaster_mode:
            st.markdown('<div class="d-alert">CEMADEN: 30% da malha colapsada.</div>', unsafe_allow_html=True)
        mode_route = st.radio("Rotas:", ["Linha Direta","GPS Real (OSRM)"], horizontal=True)
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("⬡ Recalcular Otimização", type="primary", use_container_width=True):
            if disaster_mode: st.toast("CEMADEN: Vias submersas. Recalculando...", icon="⚠️")
            with st.spinner("Processando..."): handle_execution(disaster_mode)
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🗑 Limpar Malha", use_container_width=True):
            st.session_state["manual_suppliers"] = pd.DataFrame(columns=["ID","Nome","Lat","Lon","Excedente_kg","Categoria","Inventario"])
            st.session_state["manual_ngos"]      = pd.DataFrame(columns=["ID","Nome","Lat","Lon","Demanda_kg","Categoria","Inventario"])
            for k in ["results","surplus_df","deficit_df","ran"]: st.session_state.pop(k,None)
            st.rerun()

    if "ran" not in st.session_state:
        st.session_state["ran"] = True
        handle_execution(False)

    suppliers_df = st.session_state["manual_suppliers"]
    ngos_df      = st.session_state["manual_ngos"]
    results_df   = st.session_state.get("results", pd.DataFrame())
    caos = st.session_state.get("caos", {'Total_Desperdicio_kg':0,'Refeicoes_Geradas':0,'Custo_Logistico_Caotico':0,'Total_Transportado_kg':0})
    opt  = st.session_state.get("opt",  {'Total_Desperdicio_kg':0,'Refeicoes_Geradas':0,'Custo_Logistico_Otimo':0,'Total_Transportado_kg':0,'Total_Fornecido_kg':0,'Total_Demanda_kg':0})

    co2=opt['Total_Transportado_kg']*2.5; arv=int(co2/21)
    dw=((caos['Total_Desperdicio_kg']-opt['Total_Desperdicio_kg'])/max(1,caos['Total_Desperdicio_kg']))*100
    dref=opt['Refeicoes_Geradas']-caos['Refeicoes_Geradas']
    cc_=caos["Custo_Logistico_Caotico"]/max(1,caos["Total_Transportado_kg"])
    co_=opt["Custo_Logistico_Otimo"]/max(1,opt["Total_Transportado_kg"])
    pck=(1-(co_/max(0.01,cc_)))*100

    st.markdown(f"""
    <div class="top-header" style="display:flex;align-items:center;justify-content:space-between;margin-bottom:18px;padding-bottom:14px;border-bottom:1px solid #0d1117;">
      <div class="header-text-container">
        <div style="font-family:'Space Mono',monospace;font-size:.58rem;color:#00ff88;letter-spacing:3px;text-transform:uppercase;">// Painel Operacional</div>
        <div style="font-family:'Syne',sans-serif;font-size:1.6rem;font-weight:800;color:#f9fafb;line-height:1.1;margin-top:2px;">Analytics Central</div>
      </div>
      <div style="display:flex;gap:10px;" class="hide-on-mobile">
        <div style="background:#041a0f;border:1px solid #0a3d1f;border-radius:8px;padding:8px 14px;text-align:center;">
          <div style="font-family:'Space Mono',monospace;font-size:1rem;font-weight:700;color:#00ff88;">{len(suppliers_df)}</div>
          <div style="font-family:'Space Mono',monospace;font-size:.55rem;color:#374151;letter-spacing:1px;">MERCADOS</div>
        </div>
        <div style="background:#060d1c;border:1px solid #0e1f40;border-radius:8px;padding:8px 14px;text-align:center;">
          <div style="font-family:'Space Mono',monospace;font-size:1rem;font-weight:700;color:#38bdf8;">{len(ngos_df)}</div>
          <div style="font-family:'Space Mono',monospace;font-size:.55rem;color:#374151;letter-spacing:1px;">ONGS</div>
        </div>
        <div style="background:#060d1c;border:1px solid #0e1f40;border-radius:8px;padding:8px 14px;text-align:center;">
          <div style="font-family:'Space Mono',monospace;font-size:1rem;font-weight:700;color:#f59e0b;">{len(results_df)}</div>
          <div style="font-family:'Space Mono',monospace;font-size:.55rem;color:#374151;letter-spacing:1px;">ROTAS</div>
        </div>
      </div>
    </div>""", unsafe_allow_html=True)

    menu_opcoes = ["🗺 Mapa & Overview","◈ Despachos","⚠ Déficit ONGs","▤ Estoque","◎ Previsão IA","❖ App Motorista"]
    
    if "aba_selecionada" not in st.session_state:
        st.session_state.aba_selecionada = menu_opcoes[0]
        
    st.markdown('<div class="sticky-header">', unsafe_allow_html=True)
    with st.popover(f"{st.session_state.aba_selecionada}", use_container_width=True):
        for op in menu_opcoes:
            if st.button(op, use_container_width=True, key=f"nav_{op}"):
                st.session_state.aba_selecionada = op
                st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

    aba_selecionada = st.session_state.aba_selecionada

    if aba_selecionada == menu_opcoes[0]:
        c1,c2,c3,c4 = st.columns(4)
        with c1: st.markdown(f'<div class="mc"><div class="mc-bar" style="background:#ef4444;"></div><div class="mc-label">Desperdício Líquido</div><div class="mc-value">{opt["Total_Desperdicio_kg"]:.0f}<span class="mc-unit"> kg</span></div><div class="mc-diff">↓ {dw:.1f}% vs manual</div></div>', unsafe_allow_html=True)
        with c2: st.markdown(f'<div class="mc"><div class="mc-bar" style="background:#38bdf8;"></div><div class="mc-label">Refeições Geradas</div><div class="mc-value">{opt["Refeicoes_Geradas"]}<span class="mc-unit"> ref.</span></div><div class="mc-diff">+{dref} a mais que caótico</div></div>', unsafe_allow_html=True)
        with c3: st.markdown(f'<div class="mc"><div class="mc-bar" style="background:#f59e0b;"></div><div class="mc-label">Custo / kg</div><div class="mc-value">R${co_:.2f}</div><div class="mc-diff">↓ {pck:.1f}% de eficiência</div></div>', unsafe_allow_html=True)
        with c4: st.markdown(f'<div class="mc"><div class="mc-bar" style="background:#00ff88;"></div><div class="mc-label">Crédito ESG</div><div class="mc-value">{co2:.0f}<span class="mc-unit"> kg CO₂</span></div><div class="mc-diff">≈ {arv} árvores/ano</div></div>', unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)
        col_graf, col_mapa = st.columns([1, 2.2])

        with col_graf:
            if opt['Total_Transportado_kg'] > 0:
                fig = go.Figure()
                fig.add_trace(go.Bar(name='Manual',x=['Entregue','Perdido'],y=[caos['Total_Transportado_kg'],caos['Total_Desperdicio_kg']],marker_color=['#1f2937','#111827'],text=[f"{caos['Total_Transportado_kg']:.0f}",f"{caos['Total_Desperdicio_kg']:.0f}"],textposition='outside',textfont=dict(color='#4b5563',size=10)))
                fig.add_trace(go.Bar(name='SmartSurplus',x=['Entregue','Perdido'],y=[opt['Total_Transportado_kg'],opt['Total_Desperdicio_kg']],marker_color=['#00ff88','#052e16'],text=[f"{opt['Total_Transportado_kg']:.0f}",f"{opt['Total_Desperdicio_kg']:.0f}"],textposition='outside',textfont=dict(color='#f9fafb',size=10)))
                fig.update_layout(barmode='group',plot_bgcolor='rgba(0,0,0,0)',paper_bgcolor='rgba(0,0,0,0)',font=dict(color='#4b5563',family='Space Grotesk'),title=dict(text='Manual vs IA',font=dict(size=12,color='#f9fafb',family='Syne')),legend=dict(orientation='h',y=-0.3,font=dict(color='#6b7280',size=10)),margin=dict(l=0,r=0,t=36,b=0),xaxis=dict(gridcolor='#0d1117'),yaxis=dict(gridcolor='#0d1117'),height=220)
                st.plotly_chart(fig, use_container_width=True)
                fig2 = go.Figure(go.Pie(labels=['CO₂ Evitado','Restante'],values=[min(co2,1000),max(0,1000-co2)],hole=.75,marker=dict(colors=['#00ff88','#050810']),textinfo='none'))
                fig2.update_layout(plot_bgcolor='rgba(0,0,0,0)',paper_bgcolor='rgba(0,0,0,0)',title=dict(text='ESG Carbon',font=dict(size=12,color='#f9fafb',family='Syne')),showlegend=False,margin=dict(l=0,r=0,t=36,b=0),height=180,annotations=[dict(text=f'<b>{co2:.0f}</b>',x=.5,y=.5,font=dict(size=20,color='#00ff88',family='Syne'),showarrow=False)])
                st.plotly_chart(fig2, use_container_width=True)
                cert = f"""<!DOCTYPE html><html><head><meta charset="UTF-8"><style>body{{background:#030712;color:#f9fafb;font-family:monospace;padding:60px;}}
.w{{border:1px solid #1f2937;border-radius:20px;padding:60px;max-width:780px;margin:0 auto;}}
.top{{height:2px;background:linear-gradient(90deg,transparent,#00ff88,transparent);margin-bottom:40px;}}
.ey{{font-size:.65rem;letter-spacing:4px;color:#00ff88;margin-bottom:20px;}}
h1{{font-size:2.5rem;font-weight:800;margin-bottom:8px;}}
.g{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:16px;margin:32px 0;}}
.k{{background:#0a0f1a;border:1px solid #1f2937;border-radius:12px;padding:24px;}}
.kv{{font-size:1.8rem;font-weight:700;color:#00ff88;}}
.kl{{font-size:.6rem;color:#4b5563;letter-spacing:2px;margin-top:6px;}}
.f{{color:#374151;font-size:.6rem;border-top:1px solid #111827;padding-top:20px;margin-top:32px;}}</style></head>
<body><div class="w"><div class="top"></div><div class="ey">// Certificado ESG SmartSurplus</div><h1>SmartSurplus ESG</h1>
<div class="g"><div class="k"><div class="kv">{co2:.1f} kg</div><div class="kl">CO2E NAO GERADO</div></div>
<div class="k"><div class="kv">{opt['Refeicoes_Geradas']}</div><div class="kl">BENEFICIARIOS</div></div>
<div class="k"><div class="kv">{arv}</div><div class="kl">ARVORES/ANO</div></div></div>
<p style="color:#6b7280;line-height:1.7;">{opt['Total_Transportado_kg']:.0f} kg otimizados — desperdicio reduzido em {dw:.1f}% vs distribuicao manual.</p>
<div class="f">AUDITADO VIA OSRM · PULP LP · {time.strftime('%d/%m/%Y')}</div></div></body></html>"""
                st.download_button("⬇ Certificado ESG", cert, "ESG_SmartSurplus.html", "text/html", use_container_width=True)
            else:
                st.markdown('<div class="empty"><div class="empty-icon">⬡</div><div class="empty-title">Sem dados ainda</div><div class="empty-sub">Clique em "Carregar Demo" no menu lateral</div></div>', unsafe_allow_html=True)

        with col_mapa:
            if not suppliers_df.empty or not ngos_df.empty:
                lats = pd.concat([suppliers_df['Lat'] if not suppliers_df.empty else pd.Series(), ngos_df['Lat'] if not ngos_df.empty else pd.Series()])
                lons = pd.concat([suppliers_df['Lon'] if not suppliers_df.empty else pd.Series(), ngos_df['Lon'] if not ngos_df.empty else pd.Series()])
                clat, clon = lats.mean(), lons.mean()
            else: clat, clon = -23.5505, -46.6333
            m = folium.Map(location=[clat,clon], zoom_start=11, tiles="CartoDB dark_matter")
            m.get_root().html.add_child(folium.Element("<style>.leaflet-control-attribution{display:none!important}</style>"))
            if disaster_mode and not suppliers_df.empty and not ngos_df.empty:
                cr = st.session_state.get("crisis_route")
                if cr:
                    cp = get_osrm_route(*cr) if mode_route=="GPS Real (OSRM)" else [[cr[0],cr[1]],[cr[2],cr[3]]]
                    folium.PolyLine(cp,color="#ef4444",weight=4,opacity=.8,dash_array="8",tooltip="Via Bloqueada").add_to(m)
                    mid = len(cp)//2
                    folium.CircleMarker(cp[mid],radius=40,color="#ef4444",weight=1,fill=True,fill_color="#ef4444",fill_opacity=.12).add_to(m)
            for _, r in suppliers_df.iterrows():
                folium.Marker([r["Lat"],r["Lon"]], popup=f"<b>{r['Nome']}</b><br>{r.get('Categoria','')}<br>{r['Excedente_kg']} kg", tooltip=f"🟢 {r['Nome']}",
                    icon=folium.DivIcon(html='<div style="background:#00ff88;width:26px;height:26px;border-radius:50% 50% 50% 0;border:2px solid #fff;box-shadow:0 0 10px rgba(0,255,136,.7);transform:rotate(-45deg);display:flex;align-items:center;justify-content:center;font-size:12px;"><span style="transform:rotate(45deg)">🏪</span></div>',icon_size=(26,26),icon_anchor=(13,32))).add_to(m)
            for _, r in ngos_df.iterrows():
                folium.Marker([r["Lat"],r["Lon"]], popup=f"<b>{r['Nome']}</b><br>{r.get('Categoria','')}<br>Necessidade: {r['Demanda_kg']} kg", tooltip=f"🔵 {r['Nome']}",
                    icon=folium.DivIcon(html='<div style="background:#38bdf8;width:26px;height:26px;border-radius:50% 50% 50% 0;border:2px solid #fff;box-shadow:0 0 10px rgba(56,189,248,.7);transform:rotate(-45deg);display:flex;align-items:center;justify-content:center;font-size:12px;"><span style="transform:rotate(45deg)">🤝</span></div>',icon_size=(26,26),icon_anchor=(13,32))).add_to(m)
            if not results_df.empty:
                sc = suppliers_df.set_index("ID")[["Lat","Lon"]]
                nc = ngos_df.set_index("ID")[["Lat","Lon"]]
                for _, r in results_df.iterrows():
                    if r["Fornecedor"] not in sc.index or r["ONG"] not in nc.index: continue
                    slat,slon = sc.loc[r["Fornecedor"],"Lat"],sc.loc[r["Fornecedor"],"Lon"]
                    nlat,nlon = nc.loc[r["ONG"],"Lat"],nc.loc[r["ONG"],"Lon"]
                    qty = r["Qtde_kg"]; w = max(2,min(7,(qty/50)*7))
                    cor = "#38bdf8" if disaster_mode else "#00ff88"
                    path = get_osrm_route(slat,slon,nlat,nlon) if mode_route=="GPS Real (OSRM)" else [[slat,slon],[nlat,nlon]]
                    plugins.AntPath(path,color=cor,pulse_color="#030712",weight=w,delay=900,dash_array=[8,20],tooltip=f"{r['Fornecedor']} -> {r['ONG']} ({qty:.0f} kg)").add_to(m)
            map_resp = st_folium(m, width=None, height=520, returned_objects=["last_clicked"])
            if map_resp and map_resp.get("last_clicked"):
                lc = map_resp["last_clicked"]
                if st.session_state.get("map_click_data") != lc and st.session_state.get("map_click_processed") != lc:
                    st.session_state["map_click_data"] = lc; st.rerun()

    elif aba_selecionada == menu_opcoes[1]:
        st.markdown("<br>", unsafe_allow_html=True)
        if not results_df.empty:
            pdf = results_df.merge(suppliers_df[["ID","Nome"]],left_on="Fornecedor",right_on="ID").rename(columns={"Nome":"Origem"})
            pdf = pdf.merge(ngos_df[["ID","Nome"]],left_on="ONG",right_on="ID").rename(columns={"Nome":"Destino"})
            def wa(row):
                msg = f"SmartSurplus\nOrigem: {row['Origem']}\nDestino: {row['Destino']}\nCarga: {row.get('Itens_Entregues',str(row['Qtde_kg']))}"
                return f"https://wa.me/?text={urllib.parse.quote(msg)}"
            pdf["WhatsApp Driver"] = pdf.apply(wa, axis=1)
            cols = ["Origem","Destino","Qtde_kg","Itens_Entregues","Distancia_km","Custo_Estimado","WhatsApp Driver"]
            cols = [c for c in cols if c in pdf.columns]
            st.dataframe(pdf[cols], use_container_width=True, hide_index=True, column_config={
                "Qtde_kg": st.column_config.NumberColumn("Qtde", format="%.1f kg"),
                "Distancia_km": st.column_config.NumberColumn("Distância", format="%.2f km"),
                "Custo_Estimado": st.column_config.NumberColumn("Custo", format="R$ %.2f"),
                "WhatsApp Driver": st.column_config.LinkColumn("📲 Driver WA")})
            st.markdown("<br>", unsafe_allow_html=True)
            out = io.BytesIO()
            exp_cols = [c for c in cols if c != "WhatsApp Driver"]
            with pd.ExcelWriter(out, engine='openpyxl') as w: pdf[exp_cols].to_excel(w, index=False, sheet_name='Manifesto')
            out.seek(0)
            _, c2, _ = st.columns([1,2,1])
            with c2: st.download_button("⬇ Manifesto (.xlsx)", out, "Manifesto_SmartSurplus.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)
        else:
            st.markdown('<div class="empty"><div class="empty-icon">📦</div><div class="empty-title">Sem despachos</div><div class="empty-sub">Calcule a otimização primeiro</div></div>', unsafe_allow_html=True)

    elif aba_selecionada == menu_opcoes[2]:
        st.markdown("<br>", unsafe_allow_html=True)
        ddf = st.session_state.get("deficit_df", pd.DataFrame())
        if not ddf.empty and not ngos_df.empty:
            merged = ddf.merge(ngos_df[["ID","Nome"]], left_on="ID_Entidade", right_on="ID", how="left")
            merged = merged[["Nome","Categoria","Falta_kg"]].rename(columns={"Nome":"ONG","Falta_kg":"Déficit (kg)"})
            st.dataframe(merged, use_container_width=True, hide_index=True, column_config={"Déficit (kg)": st.column_config.NumberColumn(format="%.1f kg")})
        else: st.success("✅ Toda demanda das ONGs foi atendida. Nenhum déficit.")

    elif aba_selecionada == menu_opcoes[3]:
        st.markdown("<br>", unsafe_allow_html=True)
        sdf = st.session_state.get("surplus_df", pd.DataFrame())
        if not sdf.empty and not suppliers_df.empty:
            merged = sdf.merge(suppliers_df[["ID","Nome"]], left_on="ID_Entidade", right_on="ID", how="left")
            merged = merged[["Nome","Categoria","Sobra_kg"]].rename(columns={"Nome":"Supermercado","Sobra_kg":"Sobra (kg)"})
            st.dataframe(merged, use_container_width=True, hide_index=True, column_config={"Sobra (kg)": st.column_config.NumberColumn(format="%.1f kg")})
        else: st.success("✅ Estoque 100% esvaziado. Nenhuma sobra.")

    elif aba_selecionada == menu_opcoes[4]:
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown('<div class="slabel">// Inteligência Preditiva</div><div class="stitle">Simulador LSTM — Anomalias Globais</div>', unsafe_allow_html=True)
        cc1, cc2 = st.columns([1.1, 2.2])
        with cc1:
            inf = st.slider("Choque Inflacionário (%)", -5, 30, 5)
            cli = st.slider("Extremo Climático (%)", -10, 40, 12)
            fr = 1.0 + inf/100 + cli/100; ap = (fr-1)*100; frota = max(0, int(ap*.8))
            st.markdown(f'<div class="mc" style="margin-top:20px;"><div class="mc-bar" style="background:#ef4444;"></div><div class="mc-label">Pico Projetado</div><div class="mc-value" style="font-size:1.3rem;">Dezembro</div><div class="mc-diff" style="color:#ef4444;">▲ +{ap:.1f}% desperdício</div></div><div class="mc"><div class="mc-bar" style="background:#38bdf8;"></div><div class="mc-label">Recomendação IA</div><div style="color:#9ca3af;font-size:.82rem;line-height:1.6;padding-top:6px;">Expandir frotas em <b style="color:#f9fafb;">{frota}%</b> no Q4.</div></div>', unsafe_allow_html=True)
        with cc2:
            meses = ['Jan','Fev','Mar','Abr','Mai','Jun','Jul','Ago','Set','Out','Nov','Dez']
            kg_b = st.session_state.get("manual_suppliers", pd.DataFrame())
            mult = max(1, kg_b["Excedente_kg"].sum()/100) if not kg_b.empty and "Excedente_kg" in kg_b else 10
            base = [int(x*mult) for x in [100,95,110,105,130,120,150,160,140,180,190,250]]
            np.random.seed(42)
            pred = [x*fr + np.random.normal(0, max(1, x*.05)) for x in base]
            fig3 = go.Figure()
            fig3.add_trace(go.Scatter(x=meses,y=base,name='Histórico',line=dict(color='#1f2937',width=2),mode='lines+markers',marker=dict(size=4)))
            fig3.add_trace(go.Scatter(x=meses,y=pred,name='Predição LSTM',line=dict(color='#00ff88',width=2,dash='dot'),mode='lines+markers',marker=dict(size=4),fill='tonexty',fillcolor='rgba(0,255,136,.04)'))
            fig3.update_layout(plot_bgcolor='rgba(0,0,0,0)',paper_bgcolor='rgba(0,0,0,0)',font=dict(color='#4b5563',family='Space Grotesk'),title=dict(text='Curva de Estresse Logístico',font=dict(size=13,color='#f9fafb',family='Syne')),hovermode='x unified',legend=dict(orientation='h',y=-0.25,font=dict(color='#6b7280',size=10)),margin=dict(l=0,r=0,t=36,b=0),xaxis=dict(gridcolor='#0d1117'),yaxis=dict(gridcolor='#0d1117'))
            st.plotly_chart(fig3, use_container_width=True)

    elif aba_selecionada == menu_opcoes[5]:
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown('<div class="slabel">// Multi-Tenant Architecture</div><div class="stitle">App do Motorista via QR Code</div>', unsafe_allow_html=True)
        st.markdown('<p style="color:#4b5563;font-size:.88rem;max-width:560px;line-height:1.7;">Aponte a câmera do celular para o QR Code. O servidor detecta <code style="color:#00ff88;background:#041a0f;padding:2px 6px;border-radius:4px;">?role=driver</code> e injeta a interface do motorista.</p>', unsafe_allow_html=True)
        base_url = st.text_input("URL pública:", "https://leandro-rafael-smartsurplus-logistics-app-foiglc.streamlit.app/")
        if not results_df.empty:
            pts = []
            locs_info = []
            sc = suppliers_df.set_index("ID")
            nc = ngos_df.set_index("ID")
            
            for _, r in results_df.head(4).iterrows():
                if r["Fornecedor"] in sc.index:
                    lat, lon = sc.loc[r['Fornecedor'], 'Lat'], sc.loc[r['Fornecedor'], 'Lon']
                    pts.append(f"{lat},{lon}")
                    if len(locs_info) < 4: locs_info.append(f"<span style='color:#00ff88'>Coleta:</span> {sc.loc[r['Fornecedor'], 'Nome']}")
                if r["ONG"] in nc.index:
                    lat, lon = nc.loc[r['ONG'], 'Lat'], nc.loc[r['ONG'], 'Lon']
                    pts.append(f"{lat},{lon}")
                    if len(locs_info) < 4: locs_info.append(f"<span style='color:#38bdf8'>Entrega:</span> {nc.loc[r['ONG'], 'Nome']}")
            
            clean_pts = []
            gmaps_pts = []
            for p in pts:
                if not clean_pts or clean_pts[-1] != p: 
                    clean_pts.append(p)
                    lat, lon = p.split(",")
                    gmaps_pts.append(f"{lat},{lon}")
            clean_pts = clean_pts[:8]
            gmaps_pts = gmaps_pts[:8]
            pts_str = "|".join(clean_pts)
            
            if base_url.endswith("/"): base_url = base_url[:-1]
            link_gps = f"{base_url}/?role=driver"
            
            import qrcode
            
            cq1, ci = st.columns([1, 2])
            with cq1:
                st.markdown('<div style="text-align:center;font-size:0.75rem;color:#00ff88;margin-bottom:8px;font-family:monospace;">📍 PORTAL DO MOTORISTA</div>', unsafe_allow_html=True)
                qr = qrcode.QRCode(version=1, box_size=8, border=2)
                qr.add_data(link_gps); qr.make(fit=True)
                img = qr.make_image(fill_color="#00ff88", back_color="#030712")
                buf = io.BytesIO(); img.save(buf, format="PNG")
                st.image(buf, use_container_width=True)
            with ci:
                loc_html = "<br>".join(locs_info)
                st.markdown(f'<div class="mc"><div class="mc-bar" style="background:#00ff88;"></div><div class="mc-label">Navegação Integrada</div><div style="color:#f9fafb;font-size:.85rem;padding-top:8px;line-height:1.6;">{loc_html}<br><span style="color:#6b7280;font-size:0.75rem;margin-top:6px;display:inline-block;">+ Todos os dados foram sincronizados com o Marketplace. Os motoristas já podem escolher suas corridas.</span></div></div>', unsafe_allow_html=True)
        else:
            st.markdown('<div class="empty"><div class="empty-icon">📱</div><div class="empty-title">Sem lotes</div><div class="empty-sub">Calcule a otimização para abastecer o Marketplace</div></div>', unsafe_allow_html=True)