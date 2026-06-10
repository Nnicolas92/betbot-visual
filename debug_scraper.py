#!/usr/bin/env python3
"""
debug_scraper.py
Guarda el HTML real de Betwarrior y Bookmaker.eu
para analizar la estructura y arreglar el scraper definitivamente.
Correr UNA sola vez: python debug_scraper.py
"""
import asyncio
from pathlib import Path

try:
    from playwright.async_api import async_playwright
except ImportError:
    print("Instalar: pip install playwright && python -m playwright install chromium")
    exit(1)

UAGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"

async def dump_site(url, nombre):
    print(f"\n{'='*60}")
    print(f"Abriendo {nombre}: {url}")
    print(f"{'='*60}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,   # VISIBLE para ver que carga
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled"]
        )
        ctx  = await browser.new_context(user_agent=UAGENT, locale="es-AR",
                                          viewport={"width":1400,"height":900})
        page = await ctx.new_page()

        try:
            await page.goto(url, wait_until="networkidle", timeout=60000)
        except Exception as e:
            print(f"  goto timeout/error: {e} -- esperando igual...")

        print("  Esperando 10 segundos que cargue JS...")
        await page.wait_for_timeout(10000)

        # Capturar HTML completo
        html = await page.content()
        fname = f"debug_{nombre}.html"
        Path(fname).write_text(html, encoding="utf-8")
        print(f"  HTML guardado en: {fname} ({len(html):,} chars)")

        # Capturar texto visible
        txt = await page.evaluate("() => document.body.innerText")
        fname_txt = f"debug_{nombre}.txt"
        Path(fname_txt).write_text(txt, encoding="utf-8")
        print(f"  Texto visible guardado en: {fname_txt} ({len(txt):,} chars)")

        # Mostrar primeras 50 lineas del texto visible
        lines = [l.strip() for l in txt.split("\n") if l.strip()]
        print(f"\n  Primeras 50 lineas de texto visible:")
        print(f"  {'-'*50}")
        for i, l in enumerate(lines[:50]):
            print(f"  {i+1:3}. {l[:100]}")

        # Buscar numeros que parezcan cuotas
        import re
        cuotas = re.findall(r'\b(\d{1,2}\.\d{2})\b', txt)
        cuotas_v = [float(c) for c in cuotas if 1.10 <= float(c) <= 30.0]
        print(f"\n  Cuotas encontradas en texto: {len(cuotas_v)}")
        if cuotas_v:
            print(f"  Ejemplos: {sorted(set(cuotas_v))[:20]}")

        # Analizar clases CSS con 'odd', 'price', 'coef', 'rate'
        clases = await page.evaluate("""
          () => {
            const found = new Set();
            document.querySelectorAll('*').forEach(el => {
              const c = el.className;
              if (typeof c === 'string') {
                c.split(' ').forEach(cls => {
                  if (cls.match(/odd|price|coef|rate|quota|cuota|market|outcome|selection/i))
                    found.add(cls);
                });
              }
            });
            return [...found].slice(0, 30);
          }
        """)
        print(f"\n  Clases CSS relevantes encontradas:")
        for c in clases:
            print(f"    {c}")

        # Buscar elementos data-* relevantes
        data_attrs = await page.evaluate("""
          () => {
            const found = new Set();
            document.querySelectorAll('[data-odd],[data-price],[data-coef],[data-rate],[data-value]')
              .forEach(el => {
                found.add(JSON.stringify({
                  tag: el.tagName,
                  text: el.innerText.trim().slice(0,30),
                  odd: el.dataset.odd || el.dataset.price || el.dataset.coef || el.dataset.value
                }));
              });
            return [...found].slice(0, 10);
          }
        """)
        if data_attrs:
            print(f"\n  Elementos con data-odd/price/coef:")
            for d in data_attrs:
                print(f"    {d}")

        print(f"\n  Navegador abierto 5 segundos mas para que veas...")
        await page.wait_for_timeout(5000)
        await browser.close()

async def main():
    print("""
========================================================
  DEBUG SCRAPER - Ver estructura real de los sitios
========================================================
  Va a abrir DOS ventanas de Chrome visibles.
  Miralo mientras carga para confirmar que el sitio abre.
  Resultado guardado en debug_bw.html y debug_bk.html
========================================================""")

    # Correr secuencialmente para no confundir
    await dump_site("https://mza.betwarrior.bet.ar/es-ar/sports/home", "bw")
    await dump_site("https://be.bookmaker.eu/sports", "bk")

    print("\n" + "="*60)
    print("DEBUG COMPLETADO")
    print("Manda el contenido de debug_bw.txt y debug_bk.txt")
    print("o los archivos .html si podes")
    print("="*60)

if __name__ == "__main__":
    asyncio.run(main())
