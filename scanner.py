import requests
import os
from colorama import Fore, Style, init
init(autoreset=True)

ODDS_API_KEY = os.environ.get("ODDS_API_KEY", "4ca644e6de87f96db8bac15e467a9e4a")
BASE_URL = "https://api.the-odds-api.com/v4"

SPORTS = {
    "1": {"name": "⚽ FIFA World Cup",            "key": "soccer_fifa_world_cup"},
    "2": {"name": "⚽ Copa Libertadores",          "key": "soccer_conmebol_copa_libertadores"},
    "3": {"name": "⚽ Copa Sudamericana",          "key": "soccer_conmebol_copa_sudamericana"},
    "4": {"name": "⚽ Brazil Serie B",             "key": "soccer_brazil_serie_b"},
    "5": {"name": "⚽ Primera Division Chile",     "key": "soccer_chile_campeonato"},
    "6": {"name": "🎾 WTA Queen's Club",           "key": "tennis_wta_queens_club_champ"},
    "7": {"name": "🏀 NBA",                        "key": "basketball_nba"},
    "8": {"name": "🏀 WNBA",                       "key": "basketball_wnba"},
}

def get_odds(sport_key):
    url = f"{BASE_URL}/sports/{sport_key}/odds/"
    params = {
        "apiKey": ODDS_API_KEY,
        "regions": "eu,us,uk",
        "markets": "h2h",
        "oddsFormat": "decimal",
        "dateFormat": "iso"
    }
    r = requests.get(url, params=params, timeout=15)
    if r.status_code != 200:
        print(Fore.RED + f"Error API ({r.status_code}): {r.text[:200]}")
        return []
    remaining = r.headers.get("x-requests-remaining", "?")
    print(Fore.WHITE + f"  (Requests API restantes hoy: {remaining})")
    return r.json()

def calcular_edge(odds_list):
    if not odds_list or len(odds_list) < 2:
        return 0
    best = sorted(odds_list, reverse=True)[:3]
    prob_total = sum(1/o for o in best)
    edge = (1 - prob_total) * 100
    return round(edge, 2)

def analizar_partido(game):
    home = game.get("home_team", "?")
    away = game.get("away_team", "?")
    commence = game.get("commence_time", "")[:16].replace("T", " ")
    bookmakers = game.get("bookmakers", [])

    best_home = best_away = best_draw = 0
    book_home = book_away = book_draw = ""
    home_odds_all = []
    away_odds_all = []

    for bm in bookmakers:
        bname = bm.get("title", "")
        for market in bm.get("markets", []):
            if market.get("key") != "h2h":
                continue
            for outcome in market.get("outcomes", []):
                price = outcome.get("price", 0)
                oname = outcome.get("name", "")
                if oname == home:
                    home_odds_all.append(price)
                    if price > best_home:
                        best_home = price; book_home = bname
                elif oname == away:
                    away_odds_all.append(price)
                    if price > best_away:
                        best_away = price; book_away = bname
                elif oname == "Draw":
                    if price > best_draw:
                        best_draw = price; book_draw = bname

    return {
        "home": home, "away": away, "commence": commence,
        "best_home": best_home, "book_home": book_home,
        "best_away": best_away, "book_away": book_away,
        "best_draw": best_draw, "book_draw": book_draw,
        "edge_home": calcular_edge(home_odds_all),
        "edge_away": calcular_edge(away_odds_all),
        "bookmakers_count": len(bookmakers)
    }

def mostrar_partidos(sport_key, sport_name):
    print(f"\n{Fore.CYAN}Cargando partidos de {sport_name}...{Style.RESET_ALL}")
    games = get_odds(sport_key)

    if not games:
        print(Fore.YELLOW + "No hay partidos disponibles ahora para este deporte.")
        return []

    partidos = []
    print(f"\n{Fore.WHITE}{'#':>3}  {'REC':>3}  {'PARTIDO':<38} {'HORA':<17} {'LOCAL':>6} {'VISIT':>6} {'DRAW':>5} {'EDGE%':>6} {'LIBROS'}")
    print(Fore.WHITE + "─" * 105)

    for i, game in enumerate(games[:25], 1):
        p = analizar_partido(game)
        partidos.append({**p, "game_id": game.get("id"), "sport": sport_key})

        best_edge = max(p["edge_home"], p["edge_away"])
        if best_edge > 2:
            ec = Fore.GREEN; rec = "✅"
        elif best_edge > 0:
            ec = Fore.YELLOW; rec = "⚠️ "
        else:
            ec = Fore.RED; rec = "❌"

        draw_str = f"{p['best_draw']:.2f}" if p["best_draw"] else " N/A"
        hname = (p["home"][:17] + "..") if len(p["home"]) > 19 else p["home"]
        aname = (p["away"][:15] + "..") if len(p["away"]) > 17 else p["away"]

        print(f"{Fore.WHITE}{i:>3}  {rec}  {hname:<19}vs {aname:<18}"
              f"{p['commence']:<17} "
              f"{Fore.CYAN}{p['best_home']:>6.2f} "
              f"{Fore.MAGENTA}{p['best_away']:>6.2f} "
              f"{Fore.BLUE}{draw_str:>5} "
              f"{ec}{best_edge:>+5.1f}%"
              f"{Fore.WHITE} {p['bookmakers_count']:>4}📚")

    return partidos
