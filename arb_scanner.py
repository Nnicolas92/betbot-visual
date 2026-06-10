#!/usr/bin/env python3
"""
arb_scanner.py v4.4
- Fix regex rota en JS evaluate
- Login BW maneja popups/modales emergentes
- Login BK robusto con screenshot de debug si falla
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

def similitud(a, b):
    a = re.sub(r'[^a-z0-9 ]', '', a.lower())
    b = re.sub(r'[^a-z0-9 ]', '', b.lower())
    return SequenceMatcher(None, a, b).ratio()

def calcular_arb(o1, o2, bankroll=None):
    if bankroll is None: bankroll = BANKROLL
    ti = 1/o1 + 1/o2
    if ti >= 1.0: return None
    m  = (1 - ti) * 100
    s1 = round(bankroll * (1/o1) / ti, 2)
    s2 = round(bankroll * (1/o2) / ti, 2)
    g  = round(s1 * o1 - bankroll, 2)
    return {"margen": round(m,3), "s1": s1, "s2": s2, "ganancia": g, "roi": round(g/bankroll*100,2)}

# ── helper: cerrar cualquier popup/overlay emergente ─────────────────────────
async def cerrar_popups(page):
    """Intenta cerrar overlays, cookies, chats, modales que bloquean el form."""
    dismissers = [
        "button[aria-label*='close']", "button[aria-label*='Close']",
        "button[aria-label*='cerrar']", "button[aria-label*='Cerrar']",
        ".modal__close", ".popup__close", ".close-btn",
        "[class*='close']", "[class*='dismiss']",
        "text=Cerrar", "text=Aceptar", "text=Entendido",
        "text=Acepto", "text=OK", "text=No gracias",
        # cookie banners comunes
        "#onetrust-accept-btn-handler",
        "[id*='cookie'] button", "[class*='cookie'] button",
    ]
    for sel in dismissers:
        try:
            loc = page.locator(sel)
            if await loc.count() > 0:
                await loc.first.click(timeout=1500)
                await page.wait_for_timeout(800)
        except:
            pass

# ── BETWARRIOR LOGIN ──────────────────────────────────────────────────────────
async def bw_login(page):
    print("  [BW] Login...", end=" ", flush=True)
    await page.goto("https://mza.betwarrior.bet.ar/es-ar/sports/home",
                    wait_until="networkidle", timeout=50000)
    await page.wait_for_timeout(3000)
    await cerrar_popups(page)

    # Hacer click en ENTRAR / UNIRSE / LOGIN
    for txt in ["ENTRAR", "Entrar", "UNIRSE", "Iniciar sesión", "LOGIN", "Login"]:
        try:
            btn = page.locator(f"text={txt}")
            if await btn.count() > 0:
                await btn.first.click()
                await page.wait_for_timeout(2000)
                break
        except: pass

    # Esperar que aparezca el campo de password (modal/popup)
    try:
        await page.wait_for_selector("input[type='password']", timeout=10000)
    except:
        # Tomar screenshot para debug
        await page.screenshot(path="debug_bw_login.png")
        print("FALLO - ver debug_bw_login.png")
        return False

    await cerrar_popups(page)  # por si hay otro popup encima

    # Llenar usuario
    user_f = None
    for sel in ["input[type='email']", "input[type='text']",
                "input[name*='user']", "input[name*='email']",
                "input[placeholder*='usuario']", "input[placeholder*='email']",
                "input[placeholder*='correo']"]:
        user_f = await page.query_selector(sel)
        if user_f: break

    pass_f = await page.query_selector("input[type='password']")

    if not user_f or not pass_f:
        await page.screenshot(path="debug_bw_login.png")
        print("CAMPOS NO ENCONTRADOS - ver debug_bw_login.png")
        return False

    await user_f.click()
    await page.wait_for_timeout(300)
    await user_f.fill(BW_USER)
    await pass_f.click()
    await page.wait_for_timeout(300)
    await pass_f.fill(BW_PASS)

    submit = None
    for sel in ["button[type='submit']", "input[type='submit']",
                "button:has-text('Entrar')", "button:has-text('ENTRAR')",
                "button:has-text('Iniciar')", "button:has-text('Login')"]:
        submit = await page.query_selector(sel)
        if submit: break

    if submit:
        await submit.click()
    else:
        await pass_f.press("Enter")

    await page.wait_for_timeout(6000)
    await cerrar_popups(page)
    print("OK")
    return True

# ── BETWARRIOR SCRAPE ─────────────────────────────────────────────────────────
KAMBI_ODDS_JS = """
() => {
  const partidos = [];
  const eventos = document.querySelectorAll(
    '[class*="KambiBC-event-item"],[class*="KambiBC-bet-offer"]'
  );
  eventos.forEach(ev => {
    const nameEl = ev.querySelector(
      '[class*="KambiBC-event-participants"],[class*="participant"],[class*="team-name"],[class*="event-name"]'
    );
    const nombre = nameEl ? nameEl.innerText.trim().replace(/\\n+/g,' ') : '';
    const cuotas = [];
    ev.querySelectorAll('[class*="KambiBC-betty-outcome"]').forEach(oc => {
      oc.querySelectorAll('span,div').forEach(s => {
        const txt = s.innerText.trim();
        const v = parseFloat(txt);
        if (!isNaN(v) && v >= 1.05 && v <= 50 && txt.indexOf('.') !== -1 && !txt.includes(' '))
          cuotas.push(v);
      });
    });
    if (nombre.length > 3 && cuotas.length >= 2)
      partidos.push({nombre: nombre.slice(0,70), cuotas: Array.from(new Set(cuotas)).slice(0,4)});
  });
  if (partidos.length === 0) {
    const allOdds = [];
    document.querySelectorAll('[class*="KambiBC-betty-outcome"]').forEach(oc => {
      oc.querySelectorAll('span,div').forEach(s => {
        const txt = s.innerText.trim();
        const v = parseFloat(txt);
        if (!isNaN(v) && v >= 1.05 && v <= 50 && txt.indexOf('.') !== -1 && !txt.includes(' '))
          allOdds.push(v);
      });
    });
    for (let i = 0; i+1 < allOdds.length; i += 2)
      partidos.push({nombre: 'Partido_BW_' + Math.floor(i/2), cuotas: allOdds.slice(i, i+3)});
  }
  return partidos;
}
"""

async def scrape_bw(page):
    partidos = []
    try:
        print("  [BW] Cuotas...", end=" ", flush=True)
        await page.reload(wait_until="networkidle", timeout=40000)
        await page.wait_for_timeout(3000)
        await cerrar_popups(page)
        try:
            await page.wait_for_selector("[class*='KambiBC-betty-outcome']", timeout=10000)
        except: pass
        partidos = await page.evaluate(KAMBI_ODDS_JS)
        print(f"OK ({len(partidos)} partidos)")
    except Exception as e:
        print(f"ERROR: {e}")
    return partidos

# ── BOOKMAKER LOGIN ───────────────────────────────────────────────────────────
async def bk_login(page):
    print("  [BK] Login...", end=" ", flush=True)
    await page.goto("https://www.bookmaker.eu",
                    wait_until="networkidle", timeout=50000)
    await page.wait_for_timeout(3000)
    await cerrar_popups(page)

    # Click en Login
    for txt in ["Login to Account", "Login", "Entrar", "Sign In", "Ingresar"]:
        try:
            btn = page.locator(f"text={txt}")
            if await btn.count() > 0:
                await btn.first.click()
                await page.wait_for_timeout(2000)
                break
        except: pass

    # Esperar password field
    try:
        await page.wait_for_selector("input[type='password']", timeout=10000)
    except:
        # Intentar URL directa de login
        await page.goto("https://www.bookmaker.eu/login",
                        wait_until="networkidle", timeout=40000)
        await page.wait_for_timeout(3000)
        await cerrar_popups(page)
        try:
            await page.wait_for_selector("input[type='password']", timeout=8000)
        except:
            await page.screenshot(path="debug_bk_login.png")
            print("FALLO - ver debug_bk_login.png")
            return False

    await cerrar_popups(page)

    user_f = None
    for sel in ["input[name='username']", "input[name='email']",
                "input[name='account']", "input[type='email']",
                "input[type='text']", "input[placeholder*='user']",
                "input[placeholder*='account']", "input[placeholder*='email']"]:
        user_f = await page.query_selector(sel)
        if user_f: break

    pass_f = await page.query_selector("input[type='password']")

    if not user_f or not pass_f:
        await page.screenshot(path="debug_bk_login.png")
        print("CAMPOS NO ENCONTRADOS - ver debug_bk_login.png")
        return False

    await user_f.click()
    await page.wait_for_timeout(300)
    await user_f.fill(BK_USER)
    await pass_f.click()
    await page.wait_for_timeout(300)
    await pass_f.fill(BK_PASS)

    submit = None
    for sel in ["button[type='submit']", "input[type='submit']",
                "button:has-text('Login')", "button:has-text('Sign In')",
                "button:has-text('Entrar')", "button:has-text('Ingresar')"]:
        submit = await page.query_selector(sel)
        if submit: break

    if submit:
        await submit.click()
    else:
        await pass_f.press("Enter")

    await page.wait_for_timeout(6000)
    await cerrar_popups(page)
    print("OK")
    return True

# ── BOOKMAKER SCRAPE ──────────────────────────────────────────────────────────
BK_ODDS_JS = """
() => {
  const partidos = [];
  const lines = document.body.innerText.split('\\n')
    .map(function(l){ return l.trim(); })
    .filter(function(l){ return l.length > 0; });

  function esOddDecimal(raw) {
    var r = raw.replace(',', '.');
    if (r.indexOf('.') === -1) return false;
    var v = parseFloat(r);
    return !isNaN(v) && v >= 1.05 && v <= 50;
  }
  function esOddAmericana(raw) {
    return /^[+-][0-9]{2,4}$/.test(raw);
  }
  function americanaADecimal(raw) {
    var a = parseInt(raw);
    return a > 0 ? parseFloat((a/100+1).toFixed(3)) : parseFloat((100/Math.abs(a)+1).toFixed(3));
  }

  for (var i = 0; i < lines.length - 2; i++) {
    var l = lines[i];
    var esPartido = l.indexOf(' vs ') !== -1 || l.indexOf(' VS ') !== -1 ||
                    l.indexOf(' @ ')  !== -1 ||
                    (l.length > 4 && l.length < 80);
    if (!esPartido) continue;

    var cuotas = [];
    for (var j = i+1; j < Math.min(i+12, lines.length); j++) {
      var raw = lines[j].replace(',','.');
      if (esOddAmericana(lines[j])) {
        cuotas.push(americanaADecimal(lines[j]));
      } else if (esOddDecimal(raw)) {
        cuotas.push(parseFloat(raw));
      }
    }
    if (cuotas.length >= 2) {
      var unique = cuotas.filter(function(v,idx,arr){ return arr.indexOf(v) === idx; });
      partidos.push({nombre: l.slice(0,70), cuotas: unique.slice(0,4)});
      i += 3;
    }
  }
  return partidos;
}
"""

async def scrape_bk(page):
    partidos = []
    try:
        print("  [BK] Cuotas...", end=" ", flush=True)
        await page.goto("https://www.bookmaker.eu/sports-betting/football",
                        wait_until="networkidle", timeout=40000)
        await page.wait_for_timeout(3000)
        await cerrar_popups(page)
        html_len = len(await page.content())
        partidos = await page.evaluate(BK_ODDS_JS)
        print(f"OK ({len(partidos)} partidos, html: {html_len:,} chars)")
        if len(partidos) == 0 and html_len < 80000:
            txt = await page.evaluate("function(){ return document.body.innerText; }")
            Path("debug_bk_live.txt").write_text(txt[:5000], encoding="utf-8")
            await page.screenshot(path="debug_bk_live.png")
            print("  [BK] Screenshot guardado: debug_bk_live.png")
    except Exception as e:
        print(f"ERROR: {e}")
    return partidos

# ── CRUZAR Y ALERTAR ─────────────────────────────────────────────────────────
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

# ── SCAN ─────────────────────────────────────────────────────────────────────
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

# ── MAIN ──────────────────────────────────────────────────────────────────────
async def main():
    if not BK_USER or not BK_PASS or not BW_USER or not BW_PASS:
        print("[ERROR] Faltan credenciales en .env")
        print("Necesario: BETWARRIOR_USER, BETWARRIOR_PASS, BOOKMAKER_USER, BOOKMAKER_PASS")
        return

    print(f"""
================================================================
  BETBOT SCANNER v4.4 - Betwarrior vs Bookmaker.eu
================================================================
  Bankroll  : ${BANKROLL:,.0f}  |  Margen min: {MIN_MARGEN:.1f}%  |  Intervalo: {SCAN_INTERVAL}s
  BW Login  : {BW_USER}
  BK Login  : {BK_USER}
================================================================
  Iniciando sesiones (puede tardar 20-30 seg)...
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

        # Login secuencial
        ok_bw = await bw_login(page_bw)
        ok_bk = await bk_login(page_bk)

        if not ok_bw:
            print("  [AVISO] BW login fallo - revisa debug_bw_login.png")
        if not ok_bk:
            print("  [AVISO] BK login fallo - revisa debug_bk_login.png")

        print("\n  Comenzando scans...")
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
