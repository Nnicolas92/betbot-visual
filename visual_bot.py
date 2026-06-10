"""
visual_bot.py v4.1
Login + busqueda de partido + arbitraje en DOS casas
Modo MANUAL para casas sin login implementado
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

# Todas las casas — las que tienen LOGIN_AUTO abren y logean solas
# Las que tienen solo URL abren el navegador y el usuario hace login manualmente
CASAS = {
    "1":  {"name": "Bookmaker.eu",  "url": "https://be.bookmaker.eu",                   "login_auto": True},
    "2":  {"name": "Betsson",        "url": "https://www.betsson.com/es",                 "login_auto": True},
    "3":  {"name": "Bet365",         "url": "https://www.bet365.com",                    "login_auto": False},
    "4":  {"name": "1xBet",          "url": "https://1xbet.com/es",                      "login_auto": False},
    "5":  {"name": "Unibet",         "url": "https://www.unibet.com/betting",            "login_auto": False},
    "6":  {"name": "William Hill",   "url": "https://sports.williamhill.com/betting/es-es","login_auto": False},
    "7":  {"name": "Pinnacle",       "url": "https://www.pinnacle.com/es/",              "login_auto": False},
    "8":  {"name": "DraftKings",     "url": "https://sportsbook.draftkings.com",         "login_auto": False},
    "9":  {"name": "FanDuel",        "url": "https://sportsbook.fanduel.com",            "login_auto": False},
    "10": {"name": "BetOnline",      "url": "https://www.betonline.ag/sportsbook",       "login_auto": False},
    "11": {"name": "SportsBetting",  "url": "https://www.sportsbetting.ag/sportsbook",  "login_auto": False},
    "12": {"name": "MyBookie",       "url": "https://mybookie.ag/sportsbook",           "login_auto": False},
    "13": {"name": "BetUS",          "url": "https://www.betus.com.pa/sportsbook",      "login_auto": False},
    "14": {"name": "Bovada",         "url": "https://www.bovada.lv/sports",             "login_auto": False},
    "15": {"name": "Betway",         "url": "https://sports.betway.com/es",             "login_auto": False},
}

def buscar_casa_por_nombre(nombre: str) -> str:
    """Busca el key de una casa por nombre (para matchear con lo que devuelve la API)"""
    nombre_lower = nombre.lower()
    for k, v in CASAS.items():
        if v["name"].lower() in nombre_lower or nombre_lower in v["name"].lower():
            return k
    return None

# ──────────────────────────────────────────────
# LOGIN AUTOMATICO
# ──────────────────────────────────────────────
async def _try_fill(page, selectors, value, campo):
    for sel in selectors:
        try:
            el = page.locator(sel).first
            if await el.is_visible(timeout=2000):
                await el.fill(value)
                return True
        except:
            pass
    return False

async def login_bookmaker(page, user, password):
    print("  🔐 Login Bookmaker.eu...")
    await page.goto("https://be.bookmaker.eu/es/pagina-ingreso/", wait_until="domcontentloaded", timeout=30000)
    await page.wait_for_timeout(2000)
    try:
        btn = page.locator("text=Continuar de todos modos")
        if await btn.is_visible(timeout=3000):
            await btn.click(); await page.wait_for_timeout(1000)
    except: pass
    await _try_fill(page, ["input[name='username']","input[type='text']"], user, "usuario")
    await _try_fill(page, ["input[name='password']","input[type='password']"], password, "pass")
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
    await _try_fill(page, ["input[name='username']","input[type='email']","input[id*='user']"], user, "usuario")
    await _try_fill(page, ["input[type='password']","input[id*='pass']"], password, "pass")
    try:
        await page.click("button[type='submit'], button:has-text('Iniciar'), button:has-text('Entrar')")
    except:
        await page.keyboard.press("Enter")
    await page.wait_for_timeout(3000)
    print("  ✅ Login Betsson enviado")

LOGIN_AUTO = {"1": login_bookmaker, "2": login_betsson}

async def abrir_casa(page, casa_key, creds):
    """Abre la casa: login automatico si esta implementado, sino abre la URL y espera al usuario"""
    casa = CASAS[casa_key]
    if casa["login_auto"] and casa_key in LOGIN_AUTO:
        cr = creds.get(casa_key, {})
        if cr.get("user") and cr.get("password"):
            await LOGIN_AUTO[casa_key](page, cr["user"], cr["password"])
            return
    # Modo manual: abre el navegador y el usuario hace login
    print(f"  🖱️  {casa['name']}: abriendo... hacé login vos manualmente")
    await page.goto(casa["url"], wait_until="domcontentloaded", timeout=30000)
    await page.wait_for_timeout(2000)

# ──────────────────────────────────────────────
# BUSCAR PARTIDO
# ──────────────────────────────────────────────
URLs_FUTBOL = {
    "1":  "https://be.bookmaker.eu/es/deportes/futbol/",
    "2":  "https://www.betsson.com/es/apuestas-deportivas/futbol",
    "3":  "https://www.bet365.com/#/AS/B1/",
    "4":  "https://1xbet.com/es/line/Football",
    "5":  "https://www.unibet.com/betting/sports/filter/football/all/all/matches",
    "6":  "https://sports.williamhill.com/betting/es-es/football",
    "7":  "https://www.pinnacle.com/es/football/matchups/",
    "14": "https://www.bovada.lv/sports/soccer",
    "15": "https://sports.betway.com/es/sports/evt/soccer",
}

async def buscar_partido(page, home, away, casa_key):
    url = URLs_FUTBOL.get(casa_key, CASAS[casa_key]["url"])
    print(f"  🔍 Buscando {home} vs {away} en {CASAS[casa_key]['name']}...")
    await page.goto(url, wait_until="domcontentloaded", timeout=30000)
    await page.wait_for_timeout(3000)
    for termino in [home, away]:
        try:
            el = page.locator(f"text={termino}").first
            if await el.is_visible(timeout=5000):
                await el.click(); await page.wait_for_timeout(2000)
                print(f"  ✅ Partido encontrado")
                return True
        except: pass
    print(f"  ⚠️  No encontrado automáticamente — buscalo vos en el navegador")
    return False

# ──────────────────────────────────────────────
# CALCULAR ARBITRAJE
# ──────────────────────────────────────────────
def calcular_stakes(partido, monto_total):
    h = partido["best_home"]
    a = partido["best_away"]
    d = partido.get("best_draw") or 0
    suma = (1/h) + (1/a) + (1/d if d else 0)
    if suma >= 1.0:
        return None
    profit_pct = ((1 - suma) / suma) * 100
    s_h = round(monto_total * (1/h) / suma, 2)
    s_a = round(monto_total * (1/a) / suma, 2)
    s_d = round(monto_total * (1/d) / suma, 2) if d else 0
    ganancia = round(monto_total * (1/suma) - monto_total, 2)
    return {"profit_pct": profit_pct, "stake_home": s_h, "stake_away": s_a,
            "stake_draw": s_d, "ganancia_garantizada": ganancia}

# ──────────────────────────────────────────────
# FLUJO PRINCIPAL
# ──────────────────────────────────────────────
async def arbitraje_completo(casa1_key, casa2_key, partido, creds, monto_total):
    if not PLAYWRIGHT_OK:
        print("❌ Playwright no instalado. Corré INSTALAR.bat")
        return

    ts = datetime.now().strftime("%H%M%S")
    casa1 = CASAS[casa1_key]; casa2 = CASAS[casa2_key]
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
    → ${stakes['stake_home']:.2f} en LOCAL    ({casa1['name']})
    → ${stakes['stake_away']:.2f} en VISITANTE ({casa2['name']})""")
        if stakes["stake_draw"]:
            print(f"    → ${stakes['stake_draw']:.2f} en EMPATE")
    else:
        suma = (1/partido['best_home']) + (1/partido['best_away'])
        print(f"\n  ⚠️  Sin arbitraje puro (overround {(suma-1)*100:.1f}%) — verificá cuotas en vivo")

    if not casa1["login_auto"] or not casa2["login_auto"]:
        print(f"""
  ℹ️  MODO MANUAL para casas sin login automático:
      El navegador va a abrir — hacé login vos mismo.
      Después el bot busca el partido automáticamente.""")

    ok = input("\n▶ ¿Abrir DOS navegadores y proceder? (s/n): ").strip().lower()
    if ok != "s":
        print("Cancelado."); return

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            args=["--start-maximized","--disable-blink-features=AutomationControlled",
                  "--no-sandbox","--disable-infobars"]
        )
        ctx1 = await browser.new_context(viewport={"width":1200,"height":850}, user_agent=USER_AGENT, locale="es-AR")
        ctx2 = await browser.new_context(viewport={"width":1200,"height":850}, user_agent=USER_AGENT, locale="es-AR")
        pg1 = await ctx1.new_page()
        pg2 = await ctx2.new_page()
        if STEALTH_OK:
            await stealth_async(pg1); await stealth_async(pg2)

        # Abrir ambas casas (auto o manual)
        await asyncio.gather(
            abrir_casa(pg1, casa1_key, creds),
            abrir_casa(pg2, casa2_key, creds)
        )

        # Si alguna es manual, esperar que el usuario haga login
        if not casa1["login_auto"] or not casa2["login_auto"]:
            input("\n👉 Hacé login en las ventanas que lo piden y presioná ENTER para continuar...")

        # Buscar partido en ambas
        await asyncio.gather(
            buscar_partido(pg1, partido["home"], partido["away"], casa1_key),
            buscar_partido(pg2, partido["home"], partido["away"], casa2_key)
        )

        await asyncio.gather(
            pg1.screenshot(path=str(SCREENSHOTS_DIR/f"{ts}_{casa1['name']}.png")),
            pg2.screenshot(path=str(SCREENSHOTS_DIR/f"{ts}_{casa2['name']}.png"))
        )

        print(f"""
╔══════════════════════════════════════════════════════════╗
║  DOS NAVEGADORES ABIERTOS — APOSTÁ AHORA                ║""")
        if stakes:
            print(f"║  {casa1['name']}: ${stakes['stake_home']:.2f} en LOCAL ({partido['home']})")
            print(f"║  {casa2['name']}: ${stakes['stake_away']:.2f} en VISITANTE ({partido['away']})")
            if stakes["stake_draw"]:
                print(f"║  Empate: ${stakes['stake_draw']:.2f}")
            print(f"║  GANANCIA GARANTIZADA: ${stakes['ganancia_garantizada']:.2f} (+{stakes['profit_pct']:.2f}%)")
        else:
            print("║  Verificá las cuotas en vivo y apostá")
        print("╚══════════════════════════════════════════════════════════╝")

        input("\n👉 Presioná ENTER cuando hayas apostado en AMBAS casas...")
        await browser.close()
        print("✅ Listo.")

def abrir_arbitraje_sync(casa1_key, casa2_key, partido, creds={}, monto=100):
    asyncio.run(arbitraje_completo(casa1_key, casa2_key, partido, creds, monto))
