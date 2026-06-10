#!/usr/bin/env python3
"""
arb_scanner.py v4.5
Fix definitivo basado en screenshots reales:
- BW: login buscando por placeholder 'Correo electronico'
- BK: scraper lee tabla HTML con moneylines americanas
"""
import asyncio, json, os, re
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
SCAN_INTERVAL = int(os.getenv("SCAN_INTERVAL", "30"))
BW_USER       = os.getenv("BETWARRIOR_USER", "").strip()
BW_PASS       = os.getenv("BETWARRIOR_PASS", "").strip()
BK_USER       = os.getenv("BOOKMAKER_USER", "").strip()
BK_PASS       = os.getenv("BOOKMAKER_PASS", "").strip()
ALERT_LOG     = Path("surebets_encontrados.json")
SIM_THRESHOLD = 0.52
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"

def similitud(a, b):
    a = re.sub(r'[^a-z0-9 ]', '', a.lower())
    b = re.sub(r'[^a-z0-9 ]', '', b.lower())
    return SequenceMatcher(None, a, b).ratio()

def americana_a_decimal(s):
    """Convierte moneyline americana (+150, -110) a cuota decimal."""
    try:
        a = int(s)
        if a > 0: return round(a/100 + 1, 3)
        else:     return round(100/abs(a) + 1, 3)
    except: return None

def calcular_arb(o1, o2, bankroll=None):
    if bankroll is None: bankroll = BANKROLL
    ti = 1/o1 + 1/o2
    if ti >= 1.0: return None
    m  = (1 - ti) * 100
    s1 = round(bankroll * (1/o1) / ti, 2)
    s2 = round(bankroll * (1/o2) / ti, 2)
    g  = round(s1 * o1 - bankroll, 2)
    return {"margen": round(m,3), "s1": s1, "s2": s2, "ganancia": g, "roi": round(g/bankroll*100,2)}

async def cerrar_popups(page):
    for sel in [
        "button[aria-label*='close']", "button[aria-label*='Close']",
        ".close", "[class*='close-btn']", "[class*='modal__close']",
        "#onetrust-accept-btn-handler",
        "text=Aceptar", "text=Entendido", "text=OK",
    ]:
        try:
            loc = page.locator(sel)
            if await loc.count() > 0:
                await loc.first.click(timeout=1200)
                await page.wait_for_timeout(600)
        except: pass

# ── BETWARRIOR LOGIN ────────────────────────────────────────────────────
async def bw_login(page):
    print("  [BW] Login...", end=" ", flush=True)
    await page.goto("https://mza.betwarrior.bet.ar/es-ar/sports/home",
                    wait_until="networkidle", timeout=50000)
    await page.wait_for_timeout(3000)

    # Click en ENTRAR/UNIRSE (boton top-right)
    try:
        await page.click("text=ENTRAR/UNIRSE", timeout=5000)
        await page.wait_for_timeout(2000)
    except:
        try:
            await page.click("text=ENTRAR", timeout=3000)
            await page.wait_for_timeout(2000)
        except: pass

    # Esperar modal con campos -- buscar por placeholder exacto del screenshot
    try:
        await page.wait_for_selector(
            "input[placeholder='Correo electr\u00f3nico'], input[placeholder='Correo electronico'], input[placeholder*='correo'], input[placeholder*='email'], input[placeholder*='Email']",
            timeout=10000
        )
    except:
        await page.screenshot(path="debug_bw_login.png")
        print("FALLO - ver debug_bw_login.png")
        return False

    # Llenar email
    await page.fill(
        "input[placeholder='Correo electr\u00f3nico'], input[placeholder='Correo electronico'], input[placeholder*='correo'], input[placeholder*='email'], input[placeholder*='Email']",
        BW_USER
    )
    await page.wait_for_timeout(400)

    # Llenar contrasena
    await page.fill("input[placeholder='Contrase\u00f1a'], input[placeholder='Contrasena'], input[type='password']", BW_PASS)
    await page.wait_for_timeout(400)

    # Click en INICIAR SESION
    try:
        await page.click("text=INICIAR SESI\u00d3N", timeout=4000)
    except:
        try:
            await page.click("text=INICIAR SESION", timeout=3000)
        except:
            await page.press("input[type='password']", "Enter")

    await page.wait_for_timeout(6000)
    print("OK")
    return True

# ── BETWARRIOR SCRAPE ────────────────────────────────────────────────────
async def scrape_bw(page):
    partidos = []
    try:
        print("  [BW] Cuotas...", end=" ", flush=True)
        await page.reload(wait_until="networkidle", timeout=40000)
        await page.wait_for_timeout(3000)
        try:
            await page.wait_for_selector("[class*='KambiBC-betty-outcome']", timeout=10000)
        except: pass

        partidos = await page.evaluate("""
        (function() {
          var partidos = [];
          var eventos = document.querySelectorAll('[class*="KambiBC-event-item"],[class*="KambiBC-bet-offer"]');
          eventos.forEach(function(ev) {
            var nameEl = ev.querySelector('[class*="KambiBC-event-participants"],[class*="participant"],[class*="team-name"],[class*="event-name"]');
            var nombre = nameEl ? nameEl.innerText.trim().replace(/\\n+/g,' ') : '';
            var cuotas = [];
            ev.querySelectorAll('[class*="KambiBC-betty-outcome"]').forEach(function(oc) {
              oc.querySelectorAll('span,div').forEach(function(s) {
                var txt = s.innerText.trim();
                var v = parseFloat(txt);
                if (!isNaN(v) && v >= 1.05 && v <= 50 && txt.indexOf('.') !== -1 && txt.indexOf(' ') === -1)
                  cuotas.push(v);
              });
            });
            if (nombre.length > 3 && cuotas.length >= 2) {
              var unique = cuotas.filter(function(v,i,a){ return a.indexOf(v)===i; });
              partidos.push({nombre: nombre.slice(0,70), cuotas: unique.slice(0,4)});
            }
          });
          if (partidos.length === 0) {
            var allOdds = [];
            document.querySelectorAll('[class*="KambiBC-betty-outcome"]').forEach(function(oc) {
              oc.querySelectorAll('span,div').forEach(function(s) {
                var txt = s.innerText.trim();
                var v = parseFloat(txt);
                if (!isNaN(v) && v >= 1.05 && v <= 50 && txt.indexOf('.') !== -1)
                  allOdds.push(v);
              });
            });
            for (var i = 0; i+1 < allOdds.length; i += 2)
              partidos.push({nombre: 'Partido_BW_' + Math.floor(i/2), cuotas: allOdds.slice(i, i+3)});
          }
          return partidos;
        })()
        """)
        print(f"OK ({len(partidos)} partidos)")
    except Exception as e:
        print(f"ERROR: {e}")
    return partidos

# ── BOOKMAKER LOGIN ─────────────────────────────────────────────────────
async def bk_login(page):
    print("  [BK] Login...", end=" ", flush=True)
    # BK del screenshot ya carga logueado directo
    # Ir a la pagina de odds con login embebido
    await page.goto("https://www.bookmaker.eu/sports-betting/football",
                    wait_until="networkidle", timeout=50000)
    await page.wait_for_timeout(3000)

    # Si pide login, hacerlo
    pass_el = await page.query_selector("input[type='password']")
    if pass_el:
        user_f = None
        for sel in ["input[name='username']", "input[name='email']",
                    "input[name='account']", "input[type='text']",
                    "input[type='email']"]:
            user_f = await page.query_selector(sel)
            if user_f: break
        if user_f:
            await user_f.fill(BK_USER)
            await pass_el.fill(BK_PASS)
            await pass_el.press("Enter")
            await page.wait_for_timeout(6000)

    html_len = len(await page.content())
    print(f"OK (html: {html_len:,} chars)")
    return True

# ── BOOKMAKER SCRAPE - tabla HTML con moneylines americanas ─────────────────
async def scrape_bk(page):
    partidos = []
    try:
        print("  [BK] Cuotas...", end=" ", flush=True)

        # Deportes a scrapear
        urls = [
            "https://www.bookmaker.eu/sports-betting/football",
            "https://www.bookmaker.eu/sports-betting/basketball",
            "https://www.bookmaker.eu/sports-betting/baseball",
        ]

        for url in urls:
            await page.goto(url, wait_until="networkidle", timeout=40000)
            await page.wait_for_timeout(2000)

            # Leer tabla HTML: filas con Team + Moneyline
            rows = await page.evaluate("""
            (function() {
              var result = [];
              // La tabla tiene columnas: Time | Team | Spread | Total | Moneyline
              var rows = document.querySelectorAll('tr');
              var prevTeam = null;
              var prevMl   = null;

              rows.forEach(function(row) {
                var cells = row.querySelectorAll('td');
                if (cells.length < 2) return;

                // Buscar celda de equipo (texto largo sin numeros solos)
                var teamCell = null;
                var mlCell   = null;

                cells.forEach(function(td) {
                  var txt = td.innerText.trim();
                  // Moneyline americana: +XXX o -XXX
                  if (/^[+-][0-9]{2,4}$/.test(txt)) mlCell = txt;
                  // Nombre de equipo: texto sin slash, longitud razonable
                  else if (txt.length > 3 && txt.length < 50 && !/^[0-9\/:.]+$/.test(txt) && txt.indexOf('$') === -1)
                    teamCell = txt;
                });

                if (teamCell && mlCell) {
                  if (prevTeam && prevMl) {
                    // Par completo
                    result.push({
                      nombre: prevTeam + ' vs ' + teamCell,
                      cuotas: [prevMl, mlCell]  // strings, se convierten despues
                    });
                    prevTeam = null; prevMl = null;
                  } else {
                    prevTeam = teamCell;
                    prevMl   = mlCell;
                  }
                }
              });
              return result;
            })()
            """)

            # Convertir moneylines a decimal
            for row in rows:
                cuotas_dec = []
                for ml in row["cuotas"]:
                    d = americana_a_decimal(ml)
                    if d: cuotas_dec.append(d)
                if len(cuotas_dec) >= 2:
                    partidos.append({"nombre": row["nombre"], "cuotas": cuotas_dec})

        html_len = len(await page.content())
        print(f"OK ({len(partidos)} partidos, html: {html_len:,} chars)")

        if len(partidos) == 0:
            txt = await page.evaluate("(function(){ return document.body.innerText; })()")
            Path("debug_bk_live.txt").write_text(txt[:5000], encoding="utf-8")
            await page.screenshot(path="debug_bk_live.png")
            print("  [BK] 0 partidos - ver debug_bk_live.png")

    except Exception as e:
        print(f"ERROR: {e}")
    return partidos

# ── CRUZAR Y ALERTAR ────────────────────────────────────────────────────────
def cruzar(bw, bk):
    surebets = []; matches = 0
    for pbw in bw:
        for pbk in bk:
            if similitud(pbw["nombre"], pbk["nombre"]) < SIM_THRESHOLD: continue
            matches += 1
            for o_bw in pbw["cuotas"]:
                for o_bk in pbk["cuotas"]:
                    res = calcular_arb(o_bw, o_bk)
                    if res and res["margen"] >= MIN_MARGEN:
                        sb = {"timestamp": datetime.now().isoformat(),
                              "evento": pbw["nombre"], "evento_bk": pbk["nombre"],
                              "odd_bw": o_bw, "odd_bk": o_bk, **res}
                        surebets.append(sb)
                        alerta(sb)
    if matches: print(f"  {matches} partidos cruzados")
    return surebets

def alerta(sb):
    print()
    print("=" * 66)
    print("  *** SUREBET ENCONTRADO - APOSTA AHORA! ***")
    print("=" * 66)
    print(f"  Evento BW  : {sb['evento']}")
    print(f"  Evento BK  : {sb['evento_bk']}")
    print(f"  {'-'*62}")
    print(f"  APUESTA 1 : ${sb['s1']:>10,.2f}  cuota {sb['odd_bw']:.3f}  --> BETWARRIOR")
    print(f"  APUESTA 2 : ${sb['s2']:>10,.2f}  cuota {sb['odd_bk']:.3f}  --> BOOKMAKER.EU")
    print(f"  {'-'*62}")
    print(f"  Margen    : +{sb['margen']:.3f}%")
    print(f"  GANANCIA  : ${sb['ganancia']:>10,.2f}   ROI: {sb['roi']:.2f}%")
    print("=" * 66)

async def scan_once(page_bw, page_bk):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"\n[{ts}] ---- INICIO DE SCAN ----")
    bw_r, bk_r = await asyncio.gather(scrape_bw(page_bw), scrape_bk(page_bk))
    print(f"  [BW] {len(bw_r)} partidos | [BK] {len(bk_r)} partidos")
    surebets = cruzar(bw_r, bk_r)
    if surebets:
        hist = []
        if ALERT_LOG.exists():
            try: hist = json.loads(ALERT_LOG.read_text(encoding="utf-8"))
            except: pass
        ALERT_LOG.write_text(json.dumps(hist+surebets, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"  [GUARDADO] {len(surebets)} surebet(s) en {ALERT_LOG}")
    else:
        print(f"  [RESULTADO] Sin surebets (margen min: {MIN_MARGEN}%)")
    return surebets

async def main():
    if not BK_USER or not BK_PASS or not BW_USER or not BW_PASS:
        print("[ERROR] Faltan credenciales en .env")
        return

    print(f"""
================================================================
  BETBOT SCANNER v4.5 - Betwarrior (Kambi) vs Bookmaker.eu
================================================================
  Bankroll  : ${BANKROLL:,.0f}  |  Margen: {MIN_MARGEN:.1f}%  |  Intervalo: {SCAN_INTERVAL}s
  BW Login  : {BW_USER}
  BK Login  : {BK_USER}
================================================================""")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled"]
        )
        vp = {"width": 1400, "height": 900}
        ctx_bw = await browser.new_context(user_agent=UA, locale="es-AR", viewport=vp)
        ctx_bk = await browser.new_context(user_agent=UA, locale="es-AR", viewport=vp)
        page_bw = await ctx_bw.new_page()
        page_bk = await ctx_bk.new_page()

        await bw_login(page_bw)
        await bk_login(page_bk)

        print("  Sesiones listas. Escaneando...")
        total = 0; scan_n = 0
        while True:
            try:
                sb = await scan_once(page_bw, page_bk)
                total += len(sb)
                scan_n += 1
                print(f"\n  Scans: {scan_n} | Surebets: {total} | Proximo en {SCAN_INTERVAL}s...")
                await asyncio.sleep(SCAN_INTERVAL)
            except KeyboardInterrupt:
                print(f"\nDetenido. Total: {total}")
                break
            except Exception as e:
                print(f"  Error: {e}")
                await asyncio.sleep(15)

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
