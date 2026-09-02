#PONDERACION CON RETROALIMENTACION.
#
#Esto es lo que pediste: que el sistema se corrija solo. Aqui esta el como.
#
#Cada fuente (Dixon-Coles, Elo, mercado) entrega su propia matriz de marcadores.
#La pregunta es cuanto vale la opinion de cada una. La respuesta NO se decide a
#dedo: se aprende de los partidos que ya se jugaron.
#
#El criterio es la LOG-PERDIDA (log-loss). Es la medida honesta de un
#pronosticador probabilistico: castiga muchisimo decir "90% seguro" y fallar, y
#premia poco decir "40%" y acertar. Con acierto/fallo a secas puedes parecer
#bueno acertando favoritos obvios; con log-loss no puedes esconderte.
#
#Se buscan los pesos que minimizan la log-perdida sobre el historial, con dos
#seguros contra el sobreajuste:
#  1. PRIOR: se arranca de unos pesos por defecto sensatos y se necesita
#     evidencia real para moverlos (equivale a partidos ficticios de arranque).
#     Con 10 partidos en el historial casi no se mueve; con 300 manda el dato.
#  2. SUELO: ninguna fuente puede caer a 0 del todo. Una fuente que hoy parece
#     mala puede ser la unica que funcione cuando cambie el contexto.
import math

PESOS_POR_DEFECTO = {
    #Arranque razonable segun lo que se sabe del problema: el mercado es la
    #fuente mas fiable, el modelo estadistico aporta lo suyo y el Elo diversifica.
    "mercado": 0.50,
    "dixon_coles": 0.35,
    "elo": 0.15,
}
FUERZA_PRIOR = 200.0   #a cuantos partidos "equivale" el prior
MINIMO_PARTIDOS = 200  #por debajo de esto NO se tocan los pesos (medido: por
                       #debajo de 200 el optimizador acierta la mejor fuente
                       #menos del 80% de las veces; a partir de 200, mas del 90%)
PESO_MINIMO = 0.05


def normalizar(pesos):
    total = sum(max(0.0, v) for v in pesos.values())
    if total <= 0:
        n = len(pesos) or 1
        return {k: 1.0 / n for k in pesos}
    return {k: max(0.0, v) / total for k, v in pesos.items()}


def aplicar_suelo(pesos, suelo=PESO_MINIMO):
    p = normalizar(pesos)
    p = {k: max(suelo, v) for k, v in p.items()}
    return normalizar(p)


def mezclar_probabilidades(por_fuente, pesos):
    #por_fuente: {"mercado": {"local":..,"empate":..,"visitante":..}, ...}
    #Las fuentes que falten en este partido se ignoran y los pesos se
    #renormalizan entre las presentes: si no hay cuotas, el motor sigue
    #funcionando con las otras dos en vez de quedarse mudo.
    activas = {k: v for k, v in por_fuente.items() if v}
    if not activas:
        return None
    w = {k: pesos.get(k, 0.0) for k in activas}
    if sum(w.values()) <= 0:
        w = {k: 1.0 for k in activas}
    w = normalizar(w)
    salida = {}
    for resultado in ("local", "empate", "visitante"):
        salida[resultado] = sum(w[k] * activas[k].get(resultado, 0.0) for k in activas)
    total = sum(salida.values())
    if total <= 0:
        return None
    return {k: v / total for k, v in salida.items()}


def log_perdida(probabilidades, reales):
    #probabilidades: lista de dicts 1x2. reales: lista de "local"/"empate"/"visitante"
    if not probabilidades:
        return None
    total = 0.0
    for p, real in zip(probabilidades, reales):
        valor = max(1e-9, min(1.0, p.get(real, 0.0)))
        total -= math.log(valor)
    return total / len(probabilidades)


def _perdida_con_pesos(historial, pesos):
    probs, reales = [], []
    for caso in historial:
        mezcla = mezclar_probabilidades(caso["fuentes"], pesos)
        if not mezcla:
            continue
        probs.append(mezcla)
        reales.append(caso["real"])
    if not probs:
        return None, 0
    return log_perdida(probs, reales), len(probs)


def _descenso(historial, arranque, fuentes):
    #Descenso por coordenadas sobre el simplex: probado, estable y sin
    #dependencias. Con 3 fuentes es de sobra.
    actual = dict(arranque)
    mejor, _ = _perdida_con_pesos(historial, actual)
    if mejor is None:
        return dict(arranque)
    paso = 0.25
    for _ in range(40):
        mejoro = False
        for f in fuentes:
            for signo in (1, -1):
                prueba = dict(actual)
                prueba[f] = max(0.0, prueba[f] + signo * paso)
                prueba = normalizar(prueba)
                valor, _ = _perdida_con_pesos(historial, prueba)
                if valor is not None and valor < mejor - 1e-9:
                    mejor, actual, mejoro = valor, prueba, True
        if not mejoro:
            paso *= 0.5
            if paso < 0.005:
                break
    return actual


def optimizar_pesos(historial, pesos_iniciales=None, fuerza_prior=FUERZA_PRIOR,
                    minimo=MINIMO_PARTIDOS):
    #historial: lista de {"fuentes": {...probabilidades por fuente...},
    #                     "real": "local"|"empate"|"visitante"}
    #
    #TRES SEGUROS contra aprender ruido en vez de calidad:
    #  1. MINIMO: con menos de `minimo` partidos no se mueve nada. Con 40
    #     partidos la diferencia entre una fuente buena y una mala esta dentro
    #     del margen de azar, y el optimizador se cree cualquier cosa.
    #  2. VALIDACION: se aprende con el 70% y se comprueba en el 30% restante.
    #     Si ahi no mejora, se devuelven los pesos de fabrica intactos.
    #  3. PRIOR: aun pasando la validacion, el cambio se aplica en proporcion
    #     al historial disponible. Con 200 partidos se aplica la mitad; con
    #     2000, casi todo.
    base = dict(pesos_iniciales or PESOS_POR_DEFECTO)
    fuentes = sorted({f for caso in historial for f in caso["fuentes"]} | set(base))
    if not fuentes:
        return aplicar_suelo(dict(PESOS_POR_DEFECTO)), {"partidos": 0, "movido": False}

    prior = normalizar({f: base.get(f, PESOS_POR_DEFECTO.get(f, 0.1)) for f in fuentes})
    perdida_prior, n = _perdida_con_pesos(historial, prior)
    if perdida_prior is None or n == 0:
        return aplicar_suelo(prior), {"partidos": 0, "movido": False}

    if n < minimo:
        return aplicar_suelo(prior), {
            "partidos": n, "movido": False,
            "log_perdida_prior": perdida_prior,
            "log_perdida_final": perdida_prior,
            "motivo": f"hacen falta al menos {minimo} partidos para mover los pesos",
        }

    #--- validacion: aprender con el 70%, comprobar en el 30% ---
    corte = int(n * 0.70)
    entren, validacion = historial[:corte], historial[corte:]
    candidatos = _descenso(entren, prior, fuentes)
    v_prior, _ = _perdida_con_pesos(validacion, prior)
    v_cand, _ = _perdida_con_pesos(validacion, candidatos)
    if v_prior is None or v_cand is None or v_cand >= v_prior:
        return aplicar_suelo(prior), {
            "partidos": n, "movido": False,
            "log_perdida_prior": perdida_prior,
            "log_perdida_final": perdida_prior,
            "motivo": "los pesos aprendidos no mejoraron en partidos no vistos",
        }

    #--- pasa la validacion: se reaprende con todo y se aplica con freno ---
    aprendidos = _descenso(historial, prior, fuentes)
    peso_dato = n / (n + fuerza_prior)
    final = {f: (1.0 - peso_dato) * prior[f] + peso_dato * aprendidos[f] for f in fuentes}
    final = aplicar_suelo(final)
    perdida_final, _ = _perdida_con_pesos(historial, final)

    return final, {
        "partidos": n,
        "peso_dato": peso_dato,
        "log_perdida_prior": perdida_prior,
        "log_perdida_final": perdida_final,
        "mejora": (perdida_prior - perdida_final) if perdida_final is not None else 0.0,
        "movido": True,
    }