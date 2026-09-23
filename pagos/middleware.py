#Conciliacion automatica de pagos, sin cron.
#
#El comando conciliar_pagos rescata los pagos cuyo aviso de Wompi se perdio,
#cierra los intentos abandonados y apaga las suscripciones vencidas. Pero
#solo sirve si alguien lo ejecuta: conciliar.bat lo hacia desde el
#Programador de tareas de un computador, y en Railway no corria nunca.
#
#Aqui lo dispara el propio trafico del sitio: como mucho una vez por hora,
#en un hilo aparte (el visitante no espera nada) y en UN solo proceso aunque
#gunicorn tenga varios, porque cache.add es atomico: solo el primero que
#llega consigue poner la marca.
import logging
import threading

from django.conf import settings
from django.core.cache import cache
from django.db import connections

logger = logging.getLogger(__name__)

MARCA = "conciliacion_automatica"
CADA_SEGUNDOS = 3600


def _conciliar():
    from pagos import pasarela, servicios
    try:
        if pasarela.configurada():
            servicios.conciliar_pendientes()
        servicios.caducar_pendientes()
        servicios.marcar_vencidas()
    except Exception:
        #Si falla, el sitio sigue igual; la proxima hora se vuelve a intentar
        logger.exception("Fallo la conciliacion automatica")
    finally:
        #El hilo abrio su propia conexion a la base: se cierra al terminar
        connections.close_all()


class ConciliacionAutomatica:

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        respuesta = self.get_response(request)
        if getattr(settings, "CONCILIACION_AUTOMATICA", False):
            try:
                if cache.add(MARCA, 1, CADA_SEGUNDOS):
                    threading.Thread(target=_conciliar, daemon=True).start()
            except Exception:
                pass
        return respuesta
