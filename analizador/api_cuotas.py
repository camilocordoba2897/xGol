#Capa de cuotas de casas de apuestas.
#
#Consume the-odds-api.com. El plan gratuito da 500 creditos al mes:
#cada peticion de una liga con un mercado gasta 1 credito. Por eso la
#respuesta se cachea 10 minutos por liga y NO por partido: se pide la
#liga completa una vez y de ahi se saca el partido que haga falta.
#
#Si no hay clave configurada la funcion devuelve (None, "sin_clave") y
#el frontend simplemente no pinta la tarjeta. Nada mas se rompe.
#
#Configuracion en .env:
#   ODDS_API_KEY=tu_clave
#y en settings.py:
#   ODDS_API_KEY = os.getenv("ODDS_API_KEY", "")
import unicodedata

import requests
from django.conf import settings
from django.core.cache import cache

BASE_ODDS = "https://api.the-odds-api.com/v4"

ERROR_SIN_CLAVE = "sin_clave"
ERROR_CUOTA = "cuota"     #429: se agoto el limite del plan
ERROR_RED = "red"

#Codigo de liga del analizador -> clave de deporte en the-odds-api
LIGAS_ODDS = {
    "PL":  "soccer_epl",
    "PD":  "soccer_spain_la_liga",
    "SA":  "soccer_italy_serie_a",
    "BL1": "soccer_germany_bundesliga",
    "FL1": "soccer_france_ligue_one",
    "DED": "soccer_netherlands_eredivisie",
    "PPL": "soccer_portugal_primeira_liga",
    "BSA": "soccer_brazil_campeonato",
    "CL":  "soccer_uefa_champs_league",
}

#Palabras que sobran al comparar nombres de equipo entre los dos proveedores
#(football-data dice "Fluminense FC" y the-odds-api "Fluminense")
RUIDO = {
    "fc", "cf", "sc", "ac", "afc", "cd", "ec", "se", "ss", "as", "rc", "ca",
    "club", "clube", "de", "do", "da", "the", "futebol", "football", "calcio",
}


#Equipos cuyo nombre cambia de idioma entre proveedores: no basta con
#quitar tildes. Se mapea la variante al nombre que usa the-odds-api.
#Comparar solo por la primera palabra seria peligroso ("Real Madrid"
#coincidiria con "Real Sociedad"), por eso la tabla es explicita.
ALIAS = {
    "bayern munchen": "bayern munich",
    "borussia monchengladbach": "borussia moenchengladbach",
    "1 fc koln": "fc cologne",
    "koln": "fc cologne",
    "athletic bilbao": "athletic club",
    "sporting cp": "sporting lisbon",
    "atletico madrid": "atletico madrid",
}


def _normalizar(nombre):
    #Minusculas, sin tildes y sin las palabras de relleno tipo "FC"
    texto = unicodedata.normalize("NFKD", str(nombre or ""))
    texto = "".join(c for c in texto if not unicodedata.combining(c)).lower()
    limpio = "".join(c if c.isalnum() or c.isspace() else " " for c in texto)
    palabras = [p for p in limpio.split() if p and p not in RUIDO]
    base = " ".join(palabras)
    return ALIAS.get(base, base)


def _mismo_equipo(a, b):
    #Coincidencia tolerante: exacta, o uno contenido en el otro.
    #Los dos proveedores recortan distinto ("Atletico Madrid" / "Atletico de Madrid")
    na, nb = _normalizar(a), _normalizar(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    return na in nb or nb in na


def _pedir_odds(deporte):
    #Devuelve (lista_partidos, error). error es None si todo salio bien.
    clave = getattr(settings, "ODDS_API_KEY", "")
    if not clave:
        return [], ERROR_SIN_CLAVE
    try:
        r = requests.get(
            f"{BASE_ODDS}/sports/{deporte}/odds",
            params={
                "apiKey": clave,
                "regions": "eu",          #casas europeas: las que mas mercados cubren
                "markets": "h2h",         #1X2. Cada mercado extra gasta otro credito
                "oddsFormat": "decimal",
            },
            timeout=15,
        )
        if r.status_code == 429:
            return [], ERROR_CUOTA
        if r.status_code != 200:
            return [], ERROR_RED
        return r.json(), None
    except Exception:
        return [], ERROR_RED


def _cuotas_liga(liga):
    #Cachea la liga entera 10 minutos: asi un usuario que revisa
    #varios partidos seguidos gasta un solo credito.
    deporte = LIGAS_ODDS.get(liga)
    if not deporte:
        return [], ERROR_SIN_CLAVE
    llave = f"odds_{deporte}"
    datos = cache.get(llave)
    if datos is not None:
        return datos, None
    datos, error = _pedir_odds(deporte)
    if error:
        return [], error
    cache.set(llave, datos, 600)
    return datos, None


def _mejor_por_resultado(partido):
    #Recorre todas las casas y se queda con la cuota mas alta de cada
    #resultado, que es la que mas paga al apostador.
    local = partido.get("home_team", "")
    visitante = partido.get("away_team", "")
    mejor = {"local": None, "empate": None, "visitante": None}

    for casa in partido.get("bookmakers", []) or []:
        titulo = casa.get("title", "")
        for mercado in casa.get("markets", []) or []:
            if mercado.get("key") != "h2h":
                continue
            for salida in mercado.get("outcomes", []) or []:
                nombre = salida.get("name", "")
                try:
                    precio = float(salida.get("price"))
                except (TypeError, ValueError):
                    continue

                if nombre == "Draw":
                    destino = "empate"
                elif _mismo_equipo(nombre, local):
                    destino = "local"
                elif _mismo_equipo(nombre, visitante):
                    destino = "visitante"
                else:
                    continue

                actual = mejor[destino]
                if actual is None or precio > actual["cuota"]:
                    mejor[destino] = {"cuota": precio, "casa": titulo}

    return mejor


def cuotas_partido(liga, nombre_local, nombre_visitante):
    #Lo que consume el frontend. Devuelve (dict, error).
    #dict = {"h2h": {"local": {...}, "empate": {...}, "visitante": {...}},
    #        "actualizado": "hh:mm"}
    partidos, error = _cuotas_liga(liga)
    if error:
        return None, error

    for p in partidos:
        casa_local = p.get("home_team", "")
        casa_visita = p.get("away_team", "")
        if _mismo_equipo(casa_local, nombre_local) and _mismo_equipo(casa_visita, nombre_visitante):
            mejor = _mejor_por_resultado(p)
            if not any(mejor.values()):
                return None, "sin_datos"
            marca = ""
            for b in p.get("bookmakers", []) or []:
                marca = b.get("last_update", "") or marca
                break
            return {"h2h": mejor, "actualizado": marca[11:16] if len(marca) > 16 else ""}, None

    return None, "sin_partido"