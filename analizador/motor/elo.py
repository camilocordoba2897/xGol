#FUENTE 2 — Elo con margen de goles.
#
#Por que meter Elo si ya tenemos Dixon-Coles: porque se equivocan de forma
#DISTINTA. Dixon-Coles mira cuantos goles metes y encajas; Elo mira si ganas,
#y cuanto reacciona depende de por cuanto ganaste y contra quien. Cuando dos
#modelos que fallan distinto se promedian, el error del conjunto baja. No es
#opinion: es la razon matematica por la que existen los "ensembles".
#
#El Elo de aqui es el de la escuela FiveThirtyEight / ClubElo:
#  - K ajustado por el margen de victoria (ganar 4-0 sube mas que ganar 1-0)
#  - amortiguacion del margen cuando el favorito ya era favorito, para que las
#    goleadas contra un rival hundido no inflen el rating
#  - ventaja de campo en puntos Elo
#
#La salida NO son probabilidades sueltas: son unos goles esperados (lam1, lam2)
#para que esta fuente entre en la MISMA matriz de marcadores que las demas y
#todos los mercados sigan siendo coherentes.
import math

ELO_INICIAL = 1500.0
K_BASE = 20.0
VENTAJA_LOCAL_ELO = 60.0     #puntos Elo que vale jugar en casa
GOLES_POR_400 = 0.90         #goles de diferencia esperados por cada 400 pts Elo
REGRESION_TEMPORADA = 0.20   #cuanto se vuelve a la media al cambiar de temporada


def _clave(nombre):
    return str(nombre or "").strip().lower()


class TablaElo:
    def __init__(self, ratings=None, nombres=None, partidos=None):
        self.ratings = ratings or {}
        self.nombres = nombres or {}
        self.partidos = partidos or {}

    def rating(self, equipo):
        return self.ratings.get(_clave(equipo), ELO_INICIAL)

    def diferencia(self, local, visitante, cancha_neutral=False):
        casa = 0.0 if cancha_neutral else VENTAJA_LOCAL_ELO
        return self.rating(local) + casa - self.rating(visitante)

    def lambdas(self, local, visitante, media_goles_liga, cancha_neutral=False):
        #Convierte la diferencia de Elo en una supremacia de goles y reparte
        #el total de la liga entre los dos equipos.
        dif = self.diferencia(local, visitante, cancha_neutral)
        supremacia = GOLES_POR_400 * (dif / 400.0)
        total = max(0.6, float(media_goles_liga))
        lam1 = max(0.15, (total + supremacia) / 2.0)
        lam2 = max(0.15, (total - supremacia) / 2.0)
        return lam1, lam2

    def clasificacion(self):
        filas = [{"equipo": self.nombres.get(k, k), "elo": v,
                  "partidos": self.partidos.get(k, 0)}
                 for k, v in self.ratings.items()]
        filas.sort(key=lambda f: f["elo"], reverse=True)
        return filas

    def a_dict(self):
        return {"ratings": self.ratings, "nombres": self.nombres,
                "partidos": self.partidos}

    @classmethod
    def desde_dict(cls, d):
        return cls(dict(d.get("ratings", {})), dict(d.get("nombres", {})),
                   dict(d.get("partidos", {})))


def _multiplicador_margen(margen, dif_elo_ganador):
    #Formula 538: el margen sube K, pero se frena si el ganador ya era favorito.
    margen = abs(margen)
    if margen == 0:
        return 1.0
    return math.log(margen + 1.0) * (2.2 / (dif_elo_ganador * 0.001 + 2.2))


def calcular(partidos, k_base=K_BASE, elo_previo=None):
    #partidos: lista de dicts con local, visitante, goles_local, goles_visitante
    #y opcionalmente temporada y neutral. DEBEN venir del mas viejo al mas nuevo.
    tabla = TablaElo()
    if elo_previo:
        tabla = TablaElo.desde_dict(elo_previo.a_dict()
                                    if isinstance(elo_previo, TablaElo) else elo_previo)

    temporada_actual = None
    for p in partidos:
        try:
            gl = int(p["goles_local"])
            gv = int(p["goles_visitante"])
        except (KeyError, TypeError, ValueError):
            continue
        l, v = _clave(p.get("local")), _clave(p.get("visitante"))
        if not l or not v or l == v:
            continue

        #cambio de temporada: todos regresan un poco hacia 1500
        temporada = p.get("temporada")
        if temporada is not None and temporada != temporada_actual:
            if temporada_actual is not None:
                for k in tabla.ratings:
                    tabla.ratings[k] += REGRESION_TEMPORADA * (ELO_INICIAL - tabla.ratings[k])
            temporada_actual = temporada

        tabla.nombres.setdefault(l, p.get("local"))
        tabla.nombres.setdefault(v, p.get("visitante"))
        r_l = tabla.ratings.setdefault(l, ELO_INICIAL)
        r_v = tabla.ratings.setdefault(v, ELO_INICIAL)

        casa = 0.0 if p.get("neutral") else VENTAJA_LOCAL_ELO
        dif = r_l + casa - r_v
        esperado = 1.0 / (1.0 + 10 ** (-dif / 400.0))
        real = 1.0 if gl > gv else (0.5 if gl == gv else 0.0)

        margen = gl - gv
        dif_ganador = abs(dif) if (margen > 0) == (dif > 0) else -abs(dif)
        mult = _multiplicador_margen(margen, max(0.0, dif_ganador))
        cambio = k_base * mult * (real - esperado)

        tabla.ratings[l] = r_l + cambio
        tabla.ratings[v] = r_v - cambio
        tabla.partidos[l] = tabla.partidos.get(l, 0) + 1
        tabla.partidos[v] = tabla.partidos.get(v, 0) + 1

    return tabla