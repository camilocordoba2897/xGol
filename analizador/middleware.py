#Mantenimiento automatico del motor de prediccion, sin cron.
#
#El motor es tan bueno como sus datos. Para estar al dia necesita:
#
#  ajustar_motor           fuerzas de cada equipo y Elo con los partidos nuevos.
#                          Si no se corre, el motor no se entera de las ultimas
#                          jornadas. Gasta ~18 peticiones de API.
#  ajustar_motor --afinar  la "memoria" optima de cada liga. Una vez al mes.
#  calibrar_con_historico  pesos de cada fuente y calibracion, aprendidos a
#                          ciegas sobre miles de partidos del historico. Sin
#                          esto el motor usa los pesos de fabrica. NO gasta API.
#  evaluar_motor           pone resultado a los pronosticos ya jugados.
#
#Esos comandos se corrian a mano en un computador, y su resultado quedaba en
#ESA base de datos: el sitio publicado, con su propia base, nunca los tenia.
#Aqui los dispara el propio trafico del sitio, en un hilo aparte (el visitante
#no espera nada) y en UN solo proceso aunque gunicorn tenga varios (cache.add
#es atomico).
import logging
import threading
from io import StringIO

from django.conf import settings
from django.core.cache import cache
from django.core.management import call_command
from django.db import connections
from django.utils import timezone

logger = logging.getLogger(__name__)

#Lo que gasta API se corre de madrugada (hora de Colombia): es cuando menos
#gente usa el sitio, y ajustar las 9 ligas se come casi todo el cupo de
#football-data durante un par de minutos.
HORA_DESDE = 3
HORA_HASTA = 6
AFINAR_CADA_DIAS = 30


def _correr(*args, **kwargs):
    salida = StringIO()
    call_command(*args, stdout=salida, stderr=salida, **kwargs)
    logger.info("mantenimiento del motor: %s\n%s", " ".join(map(str, args)), salida.getvalue())


def _sin_calibracion():
    from analizador.models import PesosMotor
    return not PesosMotor.objects.exists()


def _sin_ajustes():
    from analizador.models import AjusteMotor
    return not AjusteMotor.objects.exists()


def _toca_afinar():
    #Una vez al mes. La marca vive en la cache de la base, que sobrevive a
    #los despliegues. OJO: no se mira si una liga "tiene" parametros
    #afinados: cuando afinar no mejora de verdad a los de fabrica, la liga
    #se queda con los de fabrica a proposito, y con esa regla se volveria a
    #afinar (35 minutos de procesador) todas las noches.
    return cache.get("motor_afinado_reciente") is None


def _calibrar():
    try:
        _correr("calibrar_con_historico")
    except Exception:
        logger.exception("Fallo calibrar_con_historico")
    finally:
        connections.close_all()


def _mantenimiento_nocturno(permitir_afinar=True):
    try:
        if permitir_afinar and _toca_afinar():
            _correr("ajustar_motor", "--afinar")
            cache.set("motor_afinado_reciente", 1, AFINAR_CADA_DIAS * 86400)
        else:
            _correr("ajustar_motor")
        _correr("evaluar_motor")
    except Exception:
        logger.exception("Fallo el mantenimiento nocturno del motor")
    finally:
        connections.close_all()


def _primer_ajuste():
    _mantenimiento_nocturno(permitir_afinar=False)


def _lanzar(objetivo):
    threading.Thread(target=objetivo, daemon=True).start()


class MantenimientoMotor:

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        respuesta = self.get_response(request)
        if not getattr(settings, "MOTOR_AUTOMATICO", False):
            return respuesta
        try:
            self._revisar()
        except Exception:
            pass
        return respuesta

    def _revisar(self):
        #Calibracion: si la base no la tiene, se aprende ya (no gasta API).
        #La marca dura 3 horas: tiempo de sobra para terminar sin que otro
        #proceso la lance dos veces a la vez.
        if cache.get("motor_calibrado_revisado") is None:
            cache.set("motor_calibrado_revisado", 1, 3600)
            if _sin_calibracion() and cache.add("motor_calibrando", 1, 3 * 3600):
                _lanzar(_calibrar)
            #Base sin ningun ajuste (sitio recien publicado): el primero corre
            #ya, sin esperar a la madrugada. Pasa una sola vez, y es el ajuste
            #RAPIDO: afinar deja el servidor ocupado casi 40 minutos, eso
            #queda para la madrugada.
            if _sin_ajustes() and cache.add("motor_primer_ajuste", 1, 3 * 3600):
                _lanzar(_primer_ajuste)

        #Ajuste diario: una vez por dia, de madrugada
        ahora = timezone.localtime()
        if HORA_DESDE <= ahora.hour < HORA_HASTA:
            if cache.add(f"motor_diario_{ahora.date().isoformat()}", 1, 26 * 3600):
                _lanzar(_mantenimiento_nocturno)
