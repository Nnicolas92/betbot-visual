# 🎰 BetBot Visual v4

Bot de arbitraje deportivo con login automático en DOS casas simultáneas.

## Casas soportadas
- Bookmaker.eu
- Betsson
- Bet365

## Setup en 3 pasos

### 1. Instalá dependencias
Doble click en `INSTALAR.bat`

### 2. Configurá tus credenciales
Copiá `.env.example` como `.env` y completá:
```
BOOKMAKER_USER=tu_correo@ejemplo.com
BOOKMAKER_PASS=tu_clave

BETSSON_USER=tu_correo@ejemplo.com
BETSSON_PASS=tu_clave
```

### 3. Correlo
Doble click en `CORRER.bat`

---

## Módulo de Visión IA (vision.py)

Si el HTML no tiene selectores estables, el bot usa OpenCV para:
- Detectar campos de login visualmente (por forma y color)
- Detectar botones por color (amarillo, verde, naranja)
- Hacer click por coordenadas de pantalla

Para instalar: `pip install opencv-python ultralytics`

---

## Flujo modo DOS casas
1. Escaneá partidos por deporte
2. Elegí el partido
3. Elegí las 2 casas
4. El bot hace login en AMBAS simultáneamente
5. Busca el partido en AMBAS páginas
6. Calcula las apuestas exactas para arbitraje garantizado
7. Te muestra los montos y esperá que apostés
