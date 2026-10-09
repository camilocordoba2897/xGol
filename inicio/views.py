from django.shortcuts import render
from django.utils.translation import gettext, get_language
from django.views.decorators.cache import cache_control
from django.views.decorators.gzip import gzip_page
from usuarios.models import Perfil
from suscripciones.models import Suscripcion
from django.http import HttpResponse, JsonResponse
from inicio import api_partidos, manual
from suscripciones.planes import PLANES

def inicio(request):
    perfil=None
    suscripcion_activa=False
    if request.user.is_authenticated:
        perfil,creado=Perfil.objects.get_or_create(usuario=request.user)
        suscripcion,creada=Suscripcion.objects.get_or_create(usuario=request.user)
        suscripcion_activa=suscripcion.esta_vigente()
    #Los precios salen de suscripciones/planes.py, igual que en el checkout:
    #si estuvieran escritos a mano aqui, un cambio de precio dejaria el home
    #anunciando uno y la pasarela cobrando otro.
    return render(request, 'inicio.html', {'perfil': perfil, 'suscripcion_activa': suscripcion_activa,
                                           'planes': PLANES})

def terminos_condiciones(request):
    return render(request, 'terminos_condiciones.html')

def politica_privacidad(request):
    return render(request, 'politica_privacidad.html')

def aviso_legal(request):
    return render(request, 'aviso_legal.html')

def juego_responsable(request):
    return render(request, 'juego_responsable.html')

#El manual de usuario en el idioma elegido en el home (inicio/manual.py).
#El enlace lleva ?idioma=... para que el navegador guarde una copia por idioma.
@cache_control(max_age=3600)
@gzip_page
def manual_usuario(request):
    return HttpResponse(manual.manual_en(get_language()), content_type="text/html; charset=utf-8")

#Las listas de partidos se guardan en cache una sola vez para todos los
#idiomas, con el nombre de la liga en español. Se traduce aqui, al
#responder, en el idioma de quien pide (la Champions en portugues es "Liga
#dos Campeões"; las demas se llaman igual en todo el mundo).
def _ligas_traducidas(partidos):
    return [dict(p, liga=gettext(p["liga"])) if p.get("liga") else p for p in partidos]

def partidos_hoy(request):
    return JsonResponse({"partidos": _ligas_traducidas(api_partidos.partidos_hoy())})

def partidos_proximos(request):
    return JsonResponse({"partidos": _ligas_traducidas(api_partidos.partidos_proximos())})

def partidos_vivo(request):
    return JsonResponse({"partidos": _ligas_traducidas(api_partidos.partidos_vivo())})

def predicciones_destacadas(request):
    datos = dict(api_partidos.predicciones_destacadas())
    datos["tarjetas"] = _ligas_traducidas(datos.get("tarjetas") or [])
    return JsonResponse({"predicciones": datos})

#Estas dos rutas son publicas. Antes aceptaban cualquier codigo de liga, y
#cada codigo inventado era una peticion a football-data: bastaba con pedir
#codigos al azar para agotar el cupo de 10 por minuto y dejar el home sin
#datos para todos. Solo se atienden las nueve ligas que cubre xGol.
def _liga_pedida(request):
    liga = request.GET.get("liga", api_partidos.LIGAS["Premier League"])
    return liga if liga in api_partidos.CODIGOS else None

def tabla_posiciones(request):
    liga = _liga_pedida(request)
    if liga is None:
        return JsonResponse({"tabla": [], "error": "liga_no_cubierta"}, status=400)
    return JsonResponse({"tabla": api_partidos.tabla_posiciones(liga)})

def equipos_liga(request):
    liga = _liga_pedida(request)
    if liga is None:
        return JsonResponse({"equipos": [], "error": "liga_no_cubierta"}, status=400)
    return JsonResponse({"equipos": api_partidos.equipos_liga(liga)})