#!/usr/bin/env python3
"""
arb_scanner.py v4.0
Scraping REAL de Betwarrior + Bookmaker.eu
Compara cuotas del mismo partido entre las dos casas
Alerta con exactamente donde apostar y cuanto
"""
import asyncio, json, os, re, time
from datetime import datetime
from pathlib import Path
from difflib import SequenceMatcher

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
    print("[ERROR] Playwright no instalado.")
    print("        Correr: pip install playwright && python -m playwright install chromium")
    exit(1)

# CONFIG
BANKROLL      = float(os.getenv("BANKROLL", "10000"))
MIN_MARGEN    = float(os.getenv("MIN_MARGEN", "0.5"))
SCAN_INTERVAL = int(os.getenv("SCAN_INTERVAL", "60"))
ALERT_LOG     = Path("surebets_encontrados.json")
UAGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36"

# Similitud minima para considerar que dos nombres son el mismo partido
SIM_THRESHOLD = 0.60

# ── MATEMATICA ────────────────────────────────────────────────────────────────
def calcular_arb(odd1, odd2, bankroll=None):
    if bankroll is None: bankroll = BANKROLL
    ti = 1/odd1 + 1/odd2
    if ti >= 1.0: return None
    margen = (1 - ti) * 100
    s1 = round(bankroll * (1/odd1) / ti, 2)
    s2 = round(bankroll * (1/odd2) / ti, 2)
    gan = round(s1 * odd1 - bankroll, 2)
    return {"margen": round(margen,3), "s1": s1, "s2": s2,
            "ganancia": gan, "roi": round(gan/bankroll*100, 2)}

def similitud(a, b):
    a = re.sub(r'[^a-z0-9 ]', '', a.lower())
    b = re.sub(r'[^a-z0-9 ]', '', b.lower())
    return SequenceMatcher(None, a, b).ratio()

# ── SCRAPER BETWARRIOR ────────────────────────────────────────────────────────
async def scrape_bw(page):
    """Scrapea Betwarrior y devuelve lista de partidos con cuotas."""
    partidos = []
    try:
        print("  [BW] Cargando...", end=" ", flush=True)
        await page.goto(
            "https://mza.betwarrior.bet.ar/es-ar/sports/home",
            wait_until="networkidle", timeout=45000
        )
        await page.wait_for_timeout(5000)

        # Intentar hacer scroll para cargar mas partidos
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight/2)")
        await page.wait_for_timeout(2000)

        resultado = await page.evaluate("""
          () => {
            const partidos = [];
            // Buscar todos los textos que parezcan cuotas
            const allText = document.body.innerText;
            const lines = allText.split('\\n').map(l => l.trim()).filter(l => l.length > 0);

            // Encontrar bloques: nombre de partido + cuotas
            for (let i = 0; i < lines.length - 3; i++) {
              const l = lines[i];
              // Una linea de partido suele tener 'vs', '-', o dos palabras con mayuscula
              const esPartido = l.includes(' vs ') || l.includes(' - ') ||
                                (l.length > 5 && l.length < 80 && /[A-Z]/.test(l));

              if (!esPartido) continue;

              // Buscar cuotas en las proximas 8 lineas
              const cuotas = [];
              for (let j = i+1; j < Math.min(i+9, lines.length); j++) {
                const v = parseFloat(lines[j].replace(',','.'));
                if (!isNaN(v) && v >= 1.10 && v <= 30.0 &&
                    lines[j].match(/^\\d+[,.]\\d{1,3}$/)) {
                  cuotas.push(v);
                }
              }

              if (cuotas.length >= 2) {
                partidos.push({ nombre: l.slice(0, 70), cuotas: [...new Set(cuotas)].slice(0,3) });
                i += 3; // saltar las cuotas ya procesadas
              }
            }
            return partidos;
          }
        """)

        partidos = resultado
        print(f"OK ({len(partidos)} partidos)")
    except Exception as e:
        print(f"ERROR: {e}")
    return partidos

# ── SCRAPER BOOKMAKER.EU ──────────────────────────────────────────────────────
async def scrape_bookmaker(page):
    """Scrapea Bookmaker.eu y devuelve lista de partidos con cuotas."""
    partidos = []
    try:
        print("  [BK] Cargando...", end=" ", flush=True)
        await page.goto(
            "https://be.bookmaker.eu/sports",
            wait_until="networkidle", timeout=45000
        )
        await page.wait_for_timeout(5000)
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight/2)")
        await page.wait_for_timeout(2000)

        resultado = await page.evaluate("""
          () => {
            const partidos = [];
            const allText = document.body.innerText;
            const lines = allText.split('\\n').map(l => l.trim()).filter(l => l.length > 0);

            for (let i = 0; i < lines.length - 3; i++) {
              const l = lines[i];
              const esPartido = l.includes(' vs ') || l.includes(' - ') ||
                                (l.length > 5 && l.length < 80 && /[A-Z]/.test(l));
              if (!esPartido) continue;

              const cuotas = [];
              for (let j = i+1; j < Math.min(i+9, lines.length); j++) {
                const v = parseFloat(lines[j].replace(',','.'));
                if (!isNaN(v) && v >= 1.10 && v <= 30.0 &&
                    lines[j].match(/^\\d+[,.]\\d{1,3}$/)) {
                  cuotas.push(v);
                }
              }

              if (cuotas.length >= 2) {
                partidos.push({ nombre: l.slice(0, 70), cuotas: [...new Set(cuotas)].slice(0,3) });
                i += 3;
              }
            }
            return partidos;
          }
        """)

        partidos = resultado
        print(f"OK ({len(partidos)} partidos)")
    except Exception as e:
        print(f"ERROR: {e}")
    return partidos

# ── COMPARAR PARTIDOS ENTRE CASAS ────────────────────────────────────────────
def cruzar_y_buscar_arb(partidos_bw, partidos_bk):
    """Cruza partidos de BW y BK por similitud de nombre y busca surebets."""
    surebets = []

    for pbw in partidos_bw:
        for pbk in partidos_bk:
            sim = similitud(pbw["nombre"], pbk["nombre"])
            if sim < SIM_THRESHOLD:
                continue

            # Mismo partido encontrado en las dos casas
            # Comparar cada combinacion de cuotas entre casas distintas
            for o_bw in pbw["cuotas"]:
                for o_bk in pbk["cuotas"]:
                    res = calcular_arb(o_bw, o_bk)
                    if res and res["margen"] >= MIN_MARGEN:
                        sb = {
                            "timestamp": datetime.now().isoformat(),
                            "evento":    pbw["nombre"],
                            "evento_bk": pbk["nombre"],
                            "odd_bw":    o_bw,
                            "odd_bk":    o_bk,
                            **res
                        }
                        surebets.append(sb)
                        alerta_surebet(sb)

    return surebets

# ── ALERTA ────────────────────────────────────────────────────────────────────
def alerta_surebet(sb):
    print()
    print("=" * 66)
    print("  ***  SUREBET ENCONTRADO  -  APOSTA AHORA!  ***")
    print("=" * 66)
    print(f"  Evento BW  : {sb['evento']}")
    print(f"  Evento BK  : {sb['evento_bk']}")
    print(f"  " + "-"*62)
    print(f"  APUESTA 1 : ${sb['s1']:>10,.2f}  cuota {sb['odd_bw']:.2f}  --> BETWARRIOR")
    print(f"  APUESTA 2 : ${sb['s2']:>10,.2f}  cuota {sb['odd_bk']:.2f}  --> BOOKMAKER.EU")
    print(f"  " + "-"*62)
    print(f"  Margen    : +{sb['margen']:.2f}%")
    print(f"  GANANCIA  : ${sb['ganancia']:>10,.2f}   ROI: {sb['roi']:.2f}%")
    print("=" * 66)
    print()

# ── SCAN PRINCIPAL ────────────────────────────────────────────────────────────
async def scan_once():
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"\n[{ts}] ---- INICIO DE SCAN ----")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled",
                  "--disable-web-security"]
        )

        # Paginas separadas para cada casa
        ctx_bw = await browser.new_context(user_agent=UAGENT, locale="es-AR")
        ctx_bk = await browser.new_context(user_agent=UAGENT, locale="es-AR")
        page_bw = await ctx_bw.new_page()
        page_bk = await ctx_bk.new_page()

        # Scrapear las dos casas en paralelo
        bw_result, bk_result = await asyncio.gather(
            scrape_bw(page_bw),
            scrape_bookmaker(page_bk)
        )

        await browser.close()

    print(f"  [BW] {len(bw_result)} partidos | [BK] {len(bk_result)} partidos")
    print(f"  Buscando matches entre casas...")

    surebets = cruzar_y_buscar_arb(bw_result, bk_result)

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
        print(f"  [RESULTADO] Sin surebets entre BW y BK (margen min: {MIN_MARGEN}%)")

    return surebets

# ── LOOP ──────────────────────────────────────────────────────────────────────
async def main():
    print(f"""
================================================================
  BETBOT SCANNER v4.0
  Betwarrior vs Bookmaker.eu -- Comparacion DIRECTA
================================================================
  Bankroll    : ${BANKROLL:,.0f}
  Margen min  : {MIN_MARGEN:.1f}%
  Intervalo   : {SCAN_INTERVAL}s
================================================================
  Surebets guardados en: surebets_encontrados.json
  Ctrl+C para detener
================================================================""")

    total = 0; scan_n = 0
    while True:
        try:
            sb     = await scan_once()
            total  += len(sb)
            scan_n += 1
            print(f"\n  Scans: {scan_n} | Surebets: {total} | Proximo en {SCAN_INTERVAL}s...")
            await asyncio.sleep(SCAN_INTERVAL)
        except KeyboardInterrupt:
            print(f"\nDetenido. Total surebets encontrados: {total}")
            break
        except Exception as e:
            print(f"  Error: {e}")
            await asyncio.sleep(15)

if __name__ == "__main__":
    asyncio.run(main())
