#!/usr/bin/env python3
"""
GRABAR_BETWARRIOR.py  v2.0
Abre Betwarrior, graba TUS clicks Y captura la API interna automaticamente.
Uso: python GRABAR_BETWARRIOR.py
"""
import asyncio, json, re
from pathlib import Path
from datetime import datetime

try:
    from playwright.async_api import async_playwright
except ImportError:
    print("ERROR: Falta playwright.")
    print("Corra: pip install playwright && python -m playwright install chromium")
    input("ENTER para salir..."); exit(1)

URL = "https://mza.betwarrior.bet.ar/es-ar/sports/home"
SESION_DIR = Path("sesiones/betwarrior_1")
SESION_DIR.mkdir(parents=True, exist_ok=True)
Path("screenshots").mkdir(exist_ok=True)

API_CALLS, CLICK_LOG, step = [], [], [0]

def es_odds_url(url):
    kw = ["odds","sport","event","market","fixture","match","bet","price","offer","live","coupon"]
    u = url.lower()
    return any(k in u for k in kw) and (
        u.endswith(".json") or "api" in u or "v1/" in u or "v2/" in u or "graphql" in u
    )

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False,
            args=["--start-maximized","--disable-blink-features=AutomationControlled","--no-sandbox"])
        ctx = await browser.new_context(
            viewport={"width":1366,"height":768},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
            locale="es-AR")
        page = await ctx.new_page()

        async def on_response(response):
            url = response.url
            if not es_odds_url(url): return
            try:
                ct = response.headers.get("content-type","")
                if "json" not in ct and "javascript" not in ct: return
                body = await response.text()
                if len(body) < 50: return
                API_CALLS.append({"url":url,"status":response.status,
                    "time":datetime.now().isoformat(),"size":len(body),"body":body[:8000]})
                print(f"  API ({len(body):,} bytes): {url[:75]}")
            except: pass

        page.on("response", on_response)
        await page.add_init_script("""
            window.__myClicks=[];
            document.addEventListener('click',function(e){
                window.__myClicks.push({x:e.clientX,y:e.clientY,t:Date.now()});
            },true);
        """)

        async def poll_clicks():
            last=0
            while True:
                await asyncio.sleep(0.4)
                try:
                    all_c = await page.evaluate("window.__myClicks.slice()")
                    for c in all_c[last:]:
                        step[0]+=1
                        sname=f"step_{step[0]:03d}.png"
                        await page.screenshot(path=str(SESION_DIR/sname))
                        sel = await page.evaluate(f"""() => {{
                            const e=document.elementFromPoint({c['x']},{c['y']});
                            if(!e) return null;
                            if(e.id) return '#'+e.id;
                            return e.tagName.toLowerCase()+(e.className?' .'+e.className.trim().split(' ')[0]:'');
                        }}""")
                        CLICK_LOG.append({"step":step[0],"x":c["x"],"y":c["y"],
                            "screenshot":sname,"url":page.url,"selector":sel})
                        print(f"  Click #{step[0]} ({c['x']:.0f},{c['y']:.0f})  {sel}")
                    last=len(all_c)
                except: pass

        print("""
============================================================
  MODO GRABAR - Betwarrior + captura API automatica
============================================================
  1. Navega y clickea partidos en Betwarrior.
  2. El bot graba CLICKS + llamadas API en segundo plano.
  3. Volvete aca y presiona ENTER cuando termines.
============================================================
""")
        await page.goto(URL, wait_until="domcontentloaded", timeout=30000)
        poll_task = asyncio.create_task(poll_clicks())
        await asyncio.get_event_loop().run_in_executor(None, input, "\nENTER cuando termines...\n")
        poll_task.cancel()
        await page.screenshot(path=str(SESION_DIR/"final.png"))

        sesion = {"nombre":"betwarrior_1","url_inicio":URL,
            "fecha":datetime.now().isoformat(),
            "total_clicks":len(CLICK_LOG),"total_api":len(API_CALLS),
            "clicks":CLICK_LOG,"api_calls":API_CALLS}
        (SESION_DIR/"sesion.json").write_text(json.dumps(sesion,indent=2,ensure_ascii=False))

        odds_enc=[]
        num_re=re.compile(r'\b([1-9]\d*\.?\d*)\b')
        for call in API_CALLS:
            try:
                raw=json.dumps(json.loads(call["body"]))
                nums=[float(n) for n in num_re.findall(raw) if 1.01<=float(n)<=50.0]
                if nums: odds_enc.append({"url":call["url"],"odds":nums[:20]})
            except: pass

        if odds_enc:
            (SESION_DIR/"odds_raw.json").write_text(json.dumps(odds_enc,indent=2,ensure_ascii=False))

        print(f"""
============================================================
  GRABACION COMPLETADA
  Clicks  : {len(CLICK_LOG)}
  API JSON: {len(API_CALLS)}
  Odds    : {len(odds_enc)}
  Guardado: sesiones/betwarrior_1/
============================================================
""")
        if odds_enc:
            print("Muestra de cuotas capturadas:")
            for o in odds_enc[:3]:
                print(f"  URL : {o['url'][:65]}")
                print(f"  Odds: {o['odds'][:8]}")
        else:
            print("No se capturo JSON de cuotas. Clicks grabados igual para REPLAY.")

        await browser.close()
        print("\nSiguiente paso: python arb_calculator.py")

if __name__=="__main__":
    asyncio.run(main())
