import asyncio
import os
from datetime import datetime
from pathlib import Path

try:
    from playwright.async_api import async_playwright
    PLAYWRIGHT_OK = True
except ImportError:
    PLAYWRIGHT_OK = False

SCREENSHOTS_DIR = Path("screenshots")
SCREENSHOTS_DIR.mkdir(exist_ok=True)

CASAS = {
    "1": {"name": "Bet365",        "url": "https://www.bet365.com"},
    "2": {"name": "Bookmaker.eu",  "url": "https://be.bookmaker.eu"},
    "3": {"name": "1xBet",         "url": "https://argen.1xbet.com/es/line"},
}

async def abrir_casa_y_buscar(casa_key, partido):
    if not PLAYWRIGHT_OK:
        print("❌ Playwright no instalado. Corré: py -m playwright install chromium")
        return False

    casa = CASAS.get(casa_key, CASAS["1"])
    ts = datetime.now().strftime("%H%M%S")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            args=["--start-maximized", "--disable-blink-features=AutomationControlled"]
        )
        context = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        print(f"\n🌐 Abriendo {casa['name']}...")
        await page.goto(casa["url"], wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(2500)

        scr1 = SCREENSHOTS_DIR / f"{ts}_01_home.png"
        await page.screenshot(path=str(scr1))
        print(f"📸 Screenshot: {scr1}")

        print(f"\n📋 Partido: {partido['home']} vs {partido['away']}")
        print(f"   Mejor cuota LOCAL:     {partido['best_home']:.2f} ({partido['book_home']})")
        print(f"   Mejor cuota VISITANTE: {partido['best_away']:.2f} ({partido['book_away']})")
        if partido.get("best_draw") and partido["best_draw"] > 0:
            print(f"   Mejor cuota EMPATE:    {partido['best_draw']:.2f} ({partido['book_draw']})")

        await page.wait_for_timeout(1500)
        scr2 = SCREENSHOTS_DIR / f"{ts}_02_listo.png"
        await page.screenshot(path=str(scr2))
        print(f"📸 Screenshot: {scr2}")

        print(f"\n⚠️  MODO DEMO — el bot no apuesta hasta que cargues fondos.")
        input("\n👉 Navegador abierto. Presioná ENTER para cerrar...")

        scr3 = SCREENSHOTS_DIR / f"{ts}_03_final.png"
        await page.screenshot(path=str(scr3))
        print(f"📸 Screenshot final: {scr3}")
        await browser.close()
        print("✅ Cerrado.")
        return True

def abrir_casa(casa_key, partido):
    asyncio.run(abrir_casa_y_buscar(casa_key, partido))
