from django.urls import path
from suscripciones.views import suscripcion,checkout,admin_activar_suscripcion,admin_cancelar_suscripcion

urlpatterns = [
    path('suscripcion', suscripcion, name="Suscripcion"),
    path('suscripcion/checkout/<str:clave_plan>', checkout, name="Checkout"),
    path('admin-panel/suscripcion/activar/<int:id>', admin_activar_suscripcion, name="AdminActivarSuscripcion"),
    path('admin-panel/suscripcion/cancelar/<int:id>', admin_cancelar_suscripcion, name="AdminCancelarSuscripcion"),
]