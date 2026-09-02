#EL MOTOR — aqui se junta todo.
#
#Flujo de un pronostico:
#
#   historial de la liga ─► Dixon-Coles ─┐
#   historial de la liga ─► Elo ─────────┼─► matriz mezclada ─► calibracion
#   cuotas de las casas ─► mercado ──────┘        │                    │
#                                                 ▼                    ▼
#                                    TODOS los mercados          numeros sinceros
#                                    de la misma matriz          (70% = 70%)
#
#Los pesos de la mezcla no son inventados: salen de optimizar_pesos() sobre tus
#propios partidos ya jugados. Cuanto mas lo uses, mejores son los pesos.
#
#Nada de esto necesita librerias externas ni tocar el frontend: devuelve un
#diccionario y ya.
import math

from . import calibracion, combinacion, mercado as mod_mercado, probabilidad
from .probabilidad import matriz_marcadores, mezclar_matrices, resumen_mercados


class ResultadoPronostico:
    def __init__(self, matriz, mercados, fuentes, pesos, diagnostico):
        self.matriz = matriz
        self.mercados = mercados
        self.fuentes = fuentes          #probabilidades 1x2 de cada fuente por separado
        self.pesos = pesos
        self.diagnostico = diagnostico

    def a_dict(self):
        return {
            "mercados": self.mercados,
            "fuentes": self.fuentes,
            "pesos": self.pesos,
            "diagnostico": self.diagnostico,
        }


def _confianza(mercados, diagnostico):
    #La confianza NO es la probabilidad del favorito. Es cuanto te puedes fiar
    #del numero, y depende de tres cosas distintas:
    #   - cuantas fuentes hablaron (con mercado incluido vale mucho mas)
    #   - cuanto se parecen entre si (si discrepan, algo no cuadra)
    #   - cuanto historial tiene el ajuste de la liga
    fuentes = diagnostico.get("fuentes_usadas", [])
    puntos = 0.0
    if "mercado" in fuentes:
        puntos += 45
    if "dixon_coles" in fuentes:
        puntos += 30
    if "elo" in fuentes:
        puntos += 10

    desacuerdo = diagnostico.get("desacuerdo")
    if desacuerdo is not None:
        #desacuerdo 0 = fuentes identicas; 0.15+ = se contradicen feo
        puntos += max(0.0, 15.0 * (1.0 - min(1.0, desacuerdo / 0.15)))

    partidos = diagnostico.get("partidos_ajuste", 0)
    if partidos >= 300:
        puntos += 0
    elif partidos >= 150:
        puntos -= 5
    elif partidos >= 60:
        puntos -= 12
    else:
        puntos -= 25

    puntos = max(5.0, min(100.0, puntos))
    if puntos >= 75:
        nivel = "alta"
    elif puntos >= 50:
        nivel = "media"
    else:
        nivel = "baja"
    return {"puntos": round(puntos), "nivel": nivel}


def _desacuerdo(fuentes):
    #Distancia media entre las opiniones de las fuentes sobre el 1X2
    claves = list(fuentes.keys())
    if len(claves) < 2:
        return None
    total, pares = 0.0, 0
    for i in range(len(claves)):
        for j in range(i + 1, len(claves)):
            a, b = fuentes[claves[i]], fuentes[claves[j]]
            d = sum(abs(a.get(k, 0) - b.get(k, 0)) for k in ("local", "empate", "visitante")) / 2.0
            total += d
            pares += 1
    return total / pares if pares else None


def confianza_de(fuentes_1x2, partidos_ajuste=0):
    #Confianza a partir de las probabilidades de cada fuente, sin tener que
    #recalcular el pronostico entero. La usa el home para puntuar pronosticos
    #que ya estaban guardados en base de datos.
    #
    #Existe para que la formula viva en UN SOLO SITIO. Si el home la copiara,
    #tarde o temprano las dos versiones se separarian y el mismo partido
    #tendria dos confianzas distintas segun donde lo mires.
    diagnostico = {
        "fuentes_usadas": list((fuentes_1x2 or {}).keys()),
        "desacuerdo": _desacuerdo(fuentes_1x2 or {}),
        "partidos_ajuste": partidos_ajuste,
    }
    return _confianza(None, diagnostico)


def pronosticar(local, visitante, ajuste_liga=None, tabla_elo=None, casas=None,
                pesos=None, temperatura=1.0, cancha_neutral=False,
                prob_mercado_mas_25=None):
    #ajuste_liga: objeto AjusteLiga de tasas.ajustar()
    #tabla_elo:   objeto TablaElo de elo.calcular()
    #casas:       [{"casa": "Bet365", "local": 2.10, "empate": 3.40, "visitante": 3.30}, ...]
    #
    #Todo es opcional menos que haya AL MENOS UNA fuente. Sin cuotas funciona.
    #Sin ajuste de liga funciona. Lo que no funciona es sin nada.
    matrices = {}
    fuentes_1x2 = {}
    diagnostico = {"fuentes_usadas": [], "avisos": []}

    rho = getattr(ajuste_liga, "rho", probabilidad.RHO_POR_DEFECTO)

    # --- Fuente Dixon-Coles ---
    if ajuste_liga is not None:
        lam1, lam2 = ajuste_liga.lambdas(local, visitante, cancha_neutral)
        matrices["dixon_coles"] = matriz_marcadores(lam1, lam2, rho)
        diagnostico["fuentes_usadas"].append("dixon_coles")
        diagnostico["dixon_coles"] = {"lam_local": lam1, "lam_visitante": lam2}
        diagnostico["partidos_ajuste"] = ajuste_liga.partidos_usados
        if not ajuste_liga.conoce(local):
            diagnostico["avisos"].append(f"{local} no aparece en el ajuste: se trata como equipo promedio")
        if not ajuste_liga.conoce(visitante):
            diagnostico["avisos"].append(f"{visitante} no aparece en el ajuste: se trata como equipo promedio")

    # --- Fuente Elo ---
    if tabla_elo is not None:
        media = 2.7
        if ajuste_liga is not None:
            media = math.exp(ajuste_liga.mu) * 2.0
        e1, e2 = tabla_elo.lambdas(local, visitante, media, cancha_neutral)
        matrices["elo"] = matriz_marcadores(e1, e2, rho)
        diagnostico["fuentes_usadas"].append("elo")
        diagnostico["elo"] = {
            "rating_local": tabla_elo.rating(local),
            "rating_visitante": tabla_elo.rating(visitante),
            "lam_local": e1, "lam_visitante": e2,
        }

    # --- Fuente mercado ---
    if casas:
        matriz_mkt, consenso = mod_mercado.matriz_de_mercado(
            casas, rho=rho, prob_mas_25=prob_mercado_mas_25)
        if matriz_mkt is not None:
            matrices["mercado"] = matriz_mkt
            diagnostico["fuentes_usadas"].append("mercado")
            diagnostico["mercado"] = {
                "consenso": consenso,
                "mejor_cuota": mod_mercado.mejor_cuota(casas),
            }
        else:
            diagnostico["avisos"].append("las cuotas recibidas no se pudieron interpretar")

    if not matrices:
        raise ValueError("no hay ninguna fuente disponible para pronosticar")

    for nombre, m in matrices.items():
        fuentes_1x2[nombre] = probabilidad.resultado_1x2(m)

    # --- Mezcla ---
    pesos_usados = combinacion.aplicar_suelo(
        {k: (pesos or combinacion.PESOS_POR_DEFECTO).get(k, 0.1) for k in matrices})
    matriz = mezclar_matrices([matrices[k] for k in pesos_usados],
                              [pesos_usados[k] for k in pesos_usados])

    diagnostico["desacuerdo"] = _desacuerdo(fuentes_1x2)

    # --- Calibracion del 1X2 y reajuste de la matriz ---
    r_crudo = probabilidad.resultado_1x2(matriz)
    r_cal = calibracion.aplicar_temperatura(r_crudo, temperatura)
    if temperatura and abs(temperatura - 1.0) > 1e-6:
        #Se reescala la matriz para que respete el 1X2 calibrado sin romper la
        #coherencia interna de cada grupo de marcadores.
        factores = {}
        for k in ("local", "empate", "visitante"):
            factores[k] = (r_cal[k] / r_crudo[k]) if r_crudo[k] > 1e-9 else 1.0
        n = len(matriz)
        total = 0.0
        nueva = [[0.0] * n for _ in range(n)]
        for x in range(n):
            for y in range(n):
                grupo = "local" if x > y else ("empate" if x == y else "visitante")
                v = matriz[x][y] * factores[grupo]
                nueva[x][y] = v
                total += v
        matriz = [[v / total for v in fila] for fila in nueva]
        diagnostico["temperatura"] = temperatura

    mercados = resumen_mercados(matriz)
    diagnostico["confianza"] = _confianza(mercados, diagnostico)

    return ResultadoPronostico(matriz, mercados, fuentes_1x2, pesos_usados, diagnostico)


def apuestas_con_valor(resultado, casas, umbral_ev=0.03, banca=100.0,
                       fraccion_kelly=0.25):
    #Cruza lo que dice el motor con lo que paga cada casa y saca SOLO las
    #apuestas donde te estan pagando de mas. Una probabilidad alta no es una
    #buena apuesta: 90% pagado a 1.05 es una perdida segura a largo plazo.
    if not casas:
        return []
    mejor = mod_mercado.mejor_cuota(casas)
    r = resultado.mercados["1x2"]
    salida = []
    for clave, etiqueta in (("local", "Gana local"), ("empate", "Empate"),
                            ("visitante", "Gana visitante")):
        dato = mejor.get(clave)
        if not dato:
            continue
        p = r[clave]
        ev = probabilidad.valor_esperado(p, dato["cuota"])
        if ev is None or ev < umbral_ev:
            continue
        stake = probabilidad.kelly(p, dato["cuota"], fraccion_kelly)
        salida.append({
            "mercado": etiqueta,
            "probabilidad": p,
            "cuota_justa": probabilidad.cuota_justa(p),
            "cuota_ofrecida": dato["cuota"],
            "casa": dato["casa"],
            "valor_esperado": ev,
            "stake_sugerido": round(stake * banca, 2),
        })
    salida.sort(key=lambda a: a["valor_esperado"], reverse=True)
    return salida