#!/usr/bin/env python3
"""
arb_scanner.py v3.2
Scanner automatico de surebets: Betwarrior + Bookmaker.eu
"""
import asyncio, json, os, re, time
from datetime import datetime
from pathlib import Path
import urllib.request as ureq
import urllib.error

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    from playwright.async_api import async_playwright
    PW_OK = True
except ImportError:
    PW_OK = False
    print("[AVISO] Playwright no instalado. Solo se usara OddsAPI.")
    print("        Correr: pip install playwright && python -m playwright install chromium")

# CONFIG
ODDS_API_KEY  = os.getenv("ODDS_API_KEY", "").strip()
BANKROLL      = float(os.getenv("BANKROLL", "10000"))
MIN_MARGEN    = float(os.getenv("MIN_MARGEN", "0.5"))
SCAN_INTERVAL = int(os.getenv("SCAN_INTERVAL", "30"))
ALERT_LOG     = Path("surebets_encontrados.json")
UAGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/127.0.0.0 Safari/537.36"

# Deportes que no soportan h2h (causan 422)
SKIP_MARKETS = ["_winner", "_championship", "_outright", "_season"]

# Cache de deportes
_sports_cache = []
_sports_ts    = 0

# ── MATEMATICA ───────────────────────────────────────────────────────────────
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
        "arb":      True,
        "margen":   round(margen, 3),
        "stakes":   stakes,
        "ganancia": ganancia,
        "roi":      round(ganancia / bankroll * 100, 2)
    }

# ── ODDS API ─────────────────────────────────────────────────────────────────
def get_sports():
    global _sports_cache, _sports_ts
    if not ODDS_API_KEY: return []
    if time.time() - _sports_ts < 600 and _sports_cache:
        return _sports_cache
    try:
        r = ureq.Request(
            f"https://api.the-odds-api.com/v4/sports/?apiKey={ODDS_API_KEY}",
            headers={"User-Agent": UAGENT}
        )
        with ureq.urlopen(r, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        # Filtrar deportes que sabemos que fallan con h2h
        activos = [
            s["key"] for s in data
            if s.get("active", False)
            and not any(skip in s["key"] for skip in SKIP_MARKETS)
        ]
        _sports_cache = activos
        _sports_ts    = time.time()
        print(f"  [API] {len(activos)} deportes activos cargados")
        return activos
    except Exception as e:
        print(f"  [API] Error cargando deportes: {e}")
        return _sports_cache

def fetch_odds(sport):
    if not ODDS_API_KEY: return []
    url = (f"https://api.the-odds-api.com/v4/sports/{sport}/odds/"
           f"?apiKey={ODDS_API_KEY}&regions=eu,us,uk&markets=h2h&oddsFormat=decimal")
    try:
        r = ureq.Request(url, headers={"User-Agent": UAGENT})
        with ureq.urlopen(r, timeout=12) as resp:
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
                    "evento":  f"{ev['home_team']} vs {ev['away_team']}",
                    "deporte": ev.get("sport_title", sport),
                    "inicio":  ev.get("commence_time","")[:16],
                    "casas":   bk_odds
                })
        return eventos
    except urllib.error.HTTPError:
        return []  # silenciar 404/422 completamente
    except Exception as e:
        print(f"  [API/{sport[:20]}] {e}")
        return []

# ── SCRAPING BETWARRIOR ───────────────────────────────────────────────────────
async def scrape_betwarrior():
    if not PW_OK: return []
    eventos = []
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-blink-features=AutomationControlled"]
            )
            ctx = await browser.new_context(
                viewport={"width": 1366, "height": 768},
                user_agent=UAGENT,
                locale="es-AR"
            )
            page = await ctx.new_page()
            captured = []

            async def capturar(response):
                url = response.url.lower()
                if any(k in url for k in ["odds","event","sport","market","coupon","v1/","v2/"]):
                    try:
                        ct = response.headers.get("content-type", "")
                        if "json" in ct:
                            body = await response.text()
                            if len(body) > 80:
                                captured.append({"url": response.url, "body": body})
                    except: pass

            page.on("response", capturar)

            print("  [BW] Abriendo Betwarrior...", end=" ", flush=True)
            await page.goto(
                "https://mza.betwarrior.bet.ar/es-ar/sports/home",
                wait_until="domcontentloaded",
                timeout=30000
            )
            # Esperar que carguen las cuotas
            await page.wait_for_timeout(6000)
            print("listo")

            # Parsear cuotas del DOM
            dom = await page.evaluate("""
                () => {
                    const res = [];
                    document.querySelectorAll(
                        '[class*="event"],[class*="match"],[class*="game"],[class*="fixture"]'
                    ).forEach(row => {
                        const odds = [];
                        row.querySelectorAll(
                            '[class*="odd"],[class*="price"],[class*="coef"],[class*="rate"]'
                        ).forEach(b => {
                            const v = parseFloat(b.innerText.replace(',','.'));
                            if (!isNaN(v) && v > 1.01 && v < 50) odds.push(v);
                        });
                        const nm = row.querySelector(
                            '[class*="name"],[class*="team"],[class*="participant"],[class*="title"]'
                        );
                        if (odds.length >= 2) res.push({
                            evento: nm ? nm.innerText.trim().slice(0,60) : 'Partido BW',
                            odds:   [...new Set(odds)].slice(0,4)
                        });
                    });
                    return res;
                }
            """)

            for ev in dom:
                if ev["odds"]:
                    eventos.append({
                        "evento":  ev["evento"],
                        "deporte": "Futbol",
                        "inicio":  "",
                        "casas":   {"betwarrior": ev["odds"]}
                    })

            # Parsear JSON de red capturados
            num_re = re.compile(r'\b([1-9]\d*\.\d{1,3})\b')
            for cap in captured:
                try:
                    nums = [float(n) for n in num_re.findall(cap["body"])
                            if 1.01 <= float(n) <= 50]
                    if nums:
                        eventos.append({
                            "evento":  f"BW-NET: {cap['url'][-35:]}",
                            "deporte": "API-BW",
                            "inicio":  "",
                            "casas":   {"betwarrior_net": nums[:8]}
                        })
                except: pass

            await browser.close()
            print(f"  [BW] {len(dom)} partidos en DOM | {len(captured)} respuestas de red")

    except Exception as e:
        print(f"  [BW] Error: {e}")
    return eventos

# ── ALERTA ────────────────────────────────────────────────────────────────────
def alerta_surebet(sb):
    print()
    print("=" * 62)
    print("  ***  SUREBET ENCONTRADO  -  APOSTA AHORA!  ***")
    print("=" * 62)
    print(f"  Evento  : {sb['evento']}")
    print(f"  Deporte : {sb['deporte']}")
    if sb["inicio"]: print(f"  Inicio  : {sb['inicio']}")
    print(f"  Cuota 1 : {sb['odd1']}        Cuota 2 : {sb['odd2']}")
    print(f"  Margen  : +{sb['margen']:.2f}%")
    print(f"  STAKE 1 : ${sb['stake1']:>12,.2f}")
    print(f"  STAKE 2 : ${sb['stake2']:>12,.2f}")
    print(f"  GANANCIA: ${sb['ganancia']:>12,.2f}   ROI: {sb['roi']:.2f}%")
    print("=" * 62)
    print()

# ── PROCESADOR DE EVENTOS ─────────────────────────────────────────────────────
def buscar_surebets(eventos):
    surebets = []
    for ev in eventos:
        casas = ev.get("casas", {})
        if not casas: continue
        todos = []
        for odds in casas.values():
            if isinstance(odds, list):            todos.extend(odds)
            elif isinstance(odds, (int,float)):   todos.append(float(odds))
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
                        **res
                    }
                    surebets.append(sb)
                    alerta_surebet(sb)
    return surebets

# ── SCAN PRINCIPAL ────────────────────────────────────────────────────────────
async def scan_once():
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"\n[{ts}] ---- INICIO DE SCAN ----")

    eventos = []

    # OddsAPI
    if ODDS_API_KEY:
        sports = get_sports()
        print(f"  [API] Consultando {len(sports)} deportes...")
        for sport in sports:
            ev = fetch_odds(sport)
            if ev:
                print(f"    {sport[:35]:<35} {len(ev)} eventos")
            eventos += ev
        print(f"  [API] Total: {len(eventos)} eventos con cuotas multiples")
    else:
        print("  [API] Sin API key - solo Betwarrior")

    # Betwarrior scraping
    bw = await scrape_betwarrior()
    eventos += bw

    print(f"  [TOTAL] {len(eventos)} eventos a analizar")

    # Buscar surebets
    surebets = buscar_surebets(eventos)

    if surebets:
        hist = []
        if ALERT_LOG.exists():
            try: hist = json.loads(ALERT_LOG.read_text(encoding="utf-8"))
            except: pass
        ALERT_LOG.write_text(
            json.dumps(hist + surebets, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )
        print(f"  [GUARDADO] {len(surebets)} surebet(s) en {ALERT_LOG}")
    else:
        print(f"  [RESULTADO] Sin surebets (margen min: {MIN_MARGEN}%)")

    return surebets

# ── LOOP ──────────────────────────────────────────────────────────────────────
async def main():
    print("""
================================================================
  BETBOT SCANNER v3.2 - Surebets Garantizados
  Betwarrior + Bookmaker.eu + 40 deportes
================================================================
  Bankroll    : ${:,.0f}
  Margen min  : {:.1f}%
  Intervalo   : {}s entre scans
  API Key     : {}
================================================================
  Surebets se guardan en: surebets_encontrados.json
  Ctrl+C para detener
================================================================""".format(
        BANKROLL, MIN_MARGEN, SCAN_INTERVAL,
        "CONFIGURADA OK" if ODDS_API_KEY else "NO configurada"
    ))

    total = 0
    scan_n = 0
    while True:
        try:
            sb = await scan_once()
            total  += len(sb)
            scan_n += 1
            print(f"\n  Scans: {scan_n} | Surebets totales: {total} | Proximo scan en {SCAN_INTERVAL}s...")
            await asyncio.sleep(SCAN_INTERVAL)
        except KeyboardInterrupt:
            print(f"\nDetenido. Total surebets encontrados: {total}")
            break
        except Exception as e:
            print(f"  Error inesperado: {e}")
            await asyncio.sleep(10)

if __name__ == "__main__":
    asyncio.run(main())
