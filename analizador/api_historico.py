#FUENTE HISTORICA — 62.000 partidos con cuotas, leidos de disco.
#
#POR QUE NO SE CONECTA A football-data.co.uk:
#  Ese sitio esta bloqueado desde tu red. Falla en el puerto 443 Y en el 80,
#  con y sin www, con y sin navegador simulado: no es un problema de SSL ni de
#  User-Agent, es que las peticiones no llegan al dominio. Es un sitio lleno de
#  publicidad de casas de apuestas y los proveedores de internet y los
#  antivirus lo filtran. No hay codigo que arregle eso.
#
#  La solucion no es insistir con ese dominio: es traer los MISMOS datos de
#  otro lado. El comando "descargar_historico" los baja desde GitHub (que si te
#  funciona, el proyecto ya usa git) y los deja partidos por liga en la carpeta
#  datos_historicos/. Este archivo solo lee de ahi.
#
#VENTAJA DE LEER DE DISCO, mas alla de esquivar el bloqueo:
#  Cero peticiones de red al ajustar el motor. Antes cada ajuste dependia de
#  que un servidor respondiera; ahora es un archivo local de 700 KB que se lee
#  en cinco centesimas de segundo. Menos partes moviles = menos cosas que se
#  pueden caer en mitad de una demostracion.
#
#QUE HAY EN LOS DATOS (medido, no supuesto):
#  PL 9410 | PD 9008 | SA 9012 | BL1 7522 | FL1 8756 | DED 7288 | PPL 6626 |
#  BSA 4849   ->  62.471 partidos, 61.840 con cuotas (99%), desde el año 2000.
#  Las ligas europeas llegan hasta mayo de 2025; Brasil hasta diciembre 2024.
#
#HASTA DONDE LLEGA — importante tenerlo claro:
#  El historico NO trae la temporada en curso. Eso lo sigue cubriendo
#  football-data.org, que es la fuente de los partidos recientes y de los
#  nombres oficiales. El historico aporta lo que football-data.org no puede:
#  profundidad para el ajuste y cuotas del pasado para medir el motor.
#
#Solo libreria estandar. Sin pandas y sin red.
import csv
import os
import unicodedata
from datetime import date

ERROR_SIN_LIGA = "sin_liga"
ERROR_SIN_ARCHIVO = "sin_archivo"
ERROR_SIN_DATOS = "sin_datos"

#Codigo de liga de xGol -> codigo de division en los datos de origen
LIGAS_HISTORICO = {
    "PL":  "E0",
    "PD":  "SP1",
    "SA":  "I1",
    "BL1": "D1",
    "FL1": "F1",
    "DED": "N1",
    "PPL": "P1",
    "BSA": "BRA",
}

#Columnas de los archivos ya partidos. El orden importa: es el mismo con el
#que los escribe descargar_historico.
COLUMNAS = [
    "MatchDate", "HomeTeam", "AwayTeam", "FTHome", "FTAway",
    "OddHome", "OddDraw", "OddAway", "Over25", "Under25",
    "HomeShots", "AwayShots", "HomeTarget", "AwayTarget",
    "HomeCorners", "AwayCorners",
]

TEMPORADAS_POR_DEFECTO = 5

#Palabras que muchos clubes comparten y que por si solas NO identifican a
#nadie. "Sheffield United" y "Manchester United" comparten "united" y no
#tienen nada que ver; "Coventry City" y "Man City" tampoco; "Santander" y
#"Real Sociedad" solo comparten "real".
#
#No se borran como el RUIDO, porque sumadas a otra palabra si aportan
#("West Ham United" es mas preciso que "West Ham"). Lo que se hace es que
#pesen poco: dos nombres que SOLO comparten una de estas no llegan al umbral
#y se quedan sin emparejar, que es lo correcto.
GENERICAS = {
    "united", "city", "town", "county", "albion", "wanderers", "rovers",
    "real", "deportivo", "atletico", "athletico", "athletic", "racing",
    "union", "sporting", "sport", "olympique", "stade", "borussia",
    "eintracht", "fortuna", "hertha", "vitoria", "america", "le", "saint",
    "st", "san", "sao", "nacional", "internacional", "juventude",
}
PESO_GENERICA = 0.2

#Diferencia minima entre el mejor candidato y el segundo para dar un
#emparejado por bueno. Por debajo de esto se considera empate y no se empareja:
#ver el comentario largo en emparejar_nombres().
MARGEN_AMBIGUO = 0.15

#Palabras de relleno que sobran al comparar nombres entre proveedores.
#Son siglas de tipo de club, no parte del nombre: quitarlas hace que
#"VfB Stuttgart" y "Stuttgart" se vean como lo que son, el mismo equipo.
RUIDO = {
    "fc", "cf", "sc", "ac", "afc", "cd", "ec", "se", "ss", "as", "rc", "ca",
    "club", "clube", "de", "do", "da", "the", "futebol", "football", "calcio",
    "cp", "ud", "sd", "bk", "if", "cr", "fr", "sad", "cfc", "gd", "rcd",
    "aj", "og", "ogc", "us", "vfl", "vfb", "tsg", "fsv", "ksv", "sv", "tsv",
    "bc", "acf", "ssc",
    #NO agregar aqui "sp": el historico escribe "Sp Lisbon" y "Sp Braga", y
    #quitarle el "sp" los deja en "Lisbon" y "Braga", que ya no emparejan con
    #"Sporting CP". Se resuelven con alias, no con ruido.
}

#Equipos donde el nombre corto del historico no se parece lo bastante al de
#football-data.org como para que el emparejado automatico lo resuelva solo.
#
#La tabla es corta a proposito: la mayoria los resuelve emparejar_nombres()
#comparando palabras. Aqui van los casos donde eso fallaria o, peor, acertaria
#el equipo EQUIVOCADO ("Ath Madrid" y "Athletic Club" comparten palabra y no
#son el mismo club).
ALIAS_HISTORICO = {
    #España
    "ath madrid": "atletico madrid",
    "ath bilbao": "athletic club",
    "espanol": "espanyol",
    "sociedad": "real sociedad",
    "vallecano": "rayo vallecano",
    "betis": "real betis",
    "celta": "celta vigo",
    "la coruna": "deportivo la coruna",
    #Inglaterra
    "man united": "manchester united",
    "man city": "manchester city",
    "newcastle": "newcastle united",
    "tottenham": "tottenham hotspur",
    "wolves": "wolverhampton wanderers",
    "nottm forest": "nottingham forest",
    "leeds": "leeds united",
    "west ham": "west ham united",
    "west brom": "west bromwich albion",
    "brighton": "brighton hove albion",
    #Italia
    "milan": "ac milan",
    "inter": "inter milan",
    "verona": "hellas verona",
    "roma": "as roma",
    #Alemania
    "bayern munich": "bayern munchen",
    "ein frankfurt": "eintracht frankfurt",
    "leverkusen": "bayer leverkusen",
    "dortmund": "borussia dortmund",
    "mgladbach": "borussia monchengladbach",
    "hoffenheim": "tsg hoffenheim",
    "stuttgart": "vfb stuttgart",
    "wolfsburg": "vfl wolfsburg",
    "leipzig": "rb leipzig",
    #Francia
    "paris sg": "paris saint germain",
    "marseille": "olympique marseille",
    "lyon": "olympique lyonnais",
    "st etienne": "saint etienne",
    #Paises Bajos
    "psv eindhoven": "psv",
    "az alkmaar": "az",
    "nijmegen": "nec nijmegen",
    #Brasil — el historico usa sufijos de estado y los oficiales no.
    #Sin estos alias los tres "Atletico" se pisan entre si.
    "atletico mg": "atletico mineiro",
    "athletico pr": "athletico paranaense",
    "atletico go": "atletico goianiense",
    "america mg": "america mineiro",
    "flamengo rj": "flamengo",
    "botafogo rj": "botafogo",
    "vasco": "vasco gama",
    "gremio": "gremio",
    "sao paulo": "sao paulo",
    "bragantino": "bragantino",
    #Portugal
    "estrela": "estrela amadora",
    "guimaraes": "vitoria guimaraes",
    "sp lisbon": "sporting cp",
    "sp braga": "sc braga",
}


# ============================================================
#  DONDE VIVEN LOS ARCHIVOS
# ============================================================
def carpeta_datos():
    #datos_historicos/ al lado de manage.py. Se calcula desde settings para que
    #funcione igual en tu Windows y en el servidor, sin rutas escritas a mano.
    try:
        from django.conf import settings
        return os.path.join(str(settings.BASE_DIR), "datos_historicos")
    except Exception:
        #Fuera de Django (una prueba suelta, por ejemplo) se usa la ruta
        #relativa a este mismo archivo. Nunca revienta por esto.
        aqui = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(os.path.dirname(aqui), "datos_historicos")


def archivo_de_liga(liga):
    return os.path.join(carpeta_datos(), f"{liga}.csv")


def hay_datos(liga):
    return os.path.exists(archivo_de_liga(liga))


def ligas_descargadas():
    return sorted(l for l in LIGAS_HISTORICO if hay_datos(l))


# ============================================================
#  NOMBRES
#  Todo el valor de este archivo se cae si un equipo no se
#  reconoce como el mismo que ya conoce el proyecto: el motor lo
#  trataria como equipo promedio y daria un pronostico plano SIN
#  avisar de nada. Por eso emparejar_nombres devuelve SIEMPRE la
#  lista de lo que no pudo emparejar.
# ============================================================
def normalizar(nombre):
    #Minusculas, sin tildes, sin puntuacion y sin palabras de relleno.
    #Quitar la puntuacion tambien unifica las erratas del origen:
    #"Nott'm Forest" y "Nottm Forest" caen las dos en "nottm forest".
    texto = unicodedata.normalize("NFKD", str(nombre or ""))
    texto = "".join(c for c in texto if not unicodedata.combining(c)).lower()
    #Los apostrofos se BORRAN, no se cambian por espacio. Si se cambian,
    #"Nott'm Forest" queda en "nott m forest" (tres palabras) en vez de
    #"nottm forest", y deja de encontrar su alias. Lo mismo con "M'gladbach".
    for signo in ("'", "\u2019", "\u02bc", "`", "\u00b4"):
        texto = texto.replace(signo, "")
    limpio = "".join(c if c.isalnum() or c.isspace() else " " for c in texto)
    #Se descartan los numeros sueltos: son años de fundacion, no nombre.
    #"Bologna FC 1909" y "Bologna" son el mismo club; "1. FSV Mainz 05" y
    #"Mainz" tambien. Sin esto, esos numeros bajan el parecido lo suficiente
    #como para que dos formas del mismo equipo no lleguen al umbral.
    palabras = [p for p in limpio.split()
                if p and p not in RUIDO and not p.isdigit()]
    base = " ".join(palabras)
    alias = ALIAS_HISTORICO.get(base)
    if alias:
        #El resultado del alias pasa por el mismo filtro que todo lo demas.
        #Si no, "ath bilbao" quedaria en "athletic club" mientras el nombre
        #oficial "Athletic Club" queda en "athletic", y dos formas del mismo
        #equipo se compararian como si fueran parecidas a medias.
        return " ".join(p for p in alias.split() if p not in RUIDO)
    return base


def _peso(palabra):
    return PESO_GENERICA if palabra in GENERICAS else 1.0


def _parecido(a, b):
    #Cuanto se parecen dos nombres ya normalizados, de 0 a 1.
    #
    #Se comparan PALABRAS, no letras: "man united" y "manchester united"
    #comparten "united", y eso vale mas que cualquier distancia de caracteres.
    #Pero cada palabra pesa segun lo que identifique: "united" y "city" las
    #tiene medio mundo, "wolverhampton" solo uno. Sin esa diferencia,
    #"Sheffield United" puntua igual contra "Man United" que contra
    #"Newcastle United", y el emparejado se convierte en una moneda al aire.
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    pa, pb = set(a.split()), set(b.split())
    comunes = pa & pb
    if not comunes:
        #ultimo intento: uno contenido en el otro ("koln" dentro de "1 fc koln")
        return 0.75 if (a in b or b in a) else 0.0
    peso_comun = sum(_peso(p) for p in comunes)
    peso_mayor = max(sum(_peso(p) for p in pa), sum(_peso(p) for p in pb))
    return peso_comun / peso_mayor if peso_mayor else 0.0


def emparejar_nombres(nombres_csv, nombres_oficiales, umbral=0.5):
    #Traduce los nombres del historico a los que YA usa el proyecto.
    #
    #nombres_oficiales puede venir de dos formas:
    #   - lista de nombres:  ["Barça", "Real Madrid", ...]
    #   - dict con variantes: {"Barça": ["FC Barcelona", "Barça", "FCB"], ...}
    #
    #La segunda es la buena, y la razon es concreta: football-data.org llama
    #"Barça" al FC Barcelona y "PSG" al Paris Saint-Germain. El historico los
    #llama "Barcelona" y "Paris SG". Comparando solo contra el nombre corto,
    #NINGUNO de los dos empareja, y el motor termina tratando a Barcelona como
    #dos equipos distintos con media historia cada uno. Comparando tambien
    #contra el nombre largo ("FC Barcelona", "Paris Saint-Germain FC") los dos
    #emparejan sin problema.
    #
    #Se empareja contra los oficiales y no al reves porque el frontend siempre
    #pide por el nombre corto: si el ajuste se guardara con nombres del
    #historico, el motor no encontraria a nadie.
    #
    #Devuelve (traduccion, sin_emparejar).
    if isinstance(nombres_oficiales, dict):
        pares = nombres_oficiales.items()
    else:
        pares = ((n, [n]) for n in nombres_oficiales if n)

    #(nombre canonico, clave normalizada de una de sus variantes)
    oficiales = []
    for canonico, variantes in pares:
        if not canonico:
            continue
        for v in ([variantes] if isinstance(variantes, str) else variantes):
            clave = normalizar(v)
            if clave:
                oficiales.append((canonico, clave))

    traduccion = {}
    sin_emparejar = []
    ambiguos = {}
    for bruto in nombres_csv:
        clave = normalizar(bruto)
        if not clave:
            continue
        #Se guarda el mejor Y el segundo mejor de OTRO equipo distinto.
        mejor_nombre, mejor_puntaje = None, 0.0
        rival_nombre, rival_puntaje = None, 0.0
        for canonico, clave_oficial in oficiales:
            puntaje = _parecido(clave, clave_oficial)
            if puntaje > mejor_puntaje:
                if mejor_nombre and mejor_nombre != canonico:
                    rival_nombre, rival_puntaje = mejor_nombre, mejor_puntaje
                mejor_nombre, mejor_puntaje = canonico, puntaje
            elif canonico != mejor_nombre and puntaje > rival_puntaje:
                rival_nombre, rival_puntaje = canonico, puntaje

        if not mejor_nombre or mejor_puntaje < umbral:
            sin_emparejar.append(bruto)
            continue

        #EMPATE = NO SE EMPAREJA. Esto es deliberado y es lo mas importante de
        #toda la funcion.
        #
        #En Brasil hay tres equipos "Atletico" (Mineiro, Paranaense,
        #Goianiense) y los tres puntuan igual contra "Atletico-MG" porque solo
        #comparten la palabra "atletico". Si se desempata por el orden de la
        #lista, doscientos partidos del Mineiro pueden acabar sumandose al
        #Goianiense. Ese error NO se ve por ningun lado: el motor no falla,
        #simplemente miente sobre dos equipos a la vez.
        #
        #Dejarlo sin emparejar es mucho menos malo: el equipo aparece en el
        #informe, se ve, y se arregla con un alias. Preferimos no saber a
        #saber mal.
        if rival_nombre and (mejor_puntaje - rival_puntaje) < MARGEN_AMBIGUO:
            sin_emparejar.append(bruto)
            ambiguos[bruto] = [mejor_nombre, rival_nombre]
            continue

        traduccion[bruto] = mejor_nombre
    return traduccion, sin_emparejar, ambiguos


def candidatos(nombre_oficial, nombres_csv, cuantos=3):
    #Los nombres del historico que MAS se parecen a un equipo oficial, con su
    #puntaje. Sirve para responder la pregunta util cuando algo no empareja:
    #"este equipo no tiene historia, pero, se parece a algo de lo que hay?"
    #
    #Si el mejor candidato ronda 0.4 hay un alias que escribir. Si todos estan
    #en 0.0, el equipo simplemente no jugo nunca en esta liga y no hay nada que
    #arreglar: es un ascendido.
    variantes = ([nombre_oficial] if isinstance(nombre_oficial, str)
                 else list(nombre_oficial))
    claves = [normalizar(v) for v in variantes if v]
    puntuados = []
    for bruto in nombres_csv:
        clave = normalizar(bruto)
        if not clave:
            continue
        puntuados.append((max((_parecido(clave, k) for k in claves), default=0.0), bruto))
    puntuados.sort(reverse=True)
    return puntuados[:cuantos]


def sin_historia(traduccion, nombres_oficiales):
    #LA COMPROBACION QUE DE VERDAD IMPORTA, y al reves de la obvia.
    #
    #Que un equipo del historico no empareje casi nunca es grave: suele ser un
    #equipo que descendio y ya no juega. Lo grave es lo contrario: que un
    #equipo que SI juega hoy se quede sin ningun partido de historia. Ese es el
    #que el motor va a tratar como "equipo promedio" y sobre el que va a dar un
    #pronostico plano sin avisar de nada.
    #
    #Devuelve la lista de equipos oficiales a los que no llego ni un partido.
    canonicos = set(nombres_oficiales.keys() if isinstance(nombres_oficiales, dict)
                    else nombres_oficiales)
    con_historia = set(traduccion.values())
    return sorted(canonicos - con_historia)


# ============================================================
#  LECTURA
# ============================================================
def temporada_actual():
    #Misma regla que motor_datos: las ligas europeas se nombran por el año en
    #que arrancan, y de enero a junio seguimos en la temporada anterior.
    hoy = date.today()
    return hoy.year if hoy.month >= 7 else hoy.year - 1


def _numero(valor):
    valor = (valor or "").strip()
    if not valor:
        return None
    try:
        return float(valor)
    except ValueError:
        return None


def _entero(valor):
    n = _numero(valor)
    return int(n) if n is not None else None


def _temporada_de(fecha_iso, liga):
    #Brasil juega por año natural; las europeas de agosto a mayo.
    anio = int(fecha_iso[:4])
    if liga == "BSA":
        return anio
    return anio if int(fecha_iso[5:7]) >= 7 else anio - 1


def leer(liga):
    #Todos los partidos guardados de una liga. Devuelve (partidos, error).
    if liga not in LIGAS_HISTORICO:
        return [], ERROR_SIN_LIGA
    ruta = archivo_de_liga(liga)
    if not os.path.exists(ruta):
        return [], ERROR_SIN_ARCHIVO

    hoy = date.today()
    salida = []
    try:
        with open(ruta, encoding="utf-8", errors="replace", newline="") as fh:
            for fila in csv.DictReader(fh):
                local = (fila.get("HomeTeam") or "").strip()
                visitante = (fila.get("AwayTeam") or "").strip()
                if not local or not visitante or local == visitante:
                    continue
                gl = _entero(fila.get("FTHome"))
                gv = _entero(fila.get("FTAway"))
                if gl is None or gv is None or gl < 0 or gv < 0:
                    continue
                fecha = (fila.get("MatchDate") or "").strip()[:10]
                if len(fecha) != 10:
                    continue
                try:
                    a, m, d = (int(x) for x in fecha.split("-"))
                    dias = (hoy - date(a, m, d)).days
                except ValueError:
                    continue
                if dias < 0:
                    continue

                partido = {
                    "local": local,
                    "visitante": visitante,
                    "goles_local": gl,
                    "goles_visitante": gv,
                    "dias_atras": dias,
                    "fecha": fecha,
                    "temporada": _temporada_de(fecha, liga),
                    "neutral": False,
                }

                #CUOTAS. Se usan OddHome/Draw/Away, que son el libro COMPLETO
                #de una sola casa (Bet365). Eso es lo que el motor sabe limpiar
                #con Shin en mercado.py.
                #
                #NO se usan MaxHome/MaxDraw/MaxAway aunque esten disponibles y
                #parezcan mejores: son la cuota mas alta de ~17 casas distintas,
                #y un libro armado con la mejor cuota de cada casa suma MENOS de
                #1. Convertirlo a probabilidad da numeros inflados. Es el mismo
                #error que motor_datos ya evita con las cuotas en vivo.
                cl = _numero(fila.get("OddHome"))
                ce = _numero(fila.get("OddDraw"))
                cv = _numero(fila.get("OddAway"))
                if cl and ce and cv and min(cl, ce, cv) > 1.0:
                    partido["cuotas"] = {"local": cl, "empate": ce, "visitante": cv}

                #Cuota de mas/menos 2.5 goles. nucleo.pronosticar() la acepta
                #como prob_mercado_mas_25, y con ella el mercado deja de ser
                #solo un 1X2: aporta tambien cuantos goles espera el mercado.
                mas = _numero(fila.get("Over25"))
                menos = _numero(fila.get("Under25"))
                if mas and menos and mas > 1.0 and menos > 1.0:
                    inv_mas, inv_menos = 1.0 / mas, 1.0 / menos
                    partido["prob_mas_25"] = inv_mas / (inv_mas + inv_menos)

                tl, tv = _entero(fila.get("HomeShots")), _entero(fila.get("AwayShots"))
                if tl is not None and tv is not None:
                    partido["tiros_local"], partido["tiros_visitante"] = tl, tv
                kl, kv = _entero(fila.get("HomeCorners")), _entero(fila.get("AwayCorners"))
                if kl is not None and kv is not None:
                    partido["corners_local"], partido["corners_visitante"] = kl, kv

                salida.append(partido)
    except OSError:
        return [], ERROR_SIN_ARCHIVO

    if not salida:
        return [], ERROR_SIN_DATOS
    salida.sort(key=lambda p: p["fecha"])
    return salida, None


# ============================================================
#  API PUBLICA — lo unico que consume el resto del proyecto
# ============================================================
def historial(liga, temporadas=TEMPORADAS_POR_DEFECTO, nombres_oficiales=None):
    #Lo que el motor necesita de una liga, listo para tasas.ajustar().
    #Devuelve (partidos, informe, error).
    #
    #temporadas: cuantas hacia atras conservar. Mas temporadas dan un ajuste
    #mas estable, y el decaimiento temporal de tasas.py ya se encarga de que lo
    #viejo pese poco. Pasar 0 o None trae todo lo que haya.
    todos, error = leer(liga)
    if error:
        return [], {}, error

    if temporadas:
        #Se cuentan las N temporadas mas recientes QUE HAY EN LOS DATOS, no las
        #N contadas desde hoy. La diferencia importa: el historico termina donde
        #termina, y si se contara desde la fecha de hoy, un archivo de hace un
        #año devolveria cero partidos y el motor se quedaria sin historia sin
        #que nadie entienda por que.
        disponibles = sorted({p["temporada"] for p in todos}, reverse=True)
        conservar = set(disponibles[:int(temporadas)])
        todos = [p for p in todos if p["temporada"] in conservar]
    if not todos:
        return [], {}, ERROR_SIN_DATOS

    informe = {
        "liga": liga,
        "partidos": len(todos),
        "temporadas": sorted({p["temporada"] for p in todos}),
        "desde": todos[0]["fecha"],
        "hasta": todos[-1]["fecha"],
        "con_cuotas": sum(1 for p in todos if p.get("cuotas")),
        "sin_emparejar": [],
    }

    if nombres_oficiales:
        equipos = sorted({p["local"] for p in todos} | {p["visitante"] for p in todos})
        traduccion, sin_emparejar, ambiguos = emparejar_nombres(equipos, nombres_oficiales)
        #Un equipo sin emparejar NO se descarta: se deja con su nombre de
        #origen. Borrar sus partidos deformaria el ajuste de sus rivales, que
        #si estan bien. Queda en el informe para poder revisarlo.
        for p in todos:
            p["local"] = traduccion.get(p["local"], p["local"])
            p["visitante"] = traduccion.get(p["visitante"], p["visitante"])
        informe["sin_emparejar"] = sin_emparejar
        informe["ambiguos"] = ambiguos
        informe["equipos_emparejados"] = len(traduccion)
        #Los oficiales que se quedaron sin ni un partido. Esta es la alarma
        #de verdad; "sin_emparejar" casi siempre son equipos descendidos.
        informe["oficiales_sin_historia"] = sin_historia(traduccion, nombres_oficiales)

    return todos, informe, None


def casos_para_calibrar(liga, temporadas=None):
    #Partidos con cuota Y resultado, en el formato que espera evaluacion.py.
    #Esto es lo que permite medir el motor HOY sobre miles de partidos, en vez
    #de esperar meses a acumular predicciones propias.
    partidos, _, error = historial(liga, temporadas)
    if error:
        return [], error
    casos = []
    for p in partidos:
        if not p.get("cuotas"):
            continue
        gl, gv = p["goles_local"], p["goles_visitante"]
        casos.append({
            "liga": liga,
            "local": p["local"],
            "visitante": p["visitante"],
            "fecha": p["fecha"],
            "temporada": p["temporada"],
            "cuotas": p["cuotas"],
            "prob_mas_25": p.get("prob_mas_25"),
            "real": "local" if gl > gv else ("empate" if gl == gv else "visitante"),
            "goles_local": gl,
            "goles_visitante": gv,
        })
    return casos, None