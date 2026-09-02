#FUENTE 1 — Modelo Dixon-Coles ajustado por maxima verosimilitud sobre la LIGA
#COMPLETA.
#
#Que cambia respecto al motor viejo:
#  Antes: la fuerza de un equipo salia de promediar sus ultimos 15 partidos, y
#         la "media de la liga" se sacaba de los dos equipos del partido. Si el
#         Madrid venia de jugar contra tres colistas, su ataque salia inflado.
#  Ahora: se ajustan a la vez el ataque y la defensa de TODOS los equipos de la
#         liga usando TODOS los partidos, con la verosimilitud de Poisson. La
#         calidad del rival se descuenta sola porque cada partido restringe a
#         los dos equipos al mismo tiempo. Es el metodo de Dixon & Coles (1997),
#         la base de casi todos los modelos comerciales que existen hoy.
#
#Tres piezas que hacen la diferencia:
#  1. DECAIMIENTO TEMPORAL: un partido de hace 400 dias pesa menos que uno de
#     hace 20. Se usa peso = exp(-xi * dias). xi=0.0045 => vida media ~154 dias.
#  2. REGULARIZACION (ridge): tira los ataques y defensas hacia la media. Sin
#     esto un recien ascendido con 3 partidos sale con numeros absurdos.
#  3. RHO por rejilla: se ajusta la correccion de marcadores bajos con la
#     verosimilitud completa, en vez de dejarla fija en -0.13.
#
#Solo libreria estandar. Un ajuste de 20 equipos y 400 partidos tarda decimas
#de segundo.
import math

from .probabilidad import poisson, tau_dixon_coles

XI_POR_DEFECTO = 0.0045      #decaimiento diario (vida media ~154 dias)
RIDGE_POR_DEFECTO = 0.020    #fuerza de la regularizacion
ITERACIONES = 400
PASO_INICIAL = 0.06


def _clave(nombre):
    return str(nombre or "").strip().lower()


class AjusteLiga:
    #Resultado de un ajuste: la "foto" de fuerzas de una liga en una fecha.
    def __init__(self, mu, ventaja_local, rho, ataque, defensa, equipos,
                 partidos_usados, log_verosimilitud):
        self.mu = mu                          #log del promedio de goles de la liga
        self.ventaja_local = ventaja_local    #log del multiplicador de jugar en casa
        self.rho = rho
        self.ataque = ataque                  #dict nombre_normalizado -> log ataque
        self.defensa = defensa                #dict nombre_normalizado -> log defensa
        self.equipos = equipos                #dict nombre_normalizado -> nombre bonito
        self.partidos_usados = partidos_usados
        self.log_verosimilitud = log_verosimilitud

    #--- consultas ---
    def conoce(self, equipo):
        return _clave(equipo) in self.ataque

    def lambdas(self, local, visitante, cancha_neutral=False):
        #Goles esperados de cada equipo en este enfrentamiento.
        #Un equipo desconocido se trata como equipo promedio (ataque=defensa=0),
        #que es exactamente lo correcto: sin informacion, la media de la liga.
        a_l = self.ataque.get(_clave(local), 0.0)
        d_l = self.defensa.get(_clave(local), 0.0)
        a_v = self.ataque.get(_clave(visitante), 0.0)
        d_v = self.defensa.get(_clave(visitante), 0.0)
        casa = 0.0 if cancha_neutral else self.ventaja_local
        lam1 = math.exp(self.mu + a_l - d_v + casa)
        lam2 = math.exp(self.mu + a_v - d_l)
        return lam1, lam2

    def fuerza(self, equipo):
        #Para mostrar en pantalla, en multiplicadores sobre el equipo promedio:
        #  ataque  1.30 = mete un 30% MAS de goles que el promedio (mejor)
        #  defensa 0.70 = encaja un 30% MENOS que el promedio (mejor)
        #OJO con la defensa: MENOR ES MEJOR, es un multiplicador de goles
        #encajados, no una nota. 1.70 no es una gran defensa, es un coladero.
        k = _clave(equipo)
        return {
            "ataque": math.exp(self.ataque.get(k, 0.0)),
            "defensa": math.exp(-self.defensa.get(k, 0.0)),
            "conocido": k in self.ataque,
        }

    def tabla_fuerzas(self):
        #Ordenada del mejor al peor equipo. La fuerza global es ataque dividido
        #entre goles encajados: mete mucho y encaja poco = arriba.
        filas = []
        for k, nombre in self.equipos.items():
            ataque = math.exp(self.ataque.get(k, 0.0))
            encaja = math.exp(-self.defensa.get(k, 0.0))
            filas.append({
                "equipo": nombre,
                "ataque": ataque,
                "defensa": encaja,              #menor = encaja menos = mejor
                "fuerza": ataque / max(0.05, encaja),
            })
        filas.sort(key=lambda f: f["fuerza"], reverse=True)
        return filas

    def a_dict(self):
        return {
            "mu": self.mu,
            "ventaja_local": self.ventaja_local,
            "rho": self.rho,
            "ataque": self.ataque,
            "defensa": self.defensa,
            "equipos": self.equipos,
            "partidos_usados": self.partidos_usados,
            "log_verosimilitud": self.log_verosimilitud,
        }

    @classmethod
    def desde_dict(cls, d):
        return cls(
            mu=d["mu"], ventaja_local=d["ventaja_local"], rho=d["rho"],
            ataque=dict(d["ataque"]), defensa=dict(d["defensa"]),
            equipos=dict(d.get("equipos", {})),
            partidos_usados=d.get("partidos_usados", 0),
            log_verosimilitud=d.get("log_verosimilitud", 0.0),
        )


def _pesos_temporales(partidos, fecha_ref, xi):
    #peso = exp(-xi * dias de antiguedad). Sin fecha, peso 1.
    pesos = []
    for p in partidos:
        dias = p.get("dias_atras")
        if dias is None:
            pesos.append(1.0)
        else:
            pesos.append(math.exp(-xi * max(0.0, float(dias))))
    return pesos


def ajustar(partidos, xi=XI_POR_DEFECTO, ridge=RIDGE_POR_DEFECTO,
            iteraciones=ITERACIONES, fecha_ref=None):
    #partidos: lista de dicts con
    #   local, visitante, goles_local, goles_visitante, dias_atras (opcional),
    #   neutral (opcional)
    #
    #Devuelve un AjusteLiga. Lanza ValueError si no hay datos suficientes.
    limpios = []
    for p in partidos:
        try:
            gl = int(p["goles_local"])
            gv = int(p["goles_visitante"])
        except (KeyError, TypeError, ValueError):
            continue
        l, v = _clave(p.get("local")), _clave(p.get("visitante"))
        if not l or not v or l == v or gl < 0 or gv < 0:
            continue
        limpios.append({
            "l": l, "v": v, "gl": gl, "gv": gv,
            "dias_atras": p.get("dias_atras"),
            "neutral": bool(p.get("neutral")),
            "nombre_l": p.get("local"), "nombre_v": p.get("visitante"),
        })
    if len(limpios) < 20:
        raise ValueError("hacen falta al menos 20 partidos para ajustar la liga")

    nombres = {}
    for p in limpios:
        nombres.setdefault(p["l"], p["nombre_l"])
        nombres.setdefault(p["v"], p["nombre_v"])
    equipos = sorted(nombres.keys())
    idx = {e: i for i, e in enumerate(equipos)}
    n_eq = len(equipos)

    pesos = _pesos_temporales(limpios, fecha_ref, xi)
    peso_total = sum(pesos) or 1.0

    #--- arranque sensato: media global de goles y ventaja local empirica ---
    goles_local = sum(w * p["gl"] for w, p in zip(pesos, limpios)) / peso_total
    goles_visita = sum(w * p["gv"] for w, p in zip(pesos, limpios)) / peso_total
    media = max(0.2, (goles_local + goles_visita) / 2.0)
    mu = math.log(media)
    ventaja = math.log(max(0.5, goles_local / max(0.05, goles_visita))) / 2.0

    ataque = [0.0] * n_eq
    defensa = [0.0] * n_eq

    #--- ascenso de gradiente sobre la log-verosimilitud COMPLETA ---
    #Se incluye el termino tau de Dixon-Coles en el gradiente. Solo afecta a
    #cuatro casillas (0-0, 1-0, 0-1, 1-1), pero si se deja fuera el modelo
    #compensa el sesgo inflando rho y la media de goles se queda corta.
    #Se alterna: ajustar fuerzas con el rho actual -> reajustar rho -> repetir.
    def _lambdas_de(i, j, neutral):
        casa = 0.0 if neutral else ventaja
        e1 = min(2.5, max(-3.0, mu + ataque[i] - defensa[j] + casa))
        e2 = min(2.5, max(-3.0, mu + ataque[j] - defensa[i]))
        return e1, e2, math.exp(e1), math.exp(e2)

    def _normalizador(lam1, lam2, rho_prueba):
        #La correccion tau reparte probabilidad pero no la conserva: la matriz
        #deja de sumar 1. Como tau solo vale distinto de 1 en cuatro casillas,
        #la constante que lo arregla se calcula exacta y barata:
        #   Z = 1 + suma sobre esas 4 casillas de p_poisson * (tau - 1)
        #Sin este termino, rho se infla para compensar y los marcadores bajos
        #salen deformados. Es el error clasico al implementar Dixon-Coles.
        z = 1.0
        for x, y in ((0, 0), (0, 1), (1, 0), (1, 1)):
            p_pois = poisson(lam1, x) * poisson(lam2, y)
            z += p_pois * (tau_dixon_coles(x, y, lam1, lam2, rho_prueba) - 1.0)
        return z

    def ll_con_rho(rho_prueba):
        #Verosimilitud completa (Poisson + tau + normalizacion)
        total = 0.0
        for w, p in zip(pesos, limpios):
            i, j = idx[p["l"]], idx[p["v"]]
            e1, e2, lam1, lam2 = _lambdas_de(i, j, p["neutral"])
            t = tau_dixon_coles(p["gl"], p["gv"], lam1, lam2, rho_prueba)
            z = _normalizador(lam1, lam2, rho_prueba)
            if t <= 0 or z <= 0:
                return -1e18
            total += w * (p["gl"] * e1 - lam1 + p["gv"] * e2 - lam2
                          + math.log(t) - math.log(z))
        return total

    def mejor_rho_actual():
        #Rango acotado a lo que se observa en ligas reales.
        #Sin este limite, rho se dispara para compensar sesgos de otros
        #parametros y acaba deformando los marcadores bajos.
        mejor_r, mejor_v = 0.0, ll_con_rho(0.0)
        r = -0.25
        while r <= 0.10001:
            v = ll_con_rho(r)
            if v > mejor_v:
                mejor_r, mejor_v = r, v
            r += 0.005
        return mejor_r, mejor_v

    rho = 0.0
    anterior = None
    for ronda in range(4):
        paso = PASO_INICIAL
        anterior = None
        for _ in range(iteraciones // 4):
            g_at = [0.0] * n_eq
            g_df = [0.0] * n_eq
            g_mu = 0.0
            g_hv = 0.0
            ll = 0.0

            for w, p in zip(pesos, limpios):
                i, j = idx[p["l"]], idx[p["v"]]
                e1, e2, lam1, lam2 = _lambdas_de(i, j, p["neutral"])
                x, y = p["gl"], p["gv"]

                r1 = x - lam1
                r2 = y - lam2

                #derivada del termino tau respecto a los exponentes
                t = tau_dixon_coles(x, y, lam1, lam2, rho)
                d1 = d2 = 0.0
                if t > 1e-9 and rho != 0.0:
                    if x == 0 and y == 0:
                        d1 = -lam1 * lam2 * rho / t
                        d2 = -lam1 * lam2 * rho / t
                    elif x == 0 and y == 1:
                        d1 = lam1 * rho / t
                    elif x == 1 and y == 0:
                        d2 = lam2 * rho / t
                    ll += w * math.log(t)

                g_at[i] += w * (r1 + d1)
                g_df[j] -= w * (r1 + d1)
                g_at[j] += w * (r2 + d2)
                g_df[i] -= w * (r2 + d2)
                g_mu += w * (r1 + d1 + r2 + d2)
                if not p["neutral"]:
                    g_hv += w * (r1 + d1)

                ll += w * (x * e1 - lam1 + y * e2 - lam2)

            #penalizacion ridge (empuja hacia el equipo promedio)
            for i in range(n_eq):
                g_at[i] -= ridge * peso_total * ataque[i]
                g_df[i] -= ridge * peso_total * defensa[i]
                ll -= 0.5 * ridge * peso_total * (ataque[i] ** 2 + defensa[i] ** 2)

            #paso adaptativo: si la verosimilitud baja, recorto el paso
            if anterior is not None and ll < anterior:
                paso *= 0.5
                if paso < 1e-5:
                    break
            else:
                paso *= 1.02
            anterior = ll

            escala = paso / peso_total
            for i in range(n_eq):
                ataque[i] += escala * g_at[i]
                defensa[i] += escala * g_df[i]
            mu += escala * g_mu
            ventaja += escala * g_hv
            ventaja = min(0.6, max(-0.2, ventaja))

            #identificabilidad: ataque y defensa solo estan definidos salvo una
            #constante. Se centran y el sobrante se pasa a mu.
            m_at = sum(ataque) / n_eq
            m_df = sum(defensa) / n_eq
            for i in range(n_eq):
                ataque[i] -= m_at
                defensa[i] -= m_df
            mu += m_at - m_df

        rho, anterior = mejor_rho_actual()

    mejor_rho = rho

    return AjusteLiga(
        mu=mu,
        ventaja_local=ventaja,
        rho=mejor_rho,
        ataque={e: ataque[idx[e]] for e in equipos},
        defensa={e: defensa[idx[e]] for e in equipos},
        equipos={e: nombres[e] for e in equipos},
        partidos_usados=len(limpios),
        log_verosimilitud=anterior or 0.0,
    )