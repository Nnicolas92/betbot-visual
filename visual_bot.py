"""
visual_bot.py v4
Login + busqueda de partido + arbitraje en DOS casas
Casas soportadas: Bookmaker.eu, Betsson, Bet365
"""
import asyncio
from datetime import datetime
from pathlib import Path
from config import get_cred

try:
    from playwright.async_api import async_playwright
    PLAYWRIGHT_OK = True
except ImportError:
    PLAYWRIGHT_OK = False

try:
    from playwright_stealth import stealth_async
    STEALTH_OK = True
except ImportError:
    STEALTH_OK = False

try:
    from vision import login_por_vision
    VISION_OK = True
except Exception:
    VISION_OK = False

SCREENSHOTS_DIR = Path("screenshots")
SCREENSHOTS_DIR.mkdir(exist_ok=True)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/127.0.0.0 Safari/537.36"
)

CASAS = {
    "1": {"name": "Bet365",       "url": "https://www.bet365.com"},
    "2": {"name": "Bookmaker.eu", "url": "https://be.bookmaker.eu"},
    "3": {"name": "Betsson",      "url": "https://www.betsson.com/es"},
}

# ────────────────────────────────
# LOGIN
# ────────────────────────────────
async def _try_selectors(page, selectors: list, value: str, campo: str):
    for sel in selectors:
        try:
            el = page.locator(sel).first
            if await el.is_visible(timeout=2000):
                await el.fill(value)
                return True
        except:
            pass
    print(f"  ⚠️  No encontré campo {campo} por CSS — intentando visión...")
    return False

async def login_bookmaker(page, user, password):
    print("  🔐 Login Bookmaker.eu...")
    await page.goto("https://be.bookmaker.eu/es/pagina-ingreso/", wait_until="domcontentloaded", timeout=30000)
    await page.wait_for_timeout(2000)
    try:
        btn = page.locator("text=Continuar de todos modos")
        if await btn.is_visible(timeout=3000):
            await btn.click()
            await page.wait_for_timeout(1000)
    except:
        pass
    u_ok = await _try_selectors(page,
        ["input[name='username']","input[placeholder*='suario']","input[type='text']"],
        user, "usuario")
    p_ok = await _try_selectors(page,
        ["input[name='password']","input[type='password']"],
        password, "contraseña")
    if not u_ok or not p_ok:
        if VISION_OK:
            await login_por_vision(page, user, password, "Bookmaker.eu")
            return
    try:
        await page.click("button[type='submit'], button:has-text('Entrar'), button:has-text('Ingresar')")
    except:
        await page.keyboard.press("Enter")
    await page.wait_for_timeout(3000)
    print("  ✅ Login Bookmaker enviado")

async def login_betsson(page, user, password):
    print("  🔐 Login Betsson...")
    await page.goto("https://www.betsson.com/es/login", wait_until="domcontentloaded", timeout=30000)
    await page.wait_for_timeout(2000)
    u_ok = await _try_selectors(page,
        ["input[name='username']","input[id*='user']","input[placeholder*='suario']","input[type='email']"],
        user, "usuario")
    p_ok = await _try_selectors(page,
        ["input[name='password']","input[type='password']","input[id*='pass']"],
        password, "contraseña")
    if not u_ok or not p_ok:
        if VISION_OK:
            await login_por_vision(page, user, password, "Betsson")
            return
    try:
        await page.click("button[type='submit'], button:has-text('Iniciar'), button:has-text('Entrar')")
    except:
        await page.keyboard.press("Enter")
    await page.wait_for_timeout(3000)
    print("  ✅ Login Betsson enviado")

async def login_bet365(page, user, password):
    print("  🔐 Login Bet365...")
    await page.goto("https://www.bet365.com", wait_until="domcontentloaded", timeout=30000)
    await page.wait_for_timeout(2000)
    try:
        await page.click("a:has-text('Iniciar'), .hm-Login")
        await page.wait_for_timeout(1500)
    except:
        pass
    u_ok = await _try_selectors(page,
        ["input[name='username']","input[placeholder*='sername']"],
        user, "usuario")
    p_ok = await _try_selectors(page,
        ["input[type='password']"],
        password, "contraseña")
    if not u_ok or not p_ok:
        if VISION_OK:
            await login_por_vision(page, user, password, "Bet365")
            return
    try:
        await page.click("button[type='submit']")
    except:
        await page.keyboard.press("Enter")
    await page.wait_for_timeout(3000)
    print("  ✅ Login Bet365 enviado")

LOGIN_FN = {"1": login_bet365, "2": login_bookmaker, "3": login_betsson}

# ────────────────────────────────
# BUSCAR PARTIDO
# ────────────────────────────────
async def buscar_partido(page, home, away, casa_key):
    urls = {
        "2": "https://be.bookmaker.eu/es/deportes/futbol/",
        "3": "https://www.betsson.com/es/apuestas-deportivas/futbol",
        "1": "https://www.bet365.com/#/AS/B1/",
    }
    url = urls.get(casa_key, CASAS[casa_key]["url"])
    print(f"  🔍 Buscando {home} vs {away} en {CASAS[casa_key]['name']}...")
    await page.goto(url, wait_until="domcontentloaded", timeout=30000)
    await page.wait_for_timeout(3000)
    for termino in [home, away]:
        try:
            el = page.locator(f"text={termino}").first
            if await el.is_visible(timeout=5000):
                await el.click()
                await page.wait_for_timeout(2000)
                print(f"  ✅ Partido encontrado")
                return True
        except:
            pass
    print(f"  ⚠️  Partido no encontrado automáticamente — buscalo en el navegador")
    return False

# ────────────────────────────────
# CALCULAR ARBITRAJE
# ────────────────────────────────
def calcular_stakes(partido, monto_total):
    h = partido["best_home"]
    a = partido["best_away"]
    d = partido.get("best_draw", 0) or 0
    suma = (1/h) + (1/a) + (1/d if d else 0)
    if suma >= 1.0:
        return None
    profit_pct = ((1 - suma) / suma) * 100
    s_h = round(monto_total * (1/h) / suma, 2)
    s_a = round(monto_total * (1/a) / suma, 2)
    s_d = round(monto_total * (1/d) / suma, 2) if d else 0
    ganancia = round(monto_total * (1/suma) - monto_total, 2)
    return {"profit_pct": profit_pct, "stake_home": s_h, "stake_away": s_a,
            "stake_draw": s_d, "ganancia_garantizada": ganancia, "suma_prob": suma}

# ────────────────────────────────
# FLUJO PRINCIPAL DOS CASAS
# ────────────────────────────────
async def arbitraje_completo(casa1_key, casa2_key, partido, creds, monto_total):
    if not PLAYWRIGHT_OK:
        print("❌ Playwright no instalado. Corré INSTALAR.bat")
        return

    ts = datetime.now().strftime("%H%M%S")
    casa1 = CASAS[casa1_key]
    casa2 = CASAS[casa2_key]
    stakes = calcular_stakes(partido, monto_total)

    print(f"""
╔══════════════════════════════════════════════════════╗
║  🎯 ARBITRAJE — {casa1['name']} + {casa2['name']}
╚══════════════════════════════════════════════════════╝
  Partido : {partido['home']} vs {partido['away']}
  LOCAL   : {partido['best_home']:.2f}  ({partido['book_home']})
  VISITA  : {partido['best_away']:.2f}  ({partido['book_away']})""")
    if partido.get("best_draw") and partido["best_draw"] > 0:
        print(f"  EMPATE  : {partido['best_draw']:.2f}  ({partido['book_draw']})")
    if stakes:
        print(f"""
  ✅ GANANCIA GARANTIZADA: +{stakes['profit_pct']:.2f}% = ${stakes['ganancia_garantizada']:.2f}
  Con ${monto_total} total:
    → ${stakes['stake_home']:.2f} en LOCAL
    → ${stakes['stake_away']:.2f} en VISITANTE""")
        if stakes["stake_draw"]:
            print(f"    → ${stakes['stake_draw']:.2f} en EMPATE")
    else:
        suma = (1/partido['best_home']) + (1/partido['best_away'])
        print(f"\n  ⚠️  Sin arbitraje puro (overround {(suma-1)*100:.1f}%) — verificá cuotas en vivo")

    ok = input("\n▶ ¿Abrir DOS navegadores y proceder? (s/n): ").strip().lower()
    if ok != "s":
        print("Cancelado."); return

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            args=["--start-maximized","--disable-blink-features=AutomationControlled",
                  "--no-sandbox","--disable-infobars","--disable-notifications"]
        )
        ctx1 = await browser.new_context(viewport={"width":1200,"height":850}, user_agent=USER_AGENT, locale="es-AR")
        ctx2 = await browser.new_context(viewport={"width":1200,"height":850}, user_agent=USER_AGENT, locale="es-AR")
        pg1 = await ctx1.new_page()
        pg2 = await ctx2.new_page()
        if STEALTH_OK:
            await stealth_async(pg1)
            await stealth_async(pg2)

        c1 = creds.get(casa1_key, {})
        c2 = creds.get(casa2_key, {})
        if c1.get("user") and c1.get("password") and c2.get("user") and c2.get("password"):
            await asyncio.gather(
                LOGIN_FN[casa1_key](pg1, c1["user"], c1["password"]),
                LOGIN_FN[casa2_key](pg2, c2["user"], c2["password"])
            )
        else:
            if c1.get("user") and c1.get("password"):
                await LOGIN_FN[casa1_key](pg1, c1["user"], c1["password"])
            else:
                await pg1.goto(CASAS[casa1_key]["url"], wait_until="domcontentloaded")
            if c2.get("user") and c2.get("password"):
                await LOGIN_FN[casa2_key](pg2, c2["user"], c2["password"])
            else:
                await pg2.goto(CASAS[casa2_key]["url"], wait_until="domcontentloaded")

        await asyncio.gather(
            buscar_partido(pg1, partido["home"], partido["away"], casa1_key),
            buscar_partido(pg2, partido["home"], partido["away"], casa2_key)
        )

        await asyncio.gather(
            pg1.screenshot(path=str(SCREENSHOTS_DIR/f"{ts}_partido_{casa1['name']}.png")),
            pg2.screenshot(path=str(SCREENSHOTS_DIR/f"{ts}_partido_{casa2['name']}.png"))
        )

        print(f"""
╔══════════════════════════════════════════════════════════╗
║  DOS NAVEGADORES ABIERTOS                                ║""")
        if stakes:
            print(f"║  {casa1['name']}: apostá ${stakes['stake_home']:.2f} en LOCAL ({partido['home']})")
            print(f"║  {casa2['name']}: apostá ${stakes['stake_away']:.2f} en VISITANTE ({partido['away']})")
            if stakes["stake_draw"]:
                print(f"║  Empate: apostá ${stakes['stake_draw']:.2f} en cualquier casa")
            print(f"║  GANANCIA GARANTIZADA: ${stakes['ganancia_garantizada']:.2f} (+{stakes['profit_pct']:.2f}%)")
        else:
            print("║  Verificá las cuotas EN VIVO y apostá manualmente")
        print(f"╚══════════════════════════════════════════════════════════╝")

        input("\n👉 Presioná ENTER cuando hayas apostado en AMBAS casas...")
        await browser.close()
        print("✅ Listo.")

def abrir_arbitraje_sync(casa1_key, casa2_key, partido, creds={}, monto=100):
    asyncio.run(arbitraje_completo(casa1_key, casa2_key, partido, creds, monto))
