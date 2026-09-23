from django.urls import path
from analizador.motor_vistas import motor_pronostico
from analizador.views import (analizador,cargar_apuestas,guardar_apuestas,
    auto_partidos,auto_enfrentamiento,auto_resultados,auto_cuotas)

urlpatterns = [
    path('analizador', analizador, name="Analizador"),
    path('analizador/apuestas/cargar', cargar_apuestas, name="CargarApuestas"),
    path('analizador/apuestas/guardar', guardar_apuestas, name="GuardarApuestas"),
    path('analizador/auto/partidos', auto_partidos, name="AutoPartidos"),
    path('analizador/auto/enfrentamiento', auto_enfrentamiento, name="AutoEnfrentamiento"),
    path('analizador/auto/resultados', auto_resultados, name="AutoResultados"),
    path('analizador/auto/cuotas', auto_cuotas, name="AutoCuotas"),
    path('analizador/motor/pronostico', motor_pronostico, name="MotorPronostico"),
]