from django.contrib import admin
from analizador.models import PartidoRegistrado,RegistroApuesta

@admin.register(PartidoRegistrado)
class PartidoRegistradoAdmin(admin.ModelAdmin):
  list_display=("equipo_local","equipo_visitante","liga","fecha","usuario")
  list_filter=("usuario","liga")
  search_fields=("equipo_local","equipo_visitante","usuario__username")

@admin.register(RegistroApuesta)
class RegistroApuestaAdmin(admin.ModelAdmin):
  list_display=("etiqueta","mercado","probabilidad","acierto","propia","fecha","usuario")
  list_filter=("usuario","mercado","acierto","propia")
  search_fields=("etiqueta","equipo_local","equipo_visitante","usuario__username")
