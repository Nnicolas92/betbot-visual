#!/usr/bin/env python3
"""
arb_scanner.py v4.3
Login REAL en Betwarrior (Kambi) + Bookmaker.eu
Credenciales desde .env: BETWARRIOR_USER/PASS y BOOKMAKER_USER/PASS
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
SIM_THRESHOLD = 0.55
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"

# Estado de sesion (se logueamos una vez, no en cada scan)
_bw_logged  = False
_bk_logged  = False
_bw_browser = None
_bk_browser = None
_bw_page    = None
_bk_page    = None

# ── MATEMATICA ───────────────────────────────────────────────
def calcular_arb(o1, o2, bankroll=None):
    if bankroll is None: bankroll = BANKROLL
    ti = 1/o1 + 1/o2
    if ti >= 1.0: return None
    m = (1 - ti) * 100
    s1 = round(bankroll * (1/o1) / ti, 2)
    s2 = round(bankroll * (1/o2) / ti, 2)
    g  = round(s1 * o1 - bankroll, 2)
    return {"margen": round(m,3), "s1": s1, "s2": s2, "ganancia": g, "roi": round(g/bankroll*100,2)}

def similitud(a, b):
    a = re.sub(r'[^a-z0-9 ]','', a.lower())
    b = re.sub(r'[^a-z0-9 ]','', b.lower())
    return SequenceMatcher(None, a, b).ratio()

# ── BETWARRIOR: LOGIN ────────────────────────────────────────────
async def bw_login(page):
    global _bw_logged
    print("  [BW] Haciendo login...", end=" ", flush=True)
    await page.goto("https://mza.betwarrior.bet.ar/es-ar/sports/home",
                    wait_until="networkidle", timeout=50000)
    await page.wait_for_timeout(3000)

    # Buscar y clickear boton ENTRAR
    try:
        entrar = page.locator("text=ENTRAR, text=Entrar, text=Iniciar sesion, text=Login")
        if await entrar.count() > 0:
            await entrar.first.click()
            await page.wait_for_timeout(2000)
    except: pass

    # Esperar campo de usuario
    try:
        await page.wait_for_selector("input[type='text'], input[name*='user'], input[name*='email']",
                                      timeout=8000)
    except:
        print("ADVERTENCIA: formulario no encontrado")
        return

    # Llenar usuario y contraseña
    try:
        user_f = await page.query_selector("input[type='text'], input[name*='user'], input[name*='email']")
        pass_f = await page.query_selector("input[type='password']")
        if user_f and pass_f:
            await user_f.fill(BW_USER)
            await pass_f.fill(BW_PASS)
            await pass_f.press("Enter")
            await page.wait_for_timeout(5000)
            print("OK")
            _bw_logged = True
        else:
            print("campos no encontrados")
    except Exception as e:
        print(f"ERROR: {e}")

# ── BETWARRIOR: SCRAPE (usa sesion activa) ──────────────────────────
async def scrape_bw(page):
    partidos = []
    try:
        print("  [BW] Leyendo cuotas...", end=" ", flush=True)
        # Recargar para tener cuotas frescas
        await page.reload(wait_until="networkidle", timeout=40000)
        await page.wait_for_timeout(3000)
        try:
            await page.wait_for_selector("[class*='KambiBC-betty-outcome']", timeout=10000)
        except: pass

        resultado = await page.evaluate("""
          () => {
            const partidos = [];
            // Metodo 1: por contenedores de eventos
            const eventos = document.querySelectorAll(
              '[class*="KambiBC-event-item"],[class*="KambiBC-bet-offer"]'
            );
            eventos.forEach(ev => {
              const nameEl = ev.querySelector(
                '[class*="KambiBC-event-participants"],[class*="participant"],[class*="team-name"],[class*="event-name"]'
              );
              const nombre = nameEl ? nameEl.innerText.trim().replace(/\n+/g,' ') : '';
              const cuotas = [];
              ev.querySelectorAll('[class*="KambiBC-betty-outcome"]').forEach(oc => {
                oc.querySelectorAll('span,div').forEach(s => {
                  const txt = s.innerText.trim();
                  if (/^\d+\.\d+$/.test(txt)) {
                    const v = parseFloat(txt);
                    if (v >= 1.05 && v <= 50) cuotas.push(v);
                  }
                });
              });
              if (nombre.length > 3 && cuotas.length >= 2)
                partidos.push({nombre: nombre.slice(0,70), cuotas: [...new Set(cuotas)].slice(0,4)});
            });
            // Metodo 2 (fallback): agrupar todos los outcomes de Kambi en pares
            if (partidos.length === 0) {
              const allOdds = [];
              document.querySelectorAll('[class*="KambiBC-betty-outcome"]').forEach(oc => {
                oc.querySelectorAll('span,div').forEach(s => {
                  const txt = s.innerText.trim();
                  if (/^\d+\.\d+$/.test(txt)) {
                    const v = parseFloat(txt);
                    if (v >= 1.05 && v <= 50) allOdds.push(v);
                  }
                });
              });
              for (let i = 0; i+1 < allOdds.length; i += 2)
                partidos.push({nombre: `Partido_BW_${Math.floor(i/2)}`, cuotas: allOdds.slice(i, i+3)});
            }
            return partidos;
          }
        """)
        partidos = resultado
        print(f"OK ({len(partidos)} partidos)")
    except Exception as e:
        print(f"ERROR: {e}")
    return partidos

# ── BOOKMAKER: LOGIN ───────────────────────────────────────────────
async def bk_login(page):
    global _bk_logged
    print("  [BK] Haciendo login...", end=" ", flush=True)

    # Ir a la pagina principal
    await page.goto("https://www.bookmaker.eu",
                    wait_until="networkidle", timeout=50000)
    await page.wait_for_timeout(3000)

    # Bypass warning de version de Chrome si aparece
    try:
        bypass = page.locator("text=Continuar de todos modos")
        if await bypass.count() > 0:
            await bypass.first.click()
            await page.wait_for_timeout(2000)
    except: pass

    # Hacer clic en Login/Entrar
    try:
        login_btn = page.locator("text=Login to Account, text=Login, text=Entrar, text=Sign In")
        if await login_btn.count() > 0:
            await login_btn.first.click()
            await page.wait_for_timeout(2000)
    except: pass

    # Esperar formulario
    try:
        await page.wait_for_selector("input[type='password']", timeout=8000)
    except:
        # Intentar ir directo a /login
        await page.goto("https://www.bookmaker.eu/login",
                        wait_until="networkidle", timeout=40000)
        await page.wait_for_timeout(3000)
        try:
            bypass = page.locator("text=Continuar de todos modos")
            if await bypass.count() > 0:
                await bypass.first.click()
                await page.wait_for_timeout(2000)
        except: pass

    # Llenar formulario
    try:
        # Campos de usuario (probar varios selectores)
        user_f = None
        for sel in ["input[name='username']", "input[name='email']",
                    "input[name='account']", "input[type='text']",
                    "input[placeholder*='user']", "input[placeholder*='account']",
                    "input[placeholder*='email']"]:
            user_f = await page.query_selector(sel)
            if user_f: break

        pass_f = await page.query_selector("input[type='password']")

        if user_f and pass_f:
            await user_f.click()
            await user_f.fill(BK_USER)
            await pass_f.click()
            await pass_f.fill(BK_PASS)

            # Submit: buscar boton o presionar Enter
            submit = await page.query_selector(
                "button[type='submit'], input[type='submit'], "
                "button:has-text('Login'), button:has-text('Sign In'), "
                "button:has-text('Entrar'), button:has-text('Ingresar')"
            )
            if submit:
                await submit.click()
            else:
                await pass_f.press("Enter")

            await page.wait_for_timeout(6000)
            print("OK")
            _bk_logged = True
        else:
            print("FORMULARIO NO ENCONTRADO - guardando debug...")
            html = await page.content()
            Path("debug_bk_login.html").write_text(html[:50000], encoding="utf-8")
            print("  Revisa debug_bk_login.html")
    except Exception as e:
        print(f"ERROR: {e}")

# ── BOOKMAKER: SCRAPE (usa sesion activa) ──────────────────────────
async def scrape_bk(page):
    partidos = []
    try:
        print("  [BK] Leyendo cuotas...", end=" ", flush=True)
        await page.goto("https://www.bookmaker.eu/sports-betting/football",
                        wait_until="networkidle", timeout=40000)
        await page.wait_for_timeout(3000)

        # Bypass si aparece de nuevo
        try:
            bypass = page.locator("text=Continuar de todos modos")
            if await bypass.count() > 0:
                await bypass.first.click()
                await page.wait_for_timeout(2000)
        except: pass

        html_len = len(await page.content())

        resultado = await page.evaluate("""
          () => {
            const partidos = [];
            const lines = document.body.innerText.split('\\n')
              .map(l => l.trim()).filter(l => l.length > 0);

            for (let i = 0; i < lines.length - 2; i++) {
              const l = lines[i];
              const esPartido = l.includes(' vs ') || l.includes(' VS ') ||
                                l.includes(' @ ') ||
                                (l.length > 4 && l.length < 80);
              if (!esPartido) continue;

              const cuotas = [];
              for (let j = i+1; j < Math.min(i+12, lines.length); j++) {
                const raw = lines[j].replace(',','.');
                // Cuotas americanas (+150, -110)
                const am = raw.match(/^([+-]\d{2,4})$/);
                if (am) {
                  const a = parseInt(am[1]);
                  const dec = a > 0 ? +(a/100+1).toFixed(3) : +(100/Math.abs(a)+1).toFixed(3);
                  if (dec >= 1.05 && dec <= 50) { cuotas.push(dec); continue; }
                }
                // Cuotas decimales
                if (/^\d+[.,]\d{1,4}$/.test(raw)) {
                  const d = parseFloat(raw);
                  if (d >= 1.05 && d <= 50) cuotas.push(d);
                }
              }
              if (cuotas.length >= 2) {
                partidos.push({nombre: l.slice(0,70), cuotas: [...new Set(cuotas)].slice(0,4)});
                i += 3;
              }
            }
            return partidos;
          }
        """)

        partidos = resultado
        print(f"OK ({len(partidos)} partidos, html: {html_len:,} chars)")

        if len(partidos) == 0:
            txt = await page.evaluate("() => document.body.innerText")
            Path("debug_bk_live.txt").write_text(txt[:5000], encoding="utf-8")
            print(f"  [BK] 0 partidos - ver debug_bk_live.txt")
    except Exception as e:
        print(f"ERROR: {e}")
    return partidos

# ── CRUZAR PARTIDOS Y BUSCAR ARB ─────────────────────────────────
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
    if matches: print(f"  {matches} partidos cruzados entre casas")
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

# ── SCAN PRINCIPAL ───────────────────────────────────────────────
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

# ── MAIN ───────────────────────────────────────────────────────────
async def main():
    if not BK_USER or not BK_PASS or not BW_USER or not BW_PASS:
        print("[ERROR] Falta usuario/contrasena en .env")
        print("Verificar: BETWARRIOR_USER, BETWARRIOR_PASS, BOOKMAKER_USER, BOOKMAKER_PASS")
        return

    print(f"""
================================================================
  BETBOT SCANNER v4.3 - Betwarrior vs Bookmaker.eu
================================================================
  Bankroll      : ${BANKROLL:,.0f}
  Margen min    : {MIN_MARGEN:.1f}%
  Intervalo     : {SCAN_INTERVAL}s
  BW Usuario    : {BW_USER}
  BK Usuario    : {BK_USER}
================================================================
  Iniciando sesiones...
================================================================""")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled",
                  "--disable-web-security"]
        )
        vp = {"width": 1400, "height": 900}
        ctx_bw = await browser.new_context(user_agent=UA, locale="es-AR", viewport=vp)
        ctx_bk = await browser.new_context(user_agent=UA, locale="es-AR", viewport=vp)
        page_bw = await ctx_bw.new_page()
        page_bk = await ctx_bk.new_page()

        # Login secuencial primero (no en paralelo para evitar problemas)
        await bw_login(page_bw)
        await bk_login(page_bk)

        print("\n  Sesiones iniciadas. Comenzando scans...")

        total = 0; scan_n = 0
        while True:
            try:
                sb = await scan_once(page_bw, page_bk)
                total += len(sb)
                scan_n += 1
                print(f"\n  Scans: {scan_n} | Surebets: {total} | Proximo en {SCAN_INTERVAL}s...")
                await asyncio.sleep(SCAN_INTERVAL)
            except KeyboardInterrupt:
                print(f"\nDetenido. Total surebets: {total}")
                break
            except Exception as e:
                print(f"  Error en scan: {e}")
                await asyncio.sleep(15)

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
