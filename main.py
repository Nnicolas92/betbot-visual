#!/usr/bin/env python3
"""
BetBot Visual v4
Login automatico + busqueda de partido + arbitraje en DOS casas
Credenciales: copiar .env.example como .env y completar
"""
from colorama import Fore, Style, init
init(autoreset=True)
from scanner import SPORTS, mostrar_partidos
from visual_bot import CASAS, abrir_arbitraje_sync
from config import get_cred

BANNER = f"""
{Fore.GREEN}╔══════════════════════════════════════════════════════╗
║    🎰 BETBOT VISUAL v4 — Login + DOS casas           ║
║    Credenciales: editá el archivo .env               ║
╚══════════════════════════════════════════════════════╝{Style.RESET_ALL}
"""

def elegir_deporte():
    print(f"\n{Fore.CYAN}╔═ ELEGÍ UN DEPORTE ══════════════════════════════════╗")
    for k, v in SPORTS.items():
        print(f"║  [{k}] {v['name']:<48}║")
    print(f"╚═════════════════════════════════════════════════════╝{Style.RESET_ALL}")
    while True:
        sel = input("▶ Deporte (1-8): ").strip()
        if sel in SPORTS: return sel
        print(Fore.RED + "Número inválido.")

def elegir_partido(partidos):
    print(f"\n{Fore.YELLOW}Ingresá el número del partido (0 = volver):{Style.RESET_ALL}")
    while True:
        sel = input("▶ Partido #: ").strip()
        if sel == "0": return None
        try:
            idx = int(sel) - 1
            if 0 <= idx < len(partidos): return partidos[idx]
        except: pass
        print(Fore.RED + f"Usá 1-{len(partidos)}.")

def elegir_casa(label):
    print(f"\n{Fore.CYAN}╔═ {label} ═══════════════════════════════════════════╗")
    for k, v in CASAS.items():
        cred = get_cred(k)
        estado = "🔑 con creds" if cred.get("user") and cred.get("password") else "📝 completar .env"
        print(f"║  [{k}] {v['name']:<20} {estado:<28}║")
    print(f"╚═════════════════════════════════════════════════════╝{Style.RESET_ALL}")
    while True:
        sel = input(f"▶ {label} (1-3): ").strip()
        if sel in CASAS: return sel
        print(Fore.RED + "Inválido.")

def mostrar_resumen(partido):
    h = partido["best_home"]; a = partido["best_away"]; d = partido.get("best_draw") or 0
    suma = (1/h) + (1/a) + (1/d if d else 0)
    arb = (f"{Fore.GREEN}🟢 ARBITRAJE +{((1-suma)/suma)*100:.2f}%"
           if suma < 1 else
           f"{Fore.RED}🔴 Sin arbitraje (overround {(suma-1)*100:.1f}%)")
    print(f"""
{Fore.WHITE}┌──────────────────────────────────────────────────────┐
│  🏟  {partido['home']} vs {partido['away']}
│  LOCAL:     {Fore.GREEN}{partido['best_home']:.2f}{Fore.WHITE} ({partido['book_home']})
│  VISITANTE: {Fore.GREEN}{partido['best_away']:.2f}{Fore.WHITE} ({partido['book_away']})""")
    if d: print(f"│  EMPATE:    {Fore.GREEN}{d:.2f}{Fore.WHITE} ({partido.get('book_draw','')})")
    print(f"│  {arb}")
    print(f"{Fore.WHITE}└──────────────────────────────────────────────────────┘{Style.RESET_ALL}")

def pedir_monto():
    while True:
        try:
            m = float(input(f"\n{Fore.YELLOW}▶ Monto total a apostar (ej: 100): ${Style.RESET_ALL}").strip())
            if m > 0: return m
        except: pass
        print(Fore.RED + "Ingresá un número válido.")

def main():
    print(BANNER)
    print(f"{Fore.YELLOW}📁 Para configurar credenciales: copiá .env.example como .env y completalo{Style.RESET_ALL}\n")

    while True:
        sport_idx = elegir_deporte()
        sport = SPORTS[sport_idx]
        partidos = mostrar_partidos(sport["key"], sport["name"])
        if not partidos: continue

        partido = elegir_partido(partidos)
        if not partido: continue

        mostrar_resumen(partido)

        print(f"\n{Fore.CYAN}¿Qué hacemos?{Style.RESET_ALL}")
        print("  [1] Abrir UNA casa")
        print("  [2] Abrir DOS casas — Login + Buscar partido + APOSTAR")
        print("  [0] Volver")
        modo = input("▶ Opción: ").strip()

        if modo == "2":
            c1 = elegir_casa("CASA 1 — local/home")
            c2 = elegir_casa("CASA 2 — visitante/away")
            monto = pedir_monto()
            creds = {}
            for ck in [c1, c2]:
                cr = get_cred(ck)
                if not cr.get("user"):
                    cr["user"] = input(f"  Usuario {CASAS[ck]['name']}: ").strip()
                if not cr.get("password"):
                    cr["password"] = input(f"  Contraseña {CASAS[ck]['name']}: ").strip()
                creds[ck] = cr
            abrir_arbitraje_sync(c1, c2, partido, creds, monto)

        elif modo == "1":
            c = elegir_casa("CASA")
            cr = get_cred(c)
            if not cr.get("user"): cr["user"] = input(f"  Usuario: ").strip()
            if not cr.get("password"): cr["password"] = input(f"  Contraseña: ").strip()
            abrir_arbitraje_sync(c, c, partido, {c: cr}, 100)

        otra = input(f"\n{Fore.YELLOW}¿Ver otro partido? (s/n): {Style.RESET_ALL}").strip().lower()
        if otra != "s": break

    print(f"\n{Fore.GREEN}✅ Listo. Revisá /screenshots/{Style.RESET_ALL}\n")

if __name__ == "__main__":
    main()
