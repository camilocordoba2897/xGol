from django.shortcuts import render,redirect,get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.contrib.auth.models import User
from django.views.decorators.http import require_POST
from django.conf import settings
from suscripciones.models import Suscripcion
from suscripciones.planes import PLANES,obtener_plan,nivel_de_plan
from usuarios.decoradores import rol_requerido

@login_required(login_url="Ingresar")
def suscripcion(request):
    suscripcion,creada=Suscripcion.objects.get_or_create(usuario=request.user)

    if suscripcion.activa and not suscripcion.esta_vigente():
        suscripcion.activa=False
        suscripcion.save()

    dias_restantes=0
    if suscripcion.esta_vigente():
        dias_restantes=(suscripcion.vencimiento-timezone.now().date()).days

    nivel_actual=0
    if suscripcion.esta_vigente():
        for clave,plan in PLANES.items():
            if plan["nombre"]==suscripcion.plan:
                nivel_actual=plan["nivel"]

    return render(request,"suscripcion.html",{
        "suscripcion": suscripcion,
        "dias_restantes": dias_restantes,
        "planes": PLANES,
        "nivel_actual": nivel_actual
    })


@login_required(login_url="Ingresar")
def checkout(request,clave_plan):
    from suscripciones.planes import desglosar_precio
    from pagos import pasarela

    plan=obtener_plan(clave_plan)
    if plan is None:
        return redirect("Suscripcion")

    #Misma regla que en procesar_pago: no se muestra el checkout de un plan
    #que el usuario no puede comprar, aunque llegue por la URL directa.
    suscripcion=Suscripcion.objects.filter(usuario=request.user).first()
    if suscripcion is not None and suscripcion.esta_vigente():
        if plan["nivel"]<=nivel_de_plan(suscripcion.plan):
            messages.info(request,f"Ya tienes el plan {suscripcion.plan} activo. Solo puedes pasar a un plan superior.")
            return redirect("Suscripcion")

    desglose=desglosar_precio(plan["precio"])

    #El checkout ya no pide datos de tarjeta: solo muestra el resumen y manda
    #al usuario a la pasarela. pasarela_lista evita mostrar un boton que
    #llevaria a una pantalla rota si faltan llaves en .env.
    return render(request,"checkout.html",{
        "plan": plan,
        "clave_plan": clave_plan,
        "subtotal": desglose["subtotal"],
        "iva": desglose["iva"],
        "pasarela_lista": pasarela.configurada(),
        "ambiente": settings.WOMPI_AMBIENTE
    })


@rol_requerido("administrador")
@require_POST
def admin_activar_suscripcion(request,id):
    #Activacion manual (cortesia, prueba, pago por fuera de la pasarela).
    #Es POST porque otorga acceso de pago: con un enlace GET bastaria una
    #imagen apuntando a esta URL para regalar suscripciones sin querer.
    from pagos.models import Pago,Consecutivo,MovimientoSuscripcion
    from suscripciones.planes import desglosar_precio
    from django.db import transaction
    import uuid

    usuario=get_object_or_404(User,id=id)
    clave_plan=request.POST.get("plan","mensual")
    plan=obtener_plan(clave_plan) or PLANES["mensual"]
    metodo=request.POST.get("metodo","Manual")
    desglose=desglosar_precio(plan["precio"])

    with transaction.atomic():
        suscripcion,creada=Suscripcion.objects.select_for_update().get_or_create(usuario=usuario)
        vencimiento_anterior=suscripcion.vencimiento
        era_vigente=suscripcion.esta_vigente()
        suscripcion.activar(plan["nombre"],plan["precio"],plan["dias"])
        suscripcion.origen="admin"
        suscripcion.save(update_fields=["origen"])

        #El pago se guarda COMPLETO: antes se creaba sin subtotal, sin IVA y
        #sin numero de factura, y el PDF salia con totales en cero.
        pago=Pago.objects.create(
            usuario=usuario,
            plan=plan["nombre"],
            clave_plan=clave_plan,
            monto=plan["precio"],
            subtotal=desglose["subtotal"],
            iva=desglose["iva"],
            monto_centavos=plan["precio"]*100,
            metodo=metodo,
            metodo_detalle="MANUAL",
            estado="Aprobado",
            referencia="ADM-"+uuid.uuid4().hex[:12].upper(),
            numero_factura=Consecutivo.siguiente("factura",prefijo="FAC",ancho=5),
            pasarela="manual",
            ambiente=settings.WOMPI_AMBIENTE,
            aplicado=True,
            dias_otorgados=plan["dias"],
            vigencia_inicio=suscripcion.inicio,
            vigencia_fin=suscripcion.vencimiento,
            aprobado_en=timezone.now(),
            correo_pagador=usuario.email or "",
        )

        MovimientoSuscripcion.objects.create(
            usuario=usuario,
            tipo="Renovacion" if era_vigente else "Activacion",
            plan=plan["nombre"],
            dias=plan["dias"],
            vencimiento_anterior=vencimiento_anterior,
            vencimiento_nuevo=suscripcion.vencimiento,
            pago=pago,
            actor=request.user,
            nota="Activacion manual desde el panel",
        )

    messages.success(request,f"Suscripcion de {usuario.username} activada hasta el {suscripcion.vencimiento:%d/%m/%Y}")
    return redirect("PanelAdmin")


@rol_requerido("administrador")
@require_POST
def admin_cancelar_suscripcion(request,id):
    from pagos.models import MovimientoSuscripcion

    usuario=get_object_or_404(User,id=id)
    suscripcion,creada=Suscripcion.objects.get_or_create(usuario=usuario)
    vencimiento_anterior=suscripcion.vencimiento

    #Cancelar apaga el acceso y la renovacion. Si se quiere devolver el dinero,
    #eso se hace aparte desde el panel financiero para que quede el reembolso.
    suscripcion.activa=False
    suscripcion.renovacion_automatica=False
    suscripcion.cancelada_en=timezone.now().date()
    suscripcion.save(update_fields=["activa","renovacion_automatica","cancelada_en"])

    MovimientoSuscripcion.objects.create(
        usuario=usuario,
        tipo="Cancelacion",
        plan=suscripcion.plan,
        vencimiento_anterior=vencimiento_anterior,
        vencimiento_nuevo=suscripcion.vencimiento,
        actor=request.user,
        nota="Cancelada desde el panel de administracion",
    )

    messages.success(request,f"Suscripcion de {usuario.username} cancelada")
    return redirect("PanelAdmin")