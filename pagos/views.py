import json
from django.shortcuts import render,redirect
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponse,JsonResponse,HttpResponseBadRequest
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.urls import reverse
from urllib.parse import urlparse
from django.core.cache import cache
from django.conf import settings

from suscripciones.models import Suscripcion
from suscripciones.planes import obtener_plan,nivel_de_plan
from pagos.models import Pago,EventoPasarela
from pagos import pasarela,servicios
from usuarios.models import Perfil,falta_identidad
from usuarios.validaciones import completar_identidad

#Tope de intentos de checkout por usuario y minuto. Un bot que abra el
#checkout mil veces no llena la tabla de pagos ni gasta cupo de la pasarela.
LIMITE_INTENTOS=8


def _url_publica(request,nombre_url):
    #A DONDE VUELVE EL USUARIO DESPUES DE PAGAR.
    #
    #En produccion la URL base viene de .env porque detras de un proxy el
    #request puede reportar http:// y Wompi exige una URL alcanzable.
    #
    #PERO SOLO SE USA SI EL NAVEGADOR ESTA DE VERDAD EN ESE DOMINIO.
    #
    #Antes se usaba siempre, y eso rompia el pago en local: con el navegador
    #en 127.0.0.1 y PAGOS_URL_BASE apuntando al tunel, Wompi cobraba bien y
    #despues devolvia al usuario a un tunel apagado (ERR_NGROK_3200). El
    #dinero salia y el cliente veia una pagina de error.
    #
    #Comparando el anfitrion se acierta en los tres casos sin tocar el .env:
    #   navegador en 127.0.0.1  -> vuelve a 127.0.0.1
    #   navegador en el tunel   -> vuelve al tunel
    #   navegador en el dominio -> vuelve al dominio, con su https del .env
    ruta=reverse(nombre_url)
    base=(getattr(settings,"PAGOS_URL_BASE","") or "").rstrip("/")
    if base:
        anfitrion_base=(urlparse(base).hostname or "").lower()
        anfitrion_actual=request.get_host().split(":")[0].lower()
        if anfitrion_base and anfitrion_base==anfitrion_actual:
            return base+ruta
    return request.build_absolute_uri(ruta)


# ============================================================
#  INICIO DEL PAGO
#  Antes esta vista activaba la suscripcion directamente. Ahora solo crea el
#  intento y manda al checkout de Wompi: el acceso lo concede el webhook,
#  cuando el dinero existe de verdad.
# ============================================================
@login_required(login_url="Ingresar")
@require_POST
def procesar_pago(request,clave_plan):
    plan=obtener_plan(clave_plan)
    if plan is None:
        messages.error(request,"Ese plan no existe")
        return redirect("Suscripcion")

    if not pasarela.configurada():
        messages.error(request,"Los pagos no estan disponibles en este momento. Intentalo mas tarde.")
        return redirect("Suscripcion")

    #Mayoria de edad: si al usuario le faltan la cedula o la fecha, vienen en
    #este mismo POST desde el checkout y se guardan aqui, en el mismo clic de
    #"Ir a pagar". Un POST hecho a mano sin ellas tampoco pasa.
    if falta_identidad(request.user):
        perfil,creado=Perfil.objects.get_or_create(usuario=request.user)
        documento=request.POST.get("documento")
        fecha=request.POST.get("fecha_nacimiento")
        error=completar_identidad(perfil,documento,fecha)
        if error:
            messages.error(request,error)
            request.session["identidad_borrador"]={"documento":documento or "","fecha_nacimiento":fecha or ""}
            return redirect("Checkout",clave_plan=clave_plan)

    #No se puede comprar un plan de nivel igual o inferior al que ya esta
    #vigente. La plantilla oculta el boton, pero un boton oculto no impide un
    #POST hecho a mano: la regla se aplica aca.
    suscripcion=Suscripcion.objects.filter(usuario=request.user).first()
    if suscripcion is not None and suscripcion.esta_vigente():
        if plan["nivel"]<=nivel_de_plan(suscripcion.plan):
            messages.info(request,f"Ya tienes el plan {suscripcion.plan} activo. Solo puedes pasar a un plan superior.")
            return redirect("Suscripcion")

    llave=f"intentos_pago_{request.user.id}"
    intentos=cache.get(llave,0)
    if intentos>=LIMITE_INTENTOS:
        messages.error(request,"Hiciste demasiados intentos seguidos. Espera un minuto y vuelve a intentarlo.")
        return redirect("Suscripcion")
    cache.set(llave,intentos+1,60)

    pago,error=servicios.crear_pago_pendiente(request.user,clave_plan,servicios.obtener_ip(request))
    if error or pago is None:
        messages.error(request,"No se pudo iniciar el pago. Intentalo de nuevo.")
        return redirect("Suscripcion")

    #Se marca en la sesion que fue ESTE navegador el que inicio ESTE pago.
    #Sin esta marca, el retorno tendria que fiarse solo del id que viaja en la
    #direccion, y ese id no es un secreto: queda en el historial, en la barra
    #del navegador y en el comprobante de Wompi.
    request.session["pago_en_curso"]=pago.id

    return redirect(pasarela.url_checkout(pago,_url_publica(request,"RetornoPago")))


# ============================================================
#  RETORNO DEL USUARIO DESDE LA PASARELA
#  Es informativo. La verdad la escribe el webhook; aca solo se consulta el
#  estado para no dejar al usuario mirando una pantalla en blanco.
# ============================================================
#Sin @login_required a proposito. Al volver de la pasarela la sesion puede
#haberse perdido (dominio distinto, cookie SameSite, tunel reiniciado); si
#exigieramos sesion aqui, el usuario que ya pago aterrizaria en el login sin
#saber si le cobraron. El pago se aplica igual: quien manda es el webhook.
def retorno_pago(request):
    id_transaccion=(request.GET.get("id") or "").strip()
    if not id_transaccion:
        return redirect("Suscripcion")

    crudo,error=pasarela.consultar_transaccion(id_transaccion)
    if error or not crudo:
        return render(request,"pago_estado.html",{
            "estado":"Pendiente",
            "titulo":"Estamos confirmando tu pago",
            "detalle":"No pudimos consultar el estado en este momento. Si el cobro se hizo, tu acceso se activa solo en unos minutos.",
        })

    datos=pasarela.leer_transaccion(crudo)
    pago=Pago.objects.filter(referencia=datos["referencia"]).first()
    if pago is None:
        return redirect("Suscripcion")

    #Solo el dueno del pago ve los datos personales. Un visitante con el id de
    #la transaccion ve el estado a secas, sin nombre, correo ni referencia.
    es_dueno=request.user.is_authenticated and pago.usuario_id==request.user.id

    if not pago.id_pasarela:
        pago.id_pasarela=datos["id"]
        pago.save(update_fields=["id_pasarela","actualizado"])

    #Si el webhook aun no llego, se aplica aca. Es la misma funcion, con la
    #misma proteccion de idempotencia: nunca otorga dias dos veces.
    if datos["estado"]=="Aprobado" and not pago.aplicado:
        servicios.aplicar_transaccion(datos,ambiente_evento=settings.WOMPI_AMBIENTE)
        pago.refresh_from_db()

    if pago.estado=="Aprobado" and pago.aplicado:
        #La sesion se pudo perder en el viaje de ida y vuelta a la pasarela
        #(dominio distinto, cookie SameSite, tunel reiniciado). El estado ya
        #se verifico arriba contra la API de Wompi (consultar_transaccion),
        #no contra lo que manda el navegador, asi que si no hay una sesion de
        #OTRO usuario activa en este navegador, se restaura la del dueno del
        #pago para que no tenga que volver a iniciar sesion.
        #AQUI HABIA UN AGUJERO DE SEGURIDAD, y conviene dejarlo escrito para
        #que no se reabra:
        #
        #Antes bastaba con llegar sin sesion y con el id de la transaccion en
        #la direccion para quedar dentro como el dueno del pago. Pero ese id
        #NO es un secreto: sale en el comprobante de Wompi, queda en el
        #historial del navegador y viaja en la barra de direcciones. Si el
        #administrador probaba una compra alguna vez, su id de transaccion se
        #convertia en una llave permanente de su cuenta: cualquiera que
        #abriera esa direccion entraba como administrador.
        #
        #Ahora se exige ademas la marca que se dejo en la sesion al iniciar el
        #pago. Solo el navegador que arranco la compra puede volver a entrar
        #solo. Si la sesion se perdio de verdad, se cae a la pantalla de
        #abajo, que es incomoda pero segura.
        if not es_dueno and not request.user.is_authenticated:
            if request.session.get("pago_en_curso")==pago.id:
                login(request,pago.usuario,backend="django.contrib.auth.backends.ModelBackend")
                es_dueno=True

        if es_dueno:
            request.session.pop("pago_en_curso",None)
            return redirect("PagoConfirmado",id=pago.id)

        #Aca solo se llega si en el navegador hay una sesion de OTRA cuenta
        #distinta al dueno del pago. Por seguridad no se cambia sola: se
        #confirma el cobro y se invita a entrar con la cuenta correcta.
        #Mensaje corto y sin hablar de cuentas. El usuario acaba de pagar:
        #lo unico que necesita saber es que su suscripcion quedo activa. La
        #barra de arriba ya tiene Inicio y Analizador, asi que no hacen falta
        #botones aqui abajo.
        return render(request,"pago_estado.html",{
            "estado":"Aprobado",
            "titulo":"¡Pago confirmado!",
            "detalle":"Tu suscripcion ya esta activa. Ya puedes entrar al analizador y usar el motor de prediccion.",
        })

    textos={
        "Pendiente":("Estamos confirmando tu pago",
                     "Los pagos por PSE y transferencia pueden tardar unos minutos. Te activamos el acceso apenas el banco confirme y te avisamos por correo."),
        "Rechazado":("El pago fue rechazado",
                     "Tu banco no autorizo la transaccion. Revisa el cupo o los datos e intentalo con otro medio de pago."),
        "Anulado":("El pago se anulo",
                   "La transaccion no se completo. Puedes intentarlo de nuevo cuando quieras."),
        "Error":("Algo fallo con el cobro",
                 "La pasarela reporto un error. No se hizo ningun cobro; intentalo de nuevo en unos minutos."),
    }
    titulo,detalle=textos.get(pago.estado,textos["Pendiente"])
    return render(request,"pago_estado.html",{
        "estado":pago.estado,
        "titulo":titulo,
        "detalle":detalle,
        "pago":pago if es_dueno else None,
    })


# ============================================================
#  WEBHOOK — unica fuente de verdad
# ============================================================
@csrf_exempt
@require_POST
def webhook_wompi(request):
    #csrf_exempt es correcto y necesario: quien llama es Wompi, no un
    #navegador con sesion. La autenticacion la da la firma del evento, que se
    #valida abajo contra el secreto de eventos.
    try:
        cuerpo=json.loads(request.body.decode("utf-8"))
    except Exception:
        return HttpResponseBadRequest("json invalido")

    valido,checksum=pasarela.verificar_evento(cuerpo,request.headers.get("X-Event-Checksum",""))
    datos_tx=((cuerpo.get("data") or {}).get("transaction") or {})
    normalizado=pasarela.leer_transaccion(datos_tx)

    if not checksum:
        return HttpResponseBadRequest("evento sin firma")

    #Se guarda el evento crudo ANTES de procesarlo, valido o no. Si manana hay
    #una disputa, la evidencia esta tal como llego.
    evento,creado=EventoPasarela.objects.get_or_create(
        checksum=checksum,
        defaults={
            "pasarela":pasarela.PROVEEDOR,
            "tipo":str(cuerpo.get("event") or "")[:40],
            "ambiente":str(cuerpo.get("environment") or "")[:10],
            "id_pasarela":normalizado["id"][:60],
            "referencia":normalizado["referencia"][:40],
            "estado_reportado":normalizado["estado_crudo"][:30],
            "monto_centavos":normalizado["centavos"],
            "firma_valida":valido,
            "cuerpo":cuerpo,
            "ip":servicios.obtener_ip(request),
        },
    )

    #Reintento de un evento que ya se proceso: se responde 200 para que Wompi
    #deje de reintentar, sin volver a tocar nada.
    if not creado and evento.procesado:
        return JsonResponse({"ok":True,"duplicado":True})

    if not valido:
        evento.detalle="Firma invalida"
        evento.save(update_fields=["detalle"])
        return HttpResponseBadRequest("firma invalida")

    if cuerpo.get("event")!="transaction.updated":
        evento.procesado=True
        evento.detalle="Tipo de evento no manejado"
        evento.save(update_fields=["procesado","detalle"])
        return JsonResponse({"ok":True})

    pago,resultado=servicios.aplicar_transaccion(normalizado,ambiente_evento=cuerpo.get("environment"))
    evento.procesado=True
    evento.detalle=resultado or ""
    evento.save(update_fields=["procesado","detalle"])
    return JsonResponse({"ok":True,"resultado":resultado})


# ============================================================
#  COMPROBANTES
# ============================================================
@login_required(login_url="Ingresar")
def pago_confirmado(request,id):
    pago=Pago.objects.filter(id=id,usuario=request.user).first()
    if pago is None:
        return redirect("Suscripcion")
    if pago.estado!="Aprobado":
        return redirect(reverse("RetornoPago")+f"?id={pago.id_pasarela}")

    suscripcion,creada=Suscripcion.objects.get_or_create(usuario=request.user)

    return render(request,"pago_confirmado.html",{
        "pago": pago,
        "suscripcion": suscripcion
    })


@login_required(login_url="Ingresar")
def descargar_factura(request,id):
    from pagos.factura import generar_factura_pdf

    perfil=getattr(request.user,"perfil",None)
    es_admin=request.user.is_superuser or (perfil is not None and perfil.rol is not None and perfil.rol.nombre=="administrador")

    if es_admin:
        pago=Pago.objects.filter(id=id).first()
    else:
        pago=Pago.objects.filter(id=id,usuario=request.user).first()

    if pago is None or pago.estado!="Aprobado":
        return redirect("Suscripcion")

    pdf=generar_factura_pdf(pago)
    respuesta=HttpResponse(pdf,content_type="application/pdf")
    nombre=pago.numero_factura or pago.referencia
    respuesta["Content-Disposition"]=f'attachment; filename="{nombre}.pdf"'
    return respuesta