#Puente entre el motor y los datos que ya tiene el proyecto.
#
#El motor necesita una cosa que hoy no se pide nunca: TODOS los partidos ya
#jugados de la liga, no solo los 15 de los dos equipos del partido. Con la
#temporada completa se pueden separar de verdad ataque, defensa y ventaja de
#campo; con 15 partidos por equipo, no.
#
#COSTE EN CUOTA DE API: UNA peticion por liga y temporada. El plan gratuito de
#football-data.org da 10 por minuto. Ajustar las 9 ligas con 2 temporadas son
#18 peticiones, y el comando ajustar_motor ya espera entre una y otra.
#El resultado se guarda en base de datos: NO se repite en cada pronostico.
from datetime import date

from django.core.cache import cache

from analizador.api_datos import ERROR_RED, LIGAS, _pedir_fd
from analizador.motor import elo as mod_elo
from analizador.motor import tasas

#Ligas donde el ajuste por liga funciona bien: son campeonatos cerrados, todos
#contra todos, con la misma "media" para todos los equipos.
#La Champions (CL) es un caso aparte: juegan equipos de ligas distintas, hay
#pocos partidos por temporada y las fases finales son a doble partido. El
#ajuste sale mucho mas flojo. Se puede usar, pero conviene mas temporadas y
#saber que la confianza sera menor.
LIGAS_DE_COPA = {"CL"}


def temporada_actual():
    #Las ligas europeas se nombran por el año en que empiezan: la 2025/26 es
    #"2025". De enero a junio seguimos dentro de la temporada anterior.
    hoy = date.today()
    return hoy.year if hoy.month >= 7 else hoy.year - 1


def _dias_desde(fecha_txt, hoy=None):
    if not fecha_txt:
        return None
    hoy = hoy or date.today()
    try:
        a, m, d = (int(x) for x in fecha_txt.split("-"))
        return (hoy - date(a, m, d)).days
    except (ValueError, TypeError):
        return None


def partidos_temporada(liga, temporada=None):
    #Todos los partidos TERMINADOS de una liga en una temporada.
    #Devuelve (lista_partidos, mapa_ids, error).
    #
    #mapa_ids relaciona el id numerico de football-data con el nombre que se
    #usa en el ajuste. Sirve de seguro: si un equipo cambia de nombre corto
    #entre temporadas, el id sigue siendo el mismo y no se parte en dos
    #equipos distintos.
    temporada = temporada or temporada_actual()
    crudo, error = _pedir_fd(f"competitions/{liga}/matches",
                             {"season": temporada, "status": "FINISHED"})
    if error:
        return [], {}, error

    hoy = date.today()
    salida = []
    mapa = {}
    for m in crudo.get("matches", []) or []:
        marcador = ((m.get("score") or {}).get("fullTime") or {})
        gl, gv = marcador.get("home"), marcador.get("away")
        if gl is None or gv is None:
            continue
        local = m.get("homeTeam") or {}
        visitante = m.get("awayTeam") or {}
        nombre_l = local.get("shortName") or local.get("name")
        nombre_v = visitante.get("shortName") or visitante.get("name")
        if not nombre_l or not nombre_v:
            continue

        if local.get("id"):
            mapa[str(local["id"])] = nombre_l
        if visitante.get("id"):
            mapa[str(visitante["id"])] = nombre_v

        fecha_txt = (m.get("utcDate") or "")[:10]
        salida.append({
            "local": nombre_l,
            "visitante": nombre_v,
            "id_local": local.get("id"),
            "id_visitante": visitante.get("id"),
            "goles_local": int(gl),
            "goles_visitante": int(gv),
            "dias_atras": _dias_desde(fecha_txt, hoy),
            "temporada": temporada,
            "fecha": fecha_txt,
        })
    salida.sort(key=lambda p: p.get("fecha") or "")
    return salida, mapa, None


def equipos_oficiales(liga):
    #Plantilla COMPLETA de la liga, con todos los nombres que football-data.org
    #le da a cada equipo. Devuelve ({corto: [variantes]}, error).
    #
    #POR QUE NO SE DEDUCE DE LOS PARTIDOS:
    #  partidos_temporada() solo ve los equipos que ya jugaron un partido
    #  TERMINADO. En agosto, con la temporada recien empezada, eso son cuatro
    #  equipos o ninguno. Con esa lista a medias el emparejado del historico
    #  falla en silencio: Barcelona no aparece, no empareja, y el motor termina
    #  con dos "Barcelona" distintos y media historia en cada uno.
    #  Este endpoint devuelve la plantilla entera juegue quien juegue.
    #
    #POR QUE VARIAS VARIANTES POR EQUIPO:
    #  El nombre corto no siempre se parece al del historico: football-data.org
    #  dice "Barça" y "PSG", y el historico dice "Barcelona" y "Paris SG".
    #  Contra el nombre largo ("FC Barcelona", "Paris Saint-Germain FC") si
    #  emparejan. Se guardan las tres formas y basta con que UNA coincida.
    #
    #COSTE: una peticion por liga. Se cachea 24 horas porque una plantilla no
    #cambia a mitad de temporada.
    llave = f"equipos_oficiales_{liga}"
    try:
        guardado = cache.get(llave)
    except Exception:
        guardado = None
    if guardado is not None:
        return guardado, None

    crudo, error = _pedir_fd(f"competitions/{liga}/teams")
    if error:
        return {}, error

    equipos = {}
    for t in crudo.get("teams", []) or []:
        corto = (t.get("shortName") or t.get("name") or "").strip()
        if not corto:
            continue
        variantes = [v for v in (t.get("name"), t.get("shortName"), t.get("tla")) if v]
        equipos[corto] = variantes
    if not equipos:
        return {}, "sin_datos"

    try:
        cache.set(llave, equipos, 86400)
    except Exception:
        pass
    return equipos, None


def historial_liga(liga, temporadas=2, historico=5, informe=None):
    #Junta varias temporadas. Cuantas mas, mejor separa el modelo la fuerza
    #real del ruido; el decaimiento temporal ya se encarga de que lo viejo
    #pese poco. OJO: cada temporada extra es otra peticion a la API.
    #
    #Si una temporada falla (la API gratuita no siempre da las antiguas) se
    #sigue con las que si hay. Solo se devuelve error si no hay NINGUNA.
    actual = temporada_actual()
    todos = []
    mapa = {}
    ultimo_error = None
    for i in range(temporadas):
        datos, mapa_i, error = partidos_temporada(liga, actual - i)
        if error:
            ultimo_error = error
            continue
        todos.extend(datos)
        #las temporadas mas recientes mandan sobre el nombre del equipo
        for k, v in mapa_i.items():
            mapa.setdefault(k, v)
    if not todos:
        return [], {}, (ultimo_error or ERROR_RED)

    #--- Refuerzo con el historico de football-data.co.uk ---
    #Se agrega DESPUES y no antes a proposito: football-data.org manda sobre
    #los nombres (es el que usa el frontend) y sobre los partidos recientes.
    #El CSV solo aporta lo que falta: temporadas viejas y cuotas de cierre.
    #Si el sitio no responde, no pasa nada: el motor sigue con lo que ya tenia.
    #
    #El informe sale por un diccionario aparte y NO dentro del mapa de ids:
    #ese mapa se guarda en base de datos y se usa para traducir nombres, asi
    #que meterle una clave que no es un equipo lo rompe mas adelante.
    if historico:
        agregados, informe_hist = _agregar_historico(liga, todos, mapa, historico)
        if agregados:
            todos = agregados
        if informe is not None:
            informe.update(informe_hist)

    todos.sort(key=lambda p: (p.get("temporada", 0), p.get("fecha") or ""))
    return todos, mapa, None


def _clave_partido(p):
    #Un partido es el mismo si son los mismos dos equipos el mismo dia.
    #Sirve para no contar dos veces los partidos que estan en las dos fuentes:
    #un partido duplicado pesaria el doble en el ajuste y deformaria al equipo.
    from analizador.api_historico import normalizar
    return (p.get("fecha") or "", normalizar(p.get("local")), normalizar(p.get("visitante")))


def _agregar_historico(liga, ya_tengo, mapa, temporadas):
    #Devuelve (lista_completa, informe). Lista vacia si no se pudo agregar nada.
    try:
        from analizador import api_historico
    except Exception:
        return [], {}
    if liga not in api_historico.LIGAS_HISTORICO:
        return [], {}

    #Los nombres oficiales son los que ya conoce el proyecto. El historico se
    #traduce a esos: si el ajuste guardara "Ath Madrid" y el frontend pidiera
    #"Atletico Madrid", el motor no encontraria al equipo, lo trataria como
    #promedio y daria un pronostico plano SIN avisar de nada. Ese es el fallo
    #silencioso que hay que evitar, y por eso el informe viaja de vuelta.
    #
    #Se pide la plantilla COMPLETA con todas sus variantes de nombre. Deducir
    #los nombres de los partidos ya jugados no sirve: al empezar la temporada
    #esa lista esta casi vacia y medio historico se queda sin emparejar.
    oficiales, error_eq = equipos_oficiales(liga)
    if error_eq or not oficiales:
        #Red de seguridad: si el endpoint falla se usa lo que haya en el mapa.
        #Peor emparejado, pero el motor no se queda sin historico.
        oficiales = {n: [n] for n in sorted(set(mapa.values())) if n}
    if not oficiales:
        return [], {}
    try:
        partidos, informe, error = api_historico.historial(
            liga, temporadas=temporadas, nombres_oficiales=oficiales)
    except Exception:
        return [], {}
    if error or not partidos:
        return [], {}

    vistos = {_clave_partido(p) for p in ya_tengo}
    nuevos = []
    for p in partidos:
        clave = _clave_partido(p)
        if clave in vistos:
            continue
        vistos.add(clave)
        anio = int(p["fecha"][:4])
        nuevos.append({
            "local": p["local"],
            "visitante": p["visitante"],
            "goles_local": p["goles_local"],
            "goles_visitante": p["goles_visitante"],
            "dias_atras": p["dias_atras"],
            "temporada": anio if int(p["fecha"][5:7]) >= 7 else anio - 1,
            "fecha": p["fecha"],
            "cuotas": p.get("cuotas"),
        })
    informe["agregados"] = len(nuevos)
    return ya_tengo + nuevos, informe


def construir_ajuste(liga, temporadas=2, xi=None, ridge=None, afinar=False):
    #Ajusta Dixon-Coles + Elo para una liga.
    #Devuelve (ajuste, tabla_elo, mapa_ids, error, info_afinado).
    #
    #xi y ridge: si se pasan, se usan esos. Si no, los de fabrica.
    #afinar=True: busca los mejores para ESTA liga con sus propios datos.
    #  Cuesta ~60 ajustes (medio minuto por liga) y CERO peticiones a la API,
    #  porque reutiliza los partidos que ya se descargaron aqui mismo.
    if liga in LIGAS_DE_COPA and temporadas < 3:
        temporadas = 3   #en copa hacen falta mas temporadas para tener datos

    partidos, mapa, error = historial_liga(liga, temporadas)
    if error and not partidos:
        return None, None, {}, error, None
    if len(partidos) < 20:
        return None, None, {}, "sin_datos", None

    info = None
    if afinar:
        from analizador.motor import afinado
        xi, ridge, info = afinado.afinar(partidos)

    try:
        if xi is not None and ridge is not None:
            ajuste = tasas.ajustar(partidos, xi=xi, ridge=ridge)
        else:
            ajuste = tasas.ajustar(partidos)
    except ValueError:
        return None, None, {}, "sin_datos", None
    tabla = mod_elo.calcular(partidos)
    return ajuste, tabla, mapa, None, info


def ajuste_en_cache(liga, temporadas=2, segundos=21600):
    #Version en cache para no reajustar en cada peticion web. El ajuste tarda
    #un par de segundos; con esto solo pasa una vez cada 6 horas.
    #Lo ideal es tenerlo en base de datos con el comando ajustar_motor: esta
    #funcion es la red de seguridad para cuando ese comando aun no se corrio.
    #La cache va dentro de try/except a proposito: si la tabla de cache no
    #existe o falla, el motor tiene que seguir dando pronosticos (mas lento,
    #pero funcionando). Un problema de cache no puede tumbar el analizador.
    llave = f"motor_ajuste_{liga}_{temporadas}"
    try:
        guardado = cache.get(llave)
    except Exception:
        guardado = None
    if guardado is not None:
        return (tasas.AjusteLiga.desde_dict(guardado["ajuste"]),
                mod_elo.TablaElo.desde_dict(guardado["elo"]),
                guardado.get("mapa", {}), None)

    ajuste, tabla, mapa, error, _ = construir_ajuste(liga, temporadas)
    if error:
        return None, None, {}, error
    try:
        cache.set(llave, {"ajuste": ajuste.a_dict(), "elo": tabla.a_dict(),
                          "mapa": mapa}, segundos)
    except Exception:
        pass
    return ajuste, tabla, mapa, None


def nombre_de_equipo(valor, mapa):
    #Acepta un id numerico o un nombre y devuelve siempre el nombre con el que
    #el equipo esta guardado en el ajuste. Asi el frontend puede mandar
    #cualquiera de los dos sin que se rompa nada.
    if valor is None:
        return ""
    clave = str(valor).strip()
    if clave in (mapa or {}):
        return mapa[clave]
    return clave


def casas_desde_api(liga, nombre_local, nombre_visitante):
    #Adapta lo que devuelve api_cuotas al formato que espera el motor.
    #Devuelve (lista_de_casas, error).
    #
    #DIFERENCIA IMPORTANTE con lo que hay hoy: api_cuotas.cuotas_partido()
    #devuelve la MEJOR cuota de cada resultado, mezclando casas distintas. Eso
    #sirve para apostar, pero NO para predecir: un libro hecho con la mejor
    #cuota de tres casas suma menos de 1 y da probabilidades infladas.
    #Aqui se devuelve CASA POR CASA para que el motor limpie cada libro entero
    #y luego tome la mediana. La mejor cuota se sigue usando, pero solo para
    #calcular el valor de la apuesta.
    from analizador.api_cuotas import _cuotas_liga, _mismo_equipo

    partidos, error = _cuotas_liga(liga)
    if error:
        return [], error

    for p in partidos:
        if not (_mismo_equipo(p.get("home_team", ""), nombre_local)
                and _mismo_equipo(p.get("away_team", ""), nombre_visitante)):
            continue
        casas = []
        for casa in p.get("bookmakers", []) or []:
            precios = {}
            for mercado in casa.get("markets", []) or []:
                if mercado.get("key") != "h2h":
                    continue
                for salida in mercado.get("outcomes", []) or []:
                    nombre = salida.get("name", "")
                    try:
                        precio = float(salida.get("price"))
                    except (TypeError, ValueError):
                        continue
                    if precio <= 1.0:
                        continue
                    if nombre == "Draw":
                        precios["empate"] = precio
                    elif _mismo_equipo(nombre, p.get("home_team", "")):
                        precios["local"] = precio
                    elif _mismo_equipo(nombre, p.get("away_team", "")):
                        precios["visitante"] = precio
            #solo sirven las casas con el libro COMPLETO: si falta una de las
            #tres cuotas no se puede quitar el margen y ese libro se descarta
            if len(precios) == 3:
                precios["casa"] = casa.get("title", "")
                casas.append(precios)
        return casas, (None if casas else "sin_datos")

    return [], "sin_partido"