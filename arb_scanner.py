#!/usr/bin/env python3
"""
arb_scanner.py v4.1
Betwarrior (Kambi) + Bookmaker.eu -- selectores REALES basados en debug
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

from playwright.async_api import async_playwright

BANKROLL      = float(os.getenv("BANKROLL", "10000"))
MIN_MARGEN    = float(os.getenv("MIN_MARGEN", "0.5"))
SCAN_INTERVAL = int(os.getenv("SCAN_INTERVAL", "60"))
ALERT_LOG     = Path("surebets_encontrados.json")
SIM_THRESHOLD = 0.55

# Chrome 126 UA para pasar el bloqueo de Bookmaker
UA_126 = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"

# ── MATEMATICA ──────────────────────────────────────────────────────
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

# ── SCRAPER BETWARRIOR (Kambi) ───────────────────────────────────────
async def scrape_bw(page):
    partidos = []
    try:
        print("  [BW] Cargando...", end=" ", flush=True)
        await page.goto(
            "https://mza.betwarrior.bet.ar/es-ar/sports/home",
            wait_until="networkidle", timeout=50000
        )
        await page.wait_for_timeout(4000)

        # Esperar que aparezcan outcomes de Kambi
        try:
            await page.wait_for_selector(".KambiBC-betty-outcome", timeout=10000)
        except:
            print("  [BW] Selector Kambi no aparecio todavia, leyendo igual...")

        resultado = await page.evaluate("""
          () => {
            const partidos = [];

            // Cada evento Kambi tiene contenedor con clase bet-offer
            const eventos = document.querySelectorAll(
              '[class*="KambiBC-event-item"], [class*="KambiBC-bet-offer"]'
            );

            eventos.forEach(ev => {
              // Nombre del partido: buscar el elemento de participantes
              const nameEl = ev.querySelector(
                '[class*="KambiBC-event-participants"], [class*="participant"], [class*="team-name"], [class*="event-name"]'
              );
              const nombre = nameEl ? nameEl.innerText.trim().replace(/\\n+/g,' ') : '';

              // Cuotas: elementos outcome tienen la cuota en texto
              const outcomeEls = ev.querySelectorAll('[class*="KambiBC-betty-outcome"]');
              const cuotas = [];
              outcomeEls.forEach(oc => {
                // La cuota esta en el span interno con el numero
                const spans = oc.querySelectorAll('span, div');
                spans.forEach(s => {
                  const v = parseFloat(s.innerText.trim().replace(',','.'));
                  if (!isNaN(v) && v >= 1.05 && v <= 50.0 && s.innerText.trim().match(/^\\d+\\.\\d+$/)) {
                    cuotas.push(v);
                  }
                });
              });

              if (nombre.length > 3 && cuotas.length >= 2) {
                partidos.push({ nombre: nombre.slice(0,70), cuotas: [...new Set(cuotas)].slice(0,4) });
              }
            });

            // Fallback: si no encontro nada con el primer metodo,
            // agarrar todos los KambiBC-betty-outcome en grupos de 2-3
            if (partidos.length === 0) {
              const allOutcomes = [...document.querySelectorAll('[class*="KambiBC-betty-outcome"]')];
              const allOdds = [];
              allOutcomes.forEach(oc => {
                const txt = oc.innerText.trim();
                const lines = txt.split('\\n').map(l => l.trim()).filter(Boolean);
                lines.forEach(l => {
                  const v = parseFloat(l.replace(',','.'));
                  if (!isNaN(v) && v >= 1.05 && v <= 50.0) allOdds.push(v);
                });
              });
              // Agrupar en pares/trios (H2H tiene 2 o 3 cuotas)
              for (let i = 0; i + 1 < allOdds.length; i += 2) {
                const cuotas = allOdds.slice(i, i+3);
                if (cuotas.length >= 2)
                  partidos.push({ nombre: `Partido_${i/2}`, cuotas });
              }
            }

            return partidos;
          }
        """)

        partidos = resultado
        print(f"OK ({len(partidos)} partidos, {sum(len(p['cuotas']) for p in partidos)} cuotas)")
    except Exception as e:
        print(f"ERROR: {e}")
    return partidos

# ── SCRAPER BOOKMAKER.EU ─────────────────────────────────────────────
async def scrape_bookmaker(page):
    partidos = []
    try:
        print("  [BK] Cargando...", end=" ", flush=True)
        await page.goto(
            "https://www.bookmaker.eu/sports-betting/odds",
            wait_until="networkidle", timeout=50000
        )
        await page.wait_for_timeout(4000)

        # Hacer clic en "Continuar de todos modos" si aparece el warning de Chrome
        try:
            btn = page.locator("text=Continuar de todos modos")
            if await btn.count() > 0:
                await btn.first.click()
                print("[bypass Chrome warning]", end=" ", flush=True)
                await page.wait_for_timeout(3000)
        except:
            pass

        # Tambien intentar la URL de odds directa
        html = await page.content()
        if len(html) < 30000:
            # Pagina muy chica = probablemente solo el warning, reintentar
            await page.goto(
                "https://www.bookmaker.eu/sports-betting/football",
                wait_until="networkidle", timeout=40000
            )
            await page.wait_for_timeout(4000)
            try:
                btn = page.locator("text=Continuar de todos modos, text=Continue Anyway")
                if await btn.count() > 0:
                    await btn.first.click()
                    await page.wait_for_timeout(3000)
            except:
                pass

        resultado = await page.evaluate("""
          () => {
            const partidos = [];
            const txt = document.body.innerText;
            const lines = txt.split('\\n').map(l => l.trim()).filter(l => l.length > 0);

            // Buscar lineas con 'vs' o equipos y cuotas cerca
            for (let i = 0; i < lines.length - 2; i++) {
              const l = lines[i];
              const esPartido = l.includes(' vs ') || l.includes(' VS ') ||
                                l.includes(' v ') ||
                                (l.length > 4 && l.length < 80);
              if (!esPartido) continue;

              const cuotas = [];
              for (let j = i+1; j < Math.min(i+10, lines.length); j++) {
                const cleaned = lines[j].replace(',','.');
                // Cuotas americanas: +150, -110
                const am = cleaned.match(/^([+-]\\d{2,4})$/);
                if (am) {
                  const a = parseInt(am[1]);
                  const dec = a > 0 ? (a/100)+1 : (100/Math.abs(a))+1;
                  if (dec >= 1.05 && dec <= 50) cuotas.push(parseFloat(dec.toFixed(3)));
                  continue;
                }
                // Cuotas decimales
                const d = parseFloat(cleaned);
                if (!isNaN(d) && d >= 1.05 && d <= 50.0 &&
                    cleaned.match(/^\\d+[.,]\\d{1,4}$/)) {
                  cuotas.push(d);
                }
              }
              if (cuotas.length >= 2) {
                partidos.push({ nombre: l.slice(0,70), cuotas: [...new Set(cuotas)].slice(0,4) });
                i += 3;
              }
            }
            return partidos;
          }
        """)

        partidos = resultado
        html_len = len(await page.content())
        print(f"OK ({len(partidos)} partidos, html: {html_len:,} chars)")

        if len(partidos) == 0 and html_len < 50000:
            print("  [BK] AVISO: HTML muy chico, el sitio puede requerir login o IP bloqueada")

    except Exception as e:
        print(f"ERROR: {e}")
    return partidos

# ── CRUZAR Y BUSCAR ARBITRAJE ────────────────────────────────────────
def cruzar_y_buscar_arb(partidos_bw, partidos_bk):
    surebets = []
    matches = 0
    for pbw in partidos_bw:
        for pbk in partidos_bk:
            sim = similitud(pbw["nombre"], pbk["nombre"])
            if sim < SIM_THRESHOLD: continue
            matches += 1
            for o_bw in pbw["cuotas"]:
                for o_bk in pbk["cuotas"]:
                    res = calcular_arb(o_bw, o_bk)
                    if res and res["margen"] >= MIN_MARGEN:
                        sb = {
                            "timestamp": datetime.now().isoformat(),
                            "evento":    pbw["nombre"],
                            "evento_bk": pbk["nombre"],
                            "odd_bw": o_bw, "odd_bk": o_bk,
                            **res
                        }
                        surebets.append(sb)
                        alerta_surebet(sb)
    if matches:
        print(f"  {matches} partidos cruzados entre casas")
    return surebets

# ── ALERTA ───────────────────────────────────────────────────────────
def alerta_surebet(sb):
    print()
    print("=" * 66)
    print("  ***  SUREBET ENCONTRADO  -  APOSTA AHORA!  ***")
    print("=" * 66)
    print(f"  Evento BW  : {sb['evento']}")
    print(f"  Evento BK  : {sb['evento_bk']}")
    print(f"  {'─'*62}")
    print(f"  APUESTA 1 : ${sb['s1']:>10,.2f}  cuota {sb['odd_bw']:.3f}  --> BETWARRIOR")
    print(f"  APUESTA 2 : ${sb['s2']:>10,.2f}  cuota {sb['odd_bk']:.3f}  --> BOOKMAKER.EU")
    print(f"  {'─'*62}")
    print(f"  Margen    : +{sb['margen']:.3f}%")
    print(f"  GANANCIA  : ${sb['ganancia']:>10,.2f}   ROI: {sb['roi']:.2f}%")
    print("=" * 66)

# ── SCAN PRINCIPAL ───────────────────────────────────────────────────
async def scan_once():
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"\n[{ts}] ---- INICIO DE SCAN ----")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox",
                  "--disable-blink-features=AutomationControlled",
                  "--disable-web-security"]
        )
        ctx_bw = await browser.new_context(user_agent=UA_126, locale="es-AR",
                                            viewport={"width":1400,"height":900})
        ctx_bk = await browser.new_context(user_agent=UA_126, locale="es-AR",
                                            viewport={"width":1400,"height":900})
        page_bw = await ctx_bw.new_page()
        page_bk = await ctx_bk.new_page()

        bw_r, bk_r = await asyncio.gather(
            scrape_bw(page_bw),
            scrape_bookmaker(page_bk)
        )
        await browser.close()

    print(f"  [BW] {len(bw_r)} partidos | [BK] {len(bk_r)} partidos")

    if len(bw_r) == 0 and len(bk_r) == 0:
        print("  [AVISO] Ambos scrapers devolvieron 0. Revisar conexion o sitios bloqueados.")
        return []

    surebets = cruzar_y_buscar_arb(bw_r, bk_r)

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

# ── LOOP ─────────────────────────────────────────────────────────────
async def main():
    print(f"""
================================================================
  BETBOT SCANNER v4.1 - Betwarrior vs Bookmaker.eu
================================================================
  Bankroll    : ${BANKROLL:,.0f}
  Margen min  : {MIN_MARGEN:.1f}%
  Intervalo   : {SCAN_INTERVAL}s
================================================================""")
    total = 0; scan_n = 0
    while True:
        try:
            sb = await scan_once()
            total += len(sb)
            scan_n += 1
            print(f"\n  Scans: {scan_n} | Surebets: {total} | Proximo en {SCAN_INTERVAL}s...")
            await asyncio.sleep(SCAN_INTERVAL)
        except KeyboardInterrupt:
            print(f"\nDetenido. Total surebets: {total}")
            break
        except Exception as e:
            print(f"  Error: {e}")
            await asyncio.sleep(15)

if __name__ == "__main__":
    asyncio.run(main())
