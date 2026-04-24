import pulp
import pandas as pd
import numpy as np
import copy


def apply_disaster_to_distances(distance_dict, seed=99):
    """
    Simula vias interditadas por alagamento.
    30% dos pares têm distância triplicada (desvio forçado).
    """
    np.random.seed(seed)
    new_dist = copy.deepcopy(distance_dict)
    penalized_pairs = []
    for s in new_dist:
        for n in new_dist[s]:
            if np.random.rand() < 0.30:
                new_dist[s][n] *= 3.0
                penalized_pairs.append((s, n))
    return new_dist, penalized_pairs


def run_optimization(suppliers_df, ngos_df, distance_dict, social_weight=1000, cost_weight=1):
    """
    Resolve o problema de transporte Multi-Commodity com PuLP.
    Maximiza kg entregues (ponderado por impacto social) menos custo logístico.

    Retorna: results_df, surplus_df, deficit_df, metrics
    """
    if suppliers_df.empty or ngos_df.empty:
        empty_results  = pd.DataFrame(columns=["Fornecedor","ONG","Qtde_kg","Itens_Entregues","Distancia_km","Custo_Estimado"])
        empty_surplus  = pd.DataFrame(columns=["ID_Entidade","Categoria","Sobra_kg"])
        empty_deficit  = pd.DataFrame(columns=["ID_Entidade","Categoria","Falta_kg"])
        empty_metrics  = {"Status":"Sem dados","Total_Fornecido_kg":0,"Total_Demanda_kg":0,
                          "Total_Transportado_kg":0,"Total_Desperdicio_kg":0,
                          "Custo_Logistico_Otimo":0,"Refeicoes_Geradas":0}
        return empty_results, empty_surplus, empty_deficit, empty_metrics

    S = suppliers_df['ID'].tolist()
    N = ngos_df['ID'].tolist()

    C_set = set()
    for inv in suppliers_df['Inventario']: C_set.update(inv.keys())
    for inv in ngos_df['Inventario']:      C_set.update(inv.keys())
    C = list(C_set)

    if not C:
        empty_results  = pd.DataFrame(columns=["Fornecedor","ONG","Qtde_kg","Itens_Entregues","Distancia_km","Custo_Estimado"])
        empty_surplus  = pd.DataFrame(columns=["ID_Entidade","Categoria","Sobra_kg"])
        empty_deficit  = pd.DataFrame(columns=["ID_Entidade","Categoria","Falta_kg"])
        empty_metrics  = {"Status":"Sem categorias","Total_Fornecido_kg":0,"Total_Demanda_kg":0,
                          "Total_Transportado_kg":0,"Total_Desperdicio_kg":0,
                          "Custo_Logistico_Otimo":0,"Refeicoes_Geradas":0}
        return empty_results, empty_surplus, empty_deficit, empty_metrics

    supply = {s: row['Inventario'] for s, row in zip(S, suppliers_df.to_dict('records'))}
    demand = {n: row['Inventario'] for n, row in zip(N, ngos_df.to_dict('records'))}

    prob = pulp.LpProblem("MultiCommodity_SmartSurplus", pulp.LpMaximize)
    x    = pulp.LpVariable.dicts("route", (S, N, C), lowBound=0, cat='Continuous')

    prob += pulp.lpSum(
        x[s][n][c] * social_weight - x[s][n][c] * distance_dict.get(s, {}).get(n, 9999) * cost_weight
        for s in S for n in N for c in C
    ), "Objective"

    for s in S:
        for c in C:
            prob += pulp.lpSum(x[s][n][c] for n in N) <= supply[s].get(c, 0), f"Supply_{s}_{c.replace(' ','_').replace('/','_')}"

    for n in N:
        for c in C:
            prob += pulp.lpSum(x[s][n][c] for s in S) <= demand[n].get(c, 0), f"Demand_{n}_{c.replace(' ','_').replace('/','_')}"

    prob.solve(pulp.PULP_CBC_CMD(msg=0))
    status = pulp.LpStatus[prob.status]

    results, total_transported, total_cost = [], 0.0, 0.0

    if prob.status == pulp.LpStatusOptimal:
        for s in S:
            for n in N:
                details, flow = [], 0.0
                for c in C:
                    val = pulp.value(x[s][n][c])
                    if val is not None and val > 0.01:
                        flow += val
                        details.append(f"{val:.1f}kg {c}")
                if flow > 0.01:
                    dist = distance_dict[s][n]
                    results.append({
                        "Fornecedor":     s,
                        "ONG":            n,
                        "Qtde_kg":        round(flow, 2),
                        "Itens_Entregues": " + ".join(details),
                        "Distancia_km":   round(dist, 2),
                        "Custo_Estimado": round(flow * dist * cost_weight, 2),
                    })
                    total_transported += flow
                    total_cost        += flow * dist * cost_weight

    results_df = pd.DataFrame(results) if results else pd.DataFrame(
        columns=["Fornecedor","ONG","Qtde_kg","Itens_Entregues","Distancia_km","Custo_Estimado"])

    # Sobras e déficits
    surplus_records, deficit_records = [], []
    if prob.status == pulp.LpStatusOptimal:
        for s in S:
            for c in C:
                supplied = sum(pulp.value(x[s][n][c]) or 0 for n in N)
                rem = supply[s].get(c, 0) - supplied
                if rem > 0.01:
                    surplus_records.append({"ID_Entidade": s, "Categoria": c, "Sobra_kg": round(rem, 2)})

        for n in N:
            for c in C:
                received = sum(pulp.value(x[s][n][c]) or 0 for s in S)
                missing  = demand[n].get(c, 0) - received
                if missing > 0.01:
                    deficit_records.append({"ID_Entidade": n, "Categoria": c, "Falta_kg": round(missing, 2)})

    surplus_df = pd.DataFrame(surplus_records) if surplus_records else pd.DataFrame(columns=["ID_Entidade","Categoria","Sobra_kg"])
    deficit_df = pd.DataFrame(deficit_records) if deficit_records else pd.DataFrame(columns=["ID_Entidade","Categoria","Falta_kg"])

    total_supply = suppliers_df['Excedente_kg'].sum()
    total_demand = ngos_df['Demanda_kg'].sum()

    metrics = {
        "Status":                status,
        "Total_Fornecido_kg":    total_supply,
        "Total_Demanda_kg":      total_demand,
        "Total_Transportado_kg": round(total_transported, 2),
        "Total_Desperdicio_kg":  round(total_supply - total_transported, 2),
        "Custo_Logistico_Otimo": round(total_cost, 2),
        "Refeicoes_Geradas":     int(total_transported * 2),
    }
    return results_df, surplus_df, deficit_df, metrics


def simulate_current_scenario(suppliers_df, ngos_df, distance_dict):
    """
    Simula distribuição caótica/manual (sem otimização) para comparativo.
    Cada fornecedor distribui aleatoriamente para metade das ONGs.
    """
    if suppliers_df.empty or ngos_df.empty:
        return {"Total_Transportado_kg":0,"Total_Desperdicio_kg":0,"Custo_Logistico_Caotico":0,"Refeicoes_Geradas":0}

    S = suppliers_df['ID'].tolist()
    N = ngos_df['ID'].tolist()

    C_set = set()
    for inv in suppliers_df['Inventario']: C_set.update(inv.keys())
    for inv in ngos_df['Inventario']:      C_set.update(inv.keys())
    C = list(C_set)

    supply_rem = {s: dict(row['Inventario']) for s, row in zip(S, suppliers_df.to_dict('records'))}
    demand_rem = {n: dict(row['Inventario']) for n, row in zip(N, ngos_df.to_dict('records'))}

    total_transported, total_cost = 0.0, 0.0
    np.random.seed(7)  # seed fixo para reprodutibilidade

    for s in S:
        size       = max(1, len(N) // 2)
        random_ngos = np.random.choice(N, size=size, replace=False)
        for n in random_ngos:
            for c in C:
                avail = supply_rem[s].get(c, 0)
                req   = demand_rem[n].get(c, 0)
                if avail > 0 and req > 0:
                    send_amt = min(avail, req, np.random.uniform(5, 20))
                    supply_rem[s][c] -= send_amt
                    demand_rem[n][c] -= send_amt
                    total_transported += send_amt
                    total_cost        += send_amt * distance_dict[s][n]

    total_supply = suppliers_df['Excedente_kg'].sum()
    return {
        "Total_Transportado_kg":   round(total_transported, 2),
        "Total_Desperdicio_kg":    round(total_supply - total_transported, 2),
        "Custo_Logistico_Caotico": round(total_cost, 2),
        "Refeicoes_Geradas":       int(total_transported * 2),
    }
