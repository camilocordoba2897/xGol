#FUENTE 3 — EL MERCADO. La mas importante de las tres, y la que hoy no estabas
#usando para predecir (las cuotas se pintaban en pantalla y nada mas).
#
#Por que importa tanto: la cuota de cierre de una casa grande es el resultado de
#millones de euros apostados por gente con modelos, informacion de alineaciones,
#lesiones de ultima hora y noticias que ninguna API gratuita te da. En la
#literatura academica la cuota de cierre es el punto de referencia que casi
#nadie bate de forma sostenida. Un analizador que la ignora esta tirando a la
#basura la mejor informacion disponible, gratis.
#
#Pero la cuota TAL CUAL no es una probabilidad: lleva el margen de la casa (el
#"vig"). Si sumas 1/cuota de los tres resultados te da ~1.05, no 1. Hay que
#quitar ese margen, y COMO lo quitas cambia el resultado:
#
#  - proporcional: reparte el margen por igual. Es el metodo ingenuo y sesga
#    los favoritos hacia abajo y los tapados hacia arriba.
#  - potencia: resuelve k tal que sum((1/cuota)^k) = 1. Mejor.
#  - SHIN: modela el margen como proteccion de la casa frente a apostadores
#    informados. Es el que mejor recupera la probabilidad real en los estudios
#    publicados, sobre todo en cuotas altas. Es el que usamos por defecto.
#
#Ademas convertimos el 1X2 del mercado en goles esperados, para que el mercado
#entre a la mezcla como una matriz de marcadores mas y todos los mercados que
#calcules despues sigan siendo coherentes entre si.
import math
import statistics

from .probabilidad import matriz_marcadores, resultado_1x2, total_goles


# ============================================================
#  QUITAR EL MARGEN DE LA CASA
# ============================================================
def _inversas(cuotas):
    inv = []
    for c in cuotas:
        c = float(c)
        if c <= 1.0:
            raise ValueError("cuota invalida")
        inv.append(1.0 / c)
    return inv


def margen(cuotas):
    #Cuanto se queda la casa. 1.05 = 5% de margen.
    return sum(_inversas(cuotas))


def sin_margen_proporcional(cuotas):
    inv = _inversas(cuotas)
    total = sum(inv)
    return [i / total for i in inv]


def sin_margen_potencia(cuotas):
    #Busca k con sum((1/cuota)^k) = 1 (biseccion, siempre converge)
    inv = _inversas(cuotas)
    bajo, alto = 0.5, 3.0
    for _ in range(80):
        k = (bajo + alto) / 2.0
        s = sum(i ** k for i in inv)
        if s > 1.0:
            bajo = k
        else:
            alto = k
    k = (bajo + alto) / 2.0
    p = [i ** k for i in inv]
    total = sum(p)
    return [x / total for x in p]


def sin_margen_shin(cuotas):
    #Metodo de Shin (1993). z = proporcion de dinero de apostadores informados.
    #p_i = [sqrt(z^2 + 4(1-z) * pi_i^2 / S) - z] / (2(1-z)),  S = sum(pi)
    inv = _inversas(cuotas)
    s = sum(inv)
    if s <= 1.0:
        #cuotas sin margen (o con margen negativo): no hay nada que quitar
        return [i / s for i in inv]

    def probs(z):
        if z <= 1e-9:
            return [i / s for i in inv]
        out = []
        for pi in inv:
            dentro = z * z + 4.0 * (1.0 - z) * (pi * pi) / s
            out.append((math.sqrt(max(0.0, dentro)) - z) / (2.0 * (1.0 - z)))
        return out

    bajo, alto = 0.0, 0.6
    for _ in range(100):
        z = (bajo + alto) / 2.0
        if sum(probs(z)) > 1.0:
            bajo = z
        else:
            alto = z
    p = probs((bajo + alto) / 2.0)
    total = sum(p)
    return [x / total for x in p]


def probabilidades_reales(cuotas, metodo="shin"):
    #Devuelve las probabilidades limpias de margen.
    if metodo == "proporcional":
        return sin_margen_proporcional(cuotas)
    if metodo == "potencia":
        return sin_margen_potencia(cuotas)
    return sin_margen_shin(cuotas)


# ============================================================
#  CONSENSO ENTRE CASAS
# ============================================================
def consenso_1x2(casas, metodo="shin"):
    #casas: lista de dicts {"local": cuota, "empate": cuota, "visitante": cuota}
    #
    #IMPORTANTE: NO se usa la cuota mas alta de cada resultado (que es lo que
    #hace hoy api_cuotas.py). Mezclar la mejor cuota de tres casas distintas
    #crea un libro imposible que suma menos de 1 y da probabilidades infladas.
    #Para PREDECIR se limpia cada casa por separado y se toma la MEDIANA.
    #La cuota mas alta sigue sirviendo, pero para otra cosa: para calcular el
    #valor de la apuesta una vez que ya sabes la probabilidad real.
    limpias = []
    for c in casas:
        try:
            p = probabilidades_reales([c["local"], c["empate"], c["visitante"]], metodo)
        except (KeyError, TypeError, ValueError):
            continue
        if len(p) == 3 and all(x > 0 for x in p):
            limpias.append(p)
    if not limpias:
        return None
    local = statistics.median(p[0] for p in limpias)
    empate = statistics.median(p[1] for p in limpias)
    visitante = statistics.median(p[2] for p in limpias)
    total = local + empate + visitante
    return {
        "local": local / total,
        "empate": empate / total,
        "visitante": visitante / total,
        "casas": len(limpias),
    }


# ============================================================
#  DEL MERCADO A GOLES ESPERADOS
# ============================================================
def lambdas_desde_mercado(p_local, p_empate, p_visitante, rho=-0.13,
                          prob_mas_25=None, total_inicial=2.7):
    #Busca los goles esperados (lam1, lam2) cuya matriz Dixon-Coles reproduce
    #lo que dice el mercado. Se parametriza por TOTAL = lam1+lam2 y
    #SUPREMACIA = lam1-lam2, que es como piensan los traders de verdad.
    #
    #Si ademas tienes la linea de mas/menos 2.5 del mercado, se usa para fijar
    #el total y la solucion queda clavada.
    objetivo = (p_local, p_empate, p_visitante)

    def error(total, supremacia):
        lam1 = max(0.05, (total + supremacia) / 2.0)
        lam2 = max(0.05, (total - supremacia) / 2.0)
        m = matriz_marcadores(lam1, lam2, rho)
        r = resultado_1x2(m)
        e = ((r["local"] - objetivo[0]) ** 2 +
             (r["empate"] - objetivo[1]) ** 2 +
             (r["visitante"] - objetivo[2]) ** 2)
        if prob_mas_25 is not None:
            e += 2.0 * (total_goles(m, 2.5)["mas"] - prob_mas_25) ** 2
        return e

    #busqueda por coordenadas: alterno supremacia y total, refinando el paso
    total = float(total_inicial)
    supremacia = 0.0
    paso_t, paso_s = 0.8, 0.8
    for _ in range(9):
        for _ in range(6):
            candidatos = [supremacia - paso_s, supremacia, supremacia + paso_s]
            supremacia = min(candidatos, key=lambda s: error(total, s))
            paso_s *= 0.6
        for _ in range(6):
            candidatos = [max(0.4, total - paso_t), total, total + paso_t]
            total = min(candidatos, key=lambda t: error(t, supremacia))
            paso_t *= 0.6
        paso_s = max(0.01, paso_s)
        paso_t = max(0.01, paso_t)

    lam1 = max(0.05, (total + supremacia) / 2.0)
    lam2 = max(0.05, (total - supremacia) / 2.0)
    return lam1, lam2, error(total, supremacia)


def matriz_de_mercado(casas, rho=-0.13, prob_mas_25=None, metodo="shin"):
    #Atajo: de las cuotas de varias casas a la matriz de marcadores del mercado.
    consenso = consenso_1x2(casas, metodo)
    if not consenso:
        return None, None
    lam1, lam2, _ = lambdas_desde_mercado(
        consenso["local"], consenso["empate"], consenso["visitante"],
        rho=rho, prob_mas_25=prob_mas_25,
    )
    return matriz_marcadores(lam1, lam2, rho), consenso


def mejor_cuota(casas):
    #La cuota mas alta de cada resultado y quien la paga. Esto SI se usa la
    #mejor, porque aqui la pregunta ya no es "que va a pasar" sino
    #"donde me pagan mas por lo que ya se que va a pasar".
    mejor = {"local": None, "empate": None, "visitante": None}
    for c in casas:
        for k in mejor:
            try:
                precio = float(c.get(k))
            except (TypeError, ValueError):
                continue
            if precio <= 1.0:
                continue
            if mejor[k] is None or precio > mejor[k]["cuota"]:
                mejor[k] = {"cuota": precio, "casa": c.get("casa", "")}
    return mejor