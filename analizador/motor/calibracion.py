#CALIBRACION — que un 70% signifique de verdad 70%.
#
#Un modelo puede tener buen "olfato" (ordena bien los partidos) y a la vez
#mentir en el numero: decir 75% cuando la realidad de esos casos es 62%. Eso es
#exactamente lo que hace que un analizador "no se sienta real". El olfato y la
#sinceridad del numero son dos cosas distintas y se arreglan por separado.
#
#Aqui se arregla la sinceridad con dos herramientas:
#
#  1. TEMPERATURA. Un solo parametro T que estira o encoge la confianza:
#     p_nueva ∝ p^(1/T). T>1 = el modelo era demasiado atrevido y se le baja el
#     humo; T<1 = era demasiado tibio. Un solo parametro es la unica opcion
#     segura cuando tienes 100 partidos: con muchos parametros lo unico que
#     aprendes es el ruido de tu propio historial.
#
#  2. CORRECCION POR TRAMOS con pseudo-conteo. Para mercados de si/no
#     (ambos marcan, mas de 2.5...) se mira que paso de verdad en cada tramo de
#     probabilidad, pero cada tramo arranca con partidos ficticios que dicen
#     "el modelo tenia razon". Asi un tramo con 4 partidos casi no mueve nada, y
#     uno con 200 manda. El ajuste ademas esta topado a +-12 puntos: la
#     calibracion corrige, no reinventa.
import math

PSEUDO_CONTEO = 25.0
AJUSTE_MAXIMO = 0.12
TRAMOS = [0.0, 0.15, 0.30, 0.45, 0.60, 0.75, 0.90, 1.0]


# ============================================================
#  TEMPERATURA (para el 1X2 y cualquier mercado de varias salidas)
# ============================================================
def aplicar_temperatura(probabilidades, t):
    if t is None or abs(t - 1.0) < 1e-6:
        return dict(probabilidades)
    inv = 1.0 / max(0.25, min(4.0, float(t)))
    crudo = {k: max(1e-12, v) ** inv for k, v in probabilidades.items()}
    total = sum(crudo.values())
    return {k: v / total for k, v in crudo.items()}


def _perdida(casos, t):
    total = 0.0
    for c in casos:
        p = aplicar_temperatura(c["probabilidades"], t)
        total -= math.log(max(1e-9, p.get(c["real"], 0.0)))
    return total / len(casos) if casos else None


def _buscar_t(casos):
    mejor_t, mejor = 1.0, _perdida(casos, 1.0)
    t = 0.55
    while t <= 1.80001:
        v = _perdida(casos, t)
        if v < mejor:
            mejor_t, mejor = t, v
        t += 0.05
    paso = 0.025
    for _ in range(6):
        for cand in (mejor_t - paso, mejor_t + paso):
            if 0.5 <= cand <= 2.0:
                v = _perdida(casos, cand)
                if v < mejor:
                    mejor_t, mejor = cand, v
        paso /= 2.0
    return mejor_t


def ajustar_temperatura(historial, minimo=60, pliegues=5, margen=0.002):
    #historial: lista de {"probabilidades": {...}, "real": clave}
    #
    #REGLA IMPORTANTE: la temperatura NO se aplica solo porque mejore los
    #partidos con los que se calculo. Eso es trampa (siempre mejora, por
    #construccion). Se valida con VALIDACION CRUZADA de 5 pliegues: el
    #historial se parte en 5, se calcula la temperatura con 4 y se comprueba
    #en el que se dejo fuera, cinco veces. Solo si mejora en el conjunto de
    #partidos no vistos, y por un margen que no sea ruido, se aplica.
    #
    #Un solo corte 70/30 NO basta: probado, deja pasar temperaturas que luego
    #empeoran el modelo. Con 5 pliegues cada partido se usa una vez como
    #prueba y cuatro como entrenamiento, y el resultado deja de depender de
    #donde cayo el corte.
    #
    #Un modelo bien calibrado que se deja en paz es mejor que uno "arreglado"
    #con el ruido de 40 partidos.
    casos = [c for c in historial if c.get("probabilidades") and c.get("real")]
    if len(casos) < minimo:
        return 1.0, {"partidos": len(casos), "aplicada": False,
                     "motivo": f"hacen falta al menos {minimo} partidos"}

    def con_freno(t_bruta, n_entren):
        #Freno por tamaño de muestra: con 80 partidos se aplica la mitad del
        #ajuste, con 500 casi todo. Nunca el 100% de golpe.
        peso = n_entren / (n_entren + 80.0)
        return 1.0 + peso * (t_bruta - 1.0)

    #--- validacion cruzada ---
    n = len(casos)
    perdida_con = 0.0
    perdida_sin = 0.0
    for k in range(pliegues):
        prueba = [c for i, c in enumerate(casos) if i % pliegues == k]
        entren = [c for i, c in enumerate(casos) if i % pliegues != k]
        if not prueba or len(entren) < 20:
            continue
        t_k = con_freno(_buscar_t(entren), len(entren))
        perdida_con += _perdida(prueba, t_k) * len(prueba)
        perdida_sin += _perdida(prueba, 1.0) * len(prueba)
    perdida_con /= n
    perdida_sin /= n

    if perdida_con >= perdida_sin - margen:
        return 1.0, {
            "partidos": n, "aplicada": False,
            "log_perdida_cruzada_sin": perdida_sin,
            "log_perdida_cruzada_con": perdida_con,
            "motivo": "no mejoro en validacion cruzada: se deja el modelo como esta",
        }

    #--- pasa la validacion: se reajusta con todo el historial y se aplica ---
    t_final = con_freno(_buscar_t(casos), n)
    return t_final, {
        "partidos": n,
        "temperatura_aplicada": t_final,
        "log_perdida_cruzada_sin": perdida_sin,
        "log_perdida_cruzada_con": perdida_con,
        "mejora": perdida_sin - perdida_con,
        "aplicada": True,
    }


# ============================================================
#  TRAMOS (para mercados de si/no)
# ============================================================
def _indice_tramo(p):
    for i in range(len(TRAMOS) - 1):
        if TRAMOS[i] <= p < TRAMOS[i + 1]:
            return i
    return len(TRAMOS) - 2


def construir_tramos(historial):
    #historial: lista de {"probabilidad": float, "acierto": bool}
    #Devuelve, por tramo, el desvio observado ya suavizado.
    cubos = {}
    for c in historial:
        try:
            p = float(c["probabilidad"])
            acierto = bool(c["acierto"])
        except (KeyError, TypeError, ValueError):
            continue
        if not (0.0 <= p <= 1.0):
            continue
        i = _indice_tramo(p)
        cubo = cubos.setdefault(i, {"n": 0, "suma_prob": 0.0, "aciertos": 0})
        cubo["n"] += 1
        cubo["suma_prob"] += p
        cubo["aciertos"] += 1 if acierto else 0

    salida = {}
    for i, cubo in cubos.items():
        n = cubo["n"]
        media_prevista = cubo["suma_prob"] / n
        #pseudo-conteo: el tramo arranca creyendo al modelo
        observado = (cubo["aciertos"] + PSEUDO_CONTEO * media_prevista) / (n + PSEUDO_CONTEO)
        desvio = observado - media_prevista
        desvio = max(-AJUSTE_MAXIMO, min(AJUSTE_MAXIMO, desvio))
        salida[str(i)] = {
            "n": n,
            "prevista": media_prevista,
            "observada": cubo["aciertos"] / n,
            "desvio": desvio,
        }
    return salida


def aplicar_tramos(probabilidad, tramos):
    if not tramos:
        return probabilidad
    dato = tramos.get(str(_indice_tramo(probabilidad)))
    if not dato:
        return probabilidad
    return max(0.01, min(0.99, probabilidad + dato["desvio"]))


def curva_fiabilidad(historial):
    #Lo que hay que enseñar cuando alguien pregunte "y esto que tan bueno es".
    #Por tramo: cuantas veces dijiste X% y cuantas paso de verdad.
    tramos = construir_tramos(historial)
    filas = []
    for i in sorted(tramos, key=int):
        d = tramos[i]
        idx = int(i)
        filas.append({
            "rango": f"{int(TRAMOS[idx]*100)}-{int(TRAMOS[idx+1]*100)}%",
            "partidos": d["n"],
            "previsto": d["prevista"],
            "real": d["observada"],
            "diferencia": d["observada"] - d["prevista"],
        })
    return filas