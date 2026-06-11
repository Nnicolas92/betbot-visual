#!/usr/bin/env python3
"""
arb_scanner.py v5.0
Dos browsers VISIBLES simultaneos - igual que Arber:
  - BW y BK abren en ventanas reales lado a lado
  - Detecta surebet
  - Coloca apuestas automaticamente en ambas casas al mismo tiempo
  - Confirma y muestra ganancia
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
AUTO_BET      = os.getenv("AUTO_BET", "false").lower() == "true"
ALERT_LOG     = Path("surebets_encontrados.json")
SIM_THRESHOLD = 0.52
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"

def similitud(a, b):
    a = re.sub(r'[^a-z0-9 ]', '', a.lower())
    b = re.sub(r'[^a-z0-9 ]', '', b.lower())
    return SequenceMatcher(None, a, b).ratio()

def americana_a_decimal(s):
    try:
        a = int(str(s).strip())
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

# ── BETWARRIOR LOGIN ────────────────────────────────────────────────────
async def bw_login(page):
    print("  [BW] Login...", end=" ", flush=True)
    try:
        await page.goto("https://mza.betwarrior.bet.ar/es-ar/sports/home",
                        wait_until="networkidle", timeout=60000)
        await page.wait_for_timeout(3000)
        await page.get_by_text("Entrar/Unirse").click()
        await page.wait_for_timeout(2500)
        await page.get_by_test_id("login-email").fill(BW_USER)
        await page.wait_for_timeout(400)
        await page.get_by_test_id("login-password").fill(BW_PASS)
        await page.wait_for_timeout(400)
        await page.get_by_test_id("login-submit-button").click()
        await page.wait_for_timeout(7000)
        print("OK")
        return True
    except Exception as e:
        await page.screenshot(path="debug_bw_login.png")
        print(f"FALLO ({e})")
        return False

# ── BOOKMAKER LOGIN ────────────────────────────────────────────────────
async def bk_login(page):
    print("  [BK] Login...", end=" ", flush=True)
    try:
        await page.goto("https://www.bookmaker.eu/",
                        wait_until="networkidle", timeout=60000)
        await page.wait_for_timeout(3000)
        await page.get_by_role("textbox", name="Account").fill(BK_USER)
        await page.wait_for_timeout(300)
        await page.get_by_role("textbox", name="Password").fill(BK_PASS)
        await page.wait_for_timeout(300)
        await page.get_by_role("button", name="Login").click()
        await page.wait_for_timeout(6000)
        await page.goto("https://be.bookmaker.eu/en/sports/",
                        wait_until="networkidle", timeout=40000)
        await page.wait_for_timeout(3000)
        try:
            cb = page.get_by_role("checkbox", name="Don't show again")
            if await cb.count() > 0:
                await cb.check()
            ok = page.get_by_text("Ok", exact=True)
            if await ok.count() > 0:
                await ok.click()
            await page.wait_for_timeout(1500)
        except: pass
        print("OK")
        return True
    except Exception as e:
        await page.screenshot(path="debug_bk_login.png")
        print(f"FALLO ({e})")
        return False

# ── BETWARRIOR SCRAPE ────────────────────────────────────────────────────
async def scrape_bw(page):
    partidos = []
    try:
        print("  [BW] Cuotas...", end=" ", flush=True)
        try:
            await page.reload(wait_until="domcontentloaded", timeout=20000)
        except: pass
        await page.wait_for_timeout(8000)
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

# ── BOOKMAKER SCRAPE ────────────────────────────────────────────────────
BK_SPORTS = [
    "https://be.bookmaker.eu/en/sports/",
    "https://be.bookmaker.eu/en/sports/soccer/",
    "https://be.bookmaker.eu/en/sports/basketball/",
    "https://be.bookmaker.eu/en/sports/tennis/",
]

async def scrape_bk(page):
    partidos = []
    try:
        print("  [BK] Cuotas...", end=" ", flush=True)
        for url in BK_SPORTS:
            try:
                await page.goto(url, wait_until="networkidle", timeout=35000)
                await page.wait_for_timeout(2000)
            except: continue
            for txt in ["Don't show again", "Ok", "Accept", "Close"]:
                try:
                    el = page.get_by_text(txt, exact=True)
                    if await el.count() > 0:
                        await el.first.click()
                        await page.wait_for_timeout(600)
                except: pass
            rows = await page.evaluate("""
            (function() {
              var result = [];
              var rows = document.querySelectorAll('tr');
              var prevTeam = null, prevMl = null;
              rows.forEach(function(row) {
                var cells = row.querySelectorAll('td');
                if (cells.length < 2) return;
                var teamCell = null, mlCell = null;
                cells.forEach(function(td) {
                  var txt = td.innerText.trim();
                  if (/^[+\-][0-9]{2,4}$/.test(txt)) {
                    mlCell = txt;
                  } else if (txt.length > 3 && txt.length < 60
                             && !/^[0-9\/:.]+$/.test(txt)
                             && txt.indexOf('$') === -1) {
                    teamCell = txt;
                  }
                });
                if (teamCell && mlCell) {
                  if (prevTeam && prevMl) {
                    result.push({ nombre: prevTeam + ' vs ' + teamCell, cuotas: [prevMl, mlCell] });
                    prevTeam = null; prevMl = null;
                  } else { prevTeam = teamCell; prevMl = mlCell; }
                }
              });
              return result;
            })()
            """)
            for row in rows:
                cd = [americana_a_decimal(ml) for ml in row["cuotas"]]
                cd = [c for c in cd if c]
                if len(cd) >= 2:
                    partidos.append({"nombre": row["nombre"], "cuotas": cd})
        print(f"OK ({len(partidos)} partidos)")
        if len(partidos) == 0:
            await page.screenshot(path="debug_bk_live.png")
    except Exception as e:
        print(f"ERROR: {e}")
    return partidos

# ── APOSTAR SIMULTANEAMENTE (como Arber) ─────────────────────────────────
async def apostar_bw(page, sb):
    """Navega al partido en BW y coloca la apuesta."""
    try:
        print(f"  [BW] Colocando apuesta ${sb['s1']:.2f} @ {sb['odd_bw']}...", end=" ", flush=True)
        # Buscar el outcome con la cuota correcta y hacer click
        clicked = await page.evaluate(f"""
        (function() {{
          var target = {sb['odd_bw']};
          var outcomes = document.querySelectorAll('[class*="KambiBC-betty-outcome"]');
          for (var i=0; i<outcomes.length; i++) {{
            var spans = outcomes[i].querySelectorAll('span,div');
            for (var j=0; j<spans.length; j++) {{
              if (parseFloat(spans[j].innerText.trim()) === target) {{
                outcomes[i].click();
                return true;
              }}
            }}
          }}
          return false;
        }})()
        """)
        if not clicked:
            print("outcome no encontrado")
            return False
        await page.wait_for_timeout(1500)
        # Ingresar monto en el betslip
        stake_sel = "input[data-testid*='stake'], input[placeholder*='monto'], input[placeholder*='Monto'], input[class*='stake'], input[class*='amount']"
        try:
            await page.wait_for_selector(stake_sel, timeout=5000)
            await page.fill(stake_sel, str(sb['s1']))
            await page.wait_for_timeout(800)
            # Confirmar apuesta
            await page.click("button[data-testid*='place'], button:has-text('Confirmar'), button:has-text('Apostar'), button:has-text('Place Bet')")
            await page.wait_for_timeout(2000)
            print("CONFIRMADA")
            return True
        except:
            print("betslip no abierto")
            return False
    except Exception as e:
        print(f"ERROR: {e}")
        return False

async def apostar_bk(page, sb):
    """Coloca apuesta en BK sobre el partido ya cargado."""
    try:
        print(f"  [BK] Colocando apuesta ${sb['s2']:.2f} @ {sb['odd_bk']}...", end=" ", flush=True)
        # Buscar moneyline equivalente y click
        # BK usa tabla - buscar el link del partido
        enlaces = await page.evaluate("""
        (function() {
          var links = document.querySelectorAll('a[href*="/lines/"], a[href*="/sports/"]');
          var arr = [];
          links.forEach(function(a) { arr.push({text: a.innerText.trim(), href: a.href}); });
          return arr;
        })()
        """)
        evento_bk = sb.get('evento_bk', '')
        target_href = None
        for l in enlaces:
            if similitud(l['text'], evento_bk) > 0.4:
                target_href = l['href']
                break
        if target_href:
            await page.goto(target_href, wait_until="networkidle", timeout=20000)
            await page.wait_for_timeout(2000)
        # Click en la cuota correcta
        target_ml = int((sb['odd_bk'] - 1) * 100) if sb['odd_bk'] >= 2 else -int(100 / (sb['odd_bk'] - 1))
        clicked = await page.evaluate(f"""
        (function() {{
          var cells = document.querySelectorAll('td,a');
          for (var i=0; i<cells.length; i++) {{
            var txt = cells[i].innerText.trim();
            if (txt === '{target_ml:+d}' || txt === '{target_ml}') {{
              cells[i].click();
              return true;
            }}
          }}
          return false;
        }})()
        """)
        await page.wait_for_timeout(1500)
        # Ingresar monto
        stake_sel = "input[name*='amount'], input[name*='stake'], input[placeholder*='Amount'], input[class*='wager']"
        try:
            await page.wait_for_selector(stake_sel, timeout=5000)
            await page.fill(stake_sel, str(sb['s2']))
            await page.wait_for_timeout(800)
            await page.click("input[value*='Place'], button:has-text('Place'), button:has-text('Submit')")
            await page.wait_for_timeout(2000)
            print("CONFIRMADA")
            return True
        except:
            print("betslip no abierto")
            return False
    except Exception as e:
        print(f"ERROR: {e}")
        return False

# ── CRUZAR Y EJECUTAR ───────────────────────────────────────────────────────
async def cruzar_y_ejecutar(bw, bk, page_bw, page_bk):
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
                        imprimir_oportunidad(sb)
                        if AUTO_BET:
                            print("  Placing bets simultaneously...")
                            r1, r2 = await asyncio.gather(
                                apostar_bw(page_bw, sb),
                                apostar_bk(page_bk, sb)
                            )
                            if r1 and r2:
                                print(f"  Profit: ${sb['ganancia']:.2f} USD / {sb['roi']:.2f}%")
                            else:
                                print("  AVISO: una o ambas apuestas fallaron - verificar manualmente")
    if matches: print(f"  {matches} partidos cruzados entre casas")
    return surebets

def imprimir_oportunidad(sb):
    print()
    print("=" * 66)
    print("  *** OPPORTUNITY FOUND ***")
    print("=" * 66)
    print(f"  Evento BW  : {sb['evento']}")
    print(f"  Evento BK  : {sb['evento_bk']}")
    print(f"  {'-'*62}")
    print(f"  Placing in BetWarrior : ${sb['s1']:>9,.2f}  @ {sb['odd_bw']:.3f}")
    print(f"  Placing in Bookmaker  : ${sb['s2']:>9,.2f}  @ {sb['odd_bk']:.3f}")
    print(f"  {'-'*62}")
    print(f"  Margen    : +{sb['margen']:.3f}%")
    print(f"  Profit    : ${sb['ganancia']:>9,.2f}   ROI: {sb['roi']:.2f}%")
    print("=" * 66)

async def scan_once(page_bw, page_bk):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"\n[{ts}] ---- SCANNING ----")
    bw_r, bk_r = await asyncio.gather(scrape_bw(page_bw), scrape_bk(page_bk))
    print(f"  [BW] {len(bw_r)} partidos | [BK] {len(bk_r)} partidos")
    surebets = await cruzar_y_ejecutar(bw_r, bk_r, page_bw, page_bk)
    if not surebets:
        print(f"  No opportunities (min margin: {MIN_MARGEN}%)")
    else:
        hist = []
        if ALERT_LOG.exists():
            try: hist = json.loads(ALERT_LOG.read_text(encoding="utf-8"))
            except: pass
        ALERT_LOG.write_text(json.dumps(hist+surebets, indent=2, ensure_ascii=False), encoding="utf-8")
    return surebets

async def main():
    if not BK_USER or not BK_PASS or not BW_USER or not BW_PASS:
        print("[ERROR] Faltan credenciales en .env")
        return

    modo = "AUTO-BET ACTIVO" if AUTO_BET else "SOLO DETECCION (AUTO_BET=false en .env)"
    print(f"""
================================================================
  BETBOT SCANNER v5.0 - BetWarrior vs Bookmaker.eu
================================================================
  Bankroll  : ${BANKROLL:,.0f}  |  Margen: {MIN_MARGEN:.1f}%  |  Intervalo: {SCAN_INTERVAL}s
  Modo      : {modo}
  BW Login  : {BW_USER}
  BK Login  : {BK_USER}
================================================================
  Para activar apuestas automaticas: agregar AUTO_BET=true en .env
================================================================""")

    async with async_playwright() as p:
        # DOS BROWSERS VISIBLES - lado a lado como Arber
        browser_bw = await p.chromium.launch(
            headless=False,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled",
                  "--window-position=0,0", "--window-size=960,900"]
        )
        browser_bk = await p.chromium.launch(
            headless=False,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled",
                  "--window-position=960,0", "--window-size=960,900"]
        )

        vp = {"width": 960, "height": 900}
        ctx_bw = await browser_bw.new_context(user_agent=UA, locale="es-AR", viewport=vp)
        ctx_bk = await browser_bk.new_context(user_agent=UA, locale="en-US", viewport=vp)
        page_bw = await ctx_bw.new_page()
        page_bk = await ctx_bk.new_page()

        print("  Iniciando sesiones...")
        await asyncio.gather(bw_login(page_bw), bk_login(page_bk))
        print("  Arber started.")

        total = 0; scan_n = 0
        while True:
            try:
                sb = await scan_once(page_bw, page_bk)
                total += len(sb)
                scan_n += 1
                print(f"\n  Scans: {scan_n} | Surebets: {total} | Proximo en {SCAN_INTERVAL}s...")
                await asyncio.sleep(SCAN_INTERVAL)
            except KeyboardInterrupt:
                print(f"\nDetenido. Total encontrados: {total}")
                break
            except Exception as e:
                print(f"  Error: {e}")
                await asyncio.sleep(15)

        await browser_bw.close()
        await browser_bk.close()

if __name__ == "__main__":
    asyncio.run(main())
