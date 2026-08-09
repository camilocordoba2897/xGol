from django.contrib import admin
from usuarios.models import Rol,Perfil,Bitacora

class RolAdmin(admin.ModelAdmin):
  list_display=['nombre','descripcion','creado']
  list_filter=['nombre']
  search_fields=['nombre']
  readonly_fields=['creado']


class PerfilAdmin(admin.ModelAdmin):
  list_display=['usuario','rol','telefono','proveedor','creado']
  list_filter=['rol','proveedor']
  search_fields=['usuario__username','telefono']
  readonly_fields=['creado']


class BitacoraAdmin(admin.ModelAdmin):
  list_display=['accion','usuario','ip','creado']
  list_filter=['creado']
  search_fields=['accion','usuario__username']
  readonly_fields=['creado']


admin.site.register(Rol,RolAdmin)
admin.site.register(Perfil,PerfilAdmin)
admin.site.register(Bitacora,BitacoraAdmin)
