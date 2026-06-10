#!/usr/bin/env python3
"""
arb_scanner.py v4.2
Login real en Betwarrior + Bookmaker.eu con credenciales del .env
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

BANKROLL       = float(os.getenv("BANKROLL", "10000"))
MIN_MARGEN     = float(os.getenv("MIN_MARGEN", "0.5"))
SCAN_INTERVAL  = int(os.getenv("SCAN_INTERVAL", "30"))
BW_USER        = os.getenv("BETWARRIOR_USER", "")
BW_PASS        = os.getenv("BETWARRIOR_PASS", "")
BK_USER        = os.getenv("BOOKMAKER_USER", "")
BK_PASS        = os.getenv("BOOKMAKER_PASS", "")
ALERT_LOG      = Path("surebets_encontrados.json")
SIM_THRESHOLD  = 0.55
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"

# ── MATEMATICA ────────────────────────────────────────────────
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

# ── LOGIN + SCRAPE BETWARRIOR ─────────────────────────────────
async def scrape_bw(page):
    partidos = []
    try:
        print("  [BW] Cargando...", end=" ", flush=True)
        await page.goto("https://mza.betwarrior.bet.ar/es-ar/sports/home",
                        wait_until="networkidle", timeout=50000)
        await page.wait_for_timeout(3000)

        # Login si hay credenciales y no esta logueado
        if BW_USER and BW_PASS:
            logged = await page.query_selector("[class*='user-balance'],[class*='saldo'],[class*='account']")
            if not logged:
                print("login...", end=" ", flush=True)
                # Buscar boton login/entrar
                btn = await page.query_selector("text=ENTRAR, text=Entrar, text=LOGIN, text=Iniciar sesión, [class*='login']")
                if btn:
                    await btn.click()
                    await page.wait_for_timeout(1500)
                # Rellenar usuario
                user_input = await page.query_selector("input[type='text'], input[name*='user'], input[name*='email'], input[placeholder*='user'], input[placeholder*='email']")
                pass_input = await page.query_selector("input[type='password']")
                if user_input and pass_input:
                    await user_input.fill(BW_USER)
                    await pass_input.fill(BW_PASS)
                    await pass_input.press("Enter")
                    await page.wait_for_timeout(4000)
                    print("OK login...", end=" ", flush=True)
                else:
                    print("form no encontrado...", end=" ", flush=True)

        # Esperar cuotas Kambi
        try:
            await page.wait_for_selector("[class*='KambiBC-betty-outcome']", timeout=10000)
        except:
            pass

        resultado = await page.evaluate("""
          () => {
            const partidos = [];
            const eventos = document.querySelectorAll(
              '[class*="KambiBC-event-item"], [class*="KambiBC-bet-offer"]'
            );
            eventos.forEach(ev => {
              const nameEl = ev.querySelector(
                '[class*="KambiBC-event-participants"],[class*="participant"],[class*="team-name"],[class*="event-name"]'
              );
              const nombre = nameEl ? nameEl.innerText.trim().replace(/\n+/g,' ') : '';
              const outcomeEls = ev.querySelectorAll('[class*="KambiBC-betty-outcome"]');
              const cuotas = [];
              outcomeEls.forEach(oc => {
                oc.querySelectorAll('span,div').forEach(s => {
                  const v = parseFloat(s.innerText.trim().replace(',','.'));
                  if (!isNaN(v) && v >= 1.05 && v <= 50.0 && s.innerText.trim().match(/^\d+\.\d+$/))
                    cuotas.push(v);
                });
              });
              if (nombre.length > 3 && cuotas.length >= 2)
                partidos.push({ nombre: nombre.slice(0,70), cuotas: [...new Set(cuotas)].slice(0,4) });
            });
            // Fallback: agrupar todos los outcomes en pares
            if (partidos.length === 0) {
              const all = [...document.querySelectorAll('[class*="KambiBC-betty-outcome"]')];
              const odds = [];
              all.forEach(oc => {
                oc.querySelectorAll('span,div').forEach(s => {
                  const v = parseFloat(s.innerText.trim().replace(',','.'));
                  if (!isNaN(v) && v >= 1.05 && v <= 50.0) odds.push(v);
                });
              });
              for (let i = 0; i + 1 < odds.length; i += 2)
                partidos.push({ nombre: `Partido_BW_${Math.floor(i/2)}`, cuotas: odds.slice(i, i+3) });
            }
            return partidos;
          }
        """)
        partidos = resultado
        print(f"OK ({len(partidos)} partidos, {sum(len(p['cuotas']) for p in partidos)} cuotas)")
    except Exception as e:
        print(f"ERROR: {e}")
    return partidos

# ── LOGIN + SCRAPE BOOKMAKER.EU ───────────────────────────────
async def scrape_bookmaker(page):
    partidos = []
    try:
        print("  [BK] Cargando...", end=" ", flush=True)

        # Ir directo al login
        await page.goto("https://www.bookmaker.eu/login",
                        wait_until="networkidle", timeout=50000)
        await page.wait_for_timeout(3000)

        # Bypass warning Chrome si aparece
        try:
            btn_bypass = page.locator("text=Continuar de todos modos, text=Continue Anyway, text=Continue anyway")
            if await btn_bypass.count() > 0:
                await btn_bypass.first.click()
                await page.wait_for_timeout(2000)
        except: pass

        # Login con credenciales
        if BK_USER and BK_PASS:
            print("login...", end=" ", flush=True)
            try:
                # Intentar llenar formulario de login
                user_sel = "input[name='username'], input[name='email'], input[type='text'], input[placeholder*='user'], input[placeholder*='account']"
                pass_sel = "input[type='password']"

                await page.wait_for_selector(user_sel, timeout=8000)
                await page.fill(user_sel, BK_USER)
                await page.fill(pass_sel, BK_PASS)

                # Submit
                submit = await page.query_selector("button[type='submit'], input[type='submit'], button:has-text('Login'), button:has-text('Sign In'), button:has-text('Entrar')")
                if submit:
                    await submit.click()
                else:
                    await page.press(pass_sel, "Enter")

                await page.wait_for_timeout(5000)
                print("OK login...", end=" ", flush=True)

                # Ir a la seccion de odds
                await page.goto("https://www.bookmaker.eu/sports-betting/football",
                                wait_until="networkidle", timeout=40000)
                await page.wait_for_timeout(3000)

            except Exception as le:
                print(f"login error ({le})...", end=" ", flush=True)
                # Si no pudo hacer login, ir directo a odds igual
                await page.goto("https://www.bookmaker.eu/sports-betting/odds",
                                wait_until="networkidle", timeout=40000)
                await page.wait_for_timeout(3000)
        else:
            print("SIN CREDENCIALES en .env...", end=" ", flush=True)
            await page.goto("https://www.bookmaker.eu/sports-betting/odds",
                            wait_until="networkidle", timeout=40000)
            await page.wait_for_timeout(3000)

        html_len = len(await page.content())

        resultado = await page.evaluate("""
          () => {
            const partidos = [];
            const txt = document.body.innerText;
            const lines = txt.split('\\n').map(l => l.trim()).filter(l => l.length > 0);
            for (let i = 0; i < lines.length - 2; i++) {
              const l = lines[i];
              const esPartido = l.includes(' vs ') || l.includes(' VS ') || l.includes(' v ') ||
                                (l.length > 4 && l.length < 80 && /[A-Z]/.test(l));
              if (!esPartido) continue;
              const cuotas = [];
              for (let j = i+1; j < Math.min(i+10, lines.length); j++) {
                const cleaned = lines[j].replace(',','.');
                // Cuotas americanas
                const am = cleaned.match(/^([+-]\d{2,4})$/);
                if (am) {
                  const a = parseInt(am[1]);
                  const dec = a > 0 ? (a/100)+1 : (100/Math.abs(a))+1;
                  if (dec >= 1.05 && dec <= 50) cuotas.push(parseFloat(dec.toFixed(3)));
                  continue;
                }
                const d = parseFloat(cleaned);
                if (!isNaN(d) && d >= 1.05 && d <= 50.0 && cleaned.match(/^\d+[.,]\d{1,4}$/))
                  cuotas.push(d);
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
        print(f"OK ({len(partidos)} partidos, html: {html_len:,} chars)")

        if len(partidos) == 0:
            # Guardar texto para debug rapido
            txt = await page.evaluate("() => document.body.innerText")
            Path("debug_bk_live.txt").write_text(txt[:5000], encoding="utf-8")
            print(f"  [BK] 0 partidos - texto guardado en debug_bk_live.txt para revisar")

    except Exception as e:
        print(f"ERROR: {e}")
    return partidos

# ── CRUZAR Y BUSCAR ARBITRAJE ─────────────────────────────────
def cruzar_y_buscar_arb(partidos_bw, partidos_bk):
    surebets = []
    matches = 0
    for pbw in partidos_bw:
        for pbk in partidos_bk:
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
                        alerta_surebet(sb)
    if matches: print(f"  {matches} partidos cruzados entre casas")
    return surebets

# ── ALERTA ────────────────────────────────────────────────────
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

# ── SCAN ──────────────────────────────────────────────────────
async def scan_once():
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"\n[{ts}] ---- INICIO DE SCAN ----")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled",
                  "--disable-web-security"]
        )
        ctx_bw = await browser.new_context(user_agent=UA, locale="es-AR", viewport={"width":1400,"height":900})
        ctx_bk = await browser.new_context(user_agent=UA, locale="es-AR", viewport={"width":1400,"height":900})
        page_bw = await ctx_bw.new_page()
        page_bk = await ctx_bk.new_page()

        bw_r, bk_r = await asyncio.gather(scrape_bw(page_bw), scrape_bookmaker(page_bk))
        await browser.close()

    print(f"  [BW] {len(bw_r)} partidos | [BK] {len(bk_r)} partidos")

    surebets = cruzar_y_buscar_arb(bw_r, bk_r)

    if surebets:
        hist = []
        if ALERT_LOG.exists():
            try: hist = json.loads(ALERT_LOG.read_text(encoding="utf-8"))
            except: pass
        ALERT_LOG.write_text(json.dumps(hist + surebets, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"  [GUARDADO] {len(surebets)} surebet(s) en {ALERT_LOG}")
    else:
        print(f"  [RESULTADO] Sin surebets (margen min: {MIN_MARGEN}%)")
    return surebets

# ── LOOP ──────────────────────────────────────────────────────
async def main():
    bk_ok = "OK" if BK_USER else "NO configurado"
    bw_ok = "OK" if BW_USER else "NO configurado"
    print(f"""
================================================================
  BETBOT SCANNER v4.2 - Betwarrior vs Bookmaker.eu
================================================================
  Bankroll      : ${BANKROLL:,.0f}
  Margen min    : {MIN_MARGEN:.1f}%
  Intervalo     : {SCAN_INTERVAL}s
  BW Login      : {bw_ok}
  BK Login      : {bk_ok}
================================================================""")

    if not BK_USER or not BW_USER:
        print("  [ERROR] Falta BETWARRIOR_USER/PASS o BOOKMAKER_USER/PASS en .env")
        print("  Verificar que el .env tiene las 4 variables completas.")
        return

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
