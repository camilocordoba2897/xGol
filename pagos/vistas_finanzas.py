#Panel de control financiero. Vive aparte de views.py porque son dos cosas
#distintas: alli esta el flujo de pago del cliente, aqui la administracion del
#dinero. Asi tampoco hay que volver a tocar views.py para agregar reportes.
from datetime import datetime
from django.shortcuts import render,redirect,get_object_or_404
from django.contrib import messages
from django.http import HttpResponse
from django.views.decorators.http import require_POST
from django.core.paginator import Paginator
from django.conf import settings

from usuarios.decoradores import rol_requerido
from suscripciones.planes import PLANES
from pagos.models import Pago,Reembolso
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


@rol_requerido("administrador")
def panel_finanzas(request):
    filtros=_filtros(request)
    consulta=reportes.transacciones(filtros)
    paginas=Paginator(consulta,30)
    pagina=paginas.get_page(request.GET.get("pagina"))

    return render(request,"panel_finanzas.html",{
        "ingresos":reportes.resumen_ingresos(),
        "suscripciones":reportes.resumen_suscripciones(),
        "incidencias":reportes.resumen_incidencias(),
        "barras":reportes.barras(reportes.serie_mensual(12)),
        "por_plan":reportes.ventas_por_plan(),
        "por_metodo":reportes.ventas_por_metodo(),
        "pendientes":reportes.usuarios_pendientes(),
        "renovaciones":reportes.proximas_renovaciones(),
        "movimientos":reportes.movimientos(),
        "reembolsos":Reembolso.objects.select_related("pago","pago__usuario")[:15],
        "pagina":pagina,
        "filtros":filtros,
        "planes":PLANES,
        "total_filtrado":consulta.count(),
        "ambiente":settings.WOMPI_AMBIENTE,
        "pasarela_lista":pasarela.configurada(),
    })


@rol_requerido("administrador")
def exportar_finanzas(request):
    #El PDF es ahora el formato por defecto: reemplazo al CSV en el panel.
    #La exportacion a CSV sigue existiendo por si se pide con formato=csv,
    #para no romper un enlace guardado, pero ya no tiene boton propio.
    formato=(request.GET.get("formato") or "pdf").lower()
    tipo=(request.GET.get("tipo") or "transacciones").lower()
    marca=datetime.now().strftime("%Y%m%d_%H%M")
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
        subtitulo="Acumulados por periodo · Generado el "+datetime.now().strftime("%d/%m/%Y %H:%M")
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
                   +datetime.now().strftime("%d/%m/%Y %H:%M"))
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
def admin_reembolso(request,id):
    pago=get_object_or_404(Pago,id=id)
    if pago.estado!="Aprobado":
        messages.error(request,"Solo se puede reembolsar un pago aprobado")
        return redirect("PanelFinanzas")

    try:
        monto=int(request.POST.get("monto") or pago.monto)
    except (TypeError,ValueError):
        monto=pago.monto
    monto=max(0,min(monto,pago.monto))

    servicios.registrar_reembolso(
        pago,monto,request.POST.get("motivo",""),
        actor=request.user,revoca_dias=request.POST.get("revoca_dias")=="si")
    messages.success(request,
        f"Reembolso de ${monto:,} registrado sobre {pago.referencia}. "
        "Falta ejecutar la devolucion del dinero desde el panel de la pasarela.".replace(",","."))
    return redirect("PanelFinanzas")


@rol_requerido("administrador")
@require_POST
def admin_sincronizar_pago(request,id):
    #Vuelve a preguntarle a la pasarela por un pago concreto. Sirve cuando un
    #webhook se perdio y el usuario reclama que si pago.
    pago=get_object_or_404(Pago,id=id)
    if not pago.id_pasarela:
        messages.error(request,"Ese intento nunca llego a la pasarela, no hay nada que consultar")
        return redirect("PanelFinanzas")

    crudo,error=pasarela.consultar_transaccion(pago.id_pasarela)
    if error or not crudo:
        messages.error(request,f"No se pudo consultar la pasarela ({error})")
        return redirect("PanelFinanzas")

    pago_actualizado,resultado=servicios.aplicar_transaccion(
        pasarela.leer_transaccion(crudo),
        ambiente_evento=settings.WOMPI_AMBIENTE,
        actor=request.user)
    messages.success(request,f"Pago {pago.referencia} sincronizado: {resultado}")
    return redirect("PanelFinanzas")