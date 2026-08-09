from django.urls import path
from analizador.views import (analizador,cargar_biblioteca,guardar_biblioteca,cargar_apuestas,guardar_apuestas,
    auto_partidos,auto_enfrentamiento,auto_resultados)

urlpatterns = [
    path('analizador', analizador, name="Analizador"),
    path('analizador/biblioteca/cargar', cargar_biblioteca, name="CargarBiblioteca"),
    path('analizador/biblioteca/guardar', guardar_biblioteca, name="GuardarBiblioteca"),
    path('analizador/apuestas/cargar', cargar_apuestas, name="CargarApuestas"),
    path('analizador/apuestas/guardar', guardar_apuestas, name="GuardarApuestas"),
    path('analizador/auto/partidos', auto_partidos, name="AutoPartidos"),
    path('analizador/auto/enfrentamiento', auto_enfrentamiento, name="AutoEnfrentamiento"),
    path('analizador/auto/resultados', auto_resultados, name="AutoResultados"),
]