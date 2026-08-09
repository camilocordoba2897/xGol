#Capa de datos del analizador automatico.
#
#Hoy consume football-data.org (plan gratuito). Entrega 11 de las 27 columnas
#que usa el motor: fecha, rival, sede, goles totales, goles por tiempo y
#resultado. Las otras 16 (xG, tiros, corners, tarjetas...) se envian VACIAS
#a proposito: el motor detecta la ausencia y no las usa. Nunca poner 0 en una
#columna sin dato, un 0 falso corrompe las medias del modelo.
#
#CAMBIO A API-FOOTBALL (api-sports.io) CUANDO SE PAGUE:
#  1. Poner PROVEEDOR = "api-football" y la clave en .env
#  2. Escribir _af_partidos_liga() y _af_historial() copiando la firma de las
#     _fd_*: deben devolver exactamente la misma estructura.
#  3. Rellenar en _fila_* las columnas que football-data no trae.
#Nada mas del proyecto se toca: ni el motor, ni las vistas, ni el frontend.
import requests
from datetime import date, timedelta
from django.conf import settings
from django.core.cache import cache

PROVEEDOR = "football-data"
BASE_FD = "https://api.football-data.org/v4"

#Competencias del plan gratuito de football-data.org
LIGAS = {
    "PL":  "Premier League",
    "PD":  "LaLiga",
    "SA":  "Serie A",
    "BL1": "Bundesliga",
    "FL1": "Ligue 1",
    "DED": "Eredivisie",
    "PPL": "Primeira Liga",
    "BSA": "Brasileirao",
    "CL":  "Champions League",
}

PARTIDOS_HISTORIAL = 15   #cuantos partidos previos se piden por equipo
DIAS_ADELANTE = 45        #ventana de proximos partidos que se ofrece.
                          #45 dias porque las ligas europeas paran de mayo a
                          #agosto: con una ventana corta el selector sale vacio
                          #todo el verano aunque el calendario ya este publicado.
MAX_PARTIDOS = 40         #tope de partidos en la lista (45 dias dan muchas jornadas)

#Esqueleto de una fila: todas las columnas que espera el motor.
#Las vacias las ignora computeStats(); no las llenes con ceros.
COLUMNAS_VACIAS = {
    "xg_f": "", "xg_c": "", "xgot_f": "", "xgot_c": "",
    "tiros": "", "tiros_rival": "", "tiros_puerta": "", "tiros_puerta_rival": "",
    "corners": "", "corners_rival": "",
    "tarjetas_a": "", "tarjetas_r": "",
    "ppda_f": "", "ppda_c": "", "asistencias": "",
}


#Errores que el frontend necesita distinguir para dar un mensaje util
ERROR_CUOTA = "cuota"      #429: se agoto el limite de peticiones por minuto
ERROR_RED = "red"          #timeout o fallo de conexion


def _pedir_fd(ruta, parametros=None):
    #Devuelve (datos, error). error es None si todo salio bien.
    #El plan gratuito de football-data.org permite 10 peticiones por minuto:
    #hay que distinguir el 429 del resto o el usuario ve un fallo mudo.
    cabeceras = {"X-Auth-Token": settings.FOOTBALL_DATA_TOKEN}
    try:
        r = requests.get(f"{BASE_FD}/{ruta}", headers=cabeceras, params=parametros or {}, timeout=15)
        if r.status_code == 429:
            return {}, ERROR_CUOTA
        if r.status_code != 200:
            return {}, ERROR_RED
        return r.json(), None
    except Exception:
        return {}, ERROR_RED


def _equipo_resumen(t):
    #Datos minimos de un equipo para pintarlo en el selector
    t = t or {}
    return {
        "id": t.get("id"),
        "nombre": t.get("shortName") or t.get("name", ""),
        "nombre_largo": t.get("name", ""),
        "escudo": t.get("crest", ""),
        "sigla": t.get("tla", ""),
    }


def _fd_partidos_liga(liga):
    #Proximos partidos de la competencia, con escudos
    hoy = date.today()
    hasta = hoy + timedelta(days=DIAS_ADELANTE)
    crudo, error = _pedir_fd(f"competitions/{liga}/matches", {
        "dateFrom": hoy.isoformat(),
        "dateTo": hasta.isoformat(),
    })
    if error:
        return [], error
    salida = []
    for m in crudo.get("matches", []):
        if m.get("status") in ("FINISHED", "CANCELLED", "POSTPONED"):
            continue
        local = _equipo_resumen(m.get("homeTeam"))
        visitante = _equipo_resumen(m.get("awayTeam"))
        if not local["id"] or not visitante["id"]:
            continue
        salida.append({
            "id": m.get("id"),
            "utc": m.get("utcDate", ""),
            "estado": m.get("status", ""),
            "jornada": m.get("matchday"),
            "local": local,
            "visitante": visitante,
        })
    salida.sort(key=lambda x: x["utc"])
    return salida[:MAX_PARTIDOS], None


def _fila_desde_partido(m, id_equipo, nombre_equipo):
    #Convierte un partido de football-data a una fila del esquema del motor
    local = m.get("homeTeam", {}) or {}
    visita = m.get("awayTeam", {}) or {}
    marcador = m.get("score", {}) or {}
    completo = marcador.get("fullTime", {}) or {}
    primera = marcador.get("halfTime", {}) or {}

    es_local = local.get("id") == id_equipo
    rival = visita if es_local else local

    gf = completo.get("home") if es_local else completo.get("away")
    gc = completo.get("away") if es_local else completo.get("home")
    if gf is None or gc is None:
        return None

    if gf > gc:
        resultado = "W"
    elif gf < gc:
        resultado = "L"
    else:
        resultado = "D"

    fila = {
        "fecha": (m.get("utcDate") or "")[:10],
        "equipo": nombre_equipo,
        "rival": rival.get("shortName") or rival.get("name", ""),
        "sede": "local" if es_local else "visitante",
        "goles_f": gf,
        "goles_c": gc,
        "resultado": resultado,
    }
    fila.update(COLUMNAS_VACIAS)

    g1f = primera.get("home") if es_local else primera.get("away")
    g1c = primera.get("away") if es_local else primera.get("home")
    if g1f is not None and g1c is not None:
        fila["goles_1t_f"] = g1f
        fila["goles_1t_c"] = g1c
        fila["goles_2t_f"] = max(0, gf - g1f)
        fila["goles_2t_c"] = max(0, gc - g1c)
    else:
        fila["goles_1t_f"] = ""
        fila["goles_1t_c"] = ""
        fila["goles_2t_f"] = ""
        fila["goles_2t_c"] = ""
    return fila


def _fd_historial(id_equipo, nombre_equipo, limite):
    #Ultimos partidos jugados por el equipo, mas recientes primero
    crudo, error = _pedir_fd(f"teams/{id_equipo}/matches", {
        "status": "FINISHED",
        "limit": limite,
    })
    if error:
        return [], error
    partidos = crudo.get("matches", [])
    partidos.sort(key=lambda m: m.get("utcDate", ""), reverse=True)
    filas = []
    for m in partidos[:limite]:
        fila = _fila_desde_partido(m, id_equipo, nombre_equipo)
        if fila:
            filas.append(fila)
    return filas, None


# ============================================================
#  API PUBLICA — lo unico que consume el resto del proyecto
# ============================================================
def ligas_disponibles():
    return [{"codigo": c, "nombre": n} for c, n in LIGAS.items()]


def partidos_liga(liga):
    #Un error NUNCA se cachea: si no, un 429 pasajero deja la liga vacia 10 min
    llave = f"auto_partidos_{liga}"
    datos = cache.get(llave)
    if datos is not None:
        return datos, None
    datos, error = _fd_partidos_liga(liga)
    if error:
        return [], error
    cache.set(llave, datos, 900)
    return datos, None


def historial_equipo(id_equipo, nombre_equipo, limite=PARTIDOS_HISTORIAL):
    llave = f"auto_hist_{id_equipo}_{limite}"
    datos = cache.get(llave)
    if datos is not None:
        return datos, None
    datos, error = _fd_historial(id_equipo, nombre_equipo, limite)
    if error:
        return [], error
    #6 horas: el historial de un equipo solo cambia cuando juega
    cache.set(llave, datos, 21600)
    return datos, None


def enfrentamiento(id_local, nombre_local, id_visitante, nombre_visitante, limite=PARTIDOS_HISTORIAL):
    #Lo que consume el frontend para llenar el motor de una sola vez
    filas_local, error = historial_equipo(id_local, nombre_local, limite)
    if error:
        return {"error": error}
    filas_visitante, error = historial_equipo(id_visitante, nombre_visitante, limite)
    if error:
        return {"error": error}
    return {
        "local": {"nombre": nombre_local, "filas": filas_local},
        "visitante": {"nombre": nombre_visitante, "filas": filas_visitante},
        "columnas_sin_datos": sorted(COLUMNAS_VACIAS.keys()),
        "proveedor": PROVEEDOR,
    }


# ============================================================
#  RESULTADOS DE PARTIDOS YA JUGADOS
#  Sirven para que la pestaña Rendimiento se evalue sola: se
#  guarda la prediccion con el id del partido y, cuando termina,
#  se trae el marcador real y se puntuan las predicciones.
#
#  API-FOOTBALL: reescribir _fd_resultado() manteniendo la firma.
#  Ahi vendran ademas corners, tarjetas y tiros reales, y bastara
#  con rellenar esas claves del diccionario.
# ============================================================
def _fd_resultado(id_partido):
    crudo, error = _pedir_fd(f"matches/{id_partido}")
    if error:
        return None, error
    m = crudo.get("match") or crudo
    if not m or not m.get("id"):
        return None, ERROR_RED

    estado = m.get("status", "")
    if estado != "FINISHED":
        return {"id": id_partido, "terminado": False, "estado": estado}, None

    marcador = m.get("score", {}) or {}
    completo = marcador.get("fullTime", {}) or {}
    primera = marcador.get("halfTime", {}) or {}
    gf, gc = completo.get("home"), completo.get("away")
    if gf is None or gc is None:
        return {"id": id_partido, "terminado": False, "estado": estado}, None

    return {
        "id": id_partido,
        "terminado": True,
        "estado": estado,
        "utc": m.get("utcDate", ""),
        "local": (m.get("homeTeam", {}) or {}).get("shortName") or "",
        "visitante": (m.get("awayTeam", {}) or {}).get("shortName") or "",
        "liga": (m.get("competition", {}) or {}).get("name", ""),
        "gf": gf,
        "gc": gc,
        #Los datos que football-data no entrega van en None: el evaluador
        #salta esos mercados en vez de darlos por fallados.
        "g1f": primera.get("home"),
        "g1c": primera.get("away"),
        "cf": None, "cc": None,
        "sf": None, "sc": None,
        "tf": None, "tc": None,
        "cards": None,
    }, None


def resultado_partido(id_partido):
    #Un partido terminado ya no cambia: se cachea 24h.
    #Uno sin terminar se consulta cada 5 min.
    llave = f"auto_resultado_{id_partido}"
    datos = cache.get(llave)
    if datos is not None:
        return datos, None
    datos, error = _fd_resultado(id_partido)
    if error:
        return None, error
    if datos:
        cache.set(llave, datos, 86400 if datos.get("terminado") else 300)
    return datos, None


def resultados_partidos(ids):
    #Varios de una vez. El plan gratuito limita a 10 peticiones por
    #minuto, asi que se topa la cantidad por tanda.
    salida = {}
    error = None
    for id_partido in list(ids)[:8]:
        dato, err = resultado_partido(id_partido)
        if err:
            error = err
            break
        if dato:
            salida[str(id_partido)] = dato
    return salida, error