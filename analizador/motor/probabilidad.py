#Nucleo probabilistico del motor xGol.
#
#REGLA DE ORO DE ESTE ARCHIVO: todos los mercados salen de UNA SOLA matriz de
#marcadores. Nunca se calcula un mercado por su cuenta. Asi es imposible que el
#analizador se contradiga (que diga "gana el local 60%" y a la vez "menos de 1.5
#goles 70%"). Ese es el fallo numero uno de los analizadores caseros y la razon
#por la que los numeros "no se sienten reales".
#
#Solo libreria estandar de Python: no hace falta instalar nada.
import math

MAX_GOLES = 10          #la matriz llega a 10-10; mas alla la probabilidad es ruido
RHO_POR_DEFECTO = -0.13  #correccion Dixon-Coles tipica en ligas europeas


def poisson(lam, k):
    #P(X = k) con X ~ Poisson(lam)
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    return math.exp(-lam + k * math.log(lam) - math.lgamma(k + 1))


def tau_dixon_coles(x, y, lam1, lam2, rho):
    #Correccion de Dixon-Coles (1997) para marcadores bajos.
    #Poisson puro subestima el 0-0 y el 1-1 y sobreestima el 1-0 y el 0-1.
    #Esta correccion es la que usa practicamente toda la industria.
    if x == 0 and y == 0:
        return 1.0 - lam1 * lam2 * rho
    if x == 0 and y == 1:
        return 1.0 + lam1 * rho
    if x == 1 and y == 0:
        return 1.0 + lam2 * rho
    if x == 1 and y == 1:
        return 1.0 - rho
    return 1.0


def matriz_marcadores(lam1, lam2, rho=RHO_POR_DEFECTO, max_goles=MAX_GOLES):
    #Matriz[x][y] = P(local marca x, visitante marca y), ya corregida y normalizada.
    lam1 = max(0.05, float(lam1))
    lam2 = max(0.05, float(lam2))
    px = [poisson(lam1, k) for k in range(max_goles + 1)]
    py = [poisson(lam2, k) for k in range(max_goles + 1)]
    matriz = []
    total = 0.0
    for x in range(max_goles + 1):
        fila = []
        for y in range(max_goles + 1):
            p = px[x] * py[y] * tau_dixon_coles(x, y, lam1, lam2, rho)
            p = max(0.0, p)   #tau puede volverse negativo con rho extremo
            fila.append(p)
            total += p
        matriz.append(fila)
    if total <= 0:
        raise ValueError("matriz de marcadores degenerada")
    return [[p / total for p in fila] for fila in matriz]


def mezclar_matrices(matrices, pesos):
    #Mezcla lineal de varias matrices (una por fuente) con sus pesos.
    #Se mezcla la DISTRIBUCION completa, no cada mercado por separado: por eso
    #el resultado sigue siendo coherente entre todos los mercados.
    if not matrices:
        raise ValueError("no hay matrices que mezclar")
    suma_pesos = sum(pesos)
    if suma_pesos <= 0:
        raise ValueError("los pesos suman cero")
    n = len(matrices[0])
    salida = [[0.0] * n for _ in range(n)]
    for matriz, peso in zip(matrices, pesos):
        w = peso / suma_pesos
        for x in range(n):
            fila_m = matriz[x]
            fila_s = salida[x]
            for y in range(n):
                fila_s[y] += w * fila_m[y]
    return salida


# ============================================================
#  LECTURA DE MERCADOS DESDE LA MATRIZ
# ============================================================
def resultado_1x2(matriz):
    local = empate = visitante = 0.0
    for x, fila in enumerate(matriz):
        for y, p in enumerate(fila):
            if x > y:
                local += p
            elif x == y:
                empate += p
            else:
                visitante += p
    return {"local": local, "empate": empate, "visitante": visitante}


def doble_oportunidad(matriz):
    r = resultado_1x2(matriz)
    return {
        "1X": r["local"] + r["empate"],
        "12": r["local"] + r["visitante"],
        "X2": r["empate"] + r["visitante"],
    }


def total_goles(matriz, linea):
    #P(mas de `linea` goles) y P(menos de `linea`). Con lineas .5 no hay empate.
    mas = menos = 0.0
    for x, fila in enumerate(matriz):
        for y, p in enumerate(fila):
            if x + y > linea:
                mas += p
            else:
                menos += p
    return {"mas": mas, "menos": menos}


def ambos_marcan(matriz):
    si = 0.0
    for x, fila in enumerate(matriz):
        for y, p in enumerate(fila):
            if x >= 1 and y >= 1:
                si += p
    return {"si": si, "no": 1.0 - si}


def handicap_asiatico(matriz, linea):
    #linea = handicap aplicado AL LOCAL (-0.5 favorito, +1 underdog...).
    #Devuelve probabilidad de ganar / anular (push) / perder la apuesta al local.
    gana = empata = pierde = 0.0
    for x, fila in enumerate(matriz):
        for y, p in enumerate(fila):
            margen = (x + linea) - y
            if margen > 1e-9:
                gana += p
            elif abs(margen) < 1e-9:
                empata += p
            else:
                pierde += p
    return {"gana": gana, "anula": empata, "pierde": pierde}


def marcador_exacto(matriz, top=8):
    marcadores = []
    for x, fila in enumerate(matriz):
        for y, p in enumerate(fila):
            if x <= 6 and y <= 6:
                marcadores.append((f"{x}-{y}", p))
    marcadores.sort(key=lambda t: t[1], reverse=True)
    return marcadores[:top]


def goles_equipo(matriz, local=True, linea=0.5):
    #P(un equipo concreto pase de `linea` goles)
    mas = 0.0
    for x, fila in enumerate(matriz):
        for y, p in enumerate(fila):
            goles = x if local else y
            if goles > linea:
                mas += p
    return {"mas": mas, "menos": 1.0 - mas}


def lambdas_de_matriz(matriz):
    #Goles esperados que implica la matriz ya mezclada (para mostrar en pantalla)
    lam1 = lam2 = 0.0
    for x, fila in enumerate(matriz):
        for y, p in enumerate(fila):
            lam1 += x * p
            lam2 += y * p
    return lam1, lam2


def resumen_mercados(matriz, lineas_totales=(0.5, 1.5, 2.5, 3.5, 4.5),
                     lineas_handicap=(-2.5, -1.5, -0.5, 0.5, 1.5, 2.5)):
    #Paquete completo de mercados, todos derivados de la MISMA matriz.
    lam1, lam2 = lambdas_de_matriz(matriz)
    r1x2 = resultado_1x2(matriz)
    salida = {
        "goles_esperados_local": lam1,
        "goles_esperados_visitante": lam2,
        "goles_esperados_total": lam1 + lam2,
        "1x2": r1x2,
        "doble_oportunidad": doble_oportunidad(matriz),
        "ambos_marcan": ambos_marcan(matriz),
        "totales": {str(l): total_goles(matriz, l) for l in lineas_totales},
        "handicap": {str(l): handicap_asiatico(matriz, l) for l in lineas_handicap},
        "marcador_exacto": marcador_exacto(matriz),
        "goles_local": {str(l): goles_equipo(matriz, True, l) for l in (0.5, 1.5, 2.5)},
        "goles_visitante": {str(l): goles_equipo(matriz, False, l) for l in (0.5, 1.5, 2.5)},
    }
    #Porteria a cero
    salida["porteria_cero_local"] = sum(matriz[x][0] for x in range(len(matriz)))
    salida["porteria_cero_visitante"] = sum(matriz[0])
    return salida


# ============================================================
#  UTILIDADES DE CUOTAS
# ============================================================
def cuota_justa(probabilidad):
    #Cuota sin margen: la que haria la apuesta neutra a largo plazo.
    if probabilidad <= 0:
        return None
    return 1.0 / probabilidad


def valor_esperado(probabilidad, cuota):
    #EV por cada 1 unidad apostada. Positivo = la casa te esta pagando de mas.
    if not cuota or cuota <= 1:
        return None
    return probabilidad * (cuota - 1.0) - (1.0 - probabilidad)


def kelly(probabilidad, cuota, fraccion=0.25):
    #Kelly fraccionado (1/4 por defecto). Kelly completo es matematicamente
    #optimo pero psicologicamente insoportable: una racha mala normal te borra
    #media banca. 1/4 de Kelly conserva ~90% del crecimiento con mucho menos riesgo.
    if not cuota or cuota <= 1:
        return 0.0
    b = cuota - 1.0
    q = 1.0 - probabilidad
    bruto = (b * probabilidad - q) / b
    return max(0.0, bruto * fraccion)