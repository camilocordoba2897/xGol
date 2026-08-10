from django.contrib import admin
from pagos.models import Pago,EventoPasarela,MovimientoSuscripcion,Consecutivo

#Todo lo financiero se registra pero NO se edita a mano desde el admin: un
#pago que se pueda cambiar con dos clics deja de servir como evidencia.
#Para corregir algo estan las acciones del panel financiero, que dejan rastro.

@admin.register(Pago)
class PagoAdmin(admin.ModelAdmin):
  list_display=("referencia","usuario","plan","monto","estado","metodo","numero_factura","aplicado","creado")
  list_filter=("estado","plan","metodo","pasarela","ambiente","aplicado")
  search_fields=("referencia","numero_factura","id_pasarela","usuario__username","usuario__email")
  date_hierarchy="creado"
  readonly_fields=[campo.name for campo in Pago._meta.fields]

  def has_add_permission(self,request):
    return False

  def has_delete_permission(self,request,obj=None):
    return False


@admin.register(EventoPasarela)
class EventoPasarelaAdmin(admin.ModelAdmin):
  list_display=("creado","tipo","referencia","estado_reportado","firma_valida","procesado","ambiente")
  list_filter=("firma_valida","procesado","tipo","ambiente","pasarela")
  search_fields=("referencia","id_pasarela","checksum")
  date_hierarchy="creado"
  readonly_fields=[campo.name for campo in EventoPasarela._meta.fields]

  def has_add_permission(self,request):
    return False

  def has_change_permission(self,request,obj=None):
    return False


@admin.register(MovimientoSuscripcion)
class MovimientoSuscripcionAdmin(admin.ModelAdmin):
  list_display=("creado","usuario","tipo","plan","dias","vencimiento_nuevo","actor")
  list_filter=("tipo","plan")
  search_fields=("usuario__username","nota")
  date_hierarchy="creado"
  readonly_fields=[campo.name for campo in MovimientoSuscripcion._meta.fields]

  def has_add_permission(self,request):
    return False

  def has_change_permission(self,request,obj=None):
    return False


@admin.register(Consecutivo)
class ConsecutivoAdmin(admin.ModelAdmin):
  list_display=("nombre","valor","actualizado")
  readonly_fields=("actualizado",)