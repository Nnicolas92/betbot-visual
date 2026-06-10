import asyncio
import os
from datetime import datetime
from pathlib import Path

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

SCREENSHOTS_DIR = Path("screenshots")
SCREENSHOTS_DIR.mkdir(exist_ok=True)

CASAS = {
    "1": {"name": "Bet365",        "url": "https://www.bet365.com",          "search": "https://www.bet365.com/#/AC/B1/C1/D1002/"},
    "2": {"name": "Bookmaker.eu",  "url": "https://be.bookmaker.eu/es/deportes/", "search": "https://be.bookmaker.eu/es/deportes/futbol/"},
    "3": {"name": "1xBet",         "url": "https://argen.1xbet.com/es/line",  "search": "https://argen.1xbet.com/es/line/Football"},
}

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/127.0.0.0 Safari/537.36"
)

async def crear_pagina(context, url):
    page = await context.new_page()
    if STEALTH_OK:
        await stealth_async(page)
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
    except Exception as e:
        print(f"  ⚠️  Timeout: {e}")
    await page.wait_for_timeout(2000)
    return page

async def cerrar_popups(page):
    selectores = [
        "text=Continuar de todos modos",
        "text=Continue anyway",
        "[aria-label='Close']",
        "button.close",
        ".modal-close",
        ".popup-close",
    ]
    for sel in selectores:
        try:
            btn = page.locator(sel).first
            if await btn.is_visible(timeout=1500):
                await btn.click()
                await page.wait_for_timeout(600)
                print(f"  ✅ Popup cerrado")
                break
        except:
            pass

async def abrir_arbitraje(casa1_key, casa2_key, partido):
    if not PLAYWRIGHT_OK:
        print("❌ Playwright no instalado.")
        return
    if not STEALTH_OK:
        print("⚠️  Stealth no instalado. Instalar con: py -m pip install playwright-stealth")

    casa1 = CASAS.get(casa1_key, CASAS["2"])
    casa2 = CASAS.get(casa2_key, CASAS["3"])
    ts = datetime.now().strftime("%H%M%S")

    print(f"\n🎯 MODO ARBITRAJE: {casa1['name']} vs {casa2['name']}")
    print(f"   {partido['home']} vs {partido['away']}")
    print(f"   LOCAL: {partido['best_home']:.2f} | VISITANTE: {partido['best_away']:.2f}")
    if partido.get('best_draw') and partido['best_draw'] > 0:
        print(f"   EMPATE: {partido['best_draw']:.2f}")

    h = partido['best_home']; a = partido['best_away']; d = partido.get('best_draw', 0)
    suma = (1/h) + (1/a) + (1/d if d else 0)
    if suma < 1.0:
        profit = ((1 - suma) / suma) * 100
        stake = 1000
        print(f"\n  🟢 ARBITRAJE DETECTADO: +{profit:.2f}% garantizado")
        print(f"     Con ${stake} total:")
        print(f"     → ${round(stake*(1/h)/suma,2)} en LOCAL @ {h:.2f}")
        print(f"     → ${round(stake*(1/a)/suma,2)} en VISITANTE @ {a:.2f}")
        if d:
            print(f"     → ${round(stake*(1/d)/suma,2)} en EMPATE @ {d:.2f}")
    else:
        print(f"\n  🔴 Sin arbitraje puro en estas cuotas (las cuotas en vivo pueden diferir)")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            args=["--start-maximized","--disable-blink-features=AutomationControlled","--no-sandbox","--disable-infobars"]
        )
        ctx1 = await browser.new_context(viewport={"width":1200,"height":850}, user_agent=USER_AGENT, locale="es-AR", timezone_id="America/Argentina/Cordoba")
        ctx2 = await browser.new_context(viewport={"width":1200,"height":850}, user_agent=USER_AGENT, locale="es-AR", timezone_id="America/Argentina/Cordoba")

        print(f"\n🌐 Abriendo {casa1['name']} y {casa2['name']} en paralelo...")
        page1, page2 = await asyncio.gather(
            crear_pagina(ctx1, casa1["search"]),
            crear_pagina(ctx2, casa2["search"])
        )
        await asyncio.gather(cerrar_popups(page1), cerrar_popups(page2))

        scr1 = SCREENSHOTS_DIR / f"{ts}_1_{casa1['name'].replace('.','_')}.png"
        scr2 = SCREENSHOTS_DIR / f"{ts}_2_{casa2['name'].replace('.','_')}.png"
        await asyncio.gather(page1.screenshot(path=str(scr1)), page2.screenshot(path=str(scr2)))
        print(f"📸 {scr1}\n📸 {scr2}")

        print("\n┌─────────────────────────────────────────────┐")
        print("│  DOS NAVEGADORES ABIERTOS                   │")
        print("│  1. Buscá el partido en cada ventana        │")
        print("│  2. Verificá las cuotas en vivo             │")
        print("│  3. Apostá el monto calculado en cada casa  │")
        print("└─────────────────────────────────────────────┘")

        input("\n👉 Presioná ENTER cuando termines...")
        await asyncio.gather(page1.screenshot(path=str(SCREENSHOTS_DIR/f"{ts}_final1.png")), page2.screenshot(path=str(SCREENSHOTS_DIR/f"{ts}_final2.png")))
        await browser.close()
        print("✅ Cerrado. Screenshots en /screenshots/")

def abrir_casa(casa_key, partido):
    asyncio.run(abrir_arbitraje("2", casa_key, partido))

def abrir_arbitraje_sync(casa1_key, casa2_key, partido):
    asyncio.run(abrir_arbitraje(casa1_key, casa2_key, partido))
