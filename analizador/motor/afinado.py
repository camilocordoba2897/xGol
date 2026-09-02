#AFINADO POR LIGA — busca el decaimiento temporal y la regularizacion que
#mejor funcionan en CADA liga, con los datos de esa liga.
#
#El problema que resuelve: hasta ahora todas las ligas usaban los mismos dos
#numeros (xi=0.0045, ridge=0.020). Pero las ligas no envejecen igual. En una
#liga con mercado de fichajes fuerte y plantillas que cambian mucho, lo de hace
#seis meses vale poco. En una liga estable, sigue valiendo. Usar el mismo
#decaimiento para todas es dejar precision sobre la mesa.
#
#COMO SE MIDE (y por que asi):
#Se usa validacion "hacia adelante", que es la unica honesta con datos que
#tienen fecha. Se corta la temporada en un punto, se ajusta el modelo SOLO con
#lo anterior, y se predicen los partidos siguientes. Se repite moviendo el
#corte. Nunca se entrena con partidos posteriores a los que se predicen.
#
#Hacer una validacion cruzada normal aqui (mezclando partidos al azar) daria
#numeros preciosos y MENTIRA: el modelo estaria viendo el futuro para predecir
#el pasado, y elegiria un decaimiento absurdo.
#
#COSTE: cero peticiones a la API. Solo CPU, y se corre de vez en cuando.
import math

from . import tasas
from .probabilidad import matriz_marcadores, resultado_1x2

#Rejilla de candidatos. Vidas medias equivalentes:
#   0.0015 -> 462 dias    0.0030 -> 231 dias    0.0045 -> 154 dias
#   0.0065 -> 107 dias    0.0090 ->  77 dias
XI_CANDIDATOS = (0.0015, 0.0030, 0.0045, 0.0065, 0.0090)
#Ojo: cada combinacion cuesta un ajuste completo por pliegue. 5 xi x 3 ridge
#x 4 pliegues = 60 ajustes por liga. Por eso el afinado NO va en el comando
#diario: se corre a mano de vez en cuando.
RIDGE_CANDIDATOS = (0.008, 0.020, 0.045)
PLIEGUES = 4
MINIMO_PARTIDOS = 250


def _resultado(p):
    if p["goles_local"] > p["goles_visitante"]:
        return "local"
    if p["goles_local"] == p["goles_visitante"]:
        return "empate"
    return "visitante"


def _log_perdida(ajuste, partidos_prueba):
    #Log-perdida del ajuste sobre partidos que NO vio al entrenarse.
    total = 0.0
    n = 0
    for p in partidos_prueba:
        try:
            lam1, lam2 = ajuste.lambdas(p["local"], p["visitante"], p.get("neutral"))
            r = resultado_1x2(matriz_marcadores(lam1, lam2, ajuste.rho))
        except (ValueError, KeyError):
            continue
        prob = max(1e-9, r.get(_resultado(p), 0.0))
        total -= math.log(prob)
        n += 1
    return (total / n, n) if n else (None, 0)


def _rebasar(partidos, dias_corte):
    #El decaimiento mide la antiguedad respecto a HOY. Al validar hacia
    #adelante hay que medirla respecto a la fecha del corte, no a hoy: si no,
    #se estaria penalizando de mas a los partidos de entrenamiento y el xi que
    #salga elegido no serviria para predecir de verdad.
    salida = []
    for p in partidos:
        copia = dict(p)
        d = p.get("dias_atras")
        copia["dias_atras"] = None if d is None else max(0.0, d - dias_corte)
        salida.append(copia)
    return salida


def evaluar(partidos, xi, ridge, pliegues=PLIEGUES):
    #Devuelve (log_perdida_media, partidos_evaluados) para una combinacion.
    n = len(partidos)
    inicio = int(n * 0.55)
    paso = max(1, (n - inicio) // pliegues)

    suma = 0.0
    total = 0
    for k in range(pliegues):
        corte = inicio + k * paso
        fin = min(n, corte + paso)
        if corte < MINIMO_PARTIDOS // 2 or corte >= n:
            continue
        entren = partidos[:corte]
        prueba = partidos[corte:fin]
        if len(entren) < 60 or not prueba:
            continue

        #antiguedad medida desde el corte
        dias_corte = entren[-1].get("dias_atras")
        if dias_corte is not None:
            entren = _rebasar(entren, dias_corte)

        try:
            ajuste = tasas.ajustar(entren, xi=xi, ridge=ridge)
        except ValueError:
            continue
        perdida, cuantos = _log_perdida(ajuste, prueba)
        if perdida is None:
            continue
        suma += perdida * cuantos
        total += cuantos

    return ((suma / total), total) if total else (None, 0)


def afinar(partidos, xi_candidatos=XI_CANDIDATOS, ridge_candidatos=RIDGE_CANDIDATOS,
           pliegues=PLIEGUES, minimo=MINIMO_PARTIDOS, margen=0.002, registro=None):
    #Busca la mejor combinacion (xi, ridge) para esta liga.
    #
    #Devuelve (xi, ridge, informe). Si no hay datos suficientes o la mejora no
    #supera el margen, devuelve los valores de fabrica SIN TOCAR NADA.
    #
    #El margen existe porque una diferencia de 0.0005 en log-perdida sobre 300
    #partidos es ruido. Cambiar los parametros por eso es hacerse ilusiones.
    base = (tasas.XI_POR_DEFECTO, tasas.RIDGE_POR_DEFECTO)
    if len(partidos) < minimo:
        return base[0], base[1], {
            "afinado": False,
            "motivo": f"hacen falta al menos {minimo} partidos (hay {len(partidos)})",
        }

    perdida_base, n_base = evaluar(partidos, base[0], base[1], pliegues)
    if perdida_base is None:
        return base[0], base[1], {"afinado": False, "motivo": "no se pudo evaluar"}

    mejor = (base[0], base[1], perdida_base)
    tabla = []
    for xi in xi_candidatos:
        for ridge in ridge_candidatos:
            perdida, cuantos = evaluar(partidos, xi, ridge, pliegues)
            if perdida is None:
                continue
            tabla.append({"xi": xi, "ridge": ridge, "log_perdida": perdida,
                          "partidos": cuantos})
            if registro:
                registro(xi, ridge, perdida)
            if perdida < mejor[2]:
                mejor = (xi, ridge, perdida)

    mejora = perdida_base - mejor[2]
    if mejora < margen:
        return base[0], base[1], {
            "afinado": False,
            "log_perdida_fabrica": perdida_base,
            "log_perdida_mejor": mejor[2],
            "mejora": mejora,
            "tabla": tabla,
            "partidos_evaluados": n_base,
            "motivo": f"la mejora ({mejora:.4f}) no supera el margen de ruido ({margen})",
        }

    return mejor[0], mejor[1], {
        "afinado": True,
        "xi": mejor[0],
        "ridge": mejor[1],
        "vida_media_dias": math.log(2) / mejor[0],
        "log_perdida_fabrica": perdida_base,
        "log_perdida_mejor": mejor[2],
        "mejora": mejora,
        "tabla": tabla,
        "partidos_evaluados": n_base,
    }