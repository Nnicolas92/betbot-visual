# BetBot Visual v3.0 - Scanner de Surebets

## Que hace
Escanea Betwarrior y Bookmaker.eu cada 30 segundos buscando
**surebets** — apuestas donde ganas si o si sin importar el resultado.

---

## Instalacion rapida

### Primera vez (no tenes Python)
1. Descarga el repo como ZIP y extraelo
2. Corre `INSTALAR_PYTHON_Y_BOT.bat`
3. Copia `.env.example` a `.env` y completalo
4. Corre `SCANNER.bat`

### Ya tenes Python
```
pip install playwright python-dotenv opencv-python
python -m playwright install chromium
copy .env.example .env
```
Edita `.env`, luego corre `SCANNER.bat`

---

## Configuracion (.env)

```
ODDS_API_KEY=   <- API gratis en the-odds-api.com (500 req/mes)
BANKROLL=10000  <- Capital base para calcular stakes
MIN_MARGEN=0.5  <- % minimo para alertar (0.5 = 0.5%)
SCAN_INTERVAL=30 <- Segundos entre escaneos
```

---

## API Key gratis (RECOMENDADO)

1. Ir a **https://the-odds-api.com**
2. Registrarse (email + pass, sin tarjeta)
3. Copiar la API key
4. Pegarla en `.env` como `ODDS_API_KEY=tu_key`

Sin API key el scanner igual funciona pero solo scrapea Betwarrior.

---

## Matematica del surebet

```
Suma = 1/cuota1 + 1/cuota2
Si Suma < 1.0  ->  SUREBET GARANTIZADO
Margen = (1 - Suma) x 100%

Ejemplo:
  Betwarrior: River   x2.20  ->  1/2.20 = 0.454
  Bookmaker:  No River x2.10  ->  1/2.10 = 0.476
  Suma = 0.930  <- menor a 1 = SUREBET
  Margen = +7%
  Con $10.000 invertidos = $700 garantizados
```

---

## Archivos

| Archivo | Descripcion |
|---|---|
| `SCANNER.bat` | Arranca el scanner |
| `arb_scanner.py` | Motor del scanner |
| `CALCULAR_ARB.bat` | Calculadora manual |
| `GRABAR_BETWARRIOR.bat` | Graba clicks en Betwarrior |
| `INSTALAR_PYTHON_Y_BOT.bat` | Instalador completo |
| `.env` | Tus credenciales y config |
