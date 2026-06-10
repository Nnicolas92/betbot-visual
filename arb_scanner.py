#!/usr/bin/env python3
"""
arb_scanner.py v3.0
Scanner automatico de surebets: Betwarrior + Bookmaker.eu
Usa The Odds API (gratis) + scraping directo con Playwright.
Uso: python arb_scanner.py
"""
import asyncio, json, time, os, re
from datetime import datetime
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    import urllib.request as ureq
except: pass

try:
    from playwright.async_api import async_playwright
    PW_OK = True
except ImportError:
    PW_OK = False

# ── CONFIG (lee del .env) ────────────────────────────────────
ODDS_API_KEY   = os.getenv("ODDS_API_KEY", "")
BANKROLL       = float(os.getenv("BANKROLL", "10000"))
MIN_MARGEN     = float(os.getenv("MIN_MARGEN", "0.5"))
SCAN_INTERVAL  = int(os.getenv("SCAN_INTERVAL", "30"))
ALERT_LOG      = Path("surebets_encontrados.json")
UAGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/127.0.0.0 Safari/537.36"

# ── MATEMATICA ───────────────────────────────────────────────
def calcular_arb(odds: list, bankroll=None):
    if bankroll is None: bankroll = BANKROLL
    if len(odds) < 2: return None
    total_imp = sum(1/o for o in odds)
    margen = (1 - total_imp) * 100
    if total_imp >= 1.0:
        return {"arb": False, "margen": round(margen, 3)}
    stakes = [round((bankroll * (1/o)) / total_imp, 2) for o in odds]
    ganancia = round(stakes[0] * odds[0] - bankroll, 2)
    return {
        "arb": True,
        "margen": round(margen, 3),
        "stakes": stakes,
        "ganancia": ganancia,
        "roi": round(ganancia / bankroll * 100, 2)
    }

# ── FUENTE 1: THE ODDS API ───────────────────────────────────
def fetch_odds_api(sport):
    if not ODDS_API_KEY: return []
    url = (f"https://api.the-odds-api.com/v4/sports/{sport}/odds/"
           f"?apiKey={ODDS_API_KEY}&regions=eu,us&markets=h2h"
           f"&oddsFormat=decimal")
    try:
        r = ureq.Request(url, headers={"User-Agent": UAGENT})
        with ureq.urlopen(r, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        eventos = []
        for ev in data:
            bk_odds = {}
            for bk in ev.get("bookmakers", []):
                for mkt in bk.get("markets", []):
                    if mkt["key"] == "h2h":
                        bk_odds[bk["key"]] = [o["price"] for o in mkt["outcomes"]]
            if len(bk_odds) >= 2:
                eventos.append({
                    "evento": f"{ev['home_team']} vs {ev['away_team']}",
                    "deporte": ev.get("sport_title", sport),
                    "inicio": ev.get("commence_time","")[:16],
                    "casas": bk_odds
                })
        return eventos
    except Exception as e:
        print(f"  [OddsAPI] {e}")
        return []

# ── FUENTE 2: SCRAPING BETWARRIOR ────────────────────────────
async def scrape_betwarrior():
    if not PW_OK: return []
    eventos = []
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=["--no-sandbox","--disable-blink-features=AutomationControlled"]
            )
            ctx = await browser.new_context(
                viewport={"width":1366,"height":768},
                user_agent=UAGENT, locale="es-AR"
            )
            page = await ctx.new_page()
            captured_json = []

            async def on_resp(response):
                url = response.url.lower()
                if any(k in url for k in ["odds","event","sport","market","coupon","v1","v2","api"]):
                    try:
                        ct = response.headers.get("content-type","")
                        if "json" in ct:
                            body = await response.text()
                            if len(body) > 50:
                                captured_json.append({"url": response.url, "body": body})
                    except: pass

            page.on("response", on_resp)
            await page.goto("https://mza.betwarrior.bet.ar/es-ar/sports/home",
                wait_until="domcontentloaded", timeout=25000)
            await page.wait_for_timeout(5000)

            # Parseo DOM
            dom_odds = await page.evaluate("""
                () => {
                    const results = [];
                    document.querySelectorAll('[class*="event"],[class*="match"],[class*="game"]').forEach(row => {
                        const odds = [];
                        row.querySelectorAll('[class*="odd"],[class*="price"],[class*="coef"]').forEach(b => {
                            const v = parseFloat(b.innerText);
                            if (!isNaN(v) && v > 1.01 && v < 50) odds.push(v);
                        });
                        const nm = row.querySelector('[class*="name"],[class*="team"],[class*="title"]');
                        if (odds.length >= 2) results.push({
                            evento: nm ? nm.innerText.trim().slice(0,60) : 'Partido BW',
                            odds: odds.slice(0,3)
                        });
                    });
                    return results;
                }
            """)
            for ev in dom_odds:
                if ev["odds"]:
                    eventos.append({
                        "evento": ev["evento"],
                        "deporte": "Futbol",
                        "inicio": "",
                        "casas": {"betwarrior": ev["odds"]}
                    })

            # Parseo JSON de red
            num_re = re.compile(r'\b([1-9]\d*\.\d{1,3})\b')
            for cap in captured_json:
                try:
                    nums = [float(n) for n in num_re.findall(cap["body"]) if 1.01 <= float(n) <= 50]
                    if nums:
                        eventos.append({
                            "evento": f"BW-API: {cap['url'][:40]}",
                            "deporte": "API",
                            "inicio": "",
                            "casas": {"betwarrior_api": nums[:6]}
                        })
                except: pass

            await browser.close()
    except Exception as e:
        print(f"  [Betwarrior] {e}")
    return eventos

# ── ALERTA ───────────────────────────────────────────────────
def alerta_surebet(sb):
    print()
    print("=" * 60)
    print("  *** SUREBET ENCONTRADO! APOSTA AHORA! ***")
    print("=" * 60)
    print(f"  Evento  : {sb['evento']}")
    print(f"  Deporte : {sb['deporte']}")
    if sb['inicio']: print(f"  Inicio  : {sb['inicio']}")
    print(f"  Cuota 1 : {sb['odd1']}   Cuota 2 : {sb['odd2']}")
    print(f"  Margen  : +{sb['margen']:.2f}%")
    print(f"  STAKE 1 : ${sb['stake1']:>10,.0f}")
    print(f"  STAKE 2 : ${sb['stake2']:>10,.0f}")
    print(f"  GANANCIA: ${sb['ganancia']:>10,.0f}  (ROI {sb['roi']:.2f}%)")
    print("=" * 60)
    print()

# ── SCAN ─────────────────────────────────────────────────────
async def scan_once():
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] Escaneando...", end=" ", flush=True)

    eventos = []
    if ODDS_API_KEY:
        for sport in [
            "soccer_argentina_primera_division",
            "soccer_argentina_segunda_division",
            "soccer_conmebol_copa_libertadores",
            "soccer_fifa_world_cup",
            "soccer_spain_la_liga",
            "soccer_england_league1",
            "basketball_nba",
            "tennis_atp_wimbledon"
        ]:
            eventos += fetch_odds_api(sport)

    scraped = await scrape_betwarrior()
    eventos += scraped
    print(f"{len(eventos)} eventos")

    surebets = []
    for ev in eventos:
        casas = ev.get("casas", {})
        if not casas: continue
        todos = []
        for odds in casas.values():
            if isinstance(odds, list): todos.extend(odds)
            elif isinstance(odds, (int,float)): todos.append(float(odds))
        if len(todos) < 2: continue
        for i in range(len(todos)):
            for j in range(i+1, len(todos)):
                res = calcular_arb([todos[i], todos[j]])
                if res and res["arb"] and res["margen"] >= MIN_MARGEN:
                    sb = {
                        "timestamp": datetime.now().isoformat(),
                        "evento":    ev["evento"],
                        "deporte":   ev["deporte"],
                        "inicio":    ev["inicio"],
                        "odd1":      todos[i],
                        "odd2":      todos[j],
                        "margen":    res["margen"],
                        "stake1":    res["stakes"][0],
                        "stake2":    res["stakes"][1],
                        "ganancia":  res["ganancia"],
                        "roi":       res["roi"]
                    }
                    surebets.append(sb)
                    alerta_surebet(sb)

    if surebets:
        hist = []
        if ALERT_LOG.exists():
            try: hist = json.loads(ALERT_LOG.read_text(encoding="utf-8"))
            except: pass
        ALERT_LOG.write_text(json.dumps(hist + surebets, indent=2, ensure_ascii=False), encoding="utf-8")

    if not surebets:
        print(f"  Sin surebets por ahora...")
    return surebets

# ── LOOP PRINCIPAL ───────────────────────────────────────────
async def main():
    print("""
============================================================
  BETBOT SCANNER v3.0 - Surebets Garantizados
  Betwarrior + Bookmaker.eu
============================================================
  Bankroll    : ${:,.0f}
  Margen min  : {:.1f}%
  Intervalo   : {}s
  API Key     : {}
============================================================
  Ctrl+C para detener. Surebets se guardan en:
  surebets_encontrados.json
============================================================
""".format(BANKROLL, MIN_MARGEN, SCAN_INTERVAL,
           "CONFIGURADA OK" if ODDS_API_KEY else "NO configurada (solo scraping Betwarrior)"))

    total = 0
    while True:
        try:
            sb = await scan_once()
            total += len(sb)
            await asyncio.sleep(SCAN_INTERVAL)
        except KeyboardInterrupt:
            print(f"\nDetenido. Total surebets encontrados en esta sesion: {total}")
            break
        except Exception as e:
            print(f"  Error: {e}")
            await asyncio.sleep(10)

if __name__ == "__main__":
    asyncio.run(main())
