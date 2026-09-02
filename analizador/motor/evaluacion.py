#EVALUACION — los numeros con los que defiendes el proyecto delante de alguien.
#
#Cuando presentes esto, la pregunta que te van a hacer es "y como sabes que
#funciona". Decir "acierta mucho" no vale. Estas son las metricas que si valen,
#y lo que significa cada numero en futbol 1X2:
#
#  LOG-PERDIDA  menor es mejor. Referencias reales:
#      1.099 = tirar una moneda de tres caras (no saber nada)
#      1.030 = solo mirar quien juega en casa
#      0.990 = modelo estadistico decente
#      0.960 = el mercado de apuestas (dificilisimo de batir)
#  RPS (Ranked Probability Score)  la metrica estandar en la literatura de
#      futbol. Como el Brier pero entiende que el 1X2 esta ORDENADO: fallar
#      diciendo "gana el local" cuando gano el visitante es peor que fallar
#      diciendo "empate". Menor es mejor. ~0.19-0.21 es un buen modelo.
#  ECE (error de calibracion)  cuanto miente el numero. 0.02 = cuando dices
#      70% pasa el 68-72% de las veces. Por debajo de 0.03 esta bien.
#  ACIERTO  el que todo el mundo entiende. En 1X2 lo normal esta entre 50% y
#      55%. Si alguien te promete 80%, o esta mintiendo o esta contando solo
#      los partidos que le salieron bien.
#  ROI  el unico que importa si se apuesta: rendimiento sobre lo apostado.
import math

ORDEN_1X2 = ("local", "empate", "visitante")


def log_perdida(casos):
    #casos: [{"probabilidades": {...}, "real": clave}]
    if not casos:
        return None
    total = 0.0
    for c in casos:
        total -= math.log(max(1e-9, c["probabilidades"].get(c["real"], 0.0)))
    return total / len(casos)


def brier(casos, claves=ORDEN_1X2):
    if not casos:
        return None
    total = 0.0
    for c in casos:
        for k in claves:
            real = 1.0 if c["real"] == k else 0.0
            total += (c["probabilidades"].get(k, 0.0) - real) ** 2
    return total / len(casos)


def rps(casos, orden=ORDEN_1X2):
    #Ranked Probability Score. Suma de diferencias acumuladas al cuadrado.
    if not casos:
        return None
    total = 0.0
    for c in casos:
        acum_p = 0.0
        acum_r = 0.0
        suma = 0.0
        for k in orden[:-1]:
            acum_p += c["probabilidades"].get(k, 0.0)
            acum_r += 1.0 if c["real"] == k else 0.0
            suma += (acum_p - acum_r) ** 2
        total += suma / (len(orden) - 1)
    return total / len(casos)


def acierto(casos):
    if not casos:
        return None
    buenos = 0
    for c in casos:
        elegido = max(c["probabilidades"], key=lambda k: c["probabilidades"][k])
        if elegido == c["real"]:
            buenos += 1
    return buenos / len(casos)


def error_calibracion(casos, tramos=10):
    #ECE: se agrupan las predicciones por confianza y se compara lo prometido
    #con lo que paso. Es la metrica de "el numero es sincero".
    if not casos:
        return None
    cubos = [{"n": 0, "conf": 0.0, "acc": 0} for _ in range(tramos)]
    for c in casos:
        elegido = max(c["probabilidades"], key=lambda k: c["probabilidades"][k])
        p = c["probabilidades"][elegido]
        i = min(tramos - 1, int(p * tramos))
        cubos[i]["n"] += 1
        cubos[i]["conf"] += p
        cubos[i]["acc"] += 1 if elegido == c["real"] else 0
    n_total = len(casos)
    ece = 0.0
    for cubo in cubos:
        if cubo["n"] == 0:
            continue
        conf = cubo["conf"] / cubo["n"]
        acc = cubo["acc"] / cubo["n"]
        ece += (cubo["n"] / n_total) * abs(conf - acc)
    return ece


def rendimiento_apuestas(casos, umbral_ev=0.03, cuota_minima=1.30, cuota_maxima=8.0):
    #Simula apostar 1 unidad SOLO cuando el modelo ve valor sobre la cuota.
    #casos necesitan ademas "cuotas": {"local": c, "empate": c, "visitante": c}
    apostadas = 0
    beneficio = 0.0
    ganadas = 0
    ev_total = 0.0
    for c in casos:
        cuotas = c.get("cuotas") or {}
        for k, cuota in cuotas.items():
            try:
                cuota = float(cuota)
            except (TypeError, ValueError):
                continue
            if not (cuota_minima <= cuota <= cuota_maxima):
                continue
            p = c["probabilidades"].get(k, 0.0)
            ev = p * (cuota - 1.0) - (1.0 - p)
            if ev < umbral_ev:
                continue
            apostadas += 1
            ev_total += ev
            if c["real"] == k:
                beneficio += cuota - 1.0
                ganadas += 1
            else:
                beneficio -= 1.0
    if apostadas == 0:
        return {"apuestas": 0, "roi": None, "beneficio": 0.0, "acierto": None,
                "ev_medio": None}
    return {
        "apuestas": apostadas,
        "beneficio": beneficio,
        "roi": beneficio / apostadas,
        "acierto": ganadas / apostadas,
        "ev_medio": ev_total / apostadas,
    }


def informe(casos, etiqueta=""):
    #Todo junto, listo para imprimir o mandar al frontend.
    return {
        "etiqueta": etiqueta,
        "partidos": len(casos),
        "log_perdida": log_perdida(casos),
        "rps": rps(casos),
        "brier": brier(casos),
        "acierto": acierto(casos),
        "ece": error_calibracion(casos),
    }


def comparar(informes):
    #Ordena varios informes por log-perdida: sirve para demostrar, con datos,
    #que el motor nuevo le gana al viejo. No lo digas: enseñalo.
    validos = [i for i in informes if i.get("log_perdida") is not None]
    return sorted(validos, key=lambda i: i["log_perdida"])


def referencia_aleatoria():
    #Linea base "no se nada": util para que se vea el suelo.
    return {"log_perdida": math.log(3), "rps": 0.2222, "acierto": 1 / 3}