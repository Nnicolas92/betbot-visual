#!/usr/bin/env python3
"""
arb_calculator.py  v2.0
Calcula arbitraje entre Betwarrior y Bookmaker.
Uso: python arb_calculator.py
"""
import json
from pathlib import Path

ODDS_FILE = Path("sesiones/betwarrior_1/odds_raw.json")

def calcular_arb(odd1, odd2, bankroll=10000):
    imp1=1/odd1; imp2=1/odd2; total=imp1+imp2
    margen=(1-total)*100
    if total>=1.0:
        return {"arb":False,"margen":round(margen,3),
                "mensaje":f"Sin arb (margen {margen:.2f}%, necesita < 0%)"}
    s1=round((bankroll*imp1)/total,2)
    s2=round((bankroll*imp2)/total,2)
    gan=round(s1*odd1-bankroll,2)
    return {"arb":True,"margen":round(margen,3),
            "stake_casa1":s1,"stake_casa2":s2,
            "ganancia":gan,"roi":round(gan/bankroll*100,2),
            "mensaje":f"ARB! Ganancia garantizada: ${gan:.2f}"}

def calcular_arb_3way(odd1,oddX,odd2,bankroll=10000):
    imp1=1/odd1; impX=1/oddX; imp2=1/odd2; total=imp1+impX+imp2
    margen=(1-total)*100
    if total>=1.0:
        return {"arb":False,"margen":round(margen,3),
                "mensaje":f"Sin arb (margen {margen:.2f}%)"}
    s1=round((bankroll*imp1)/total,2)
    sX=round((bankroll*impX)/total,2)
    s2=round((bankroll*imp2)/total,2)
    gan=round(s1*odd1-bankroll,2)
    return {"arb":True,"margen":round(margen,3),
            "stake_1":s1,"stake_X":sX,"stake_2":s2,
            "ganancia":gan,"roi":round(gan/bankroll*100,2),
            "mensaje":f"ARB 3-WAY! Ganancia: ${gan:.2f}"}

def mostrar(res):
    print()
    if res["arb"]:
        print(f"  === ARBITRAJE ENCONTRADO ===")
        print(f"  Margen  : {res['margen']:.2f}%")
        if "stake_casa1" in res:
            print(f"  Stake casa 1: ${res['stake_casa1']:,.2f}")
            print(f"  Stake casa 2: ${res['stake_casa2']:,.2f}")
        else:
            print(f"  Stake 1 (local)  : ${res['stake_1']:,.2f}")
            print(f"  Stake X (empate) : ${res['stake_X']:,.2f}")
            print(f"  Stake 2 (visita) : ${res['stake_2']:,.2f}")
        print(f"  Ganancia garantizada: ${res['ganancia']:,.2f}")
        print(f"  ROI: {res['roi']:.2f}%")
    else:
        print(f"  Sin arb | {res['mensaje']}")
    print()

def ingresar_manual():
    print()
    modo=input("  Tipo: [1] 2 resultados (H2H/O-U)  [2] 1X2 futbol: ").strip()
    bk=float(input("  Bankroll total ($): ").strip() or "10000")
    if modo=="2":
        print("  Mejor cuota de cada casa:")
        o1=float(input("  LOCAL  (ej: 2.10): ").strip())
        oX=float(input("  EMPATE (ej: 3.20): ").strip())
        o2=float(input("  VISITA (ej: 3.50): ").strip())
        mostrar(calcular_arb_3way(o1,oX,o2,bk))
    else:
        o1=float(input("  Cuota Betwarrior: ").strip())
        o2=float(input("  Cuota Bookmaker : ").strip())
        mostrar(calcular_arb(o1,o2,bk))

def leer_grabadas():
    if not ODDS_FILE.exists():
        print(f"  No existe {ODDS_FILE}")
        print("  Primero corra: python GRABAR_BETWARRIOR.py")
        return
    data=json.loads(ODDS_FILE.read_text(encoding="utf-8"))
    print(f"  {len(data)} grupos de cuotas capturadas:")
    for i,d in enumerate(data[:10],1):
        print(f"  [{i:>2}] {d['url'][:65]}")
        print(f"       odds: {d['odds'][:6]}")
    print()
    ingresar_manual()

def main():
    print("""
============================================================
  ARB CALCULATOR v2.0 - Betwarrior vs Bookmaker
  [1] Ingresar cuotas manualmente
  [2] Leer cuotas grabadas (odds_raw.json)
  [0] Salir
============================================================
""")
    while True:
        op=input("Opcion: ").strip()
        if op=="0": break
        elif op=="1": ingresar_manual()
        elif op=="2": leer_grabadas()

if __name__=="__main__":
    main()
