#!/usr/bin/env python3
"""
trainer.py  v2.0
Graba tus clicks en cualquier casa y el bot los replica.
Uso: python trainer.py
"""
import asyncio, json, time
from pathlib import Path
from datetime import datetime

try:
    from playwright.async_api import async_playwright
    PW_OK=True
except ImportError:
    PW_OK=False

try:
    import cv2
    CV2_OK=True
except ImportError:
    CV2_OK=False

SESIONES_DIR=Path("sesiones")
SESIONES_DIR.mkdir(exist_ok=True)
Path("screenshots").mkdir(exist_ok=True)

UA=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36")

async def grabar(url, nombre):
    if not PW_OK: print("Instala playwright: pip install playwright && python -m playwright install chromium"); return
    sd=SESIONES_DIR/nombre; sd.mkdir(exist_ok=True)
    clicks=[]; step=[0]
    async with async_playwright() as p:
        browser=await p.chromium.launch(headless=False,
            args=["--start-maximized","--disable-blink-features=AutomationControlled"])
        ctx=await browser.new_context(viewport={"width":1366,"height":768},user_agent=UA,locale="es-AR")
        page=await ctx.new_page()
        async def on_click(x,y):
            step[0]+=1
            sname=f"step_{step[0]:03d}.png"
            await page.screenshot(path=str(sd/sname))
            sel=await page.evaluate(f"""() => {{
                const e=document.elementFromPoint({x},{y});
                if(!e) return null;
                if(e.id) return '#'+e.id;
                return e.tagName.toLowerCase()+(e.className?' .'+e.className.trim().split(' ')[0]:'');
            }}""")
            clicks.append({"step":step[0],"x":x,"y":y,"screenshot":sname,"url":page.url,"selector":sel})
            print(f"  Click #{step[0]} ({x:.0f},{y:.0f})  {sel}")
        page.on("framenavigated",lambda f: print(f"  Nav: {f.url[:60]}"))
        await page.goto(url,wait_until="domcontentloaded")
        await page.add_init_script("""
            window.__clicks=[];
            document.addEventListener('click',function(e){
                window.__clicks.push({x:e.clientX,y:e.clientY});
            },true);
        """)
        print(f"\nGRABANDO: {nombre}\nNavega y apuesta normalmente. ENTER para terminar.\n")
        async def poll():
            last=0
            while True:
                await asyncio.sleep(0.4)
                try:
                    nc=await page.evaluate("window.__clicks.slice()")
                    for c in nc[last:]: await on_click(c["x"],c["y"])
                    last=len(nc)
                except: pass
        t=asyncio.create_task(poll())
        await asyncio.get_event_loop().run_in_executor(None,input,"\nENTER cuando termines...")
        t.cancel()
        await page.screenshot(path=str(sd/"final.png"))
        data={"nombre":nombre,"url_inicio":url,"fecha":datetime.now().isoformat(),
              "total_clicks":len(clicks),"clicks":clicks}
        (sd/"sesion.json").write_text(json.dumps(data,indent=2,ensure_ascii=False))
        print(f"\nGrabado: sesiones/{nombre}/sesion.json  ({len(clicks)} clicks)")
        await browser.close()

async def replay(sesion_path):
    if not PW_OK: return
    sf=Path(sesion_path)
    data=json.loads(sf.read_text(encoding="utf-8"))
    sd=sf.parent
    print(f"\nREPLAY: {data['nombre']}  ({data['total_clicks']} clicks)")
    async with async_playwright() as p:
        browser=await p.chromium.launch(headless=False,
            args=["--start-maximized","--disable-blink-features=AutomationControlled"])
        ctx=await browser.new_context(viewport={"width":1366,"height":768},user_agent=UA,locale="es-AR")
        page=await ctx.new_page()
        await page.goto(data["url_inicio"],wait_until="domcontentloaded")
        await page.wait_for_timeout(2000)
        for ck in data["clicks"]:
            x,y=ck["x"],ck["y"]; sel=ck.get("selector"); ref=sd/ck["screenshot"]
            print(f"  Step {ck['step']}: ({x:.0f},{y:.0f})",end="")
            done=False
            if sel and isinstance(sel,str) and sel.startswith("#"):
                try:
                    el=page.locator(sel).first
                    if await el.is_visible(timeout=2000): await el.click(); done=True; print(f" -> CSS {sel}")
                except: pass
            if not done and CV2_OK and ref.exists():
                try:
                    cp=f"/tmp/c{ck['step']}.png"
                    await page.screenshot(path=cp)
                    ci=cv2.imread(cp); ri=cv2.imread(str(ref))
                    if ci is not None and ri is not None:
                        rx,ry=max(0,int(x)-60),max(0,int(y)-60)
                        rw,rh=min(120,ri.shape[1]-rx),min(120,ri.shape[0]-ry)
                        tmpl=ri[ry:ry+rh,rx:rx+rw]
                        if tmpl.size>0:
                            res=cv2.matchTemplate(ci,tmpl,cv2.TM_CCOEFF_NORMED)
                            _,mv,_,ml=cv2.minMaxLoc(res)
                            if mv>0.7:
                                nx,ny=ml[0]+rw//2,ml[1]+rh//2
                                await page.mouse.click(nx,ny); done=True
                                print(f" -> vision IA {mv:.0%}")
                except: pass
            if not done: await page.mouse.click(x,y); print(" -> coords")
            await page.wait_for_timeout(800)
        await page.screenshot(path=f"screenshots/replay_{datetime.now().strftime('%H%M%S')}.png")
        print(f"\nReplay completo ({len(data['clicks'])} clicks)")
        input("\nENTER para cerrar...")
        await browser.close()

def listar():
    ss=list(SESIONES_DIR.glob("*/sesion.json"))
    if not ss: print("  (sin sesiones)"); return []
    for i,s in enumerate(ss,1):
        d=json.loads(s.read_text(encoding="utf-8"))
        print(f"  [{i}] {d['nombre']:<35} {d['total_clicks']} clicks  {d['fecha'][:10]}")
    return ss

def main():
    print("""
============================================================
  BETBOT TRAINER v2.0
  [1] GRABAR nueva sesion
  [2] REPLAY de sesion grabada
  [0] Salir
============================================================
""")
    op=input("Opcion: ").strip()
    if op=="1":
        urls={"1":"https://be.bookmaker.eu/es/pagina-ingreso/",
              "2":"https://mza.betwarrior.bet.ar/es-ar/sports/home",
              "3":"https://www.betsson.com/es/login"}
        print("  [1] Bookmaker  [2] Betwarrior  [3] Betsson  [4] Otra")
        c=input("Casa: ").strip()
        url=urls.get(c) or input("URL: ").strip()
        nombre=input("Nombre (ej: bookmaker_futbol): ").strip() or f"sesion_{int(time.time())}"
        asyncio.run(grabar(url,nombre))
    elif op=="2":
        ss=listar()
        if not ss: return
        idx=int(input("Numero: ").strip())-1
        if 0<=idx<len(ss): asyncio.run(replay(str(ss[idx])))

if __name__=="__main__":
    main()
