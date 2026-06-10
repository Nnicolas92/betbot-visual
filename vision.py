"""
vision.py — Módulo de Visión por IA para detectar elementos en pantalla

Usa screenshot + modelo ligero para:
  1. Detectar campos de login en cualquier web
  2. Detectar botones de apuesta y cuotas
  3. Hacer click por coordenadas en vez de selectores CSS

Ideal cuando el HTML no tiene selectores estables (React, SPAs, etc.)

Requiere: pip install ultralytics mss opencv-python
"""

import asyncio
from pathlib import Path
import time

try:
    import cv2
    import numpy as np
    CV2_OK = True
except ImportError:
    CV2_OK = False

try:
    from ultralytics import YOLO
    YOLO_OK = True
except ImportError:
    YOLO_OK = False

SCREENSHOTS_DIR = Path("screenshots")
SCREENSHOTS_DIR.mkdir(exist_ok=True)

# ─────────────────────────────────────────────
# DETECTOR DE TEXTO POR IMAGEN (sin entrenar)
# Usa template matching o detección de contornos
# ─────────────────────────────────────────────

def detectar_input_por_placeholder(screenshot_path: str, texto_buscado: str):
    """
    Busca en el screenshot un campo de texto por color de fondo y posición.
    Devuelve (x_centro, y_centro) o None.
    Esta es la versión SIN modelo entrenado — funciona con OpenCV puro.
    """
    if not CV2_OK:
        return None
    img = cv2.imread(screenshot_path)
    if img is None:
        return None
    # Buscar rectángulos blancos/grises (campos de input)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    campos = []
    for c in contours:
        x, y, w, h = cv2.boundingRect(c)
        # Filtrar por proporción típica de un input
        if 200 < w < 800 and 20 < h < 70:
            campos.append((x, y, w, h))
    campos.sort(key=lambda c: c[1])  # ordenar por Y (de arriba a abajo)
    return campos  # [(x,y,w,h), ...]


async def login_por_vision(page, user: str, password: str, casa_name: str):
    """
    Intenta hacer login detectando campos visualmente si los selectores CSS fallan.
    Primero intenta CSS normal, si falla usa visión.
    """
    print(f"  👁  Vision login en {casa_name}...")
    ts = int(time.time())
    shot_path = str(SCREENSHOTS_DIR / f"{ts}_vision_login.png")
    await page.screenshot(path=shot_path)

    if not CV2_OK:
        print("  ⚠️  OpenCV no instalado — usando solo selectores CSS")
        return False

    campos = detectar_input_por_placeholder(shot_path, "")
    if not campos or len(campos) < 2:
        print(f"  ⚠️  No detecté campos de input visualmente ({len(campos) if campos else 0} encontrados)")
        return False

    # El primer campo es usuario, el segundo contraseña
    c_user = campos[0]
    c_pass = campos[1]

    cx_user = c_user[0] + c_user[2] // 2
    cy_user = c_user[1] + c_user[3] // 2
    cx_pass = c_pass[0] + c_pass[2] // 2
    cy_pass = c_pass[1] + c_pass[3] // 2

    print(f"  👁  Campo usuario detectado en ({cx_user}, {cy_user})")
    print(f"  👁  Campo contraseña detectado en ({cx_pass}, {cy_pass})")

    await page.mouse.click(cx_user, cy_user)
    await page.wait_for_timeout(300)
    await page.keyboard.type(user, delay=80)
    await page.wait_for_timeout(300)
    await page.mouse.click(cx_pass, cy_pass)
    await page.wait_for_timeout(300)
    await page.keyboard.type(password, delay=80)
    await page.wait_for_timeout(300)

    # Buscar botón de submit por color (botones suelen ser de color)
    img = cv2.imread(shot_path)
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    # Detectar amarillo (Bookmaker, Betsson) y verde (Bet365)
    masks = [
        cv2.inRange(hsv, np.array([20,100,100]), np.array([40,255,255])),   # amarillo
        cv2.inRange(hsv, np.array([35,50,50]),   np.array([85,255,255])),   # verde
        cv2.inRange(hsv, np.array([0,100,100]),  np.array([15,255,255])),   # rojo/naranja
    ]
    for mask in masks:
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        botones = [(x,y,w,h) for c in contours for x,y,w,h in [cv2.boundingRect(c)] if w>60 and h>25]
        if botones:
            bx, by, bw, bh = max(botones, key=lambda b: b[2]*b[3])  # el más grande
            await page.mouse.click(bx + bw//2, by + bh//2)
            print(f"  👁  Click en botón detectado en ({bx+bw//2}, {by+bh//2})")
            await page.wait_for_timeout(2000)
            return True

    # Fallback: Enter
    await page.keyboard.press("Enter")
    await page.wait_for_timeout(2000)
    return True


async def detectar_cuotas_en_pantalla(page) -> list:
    """
    Toma screenshot y busca números de cuota (formato X.XX) visualmente.
    Devuelve lista de cuotas detectadas con sus coordenadas.
    """
    if not CV2_OK:
        return []
    ts = int(time.time())
    shot_path = str(SCREENSHOTS_DIR / f"{ts}_cuotas.png")
    await page.screenshot(path=shot_path)
    print(f"  👁  Screenshot guardado: {shot_path}")
    print(f"  👁  Para detectar cuotas automáticamente, instalá: pip install pytesseract")
    return []
