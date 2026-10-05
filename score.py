from datetime import datetime

def calc_score(comprador):
    cnpj = comprador.get("cnpj")
    vistoria = comprador.get("vistoria", True)
    historico = comprador.get("historico", [])
    
    print(f"\n[SCORE] Analisando comprador: {cnpj}")
    
    if not vistoria:
        print(f"  [FALHA] Vistoria reprovada ou pendente.")
        return False
        
    atrasos = 0
    total = len(historico)
    
    for p in historico:
        termo = p["termo"]
        pagamento = p["pagamento"]
        
        #Converte para datetime caso os dados reais venham em formato de texto (string)
        if isinstance(termo, str):
            termo = datetime.strptime(termo, "%Y-%m-%d")
        if isinstance(pagamento, str):
            pagamento = datetime.strptime(pagamento, "%Y-%m-%d")
            
        if pagamento > termo:
            atrasos += 1
            
    score_val = ((total - atrasos) / total * 100) if total > 0 else 100
    print(f"  [OK] Pontualidade: {score_val:.0f}% ({atrasos} atrasos em {total} faturas)")
    
    if score_val < 70:
        print(f"  [FALHA] Comprador ruim (muitos atrasos).")
        return False
        
    print(f"  [OK] Comprador bom (adimplente).")
    return True

if __name__ == "__main__":
    # Exemplo: dados fic (usando datetime diretamente)
    print("Teste com dados fictícios:")
    comp_ficticio = {
        "cnpj": "12345678000195",
        "vistoria": True,
        "historico": [
            {"termo": datetime(2026, 8, 10), "pagamento": datetime(2026, 8, 9)},
            {"termo": datetime(2026, 8, 20), "pagamento": datetime(2026, 8, 20)}
        ]
    }
    calc_score(comp_ficticio)

    # Exemplo: dados reais (API ou BD)
    print("\nTeste com dados reais:")
    comp_real = {
        "cnpj": "98765432000110",
        "vistoria": True,
        "historico": [
            {"termo": "2026-08-10", "pagamento": "2026-08-15"},
            {"termo": "2026-08-20", "pagamento": "2026-08-28"}
        ]
    }
    calc_score(comp_real)
