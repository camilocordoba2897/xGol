from django.urls import path
from inicio.views import (inicio,terminos_condiciones,politica_privacidad,aviso_legal,juego_responsable,
    partidos_hoy,partidos_proximos,partidos_vivo,tabla_posiciones,equipos_liga,predicciones_destacadas)

urlpatterns = [
    path('', inicio, name="Inicio"),
    path('terminos-y-condiciones', terminos_condiciones, name="TerminosCondiciones"),
    path('politica-de-privacidad', politica_privacidad, name="PoliticaPrivacidad"),
    path('aviso-legal', aviso_legal, name="AvisoLegal"),
    path('juego-responsable', juego_responsable, name="JuegoResponsable"),
    path('partidos/hoy', partidos_hoy, name="PartidosHoy"),
    path('partidos/proximos', partidos_proximos, name="PartidosProximos"),
    path('partidos/vivo', partidos_vivo, name="PartidosVivo"),
    path('predicciones/destacadas', predicciones_destacadas, name="PrediccionesDestacadas"),
    path('tabla', tabla_posiciones, name="TablaPosiciones"),
    path('equipos', equipos_liga, name="EquiposLiga"),
]