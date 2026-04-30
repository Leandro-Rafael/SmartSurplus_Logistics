import pandas as pd
import numpy as np
import math
import streamlit as st

REAL_SUPPLIERS = [
    {"Nome": "Carrefour Pinheiros",        "Lat": -23.5684, "Lon": -46.7001, "Tipo": "Hipermercado"},
    {"Nome": "Assaí Marginal Tietê",       "Lat": -23.5186, "Lon": -46.6152, "Tipo": "Atacadão"},
    {"Nome": "Pão de Açúcar Av. Paulista", "Lat": -23.5654, "Lon": -46.6521, "Tipo": "Supermercado"},
    {"Nome": "Sam's Club Santo Amaro",     "Lat": -23.6425, "Lon": -46.7132, "Tipo": "Clube de Compras"},
    {"Nome": "Makro Butantã",              "Lat": -23.5781, "Lon": -46.7265, "Tipo": "Atacadão"},
    {"Nome": "Mambo Vila Madalena",        "Lat": -23.5471, "Lon": -46.6912, "Tipo": "Supermercado"},
    {"Nome": "Extra Aeroporto",            "Lat": -23.6288, "Lon": -46.6622, "Tipo": "Hipermercado"},
    {"Nome": "Atacadão Itaquera",          "Lat": -23.5350, "Lon": -46.4678, "Tipo": "Atacadão"},
    {"Nome": "St. Marché Itaim",           "Lat": -23.5852, "Lon": -46.6781, "Tipo": "Empório"},
    {"Nome": "Hirota Food Ipiranga",       "Lat": -23.5934, "Lon": -46.6023, "Tipo": "Supermercado"},
    {"Nome": "Sonda Pompéia",              "Lat": -23.5287, "Lon": -46.6809, "Tipo": "Supermercado"},
    {"Nome": "Carrefour Tatuapé",          "Lat": -23.5385, "Lon": -46.5746, "Tipo": "Hipermercado"},
    {"Nome": "Zaffari Morumbi",            "Lat": -23.6201, "Lon": -46.7056, "Tipo": "Supermercado"},
    {"Nome": "Assaí Interlagos",           "Lat": -23.6872, "Lon": -46.6841, "Tipo": "Atacadão"},
    {"Nome": "Pão de Açúcar Moema",        "Lat": -23.6063, "Lon": -46.6578, "Tipo": "Supermercado"},
]

REAL_NGOS = [
    {"Nome": "Banco de Alimentos SP",   "Lat": -23.5353, "Lon": -46.6341, "Tipo": "Centro de Distribuição"},
    {"Nome": "Mesa Brasil SESC",        "Lat": -23.5391, "Lon": -46.5932, "Tipo": "Hub Solidário"},
    {"Nome": "Cruz Vermelha SP",        "Lat": -23.5857, "Lon": -46.6481, "Tipo": "Assistência Médica/Alimentar"},
    {"Nome": "Cozinha Solidária MTST",  "Lat": -23.5935, "Lon": -46.5772, "Tipo": "Refeitório POP"},
    {"Nome": "Casa Hope",               "Lat": -23.6062, "Lon": -46.6415, "Tipo": "Apoio ao Câncer"},
    {"Nome": "Exército de Salvação SP", "Lat": -23.5410, "Lon": -46.6212, "Tipo": "Abrigo"},
    {"Nome": "Pastoral do Povo da Rua", "Lat": -23.5512, "Lon": -46.6358, "Tipo": "Acolhimento Sé"},
    {"Nome": "SP Invisível (SEDE)",     "Lat": -23.5583, "Lon": -46.6617, "Tipo": "Distribuição Direta"},
    {"Nome": "Missão Cena",             "Lat": -23.5367, "Lon": -46.6391, "Tipo": "Reabilitação"},
    {"Nome": "Instituto C",             "Lat": -23.5458, "Lon": -46.6530, "Tipo": "Apoio a Famílias"},
]


def haversine(lat1, lon1, lat2, lon2):
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def generate_suppliers(num_suppliers=10, seed=42):
    np.random.seed(seed)
    num_suppliers = min(num_suppliers, len(REAL_SUPPLIERS))
    data = []
    for i, s in enumerate(REAL_SUPPLIERS[:num_suppliers]):
        capacity = int(np.clip(np.random.normal(120, 50), 40, 300))
        validity = int(np.random.randint(1, 5))
        data.append({
            "ID": f"S{i+1}", "Nome": s["Nome"], "Tipo": s["Tipo"],
            "Lat": s["Lat"], "Lon": s["Lon"],
            "Excedente_kg": capacity, "Validade_media_dias": validity,
        })
    return pd.DataFrame(data)


def generate_ngos(num_ngos=8, seed=43):
    np.random.seed(seed)
    num_ngos = min(num_ngos, len(REAL_NGOS))
    data = []
    for i, n in enumerate(REAL_NGOS[:num_ngos]):
        demand = int(np.clip(np.random.normal(180, 80), 50, 400))
        data.append({
            "ID": f"N{i+1}", "Nome": n["Nome"], "Tipo": n["Tipo"],
            "Lat": n["Lat"], "Lon": n["Lon"], "Demanda_kg": demand,
        })
    return pd.DataFrame(data)


@st.cache_data(show_spinner=False)
def calculate_distance_matrix(suppliers_df, ngos_df):
    s_ids = suppliers_df["ID"].tolist()
    n_ids = ngos_df["ID"].tolist()
    dist_dict = {s: {n: 0.0 for n in n_ids} for s in s_ids}
    for _, s_row in suppliers_df.iterrows():
        for _, n_row in ngos_df.iterrows():
            d = haversine(s_row["Lat"], s_row["Lon"], n_row["Lat"], n_row["Lon"])
            dist_dict[s_row["ID"]][n_row["ID"]] = round(d, 4)
    dist_df = pd.DataFrame(dist_dict).T
    return dist_dict, dist_df