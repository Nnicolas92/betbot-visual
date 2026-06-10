#!/usr/bin/env python3
"""
arb_scanner.py v3.5
Scanner automatico de surebets reales entre casas
Fuentes: OddsAPI (cuotas por casa) + Betwarrior (DOM scraping)
"""
import asyncio, json, os, time
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
    print("[AVISO] Playwright no instalado. Solo OddsAPI.")

# CONFIG
ODDS_API_KEY  = os.getenv("ODDS_API_KEY", "").strip()
BANKROLL      = float(os.getenv("BANKROLL", "10000"))
MIN_MARGEN    = float(os.getenv("MIN_MARGEN", "0.5"))
SCAN_INTERVAL = int(os.getenv("SCAN_INTERVAL", "30"))
ALERT_LOG     = Path("surebets_encontrados.json")
UAGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/127.0 Safari/537.36"
SKIP_MARKETS  = ["_winner","_championship","_outright","_season"]

_sports_cache = []
_sports_ts    = 0

# MATEMATICA
def calcular_arb(odd1, odd2, bankroll=None):
    if bankroll is None: bankroll = BANKROLL
    total_imp = 1/odd1 + 1/odd2
    margen = (1 - total_imp) * 100
    if total_imp >= 1.0:
        return None
    s1 = round((bankroll / odd1) / total_imp * odd1 / odd1, 2)  # = bankroll * (1/odd1) / total_imp
    s1 = round(bankroll * (1/odd1) / total_imp, 2)
    s2 = round(bankroll * (1/odd2) / total_imp, 2)
    ganancia = round(s1 * odd1 - bankroll, 2)
    return {
        "margen":   round(margen, 3),
        "stakes":   [s1, s2],
        "ganancia": ganancia,
        "roi":      round(ganancia / bankroll * 100, 2)
    }

# ODDS API
def get_sports():
    global _sports_cache, _sports_ts
    if not ODDS_API_KEY: return []
    if time.time() - _sports_ts < 600 and _sports_cache:
        return _sports_cache
    try:
        req = ureq.Request(
            f"https://api.the-odds-api.com/v4/sports/?apiKey={ODDS_API_KEY}",
            headers={"User-Agent": UAGENT}
        )
        with ureq.urlopen(req, timeout=10) as r:
            data = json.loads(r.read().decode())
        activos = [s["key"] for s in data
                   if s.get("active") and not any(x in s["key"] for x in SKIP_MARKETS)]
        _sports_cache = activos
        _sports_ts    = time.time()
        print(f"  [API] {len(activos)} deportes activos")
        return activos
    except Exception as e:
        print(f"  [API] Error deportes: {e}")
        return _sports_cache

def fetch_odds(sport):
    """
    Devuelve lista de eventos.
    Cada evento tiene 'pares': lista de {odd1, casa1, odd2, casa2, label}
    para cada combinacion de outcomes de casas distintas.
    """
    if not ODDS_API_KEY: return []
    url = (f"https://api.the-odds-api.com/v4/sports/{sport}/odds/"
           f"?apiKey={ODDS_API_KEY}&regions=eu,us,uk,au&markets=h2h&oddsFormat=decimal")
    try:
        req = ureq.Request(url, headers={"User-Agent": UAGENT})
        with ureq.urlopen(req, timeout=15) as r:
            data = json.loads(r.read().decode())

        eventos = []
        for ev in data:
            # Construir mapa: outcome -> lista de (odd, bookmaker)
            outcome_map = {}  # "Team A" -> [(odd, "casa"), ...]
            for bk in ev.get("bookmakers", []):
                for mkt in bk.get("markets", []):
                    if mkt["key"] != "h2h":
                        continue
                    for oc in mkt.get("outcomes", []):
                        nm = oc["name"]
                        pr = float(oc["price"])
                        if nm not in outcome_map:
                            outcome_map[nm] = []
                        outcome_map[nm].append((pr, bk["key"]))

            if len(outcome_map) < 2:
                continue

            # Para cada outcome, quedarse con la MEJOR cuota y su casa
            best = {}  # nm -> {"odd": x, "casa": y}
            for nm, lista in outcome_map.items():
                top = max(lista, key=lambda x: x[0])
                best[nm] = {"odd": top[0], "casa": top[1]}

            if len(best) >= 2:
                eventos.append({
                    "evento":  f"{ev['home_team']} vs {ev['away_team']}",
                    "deporte": ev.get("sport_title", sport),
                    "inicio":  ev.get("commence_time", "")[:16],
                    "best":    best
                })

        return eventos

    except urllib.error.HTTPError as e:
        if e.code not in (404, 422):
            print(f"  [API/{sport[:20]}] HTTP {e.code}")
        return []
    except Exception as e:
        print(f"  [API/{sport[:20]}] {e}")
        return []

# SCRAPING BETWARRIOR
async def scrape_betwarrior():
    if not PW_OK: return []
    eventos = []
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-blink-features=AutomationControlled"]
            )
            ctx  = await browser.new_context(
                viewport={"width": 1366, "height": 768},
                user_agent=UAGENT, locale="es-AR"
            )
            page = await ctx.new_page()
            print("  [BW] Abriendo Betwarrior...", end=" ", flush=True)
            await page.goto(
                "https://mza.betwarrior.bet.ar/es-ar/sports/home",
                wait_until="networkidle",
                timeout=40000
            )
            await page.wait_for_timeout(4000)
            html_len = len(await page.content())
            print(f"listo (html: {html_len} chars)")

            # Intentar esperar que aparezcan cuotas en el DOM
            try:
                await page.wait_for_selector(
                    "[class*='odd'],[class*='price'],[class*='coef']",
                    timeout=8000
                )
            except:
                print("  [BW] Selector de cuotas no encontrado")

            dom = await page.evaluate("""
              () => {
                const res = [];

                // Estrategia 1: buscar contenedores de partido
                const containers = [
                  ...document.querySelectorAll(
                    '[class*="event"],[class*="match"],[class*="fixture"],[class*="game"]'
                  )
                ];

                containers.forEach(row => {
                  const txt   = row.innerText || '';
                  const lines = txt.split('\\n').map(l => l.trim()).filter(Boolean);

                  // Extraer numeros que parezcan cuotas (1.10 a 29.99)
                  const odds = [];
                  lines.forEach(l => {
                    const v = parseFloat(l.replace(',','.'));
                    if (!isNaN(v) && v >= 1.10 && v <= 29.99 &&
                        l.match(/^\\d+[.,]\\d{1,3}$/)) {
                      odds.push(v);
                    }
                  });

                  // Buscar nombre de equipo
                  const nmEl = row.querySelector(
                    '[class*="team"],[class*="name"],[class*="participant"],[class*="home"],[class*="away"]'
                  );
                  const nombre = nmEl ? nmEl.innerText.trim() : lines[0] || '';

                  const uq = [...new Set(odds)];
                  if (uq.length >= 2 && nombre.length > 2 &&
                      !nombre.includes('/') && !nombre.includes('.')) {
                    res.push({ nombre: nombre.slice(0,60), odds: uq.slice(0,3) });
                  }
                });

                return res;
              }
            """)

            print(f"  [BW] {len(dom)} partidos encontrados en DOM")

            for ev in dom:
                best = {}
                for idx, odd in enumerate(ev["odds"]):
                    best[f"resultado_{idx+1}"] = {"odd": odd, "casa": "betwarrior"}
                eventos.append({
                    "evento":  ev["nombre"],
                    "deporte": "Futbol (BW)",
                    "inicio":  "",
                    "best":    best
                })

            await browser.close()
    except Exception as e:
        print(f"  [BW] Error: {e}")
    return eventos

# ALERTA
def alerta_surebet(sb):
    s1 = sb["stakes"][0]
    s2 = sb["stakes"][1]
    print()
    print("=" * 66)
    print("  ***  SUREBET ENCONTRADO  -  APOSTA AHORA!  ***")
    print("=" * 66)
    print(f"  Evento   : {sb['evento']}")
    print(f"  Deporte  : {sb['deporte']}")
    if sb.get("inicio"): print(f"  Inicio   : {sb['inicio']}")
    print(f"  {'─'*62}")
    print(f"  APUESTA 1: ${s1:>10,.2f}  cuota {sb['odd1']:.2f}  --> {sb['casa1'].upper()}")
    print(f"  APUESTA 2: ${s2:>10,.2f}  cuota {sb['odd2']:.2f}  --> {sb['casa2'].upper()}")
    print(f"  {'─'*62}")
    print(f"  Margen   : +{sb['margen']:.2f}%")
    print(f"  GANANCIA : ${sb['ganancia']:>10,.2f}   ROI: {sb['roi']:.2f}%")
    print("=" * 66)
    print()

# BUSCADOR
def buscar_surebets(eventos):
    surebets = []
    for ev in eventos:
        best = ev.get("best", {})
        if len(best) < 2: continue
        items = list(best.items())
        for i in range(len(items)):
            for j in range(i+1, len(items)):
                nm_i, dat_i = items[i]
                nm_j, dat_j = items[j]
                odd1  = dat_i["odd"]
                odd2  = dat_j["odd"]
                casa1 = dat_i["casa"]
                casa2 = dat_j["casa"]
                if casa1 == casa2: continue  # mismo bookie = no es surebet
                res = calcular_arb(odd1, odd2)
                if res and res["margen"] >= MIN_MARGEN:
                    sb = {
                        "timestamp": datetime.now().isoformat(),
                        "evento":    ev["evento"],
                        "deporte":   ev["deporte"],
                        "inicio":    ev.get("inicio", ""),
                        "odd1":  odd1, "casa1": casa1, "outcome1": nm_i,
                        "odd2":  odd2, "casa2": casa2, "outcome2": nm_j,
                        **res
                    }
                    surebets.append(sb)
                    alerta_surebet(sb)
    return surebets

# SCAN
async def scan_once():
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"\n[{ts}] ---- INICIO DE SCAN ----")
    eventos = []

    if ODDS_API_KEY:
        sports = get_sports()
        print(f"  [API] Consultando {len(sports)} deportes...")
        ok = 0
        for sport in sports:
            ev = fetch_odds(sport)
            if ev:
                print(f"    {sport[:35]:<35} {len(ev)} eventos")
                ok += 1
            eventos += ev
        if ok == 0:
            print("  [API] ADVERTENCIA: ningun deporte devolvio eventos.")
            print("        Verificar API key en .env (ODDS_API_KEY=...)")
        print(f"  [API] Total: {len(eventos)} eventos")
    else:
        print("  [API] Sin API key - solo Betwarrior")

    bw = await scrape_betwarrior()
    eventos += bw
    print(f"  [TOTAL] {len(eventos)} eventos a analizar")

    surebets = buscar_surebets(eventos)

    if surebets:
        hist = []
        if ALERT_LOG.exists():
            try: hist = json.loads(ALERT_LOG.read_text(encoding="utf-8"))
            except: pass
        ALERT_LOG.write_text(
            json.dumps(hist + surebets, indent=2, ensure_ascii=False),
            encoding="utf-8")
        print(f"  [GUARDADO] {len(surebets)} surebet(s) en {ALERT_LOG}")
    else:
        print(f"  [RESULTADO] Sin surebets (margen min: {MIN_MARGEN}%)")

    return surebets

# LOOP
async def main():
    print("""
================================================================
  BETBOT SCANNER v3.5 - Surebets Reales entre Casas
================================================================
  Bankroll    : ${:,.0f}
  Margen min  : {:.1f}%
  Intervalo   : {}s
  API Key     : {}
================================================================
  Guardado en: surebets_encontrados.json
  Ctrl+C para detener
================================================================""".format(
        BANKROLL, MIN_MARGEN, SCAN_INTERVAL,
        "CONFIGURADA OK" if ODDS_API_KEY else "NO configurada - poner ODDS_API_KEY en .env"
    ))
    total = 0; scan_n = 0
    while True:
        try:
            sb     = await scan_once()
            total  += len(sb)
            scan_n += 1
            print(f"\n  Scans: {scan_n} | Surebets: {total} | Proximo en {SCAN_INTERVAL}s...")
            await asyncio.sleep(SCAN_INTERVAL)
        except KeyboardInterrupt:
            print(f"\nDetenido. Total surebets: {total}")
            break
        except Exception as e:
            print(f"  Error: {e}")
            await asyncio.sleep(10)

if __name__ == "__main__":
    asyncio.run(main())
