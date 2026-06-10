# BetBot Visual v2.0

## Casas soportadas
- **Betwarrior** (Argentina) — grabador dedicado + captura API automatica
- **Bookmaker.eu** — login auto + scraping
- **Cualquier otra** — modo trainer (grabar & replay)

## Orden de uso

```
1. INSTALAR.bat           <- Solo la primera vez
2. GRABAR_BETWARRIOR.bat  <- Navega en Betwarrior, bot graba todo
3. CALCULAR_ARB.bat       <- Ingresa cuotas, calcula si hay arbitraje
4. ENTRENAR.bat           <- El bot replica tus clicks automaticamente
```

## Archivos

```
GRABAR_BETWARRIOR.py   <- Grabador Betwarrior + captura API JSON
arb_calculator.py      <- Matematica de arbitraje 2-way y 3-way
trainer.py             <- Grabar/replay clicks en cualquier casa
main.py                <- Bot principal
scanner.py             <- Scanner de cuotas
vision.py              <- Reconocimiento visual OpenCV
config.py              <- Configuracion y credenciales
```

## Formula de arbitraje

```
Implicita = 1/odd1 + 1/odd2 (+ 1/oddX)
Si suma < 1.0  ->  HAY ARBITRAJE
Margen (%) = (1 - suma) * 100
Stake1 = Bankroll * (1/odd1) / suma
Stake2 = Bankroll * (1/odd2) / suma
Ganancia = Stake1 * odd1 - Bankroll
```

## Requisitos
- Python 3.8+
- Windows 10/11
- Cuenta en Betwarrior y/o Bookmaker.eu
