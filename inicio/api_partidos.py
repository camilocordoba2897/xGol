#Cliente para consumir football-data.org (v4) desde el servidor.
#El token viaja solo aqui (backend), nunca al navegador.
import math
import requests
from datetime import date, timedelta, datetime, timezone
from zoneinfo import ZoneInfo
from django.conf import settings
from django.core.cache import cache

BASE = "https://api.football-data.org/v4"
ZONA = ZoneInfo("America/Bogota")

#Competencias para la tabla (codigos de football-data.org). El plan gratuito
#cubre estas; la Liga BetPlay (Colombia) no esta disponible en esta API.
LIGAS = {
    "Premier League": "PL",
    "LaLiga": "PD",
    "Serie A": "SA",
    "Bundesliga": "BL1",
    "Ligue 1": "FL1",
    "Champions League": "CL",
    "Eredivisie": "DED",
    "Brasileirao": "BSA",
}

def _pedir(ruta, parametros=None):
    #Llama a un endpoint de football-data.org y devuelve el JSON (o {} si falla)
    token = settings.FOOTBALL_DATA_TOKEN
    if not token:
        return {}
    try:
        r = requests.get(
            f"{BASE}/{ruta}",
            headers={"X-Auth-Token": token},
            params=parametros or {},
            timeout=8,
        )
        r.raise_for_status()
        return r.json()
    except (requests.RequestException, ValueError):
        return {}

def _hora_local(utc):
    #Convierte la fecha UTC (ISO) a hora de Colombia -> ("HH:MM", "YYYY-MM-DD")
    if not utc:
        return "", ""
    try:
        d = datetime.fromisoformat(utc.replace("Z", "+00:00")).astimezone(ZONA)
        return d.strftime("%H:%M"), d.strftime("%Y-%m-%d")
    except ValueError:
        return "", ""

DESCANSO = 15   #minutos de entretiempo que se descuentan al estimar

def _reloj(utc, estado, minuto_api):
    #Minuto de juego. El plan gratuito de football-data casi nunca manda
    #"minute", asi que si falta se estima desde la hora de saque.
    #fuente indica de donde salio: api (exacto) o estimado (aproximado).
    if minuto_api is not None:
        try:
            m = int(minuto_api)
            return {"minuto": m, "periodo": "2T" if m > 45 else "1T",
                    "etiqueta": f"{m}'", "fuente": "api"}
        except (TypeError, ValueError):
            pass
    if estado == "PAUSED":
        return {"minuto": 45, "periodo": "HT", "etiqueta": "DESCANSO", "fuente": "estado"}
    if estado != "IN_PLAY" or not utc:
        return {"minuto": None, "periodo": "", "etiqueta": "EN VIVO", "fuente": "ninguna"}
    try:
        inicio = datetime.fromisoformat(utc.replace("Z", "+00:00"))
    except Exception:
        return {"minuto": None, "periodo": "", "etiqueta": "EN VIVO", "fuente": "ninguna"}
    transcurrido = int((datetime.now(timezone.utc) - inicio).total_seconds() // 60)
    if transcurrido < 0:
        return {"minuto": None, "periodo": "", "etiqueta": "EN VIVO", "fuente": "ninguna"}
    if transcurrido <= 45:
        m = max(1, transcurrido)
        return {"minuto": m, "periodo": "1T", "etiqueta": f"{m}'", "fuente": "estimado"}
    if transcurrido <= 45 + DESCANSO:
        return {"minuto": 45, "periodo": "1T", "etiqueta": "45+", "fuente": "estimado"}
    m = transcurrido - DESCANSO
    if m >= 90:
        return {"minuto": 90, "periodo": "2T", "etiqueta": "90+", "fuente": "estimado"}
    return {"minuto": m, "periodo": "2T", "etiqueta": f"{m}'", "fuente": "estimado"}

def _partido(m):
    #Da forma a un partido para el frontend (equipos, hora, marcador, estado)
    comp = m.get("competition", {})
    local = m.get("homeTeam", {})
    visitante = m.get("awayTeam", {})
    marcador = (m.get("score", {}) or {}).get("fullTime", {}) or {}
    hora, fecha = _hora_local(m.get("utcDate", ""))
    reloj = _reloj(m.get("utcDate", ""), m.get("status", ""), m.get("minute"))
    parcial = (m.get("score", {}) or {}).get("halfTime", {}) or {}
    return {
        "liga": comp.get("name", ""),
        "liga_logo": comp.get("emblem", ""),
        "local": local.get("shortName") or local.get("name", ""),
        "local_logo": local.get("crest", ""),
        "visitante": visitante.get("shortName") or visitante.get("name", ""),
        "visitante_logo": visitante.get("crest", ""),
        "hora": hora,
        "fecha": fecha,
        "estado": m.get("status", ""),
        "minuto": reloj["minuto"],
        "minuto_texto": reloj["etiqueta"],
        "periodo": reloj["periodo"],
        "minuto_fuente": reloj["fuente"],
        "utc": m.get("utcDate", ""),
        "goles_local": marcador.get("home"),
        "goles_visitante": marcador.get("away"),
        "goles_1t_local": parcial.get("home"),
        "goles_1t_visitante": parcial.get("away"),
    }

def _partidos_rango(desde, hasta):
    datos = _pedir("matches", {"dateFrom": desde, "dateTo": hasta})
    return [_partido(m) for m in datos.get("matches", [])]

def partidos_hoy():
    datos = cache.get("partidos_hoy")
    if datos is None:
        hoy = date.today().isoformat()
        datos = _partidos_rango(hoy, hoy)
        cache.set("partidos_hoy", datos, 180)
    return datos

def partidos_proximos():
    datos = cache.get("partidos_proximos")
    if datos is None:
        hoy = date.today()
        desde = (hoy + timedelta(days=1)).isoformat()
        hasta = (hoy + timedelta(days=7)).isoformat()
        datos = _partidos_rango(desde, hasta)
        cache.set("partidos_proximos", datos, 600)
    return datos

def partidos_vivo():
    datos = cache.get("partidos_vivo")
    if datos is None:
        #Ventana de 3 dias, no solo hoy: football-data fecha los partidos en UTC.
        #Un partido de las 22:30 UTC del domingo cae en lunes para un servidor
        #en UTC y en domingo para uno en Bogota; con un solo dia se perdian.
        hoy = date.today()
        crudo = _pedir("matches", {
            "dateFrom": (hoy - timedelta(days=1)).isoformat(),
            "dateTo": (hoy + timedelta(days=1)).isoformat(),
        })
        vivos = {"IN_PLAY", "PAUSED"}
        datos = [_partido(m) for m in crudo.get("matches", []) if m.get("status") in vivos]
        cache.set("partidos_vivo", datos, 30)
    return datos

def tabla_posiciones(liga):
    #liga: codigo de competencia de football-data.org (por defecto Premier League)
    llave = f"tabla_{liga}"
    datos = cache.get(llave)
    if datos is None:
        crudo = _pedir(f"competitions/{liga}/standings")
        datos = []
        for grupo in crudo.get("standings", []):
            if grupo.get("type") == "TOTAL":
                for fila in grupo.get("table", []):
                    equipo = fila.get("team", {})
                    datos.append({
                        "puesto": fila.get("position"),
                        "equipo": equipo.get("shortName") or equipo.get("name", ""),
                        "escudo": equipo.get("crest", ""),
                        "jugados": fila.get("playedGames"),
                        "diferencia": fila.get("goalDifference"),
                        "puntos": fila.get("points"),
                        "forma": fila.get("form", ""),
                    })
                break
        cache.set(llave, datos, 900)
    return datos
def equipos_liga(liga):
    #liga: codigo de competencia de football-data.org -> lista de equipos con escudo
    llave = f"equipos_{liga}"
    datos = cache.get(llave)
    if datos is None:
        crudo = _pedir(f"competitions/{liga}/teams")
        datos = []
        for e in crudo.get("teams", []):
            datos.append({
                "nombre": e.get("name", ""),
                "corto": e.get("shortName") or e.get("tla") or e.get("name", ""),
                "escudo": e.get("crest", ""),
            })
        datos.sort(key=lambda x: (x["nombre"] or "").lower())
        cache.set(llave, datos, 86400)
    return datos


# ============================================================
#  PREDICCION DESTACADA — Poisson doble + Dixon-Coles
#  Datos REALES: goles a favor/en contra de la tabla de la
#  competencia del partido. Si un equipo no esta en la tabla el
#  partido se descarta (no se inventan numeros).
#
#  CAMBIO A LA API DE PAGO: solo hay que reescribir _fuerzas_liga()
#  para que devuelva el mismo diccionario
#  {id_equipo: {"nombre","escudo","pj","gf","gc"}}.
#  El motor de probabilidad no se toca.
# ============================================================
PROVEEDOR = "football-data"
VENTAJA_LOCAL = 1.20
DC_RHO = -0.13
MAX_GOLES = 7
SHRINK_K = 6
MAX_DESTACADAS = 6
MAX_COMPETENCIAS = 3

def _partidos_crudos(desde, hasta):
    llave = f"crudos_{desde}_{hasta}"
    datos = cache.get(llave)
    if datos is None:
        datos = _pedir("matches", {"dateFrom": desde, "dateTo": hasta}).get("matches", [])
        cache.set(llave, datos, 180)
    return datos

def _fuerzas_liga(liga):
    llave = f"fuerzas_{liga}"
    datos = cache.get(llave)
    if datos is not None:
        return datos
    crudo = _pedir(f"competitions/{liga}/standings")
    datos = {}
    for grupo in crudo.get("standings", []):
        if grupo.get("type") != "TOTAL":
            continue
        for fila in grupo.get("table", []):
            equipo = fila.get("team", {}) or {}
            id_equipo = equipo.get("id")
            pj = fila.get("playedGames") or 0
            if not id_equipo or pj <= 0:
                continue
            datos[id_equipo] = {
                "nombre": equipo.get("shortName") or equipo.get("name", ""),
                "escudo": equipo.get("crest", ""),
                "pj": pj,
                "gf": fila.get("goalsFor") or 0,
                "gc": fila.get("goalsAgainst") or 0,
            }
    cache.set(llave, datos, 1800)
    return datos

def _poisson(lam, k):
    p = math.exp(-lam)
    for i in range(k):
        p = p * lam / (i + 1)
    return p

def _matriz_dc(lam1, lam2):
    mat = [[_poisson(lam1, h) * _poisson(lam2, a) for a in range(MAX_GOLES + 1)]
           for h in range(MAX_GOLES + 1)]
    tau = {(0, 0): 1 - lam1 * lam2 * DC_RHO, (1, 0): 1 + lam2 * DC_RHO,
           (0, 1): 1 + lam1 * DC_RHO, (1, 1): 1 - DC_RHO}
    for (h, a), t in tau.items():
        mat[h][a] = max(0.0, mat[h][a] * t)
    total = sum(sum(fila) for fila in mat) or 1
    return [[p / total for p in fila] for fila in mat]

def _regresar(fuerza, pj):
    peso = pj / (pj + SHRINK_K)
    return fuerza * peso + (1 - peso)

def _prediccion(local, visitante, media_liga):
    atk1 = _regresar((local["gf"] / local["pj"]) / media_liga, local["pj"])
    def1 = _regresar((local["gc"] / local["pj"]) / media_liga, local["pj"])
    atk2 = _regresar((visitante["gf"] / visitante["pj"]) / media_liga, visitante["pj"])
    def2 = _regresar((visitante["gc"] / visitante["pj"]) / media_liga, visitante["pj"])

    lam1 = max(0.3, atk1 * def2 * media_liga * VENTAJA_LOCAL)
    lam2 = max(0.3, atk2 * def1 * media_liga)

    mat = _matriz_dc(lam1, lam2)
    p_local = p_empate = p_visitante = 0.0
    for h in range(MAX_GOLES + 1):
        for a in range(MAX_GOLES + 1):
            p = mat[h][a]
            if h > a:
                p_local += p
            elif h == a:
                p_empate += p
            else:
                p_visitante += p

    #Marcador esperado: el mas probable DENTRO del resultado mas probable.
    #Si se toma el marcador mas probable en general casi siempre sale 1-1 (es
    #el marcador mas comun del futbol) y contradice los porcentajes de arriba.
    if p_local >= p_empate and p_local >= p_visitante:
        signo = "local"
    elif p_visitante >= p_empate:
        signo = "visitante"
    else:
        signo = "empate"

    mejor = (1, 1)
    mejor_p = -1.0
    for h in range(MAX_GOLES + 1):
        for a in range(MAX_GOLES + 1):
            if signo == "local" and h <= a:
                continue
            if signo == "visitante" and h >= a:
                continue
            if signo == "empate" and h != a:
                continue
            if mat[h][a] > mejor_p:
                mejor_p = mat[h][a]
                mejor = (h, a)

    duelo = (p_local + p_visitante) or 1
    prob_local = round(p_local / duelo * 100)
    muestra = min(1.0, min(local["pj"], visitante["pj"]) / 8)
    confianza = min(0.95, (max(p_local, p_visitante) + p_empate) * (0.75 + 0.25 * muestra))

    return {
        "prob_local": prob_local,
        "prob_visitante": 100 - prob_local,
        "p_local": round(p_local * 100, 1),
        "p_empate": round(p_empate * 100, 1),
        "p_visitante": round(p_visitante * 100, 1),
        "marcador": f"{mejor[0]} - {mejor[1]}",
        "confianza": round(confianza * 100),
        "lam_local": round(lam1, 2),
        "lam_visitante": round(lam2, 2),
    }

def predicciones_destacadas():
    datos = cache.get("predicciones_destacadas")
    if datos is not None:
        return datos

    hoy = date.today()
    del_dia = _partidos_crudos(hoy.isoformat(), hoy.isoformat())
    vivos = [m for m in del_dia if m.get("status") in ("IN_PLAY", "PAUSED")]
    ids_vivos = {m.get("id") for m in vivos}

    candidatos = vivos + [m for m in del_dia if m.get("id") not in ids_vivos]
    if len(candidatos) < MAX_DESTACADAS:
        vistos = {m.get("id") for m in candidatos}
        proximos = _partidos_crudos((hoy + timedelta(days=1)).isoformat(),
                                    (hoy + timedelta(days=7)).isoformat())
        candidatos = candidatos + [m for m in proximos if m.get("id") not in vistos]

    ligas = []
    for m in candidatos:
        codigo = (m.get("competition", {}) or {}).get("code")
        if codigo and codigo not in ligas:
            ligas.append(codigo)
        if len(ligas) >= MAX_COMPETENCIAS:
            break
    tablas = {codigo: _fuerzas_liga(codigo) for codigo in ligas}
    medias = {}

    datos = []
    for m in candidatos:
        if len(datos) >= MAX_DESTACADAS:
            break
        comp = m.get("competition", {}) or {}
        codigo = comp.get("code")
        tabla = tablas.get(codigo)
        if not tabla:
            continue
        local = tabla.get((m.get("homeTeam", {}) or {}).get("id"))
        visitante = tabla.get((m.get("awayTeam", {}) or {}).get("id"))
        if not local or not visitante:
            continue
        if codigo not in medias:
            total_pj = sum(e["pj"] for e in tabla.values())
            total_gf = sum(e["gf"] for e in tabla.values())
            medias[codigo] = (total_gf / total_pj) if total_pj else 1.35
        p = _prediccion(local, visitante, medias[codigo])
        hora, fecha = _hora_local(m.get("utcDate", ""))
        p.update({
            "liga": comp.get("name", ""),
            "local": local["nombre"],
            "local_escudo": local["escudo"],
            "visitante": visitante["nombre"],
            "visitante_escudo": visitante["escudo"],
            "hora": hora,
            "fecha": fecha,
            "estado": m.get("status", ""),
            "fuente": PROVEEDOR,
        })
        datos.append(p)

    cache.set("predicciones_destacadas", datos, 300)
    return datos