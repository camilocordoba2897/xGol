#Panel de control financiero. Vive aparte de views.py porque son dos cosas
#distintas: alli esta el flujo de pago del cliente, aqui la administracion del
#dinero. Asi tampoco hay que volver a tocar views.py para agregar reportes.
from datetime import datetime
from django.utils import timezone
from django.shortcuts import render,redirect,get_object_or_404
from django.urls import reverse
from django.contrib import messages
from django.http import HttpResponse
from django.views.decorators.http import require_POST
from django.core.paginator import Paginator
from django.conf import settings

from usuarios.decoradores import rol_requerido
from suscripciones.planes import PLANES
from pagos.models import Pago
from pagos import pasarela,servicios,reportes,exportar,reporte_pdf


def _filtros(request):
    def fecha(nombre):
        crudo=(request.GET.get(nombre) or "").strip()
        if not crudo:
            return None
        try:
            return datetime.strptime(crudo,"%Y-%m-%d").date()
        except ValueError:
            return None
    return {
        "estado":request.GET.get("estado","todos"),
        "plan":request.GET.get("plan","todos"),
        "metodo":request.GET.get("metodo","todos"),
        "desde":fecha("desde"),
        "hasta":fecha("hasta"),
        "q":request.GET.get("q",""),
    }


#Las finanzas viven en la pestana "Dinero" del panel de administracion.
#Antes habia ademas esta pagina aparte, con las mismas cifras: nada la
#enlazaba, pero el boton Consultar devolvia aqui y sacaba al
#administrador del panel. Queda solo como redireccion para los enlaces
#guardados.
def _volver_al_dinero():
    return redirect(reverse("PanelAdmin")+"?tab=dinero")


@rol_requerido("administrador")
def panel_finanzas(request):
    return _volver_al_dinero()


@rol_requerido("administrador")
def exportar_finanzas(request):
    #El PDF es ahora el formato por defecto: reemplazo al CSV en el panel.
    #La exportacion a CSV sigue existiendo por si se pide con formato=csv,
    #para no romper un enlace guardado, pero ya no tiene boton propio.
    formato=(request.GET.get("formato") or "pdf").lower()
    tipo=(request.GET.get("tipo") or "transacciones").lower()
    marca=timezone.localtime().strftime("%Y%m%d_%H%M")
    filtros=_filtros(request)

    #El PDF de transacciones se arma con los objetos Pago, no con filas de
    #texto: necesita el usuario y los montos para poder dar formato y color.
    if formato=="pdf" and tipo!="resumen":
        pagos=reportes.transacciones(filtros).select_related("usuario")
        contenido=reporte_pdf.generar_reporte_pdf(pagos,filtros)
        respuesta=HttpResponse(contenido,content_type="application/pdf")
        respuesta["Content-Disposition"]=f'attachment; filename="xgol_transacciones_{marca}.pdf"'
        return respuesta

    if tipo=="resumen":
        cabeceras=exportar.CABECERAS_RESUMEN
        filas=list(exportar.filas_resumen(reportes.resumen_ingresos()))
        nombre=f"xgol_resumen_{marca}"
        titulo="Resumen financiero"
        subtitulo="Acumulados por periodo · Generado el "+timezone.localtime().strftime("%d/%m/%Y %H:%M")
        moneda=exportar.MONEDA_RESUMEN
        totalizar=exportar.TOTALIZAR_RESUMEN
        columna_estado=None
    else:
        cabeceras=exportar.CABECERAS_TRANSACCIONES
        filas=list(exportar.filas_transacciones(
            reportes.transacciones(filtros).select_related("usuario").iterator()))
        nombre=f"xgol_transacciones_{marca}"
        titulo="Historial de transacciones"
        subtitulo=(reporte_pdf._linea_filtros(filtros)+" · Generado el "
                   +timezone.localtime().strftime("%d/%m/%Y %H:%M"))
        moneda=exportar.MONEDA_TRANSACCIONES
        totalizar=exportar.TOTALIZAR_TRANSACCIONES
        columna_estado=exportar.COLUMNA_ESTADO_TRANSACCIONES

    if formato=="csv":
        contenido=exportar.a_csv(cabeceras,filas)
        tipo_mime="text/csv; charset=utf-8"
        extension="csv"
    else:
        contenido=exportar.a_xlsx(cabeceras,filas,hoja=tipo[:31].capitalize(),
                                  titulo=titulo,subtitulo=subtitulo,
                                  columnas_moneda=moneda,totalizar=totalizar,
                                  columna_estado=columna_estado)
        tipo_mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        extension="xlsx"

    respuesta=HttpResponse(contenido,content_type=tipo_mime)
    respuesta["Content-Disposition"]=f'attachment; filename="{nombre}.{extension}"'
    return respuesta


@rol_requerido("administrador")
@require_POST
def admin_sincronizar_pago(request,id):
    #Vuelve a preguntarle a la pasarela por un pago concreto. Sirve cuando un
    #webhook se perdio y el usuario reclama que si pago.
    #Sin id de la pasarela se busca por referencia: es justo el caso del
    #cliente que pago, cerro el navegador y cuyo webhook no llego.
    pago=get_object_or_404(Pago,id=id)
    if pago.id_pasarela:
        crudo,error=pasarela.consultar_transaccion(pago.id_pasarela)
    else:
        crudo,error=pasarela.buscar_por_referencia(pago.referencia)
    if error==pasarela.ERROR_NO_ENCONTRADA:
        messages.error(request,"Ese intento nunca llegó a la pasarela, no hay nada que consultar")
        return _volver_al_dinero()
    if error or not crudo:
        messages.error(request,f"No se pudo consultar la pasarela ({error})")
        return _volver_al_dinero()

    pago_actualizado,resultado=servicios.aplicar_transaccion(
        pasarela.leer_transaccion(crudo),
        ambiente_evento=settings.WOMPI_AMBIENTE,
        actor=request.user)
    messages.success(request,f"Pago {pago.referencia} consultado en la pasarela: {_RESULTADOS.get(resultado,resultado)}")
    return _volver_al_dinero()


#Lo que devuelve aplicar_transaccion, dicho para el administrador
_RESULTADOS={
    "aplicado":"estaba aprobado y ya se le dio el acceso al cliente",
    "ya_aplicado":"ya estaba aplicado, no hubo que hacer nada",
    "actualizado_sin_otorgar":"se actualizo el estado, la pasarela no lo reporta aprobado",
    "monto_no_coincide":"el monto cobrado no coincide con el del plan, NO se dio acceso",
    "moneda_no_coincide":"la moneda no coincide, NO se dio acceso",
    "plan_desconocido":"el plan del pago ya no existe, revisarlo a mano",
}