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
    Função para resolver o problema de transporte multi-commodity.
    Maximiza o total entregue (por categoria) ponderado pelo impacto social, 
    subtraindo custos logísticos de transporte agregados.
    """
    if suppliers_df.empty or ngos_df.empty:
        return pd.DataFrame(), {}
        
    S = suppliers_df['ID'].tolist()
    N = ngos_df['ID'].tolist()
    
    C_set = set()
    for inv in suppliers_df['Inventario']: C_set.update(inv.keys())
    for inv in ngos_df['Inventario']: C_set.update(inv.keys())
    C = list(C_set)
    
    if not C:
        return pd.DataFrame(), {}

    supply = {s: row['Inventario'] for s, row in zip(S, suppliers_df.to_dict('records'))}
    demand = {n: row['Inventario'] for n, row in zip(N, ngos_df.to_dict('records'))}
    
    prob = pulp.LpProblem("MultiCommodity_SmartSurplus", pulp.LpMaximize)
    
    x = pulp.LpVariable.dicts("route", (S, N, C), lowBound=0, cat='Continuous')
    
    prob += pulp.lpSum(
        x[s][n][c] * social_weight - x[s][n][c] * distance_dict.get(s, {}).get(n, 9999) * cost_weight 
        for s in S for n in N for c in C
    ), "Objective_Function"
    
    for s in S:
        for c in C:
            prob += pulp.lpSum(x[s][n][c] for n in N) <= supply[s].get(c, 0), f"Supply_{s}_{c.replace(' ', '_')}"
            
    for n in N:
        for c in C:
            prob += pulp.lpSum(x[s][n][c] for s in S) <= demand[n].get(c, 0), f"Demand_{n}_{c.replace(' ', '_')}"
            
    prob.solve(pulp.PULP_CBC_CMD(msg=0))
    status = pulp.LpStatus[prob.status]
    
    results = []
    total_transported = 0
    total_cost = 0
    
    if prob.status == pulp.LpStatusOptimal:
        for s in S:
            for n in N:
                total_flow_sn = sum(pulp.value(x[s][n][c]) for c in C if pulp.value(x[s][n][c]) is not None)
                if total_flow_sn > 0.01:
                    dist = distance_dict[s][n]
                    results.append({
                        "Fornecedor": s,
                        "ONG": n,
                        "Qtde_kg": round(total_flow_sn, 2),
                        "Distancia_km": round(dist, 2),
                        "Custo_Estimado": round(total_flow_sn * dist * cost_weight, 2)
                    })
                    total_transported += total_flow_sn
                    total_cost += total_flow_sn * dist * cost_weight
                    
    results_df = pd.DataFrame(results) if len(results) > 0 else pd.DataFrame(columns=["Fornecedor", "ONG", "Qtde_kg", "Distancia_km", "Custo_Estimado"])
    
    total_supply = suppliers_df['Excedente_kg'].sum()
    total_demand = ngos_df['Demanda_kg'].sum()
    
    metrics = {
        "Status": status,
        "Total_Fornecido_kg": total_supply,
        "Total_Demanda_kg": total_demand,
        "Total_Transportado_kg": round(total_transported, 2),
        "Total_Desperdicio_kg": round(total_supply - total_transported, 2),
        "Custo_Logistico_Otimo": round(total_cost, 2),
        "Refeicoes_Geradas": int(total_transported * 2)
    }
    return results_df, metrics

def simulate_current_scenario(suppliers_df, ngos_df, distance_dict):
    """
    Cenário Caótico Multi-Commodity
    """
    if suppliers_df.empty or ngos_df.empty: return {}
    S = suppliers_df['ID'].tolist()
    N = ngos_df['ID'].tolist()
    
    C_set = set()
    for inv in suppliers_df['Inventario']: C_set.update(inv.keys())
    for inv in ngos_df['Inventario']: C_set.update(inv.keys())
    C = list(C_set)
    
    supply_rem = {s: dict(row['Inventario']) for s, row in zip(S, suppliers_df.to_dict('records'))}
    demand_rem = {n: dict(row['Inventario']) for n, row in zip(N, ngos_df.to_dict('records'))}
    
    total_transported = 0
    total_cost = 0
    
    for s in S:
        random_ngos = np.random.choice(N, size=len(N)//2 if len(N)>1 else len(N), replace=False) if N else []
        for n in random_ngos:
            for c in C:
                avail = supply_rem[s].get(c, 0)
                req = demand_rem[n].get(c, 0)
                if avail > 0 and req > 0:
                    send_amt = min(avail, req, np.random.uniform(5, 20)) 
                    supply_rem[s][c] -= send_amt
                    demand_rem[n][c] -= send_amt
                    total_transported += send_amt
                    total_cost += send_amt * distance_dict[s][n] * 1
                
    total_supply = suppliers_df['Excedente_kg'].sum()
    metrics = {
        "Total_Transportado_kg": round(total_transported, 2),
        "Total_Desperdicio_kg": round(total_supply - total_transported, 2),
        "Custo_Logistico_Caotico": round(total_cost, 2),
        "Refeicoes_Geradas": int(total_transported * 2)
    }
    return metrics
