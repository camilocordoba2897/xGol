#Cliente para consumir football-data.org (v4) desde el servidor.
#El token viaja solo aqui (backend), nunca al navegador.
import requests
from datetime import date, timedelta, datetime, timezone
from zoneinfo import ZoneInfo
from django.conf import settings
from django.core.cache import cache

BASE = "https://api.football-data.org/v4"
ZONA = ZoneInfo("America/Bogota")

#REGLA: esta lista tiene que ser EXACTAMENTE la misma que
#analizador/api_datos.py::LIGAS. Ni una liga de mas.
#
#Si el home anunciara una competencia que el motor no puede pronosticar,
#estariamos vendiendo algo que no existe. Por eso se quitaron la Copa
#Libertadores y la Liga BetPlay: football-data.org no las cubre y el
#analizador nunca pudo calcularlas.
LIGAS = {
    "Premier League": "PL",
    "LaLiga": "PD",
    "Serie A": "SA",
    "Bundesliga": "BL1",
    "Ligue 1": "FL1",
    "Champions League": "CL",
    "Eredivisie": "DED",
    "Primeira Liga": "PPL",
    "Brasileirao": "BSA",
}

#Los codigos, que es por lo que de verdad hay que filtrar.
#
#POR QUE NO POR NOMBRE: football-data.org NO llama a las ligas como las
#llamamos nosotros. A LaLiga le dice "Primera Division", al Brasileirao
#"Campeonato Brasileiro Serie A" y a la Champions "UEFA Champions League".
#Comparar por nombre hacia que esas tres se descartaran en silencio y la
#tarjeta del home se quedara sin partidos sin que nadie supiera por que.
#El codigo ("PD", "BSA", "CL") si viene siempre igual.
CODIGOS = set(LIGAS.values())

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

def _codigo_competencia(m):
    return ((m.get("competition") or {}).get("code") or "")


def _cubierta(m):
    #Solo pasan las competencias que el analizador sabe pronosticar
    return _codigo_competencia(m) in CODIGOS


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
        "liga_codigo": comp.get("code", ""),
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
    #Se filtra por competencia cubierta: el plan gratuito devuelve tambien
    #Championship, Mundial y Eurocopa, que el analizador no pronostica. Si
    #salieran en el home, el usuario veria partidos que luego no encuentra.
    datos = _pedir("matches", {"dateFrom": desde, "dateTo": hasta})
    return [_partido(m) for m in datos.get("matches", []) if _cubierta(m)]

def partidos_hoy():
    datos = cache.get("partidos_hoy_v2")
    if datos is None:
        hoy = date.today().isoformat()
        datos = _partidos_rango(hoy, hoy)
        cache.set("partidos_hoy_v2", datos, 180)
    return datos

def partidos_proximos():
    #ARRANCA HOY, no mañana.
    #
    #Antes empezaba al dia siguiente porque los de hoy los cubria la pestaña
    #"Hoy". Al quitar esa pestaña, los partidos de hoy se habrian perdido de
    #la pagina entera. Se descartan solo los que ya terminaron: en una lista
    #que se llama "Proximos" un partido con resultado final no pinta nada.
    #
    #PARON DE SELECCIONES: en las fechas FIFA ninguna de las nueve ligas juega
    #durante casi dos semanas. Con solo 7 dias la lista (y la tarjeta
    #flotante, que sale de aqui) se quedaba vacia. Si la semana no trae nada,
    #se sigue buscando hacia adelante en bloques de 10 dias, que es el rango
    #maximo que acepta football-data, y se para en el primero con partidos.
    datos = cache.get("partidos_proximos_v4")
    if datos is None:
        hoy = date.today()
        hasta = hoy + timedelta(days=7)
        datos = _pendientes(_partidos_rango(hoy.isoformat(), hasta.isoformat()))
        desde = hasta + timedelta(days=1)
        while not datos and desde <= hoy + timedelta(days=BUSCAR_HASTA):
            hasta = desde + timedelta(days=9)
            datos = _pendientes(_partidos_rango(desde.isoformat(), hasta.isoformat()))
            desde = hasta + timedelta(days=1)
        cache.set("partidos_proximos_v4", datos, 600)
    return datos

#Dias hacia adelante que se buscan como mucho cuando la semana viene vacia.
#Son 3 peticiones extra en el peor caso, y solo cada 10 minutos (cache).
BUSCAR_HASTA = 30

def _pendientes(partidos):
    return [p for p in partidos if p.get("estado") != "FINISHED"]

def partidos_vivo():
    datos = cache.get("partidos_vivo_v2")
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
        datos = [_partido(m) for m in crudo.get("matches", [])
                 if m.get("status") in vivos and _cubierta(m)]
        cache.set("partidos_vivo_v2", datos, 30)
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
#  TARJETA DESTACADA DEL HOME
#
#  REGLA DE ORO: de aqui NO SALE NI UN SOLO PORCENTAJE de un partido que
#  todavia no se ha jugado. Ni el 1X2, ni el marcador esperado, ni los goles
#  esperados. Y no basta con ocultarlos en pantalla: cualquiera abre las
#  herramientas del navegador y lee la respuesta de este endpoint. Si el dato
#  sale del servidor, esta regalado. Por eso se filtra AQUI.
#
#  Con los goles esperados pasa lo mismo que con el porcentaje: quien tenga
#  una calculadora saca el 1X2 a partir de lambda 2.19 y 0.94. Tampoco salen.
#
#  Lo que si sale, y es lo que de verdad vende:
#
#    EL PROXIMO PARTIDO, BLOQUEADO. Equipos, hora y liga, con el pronostico
#    detras del muro de suscripcion. Demuestra que el sistema esta vivo y
#    trabajando sobre partidos reales de hoy, sin regalar el numero por el
#    que la gente paga.
#
#    Las tarjetas de partidos ya resueltos y el balance de acierto estan
#    apagados: ver el bloque de MAX_RESUELTOS mas abajo, donde esta el
#    motivo completo.
#
#  COSTE EN API: cero peticiones extra. Todo sale de la base de datos.
# ============================================================
PROVEEDOR = "motor-xgol"
MAX_TARJETAS = 6

# ------------------------------------------------------------
#  APAGADOS A PROPOSITO: tarjetas de partidos ya resueltos y balance de
#  acierto. La tarjeta del home ensena SIEMPRE el proximo partido con el
#  candado.
#
#  POR QUE SE APAGARON, para que no se vuelvan a encender sin pensarlo:
#
#  1. EL BALANCE MENTIA SIN QUERER. Con seis partidos evaluados salia "83%
#     de acierto real" (cinco de seis). La medicion seria del motor, hecha
#     a ciegas sobre 5.353 partidos con calibrar_con_historico, da 53,3%.
#     Publicar 83% en la portada es una cifra que no se puede defender: son
#     seis partidos, es ruido, y cualquiera que mire las metricas del motor
#     ve que no cuadra.
#
#  2. ADEMAS "ACIERTO" ES LA METRICA EQUIVOCADA. Este proyecto vende
#     probabilidades calibradas, no aciertos. Un modelo que dice 60% y
#     acierta el 45% esta roto aunque ese 45% suene bien.
#
#  3. LAS TARJETAS RESUELTAS ENSENAN MARCADORES EN LA PORTADA, que es
#     justo lo contrario de lo que se quiere: la tarjeta existe para
#     demostrar que el motor esta vivo, no para contar partidos viejos.
#
#  CUANDO SE PODRIAN ENCENDER: cuando haya varios cientos de pronosticos
#  evaluados Y lo que se ensene sea una metrica de calibracion, no un
#  porcentaje de acierto. Hasta entonces, 3 fuentes y 8 mercados, que son
#  ciertos y comprobables.
# ------------------------------------------------------------
MAX_RESUELTOS = 0
MOSTRAR_BALANCE = False

def _partidos_crudos(desde, hasta):
    llave = f"crudos_{desde}_{hasta}"
    datos = cache.get(llave)
    if datos is None:
        datos = _pedir("matches", {"dateFrom": desde, "dateTo": hasta}).get("matches", [])
        cache.set(llave, datos, 180)
    return datos

def _hace(fecha_txt):
    #"hace 3 dias" a partir de una fecha YYYY-MM-DD
    if not fecha_txt:
        return ""
    try:
        a, m, d = (int(x) for x in str(fecha_txt)[:10].split("-"))
        dias = (date.today() - date(a, m, d)).days
    except (ValueError, TypeError):
        return ""
    if dias <= 0:
        return "hoy"
    if dias == 1:
        return "ayer"
    if dias < 7:
        return f"hace {dias} días"
    if dias < 30:
        semanas = dias // 7
        return "hace 1 semana" if semanas == 1 else f"hace {semanas} semanas"
    return "hace más de un mes"

def _balance():
    #Cuantos partidos lleva el motor medidos y con que acierto.
    #Historico y verificable: se calcula sobre pronosticos que se guardaron
    #ANTES de cada partido, no sobre lo que uno recuerda despues.
    try:
        from analizador.models import PrediccionMotor
    except Exception:
        return {"verificados": 0, "acierto": None}
    try:
        filas = list(PrediccionMotor.objects.filter(evaluado=True)
                     .exclude(resultado="")
                     .values("prob_local", "prob_empate", "prob_visitante", "resultado"))
    except Exception:
        return {"verificados": 0, "acierto": None}
    if not filas:
        return {"verificados": 0, "acierto": None}
    aciertos = 0
    for f in filas:
        opciones = {"local": f["prob_local"], "empate": f["prob_empate"],
                    "visitante": f["prob_visitante"]}
        if max(opciones, key=opciones.get) == f["resultado"]:
            aciertos += 1
    return {"verificados": len(filas),
            "acierto": round(aciertos / len(filas) * 100)}

def _escudos_de(codigos):
    #Escudo de cada equipo, por nombre. Sale de equipos_liga(), que ya esta
    #cacheado 24 horas: una peticion por liga y dia, nada mas.
    mapa = {}
    for codigo in codigos:
        if not codigo:
            continue
        try:
            for e in equipos_liga(codigo):
                if e.get("escudo"):
                    mapa.setdefault((e.get("corto") or "").lower(), e["escudo"])
                    mapa.setdefault((e.get("nombre") or "").lower(), e["escudo"])
        except Exception:
            continue
    return mapa


def _nombre_liga(codigo):
    for nombre, c in LIGAS.items():
        if c == codigo:
            return nombre
    return codigo or ""


def _resueltos(limite=MAX_RESUELTOS):
    #Pronosticos que ya tienen resultado. Se manda QUE dijo el motor (el signo,
    #no el porcentaje) y que paso. Aciertos y fallos, sin filtrar.
    try:
        from analizador.models import PrediccionMotor
    except Exception:
        return []
    try:
        filas = list(PrediccionMotor.objects.filter(evaluado=True)
                     .exclude(resultado="")
                     .order_by("-creado")[:limite])
    except Exception:
        return []

    escudos = _escudos_de({f.liga for f in filas})

    salida = []
    for f in filas:
        opciones = {"local": f.prob_local, "empate": f.prob_empate,
                    "visitante": f.prob_visitante}
        signo = max(opciones, key=opciones.get)
        etiqueta = {"local": f"Gana {f.equipo_local}",
                    "empate": "Empate",
                    "visitante": f"Gana {f.equipo_visitante}"}[signo]
        salida.append({
            "tipo": "resuelto",
            "local": f.equipo_local,
            "visitante": f.equipo_visitante,
            "local_escudo": escudos.get((f.equipo_local or "").lower(), ""),
            "visitante_escudo": escudos.get((f.equipo_visitante or "").lower(), ""),
            "liga": _nombre_liga(f.liga),
            "dijo": etiqueta,
            "acerto": signo == f.resultado,
            "marcador": (f"{f.goles_local} - {f.goles_visitante}"
                         if f.goles_local is not None else ""),
            "cuando": _hace(f.fecha),
        })
    return salida

def _ligas_anunciables():
    #Ligas cuyos partidos se pueden anunciar en la tarjeta.
    #Se prefieren las que ya tienen ajuste guardado; si aun no se corrio
    #"ajustar_motor", se usan todas las que cubre xGol.
    try:
        from analizador.models import AjusteMotor
        ajustadas = set(AjusteMotor.objects.values_list("liga", flat=True))
        if ajustadas:
            return ajustadas
    except Exception:
        pass
    return set(LIGAS.values())


def _proximos_bloqueados(limite):
    #Partidos que se van a jugar. SIN NINGUN NUMERO de pronostico.
    #
    #IMPORTANTE: se reutilizan partidos_vivo(), partidos_hoy() y
    #partidos_proximos(), que son EXACTAMENTE los mismos que ya pinta la
    #seccion "Partidos del dia" del home.
    #
    #Antes esta funcion pedia los partidos por su cuenta. Eso tenia dos
    #problemas: gastaba peticiones de mas (football-data solo permite 10 por
    #minuto, y una carga del home ya hace varias), y si esa peticion concreta
    #fallaba la tarjeta se quedaba vacia aunque el resto de la pagina si
    #tuviera partidos. Ahora comparten cache: si la seccion de abajo muestra
    #partidos, la tarjeta tambien.
    ligas = _ligas_anunciables()
    try:
        vivos = partidos_vivo()
        hoy = partidos_hoy()
        proximos = partidos_proximos()
    except Exception:
        return [], "sin_conexion"

    POR_JUGAR = ("SCHEDULED", "TIMED")
    EN_JUEGO = ("IN_PLAY", "PAUSED")

    #Orden: primero lo que se esta jugando, luego lo de hoy, luego la semana.
    candidatos = list(vivos)
    candidatos += [p for p in hoy if p.get("estado") in POR_JUGAR]
    candidatos += [p for p in proximos if p.get("estado") in POR_JUGAR]

    if not candidatos:
        return [], "sin_partidos"

    salida = []
    vistos = set()
    descartados_por_liga = 0
    for p in candidatos:
        if len(salida) >= limite:
            break
        clave = (p.get("local"), p.get("visitante"), p.get("utc"))
        if clave in vistos:
            continue
        vistos.add(clave)
        if not p.get("local") or not p.get("visitante"):
            continue
        codigo = p.get("liga_codigo") or ""
        if codigo not in ligas:
            descartados_por_liga += 1
            continue
        salida.append({
            "tipo": "bloqueado",
            "local": p.get("local"),
            "local_escudo": p.get("local_logo", ""),
            "visitante": p.get("visitante"),
            "visitante_escudo": p.get("visitante_logo", ""),
            "liga": p.get("liga", ""),
            "hora": p.get("hora", ""),
            "fecha": p.get("fecha", ""),
            "estado": p.get("estado", ""),
        })

    if not salida:
        #Habia partidos, pero ninguno de una liga que xGol cubra.
        return [], "sin_ligas_cubiertas"
    return salida, None


def predicciones_destacadas():
    datos = cache.get("tarjeta_home_v3")
    if datos is not None:
        return datos

    resueltos = _resueltos(MAX_RESUELTOS) if MAX_RESUELTOS else []
    proximos, motivo = _proximos_bloqueados(MAX_TARJETAS - len(resueltos))

    #Se intercalan: resuelto, proximo, resuelto, proximo...
    tarjetas = []
    for i in range(max(len(resueltos), len(proximos))):
        if i < len(resueltos):
            tarjetas.append(resueltos[i])
        if i < len(proximos):
            tarjetas.append(proximos[i])

    datos = {
        "tarjetas": tarjetas[:MAX_TARJETAS],
        "balance": (_balance() if MOSTRAR_BALANCE else None),
        "fuente": PROVEEDOR,
        #Si no hay nada que enseñar, el frontend necesita saber POR QUE para
        #decirlo en pantalla. Una tarjeta atascada en "Cargando..." para
        #siempre es peor que una que explica que no hay partidos ahora mismo.
        "motivo": (None if tarjetas else (motivo or "sin_datos")),
    }
    #Sin datos se cachea solo 60 segundos: si el problema era pasajero, la
    #tarjeta se arregla sola en un minuto en vez de quedarse mal cinco.
    cache.set("tarjeta_home_v3", datos, 300 if tarjetas else 60)
    return datos