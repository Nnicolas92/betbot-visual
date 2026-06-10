#!/usr/bin/env python3
from colorama import Fore, Style, init
init(autoreset=True)
from scanner import SPORTS, mostrar_partidos
from visual_bot import CASAS, abrir_casa

BANNER = f"""
{Fore.GREEN}╔══════════════════════════════════════════════════════╗
║         🎰 BETBOT VISUAL — Scanner + Navegador       ║
║              The Odds API + Playwright               ║
╚══════════════════════════════════════════════════════╝{Style.RESET_ALL}
"""

def elegir_deporte():
    print(f"\n{Fore.CYAN}╔═ ELEGÍ UN DEPORTE ════════════════════╗")
    for k, v in SPORTS.items():
        print(f"║  [{k}] {v['name']:<34}║")
    print(f"╚═══════════════════════════════════════╝{Style.RESET_ALL}")
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

def elegir_casa():
    print(f"\n{Fore.CYAN}╔═ ELEGÍ LA CASA ═══════════════════════╗")
    for k, v in CASAS.items():
        print(f"║  [{k}] {v['name']:<34}║")
    print(f"╚═══════════════════════════════════════╝{Style.RESET_ALL}")
    while True:
        sel = input("▶ Casa (1-3): ").strip()
        if sel in CASAS:
            return sel
        print(Fore.RED + "Número inválido.")

def mostrar_resumen(partido):
    best_edge = max(partido.get("edge_home", 0), partido.get("edge_away", 0))
    if best_edge > 2:
        verdict = f"{Fore.GREEN}✅ CONVIENE — Edge: +{best_edge:.1f}%"
    elif best_edge > 0:
        verdict = f"{Fore.YELLOW}⚠️  MARGINAL — Edge: +{best_edge:.1f}%"
    else:
        verdict = f"{Fore.RED}❌ NO CONVIENE — Edge: {best_edge:.1f}%"
    print(f"""
{Fore.WHITE}┌──────────────────────────────────────────────────┐
│  🏟  {partido['home']} vs {partido['away']}
│  🕐  {partido['commence']}
│
│  LOCAL:     {Fore.GREEN}{partido['best_home']:.2f}{Fore.WHITE} via {partido['book_home']}
│  VISITANTE: {Fore.GREEN}{partido['best_away']:.2f}{Fore.WHITE} via {partido['book_away']}""")
    if partido.get("best_draw") and partido["best_draw"] > 0:
        print(f"│  EMPATE:    {Fore.GREEN}{partido['best_draw']:.2f}{Fore.WHITE} via {partido['book_draw']}")
    print(f"│\n│  {verdict}\n{Fore.WHITE}└──────────────────────────────────────────────────┘{Style.RESET_ALL}")

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
        ver = input(f"\n{Fore.CYAN}¿Abrir navegador? (s/n): {Style.RESET_ALL}").strip().lower()
        if ver == "s":
            casa_key = elegir_casa()
            abrir_casa(casa_key, partido)
        otra = input(f"\n{Fore.YELLOW}¿Ver otro partido? (s/n): {Style.RESET_ALL}").strip().lower()
        if otra != "s":
            break
    print(f"\n{Fore.GREEN}✅ Listo. Revisá la carpeta /screenshots/{Style.RESET_ALL}\n")

if __name__ == "__main__":
    main()
