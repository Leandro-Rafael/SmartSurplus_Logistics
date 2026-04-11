import pulp
import pandas as pd
import numpy as np
import copy

def apply_disaster_to_distances(distance_dict, seed=99):
    """
    Simula vias interditadas por alagamento.
    Aumenta muito a distância/custo entre vários pares simulando desvios forçados.
    """
    np.random.seed(seed)
    new_dist = copy.deepcopy(distance_dict)
    penalized_pairs = []
    
    for s in new_dist:
        for n in new_dist[s]:
            # 30% de chance de a via principal estar bloqueada, o que triplica a distância (desvio longo)
            if np.random.rand() < 0.30:
                new_dist[s][n] = new_dist[s][n] * 3.0
                penalized_pairs.append((s, n))
    return new_dist, penalized_pairs

def run_optimization(suppliers_df, ngos_df, distance_dict, social_weight=1000, cost_weight=1):
    """
    Função para resolver o problema de transporte.
    Maximiza o total entregue ponderado pelo impacto social, e subtrai os custos de transporte.
    """
    # 1. Variáveis e conjuntos
    S = suppliers_df['ID'].tolist()
    N = ngos_df['ID'].tolist()
    
    # Dicionários de capacidades e demandas
    supply = dict(zip(suppliers_df['ID'], suppliers_df['Excedente_kg']))
    demand = dict(zip(ngos_df['ID'], ngos_df['Demanda_kg']))
    
    # 2. Inicialização do Modelo (Maximização)
    prob = pulp.LpProblem("SmartSurplus_Logistics", pulp.LpMaximize)
    
    # 3. Variáveis de decisão (x_ij: qtd de kg enviada do forn S para ONG N)
    routes = [(s, n) for s in S for n in N]
    x = pulp.LpVariable.dicts("route", (S, N), lowBound=0, cat='Continuous')
    
    # 4. Função Objetivo
    # Objetivo: Maximizar social_weight * (Soma x_ij) - cost_weight * (Soma dist_ij * x_ij)
    prob += pulp.lpSum(
        x[s][n] * social_weight - x[s][n] * distance_dict[s][n] * cost_weight 
        for s in S for n in N
    ), "Objective_Function"
    
    # 5. Restrições de Oferta (O que sai não pode ser maior que o Excedente)
    for s in S:
        prob += pulp.lpSum(x[s][n] for n in N) <= supply[s], f"Supply_{s}"
        
    # 6. Restrições de Demanda (O que chega não pode superar a Necessidade)
    for n in N:
        prob += pulp.lpSum(x[s][n] for s in S) <= demand[n], f"Demand_{n}"
        
    # 7. Resolver
    prob.solve(pulp.PULP_CBC_CMD(msg=0)) # msg=0 suprime logs no terminal
    
    status = pulp.LpStatus[prob.status]
    
    # Compilar resultados
    results = []
    total_transported = 0
    total_cost = 0
    
    if prob.status == pulp.LpStatusOptimal:
        for s in S:
            for n in N:
                val = pulp.value(x[s][n])
                if val is not None and val > 0.01: # Threshold pra evitar picos irrelevantes de floats
                    dist = distance_dict[s][n]
                    results.append({
                        "Fornecedor": s,
                        "ONG": n,
                        "Qtde_kg": round(val, 2),
                        "Distancia_km": round(dist, 2),
                        "Custo_Estimado": round(val * dist * cost_weight, 2)
                    })
                    total_transported += val
                    total_cost += val * dist * cost_weight
                    
    results_df = pd.DataFrame(results) if len(results) > 0 else pd.DataFrame(columns=["Fornecedor", "ONG", "Qtde_kg", "Distancia_km", "Custo_Estimado"])
    
    # Calcular simulação para tela
    total_supply = sum(supply.values())
    total_demand = sum(demand.values())
    
    metrics = {
        "Status": status,
        "Total_Fornecido_kg": total_supply,
        "Total_Demanda_kg": total_demand,
        "Total_Transportado_kg": round(total_transported, 2),
        "Total_Desperdicio_kg": round(total_supply - total_transported, 2),
        "Custo_Logistico_Otimo": round(total_cost, 2),
        # 1 kg rende ~2 refeições (500g a porção)
        "Refeicoes_Geradas": int(total_transported * 2)
    }
    
    return results_df, metrics

def simulate_current_scenario(suppliers_df, ngos_df, distance_dict):
    """
    Simula um cenário caótico aleatório e guloso onde os primeiros
    doadores mandam sem otimização. Serve de baseline para o 'Uau' effect.
    """
    S = suppliers_df['ID'].tolist()
    N = ngos_df['ID'].tolist()
    
    # Copia dos ditos
    supply = dict(zip(suppliers_df['ID'], suppliers_df['Excedente_kg']))
    demand = dict(zip(ngos_df['ID'], ngos_df['Demanda_kg']))
    
    total_transported = 0
    total_cost = 0
    # Processo semi-aleatório burro, que falha prematuramente. 
    # Doamos de forma ineficiente, consumindo apenas ~70% 
    # e viajando mais.
    
    for s in S:
        random_ngos = np.random.choice(N, size=len(N)//2, replace=False)
        for n in random_ngos:
            if supply[s] > 0 and demand[n] > 0:
                # Manda no máximo 30% pra não zerar otimizado
                send_amt = min(supply[s], demand[n], np.random.uniform(5, 20)) 
                supply[s] -= send_amt
                demand[n] -= send_amt
                total_transported += send_amt
                total_cost += send_amt * distance_dict[s][n] * 1 # custo unitario
                
    total_supply = suppliers_df['Excedente_kg'].sum()
    metrics = {
        "Total_Transportado_kg": round(total_transported, 2),
        "Total_Desperdicio_kg": round(total_supply - total_transported, 2),
        "Custo_Logistico_Caotico": round(total_cost, 2),
        "Refeicoes_Geradas": int(total_transported * 2)
    }
    return metrics
