#!/usr/bin/env python3
from colorama import Fore, Style, init
init(autoreset=True)
from scanner import SPORTS, mostrar_partidos
from visual_bot import CASAS, abrir_casa, abrir_arbitraje_sync

BANNER = f"""
{Fore.GREEN}╔══════════════════════════════════════════════════════╗
║      🎰 BETBOT VISUAL v2 — Arbitraje + Stealth       ║
║           The Odds API + Playwright Stealth           ║
╚══════════════════════════════════════════════════════╝{Style.RESET_ALL}
"""

def elegir_deporte():
    print(f"\n{Fore.CYAN}╔═ ELEGÍ UN DEPORTE ══════════════════════════╗")
    for k, v in SPORTS.items():
        print(f"║  [{k}] {v['name']:<40}║")
    print(f"╚═════════════════════════════════════════════╝{Style.RESET_ALL}")
    while True:
        sel = input("▶ Deporte (1-8): ").strip()
        if sel in SPORTS:
            return sel
        print(Fore.RED + "Número inválido.")

def elegir_partido(partidos):
    print(f"\n{Fore.YELLOW}Ingresá el número del partido (0 para volver):{Style.RESET_ALL}")
    while True:
        sel = input("▶ Partido #: ").strip()
        if sel == "0":
            return None
        try:
            idx = int(sel) - 1
            if 0 <= idx < len(partidos):
                return partidos[idx]
        except:
            pass
        print(Fore.RED + f"Número inválido. Usá 1-{len(partidos)}.")

def elegir_casa(label="Casa"):
    print(f"\n{Fore.CYAN}╔═ ELEGÍ {label} ══════════════════════════════╗")
    for k, v in CASAS.items():
        print(f"║  [{k}] {v['name']:<40}║")
    print(f"╚═════════════════════════════════════════════╝{Style.RESET_ALL}")
    while True:
        sel = input(f"▶ {label} (1-3): ").strip()
        if sel in CASAS:
            return sel
        print(Fore.RED + "Número inválido.")

def mostrar_resumen(partido):
    best_edge = max(partido.get("edge_home",0), partido.get("edge_away",0))
    if best_edge > 2:
        verdict = f"{Fore.GREEN}✅ CONVIENE — Edge: +{best_edge:.1f}%"
    elif best_edge > 0:
        verdict = f"{Fore.YELLOW}⚠️  MARGINAL — Edge: +{best_edge:.1f}%"
    else:
        verdict = f"{Fore.RED}❌ NO CONVIENE — Edge: {best_edge:.1f}%"
    h = partido["best_home"]; a = partido["best_away"]; d = partido.get("best_draw",0)
    suma = (1/h) + (1/a) + (1/d if d else 0)
    arb = f"{Fore.GREEN}🟢 ARBITRAJE +{((1-suma)/suma)*100:.2f}%" if suma < 1 else f"{Fore.RED}🔴 Sin arbitraje puro"
    print(f"\n{Fore.WHITE}┌──────────────────────────────────────────────┐")
    print(f"│  🏟  {partido['home']} vs {partido['away']}")
    print(f"│  🕐  {partido['commence']}")
    print(f"│  LOCAL:     {Fore.GREEN}{partido['best_home']:.2f}{Fore.WHITE} ({partido['book_home']})")
    print(f"│  VISITANTE: {Fore.GREEN}{partido['best_away']:.2f}{Fore.WHITE} ({partido['book_away']})")
    if d and d > 0:
        print(f"│  EMPATE:    {Fore.GREEN}{partido['best_draw']:.2f}{Fore.WHITE} ({partido['book_draw']})")
    print(f"│  {verdict}")
    print(f"│  {arb}")
    print(f"{Fore.WHITE}└──────────────────────────────────────────────┘{Style.RESET_ALL}")

def main():
    print(BANNER)
    while True:
        sport_idx = elegir_deporte()
        sport = SPORTS[sport_idx]
        partidos = mostrar_partidos(sport["key"], sport["name"])
        if not partidos:
            continue
        partido = elegir_partido(partidos)
        if not partido:
            continue
        mostrar_resumen(partido)
        print(f"\n{Fore.CYAN}¿Qué hacemos?{Style.RESET_ALL}")
        print("  [1] Abrir UNA casa")
        print("  [2] Abrir DOS casas para ARBITRAJE")
        print("  [0] Volver")
        modo = input("▶ Opción: ").strip()
        if modo == "1":
            abrir_casa(elegir_casa(), partido)
        elif modo == "2":
            print(f"{Fore.YELLOW}Elegí las 2 casas donde vas a apostar:{Style.RESET_ALL}")
            abrir_arbitraje_sync(elegir_casa("CASA 1"), elegir_casa("CASA 2"), partido)
        otra = input(f"\n{Fore.YELLOW}¿Ver otro partido? (s/n): {Style.RESET_ALL}").strip().lower()
        if otra != "s":
            break
    print(f"\n{Fore.GREEN}✅ Listo. /screenshots/{Style.RESET_ALL}\n")

if __name__ == "__main__":
    main()
