#Motor de pronostico de xGol.
#
#Lo unico que necesitas importar desde el resto del proyecto:
#
#   from analizador.motor import tasas, elo, nucleo
#
#   ajuste = tasas.ajustar(partidos_de_la_liga)
#   tabla  = elo.calcular(partidos_de_la_liga)
#   r      = nucleo.pronosticar("Real Madrid", "Barcelona",
#                               ajuste_liga=ajuste, tabla_elo=tabla, casas=cuotas)
#   r.mercados["1x2"]        -> {"local":0.47,"empate":0.26,"visitante":0.27}
#   r.mercados["totales"]["2.5"]["mas"]
#   r.diagnostico["confianza"]
#
#Todo con libreria estandar de Python. Sin numpy, sin scipy, sin nada que
#instalar.
from . import calibracion, combinacion, elo, evaluacion, mercado, nucleo, probabilidad, tasas

__all__ = ["probabilidad", "tasas", "elo", "mercado", "combinacion",
           "calibracion", "evaluacion", "nucleo"]

VERSION = "1.0"