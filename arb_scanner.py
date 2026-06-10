#!/usr/bin/env python3
"""
arb_scanner.py v3.4
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

# ── CONFIG ──────────────────────────────────────────────────────────────────
ODDS_API_KEY  = os.getenv("ODDS_API_KEY", "").strip()
BANKROLL      = float(os.getenv("BANKROLL", "10000"))
MIN_MARGEN    = float(os.getenv("MIN_MARGEN", "0.5"))
SCAN_INTERVAL = int(os.getenv("SCAN_INTERVAL", "30"))
ALERT_LOG     = Path("surebets_encontrados.json")
UAGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/127.0 Safari/537.36"
SKIP_MARKETS  = ["_winner","_championship","_outright","_season"]

_sports_cache = []
_sports_ts    = 0

# ── MATEMATICA ──────────────────────────────────────────────────────────────
def calcular_arb(odds: list, bankroll=None):
    if bankroll is None: bankroll = BANKROLL
    if len(odds) < 2: return None
    total_imp = sum(1/o for o in odds)
    margen = (1 - total_imp) * 100
    if total_imp >= 1.0:
        return {"arb": False, "margen": round(margen,3)}
    stakes   = [round((bankroll*(1/o))/total_imp, 2) for o in odds]
    ganancia = round(stakes[0]*odds[0] - bankroll, 2)
    return {
        "arb":      True,
        "margen":   round(margen,3),
        "stakes":   stakes,
        "ganancia": ganancia,
        "roi":      round(ganancia/bankroll*100, 2)
    }

# ── ODDS API ─────────────────────────────────────────────────────────────────
def get_sports():
    global _sports_cache, _sports_ts
    if not ODDS_API_KEY: return []
    if time.time() - _sports_ts < 600 and _sports_cache:
        return _sports_cache
    try:
        with ureq.urlopen(
            ureq.Request(f"https://api.the-odds-api.com/v4/sports/?apiKey={ODDS_API_KEY}",
                         headers={"User-Agent": UAGENT}), timeout=10) as r:
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
    """Devuelve lista de eventos con cuotas POR CASA (para comparar entre casas)."""
    if not ODDS_API_KEY: return []
    url = (f"https://api.the-odds-api.com/v4/sports/{sport}/odds/"
           f"?apiKey={ODDS_API_KEY}&regions=eu,us,uk,au&markets=h2h&oddsFormat=decimal")
    try:
        with ureq.urlopen(ureq.Request(url, headers={"User-Agent":UAGENT}), timeout=12) as r:
            data = json.loads(r.read().decode())
        eventos = []
        for ev in data:
            # Una entrada por outcome (Home / Away / Draw) con la MEJOR cuota disponible
            best = {}   # outcome_name -> {"odd": x, "casa": y}
            for bk in ev.get("bookmakers",[]):
                for mkt in bk.get("markets",[]):
                    if mkt["key"] == "h2h":
                        for oc in mkt["outcomes"]:
                            nm = oc["name"]
                            pr = oc["price"]
                            if nm not in best or pr > best[nm]["odd"]:
                                best[nm] = {"odd": pr, "casa": bk["key"]}
            # Necesitamos al menos 2 outcomes con casas DISTINTAS para arb real
            outcomes = list(best.items())
            if len(outcomes) >= 2:
                eventos.append({
                    "evento":   f"{ev['home_team']} vs {ev['away_team']}",
                    "deporte":  ev.get("sport_title", sport),
                    "inicio":   ev.get("commence_time","")[:16],
                    "outcomes": best   # {nombre: {odd, casa}}
                })
        return eventos
    except urllib.error.HTTPError:
        return []
    except Exception as e:
        print(f"  [API/{sport[:20]}] {e}")
        return []

# ── SCRAPING BETWARRIOR (solo DOM, sin captura de red) ───────────────────────
async def scrape_betwarrior():
    if not PW_OK: return []
    eventos = []
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=["--no-sandbox","--disable-blink-features=AutomationControlled"]
            )
            ctx  = await browser.new_context(
                viewport={"width":1366,"height":768},
                user_agent=UAGENT, locale="es-AR"
            )
            page = await ctx.new_page()
            print("  [BW] Abriendo Betwarrior...", end=" ", flush=True)
            await page.goto("https://mza.betwarrior.bet.ar/es-ar/sports/home",
                            wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(6000)
            print("listo")

            dom = await page.evaluate("""
              () => {
                const res = [];
                document.querySelectorAll('[class*="event"],[class*="match"],[class*="fixture"]')
                  .forEach(row => {
                    const odds = [];
                    row.querySelectorAll('[class*="odd"],[class*="price"],[class*="coef"]')
                      .forEach(b => {
                        const v = parseFloat(b.innerText.replace(',','.'));
                        if (!isNaN(v) && v > 1.10 && v < 30) odds.push(v);
                      });
                    const nm = row.querySelector('[class*="team"],[class*="name"],[class*="participant"]');
                    const txt = nm ? nm.innerText.trim() : '';
                    // Solo agregar si el nombre parece un equipo real (letras, no ruta)
                    if (odds.length >= 2 && txt.length > 2 && !txt.includes('/') && !txt.includes('.'))
                      res.push({ nombre: txt.slice(0,60), odds: [...new Set(odds)].slice(0,3) });
                  });
                return res;
              }
            """)

            for ev in dom:
                # Armar estructura compatible: cada odd es de "betwarrior"
                outcomes = {}
                for idx, odd in enumerate(ev["odds"]):
                    outcomes[f"resultado_{idx+1}"] = {"odd": odd, "casa": "betwarrior"}
                eventos.append({
                    "evento":   ev["nombre"],
                    "deporte":  "Futbol (BW)",
                    "inicio":   "",
                    "outcomes": outcomes
                })

            await browser.close()
            print(f"  [BW] {len(dom)} partidos en DOM")
    except Exception as e:
        print(f"  [BW] Error: {e}")
    return eventos

# ── ALERTA ───────────────────────────────────────────────────────────────────
def alerta_surebet(sb):
    s = sb["stakes"]
    s1 = s[0] if len(s) > 0 else 0
    s2 = s[1] if len(s) > 1 else 0
    print()
    print("=" * 64)
    print("  ***  SUREBET ENCONTRADO  -  APOSTA AHORA!  ***")
    print("=" * 64)
    print(f"  Evento   : {sb['evento']}")
    print(f"  Deporte  : {sb['deporte']}")
    if sb.get("inicio"): print(f"  Inicio   : {sb['inicio']}")
    print(f"  ─" * 32)
    print(f"  APUESTA 1: ${s1:>10,.2f}  @ {sb['odd1']:.2f}  en  {sb['casa1'].upper()}")
    print(f"  APUESTA 2: ${s2:>10,.2f}  @ {sb['odd2']:.2f}  en  {sb['casa2'].upper()}")
    print(f"  ─" * 32)
    print(f"  Margen   : +{sb['margen']:.2f}%")
    print(f"  GANANCIA : ${sb['ganancia']:>10,.2f}   ROI: {sb['roi']:.2f}%")
    print("=" * 64)
    print()

# ── BUSCADOR DE SUREBETS ─────────────────────────────────────────────────────
def buscar_surebets(eventos):
    surebets = []
    for ev in eventos:
        outcomes = ev.get("outcomes", {})
        if len(outcomes) < 2: continue
        items = list(outcomes.items())
        for i in range(len(items)):
            for j in range(i+1, len(items)):
                nm_i, dat_i = items[i]
                nm_j, dat_j = items[j]
                odd1  = dat_i["odd"]
                odd2  = dat_j["odd"]
                casa1 = dat_i["casa"]
                casa2 = dat_j["casa"]
                # Solo vale si son casas distintas (surebet real)
                if casa1 == casa2: continue
                res = calcular_arb([odd1, odd2])
                if res and res["arb"] and res["margen"] >= MIN_MARGEN:
                    sb = {
                        "timestamp": datetime.now().isoformat(),
                        "evento":    ev["evento"],
                        "deporte":   ev["deporte"],
                        "inicio":    ev.get("inicio",""),
                        "odd1":      odd1,
                        "odd2":      odd2,
                        "casa1":     casa1,
                        "casa2":     casa2,
                        "outcome1":  nm_i,
                        "outcome2":  nm_j,
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

    if ODDS_API_KEY:
        sports = get_sports()
        print(f"  [API] Consultando {len(sports)} deportes...")
        for sport in sports:
            ev = fetch_odds(sport)
            if ev: print(f"    {sport[:35]:<35} {len(ev)} eventos")
            eventos += ev
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
            json.dumps(hist+surebets, indent=2, ensure_ascii=False),
            encoding="utf-8")
        print(f"  [GUARDADO] {len(surebets)} surebet(s) en {ALERT_LOG}")
    else:
        print(f"  [RESULTADO] Sin surebets reales (margen min: {MIN_MARGEN}%)")

    return surebets

# ── LOOP ──────────────────────────────────────────────────────────────────────
async def main():
    print("""
================================================================
  BETBOT SCANNER v3.4 - Surebets Reales entre Casas
  OddsAPI (40 deportes) + Betwarrior DOM
================================================================
  Bankroll    : ${:,.0f}
  Margen min  : {:.1f}%
  Intervalo   : {}s
  API Key     : {}
================================================================
  Surebets guardados en: surebets_encontrados.json
  Ctrl+C para detener
================================================================""".format(
        BANKROLL, MIN_MARGEN, SCAN_INTERVAL,
        "CONFIGURADA OK" if ODDS_API_KEY else "NO configurada"
    ))
    total=0; scan_n=0
    while True:
        try:
            sb = await scan_once()
            total  += len(sb)
            scan_n += 1
            print(f"\n  Scans: {scan_n} | Surebets reales: {total} | Proximo en {SCAN_INTERVAL}s...")
            await asyncio.sleep(SCAN_INTERVAL)
        except KeyboardInterrupt:
            print(f"\nDetenido. Total surebets: {total}")
            break
        except Exception as e:
            print(f"  Error: {e}")
            await asyncio.sleep(10)

if __name__ == "__main__":
    asyncio.run(main())
