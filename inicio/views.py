from django.shortcuts import render
from usuarios.models import Perfil
from suscripciones.models import Suscripcion
from django.http import JsonResponse
from inicio import api_partidos

def inicio(request):
    perfil=None
    suscripcion_activa=False
    if request.user.is_authenticated:
        perfil,creado=Perfil.objects.get_or_create(usuario=request.user)
        suscripcion,creada=Suscripcion.objects.get_or_create(usuario=request.user)
        suscripcion_activa=suscripcion.esta_vigente()
    return render(request, 'inicio.html', {'perfil': perfil, 'suscripcion_activa': suscripcion_activa})

def terminos_condiciones(request):
    return render(request, 'terminos_condiciones.html')

def politica_privacidad(request):
    return render(request, 'politica_privacidad.html')

def aviso_legal(request):
    return render(request, 'aviso_legal.html')

def juego_responsable(request):
    return render(request, 'juego_responsable.html')

def partidos_hoy(request):
    return JsonResponse({"partidos": api_partidos.partidos_hoy()})

def partidos_proximos(request):
    return JsonResponse({"partidos": api_partidos.partidos_proximos()})

def partidos_vivo(request):
    return JsonResponse({"partidos": api_partidos.partidos_vivo()})

def predicciones_destacadas(request):
    return JsonResponse({"predicciones": api_partidos.predicciones_destacadas()})

def tabla_posiciones(request):
    liga = request.GET.get("liga", api_partidos.LIGAS["Premier League"])
    return JsonResponse({"tabla": api_partidos.tabla_posiciones(liga)})

def equipos_liga(request):
    liga = request.GET.get("liga", api_partidos.LIGAS["Premier League"])
    return JsonResponse({"equipos": api_partidos.equipos_liga(liga)})