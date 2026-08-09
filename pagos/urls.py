from django.urls import path
from pagos.views import procesar_pago,retorno_pago,pago_confirmado,descargar_factura,webhook_wompi
from pagos.vistas_finanzas import panel_finanzas,exportar_finanzas,admin_reembolso,admin_sincronizar_pago

urlpatterns = [
    path('pago/procesar/<str:clave_plan>', procesar_pago, name="ProcesarPago"),
    path('pago/retorno', retorno_pago, name="RetornoPago"),
    path('pago/confirmado/<int:id>', pago_confirmado, name="PagoConfirmado"),
    path('pago/factura/<int:id>', descargar_factura, name="DescargarFactura"),
    #Ruta larga y poco adivinable: reduce el ruido de bots contra el webhook.
    #La seguridad real la da la firma del evento, no la URL.
    path('pago/eventos/wompi/x7k2', webhook_wompi, name="WebhookWompi"),

    path('admin-panel/finanzas', panel_finanzas, name="PanelFinanzas"),
    path('admin-panel/finanzas/exportar', exportar_finanzas, name="ExportarFinanzas"),
    path('admin-panel/finanzas/reembolso/<int:id>', admin_reembolso, name="AdminReembolso"),
    path('admin-panel/finanzas/sincronizar/<int:id>', admin_sincronizar_pago, name="AdminSincronizarPago"),
]