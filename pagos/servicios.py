#Reglas de negocio del dinero. Todo lo que cambia el estado de un pago o de
#una suscripcion pasa por aqui, para que el webhook, la pantalla de retorno,
#el panel de administracion y el comando de conciliacion se comporten igual.
#
#Regla de oro: un pago solo puede otorgar dias UNA vez. Eso se garantiza con
#Pago.aplicado + select_for_update(), no con "revisar si ya existe".
import uuid
from datetime import timedelta
from django.db import transaction
from django.utils import timezone
from django.conf import settings

from pagos.models import Pago,Consecutivo,MovimientoSuscripcion,Reembolso
from pagos import pasarela
from suscripciones.models import Suscripcion
from suscripciones.planes import obtener_plan,desglosar_precio,nivel_de_plan

#Los intentos abandonados los cierra caducar_pendientes(); no se reutilizan.
#Wompi invalida una referencia en cuanto la ve, aunque el usuario no complete
#el pago, asi que cada intento necesita la suya.


def obtener_ip(request):
  adelante=request.META.get("HTTP_X_FORWARDED_FOR")
  if adelante:
    return adelante.split(",")[0].strip()[:45]
  return (request.META.get("REMOTE_ADDR") or "")[:45]


def nueva_referencia():
  #Referencia unica e impredecible. No se usa el id del usuario ni un
  #consecutivo: una referencia adivinable deja enumerar los pagos ajenos.
  return "XGOL"+uuid.uuid4().hex[:16].upper()


# ============================================================
#  CREACION DEL INTENTO DE PAGO
# ============================================================
def crear_pago_pendiente(usuario,clave_plan,ip=""):
  #Devuelve (pago,error). El precio SIEMPRE sale de suscripciones.planes,
  #nunca del formulario: si viniera del navegador, cualquiera podria pagar
  #$100 por el plan trimestral.
  plan=obtener_plan(clave_plan)
  if plan is None:
    return None,"plan"

  desglose=desglosar_precio(plan["precio"])
  pago=Pago.objects.create(
    usuario=usuario,
    plan=plan["nombre"],
    clave_plan=clave_plan,
    monto=plan["precio"],
    subtotal=desglose["subtotal"],
    iva=desglose["iva"],
    monto_centavos=plan["precio"]*100,
    moneda="COP",
    metodo="",
    estado="Pendiente",
    referencia=nueva_referencia(),
    pasarela=pasarela.PROVEEDOR,
    ambiente=settings.WOMPI_AMBIENTE,
    ip=ip,
    correo_pagador=usuario.email or "",
  )
  return pago,None


# ============================================================
#  APLICACION DE UNA TRANSACCION
# ============================================================
def aplicar_transaccion(datos,ambiente_evento=None,actor=None):
  #datos: diccionario ya normalizado por pasarela.leer_transaccion().
  #Devuelve (pago,resultado). resultado explica que paso, para la bitacora.
  referencia=datos.get("referencia") or ""
  if not referencia:
    return None,"sin_referencia"

  #Un evento de sandbox nunca puede activar una suscripcion de produccion.
  if ambiente_evento and ambiente_evento!=settings.WOMPI_AMBIENTE:
    return None,f"ambiente_no_coincide ({ambiente_evento})"

  enviar_correo=False
  with transaction.atomic():
    pago=Pago.objects.select_for_update().filter(referencia=referencia).first()
    if pago is None:
      return None,"referencia_desconocida"

    #Un pago que ya llego a un estado final no se reabre desde afuera.
    if pago.es_final() and pago.aplicado:
      return pago,"ya_aplicado"

    #Anti-manipulacion: el monto cobrado debe ser exactamente el que se
    #genero en el servidor. Si no coincide, no se otorga nada.
    if int(datos.get("centavos") or 0)!=int(pago.monto_centavos):
      pago.estado="Error"
      pago.mensaje=f"Monto no coincide: llego {datos.get('centavos')} y se esperaba {pago.monto_centavos}"
      pago.id_pasarela=datos.get("id") or pago.id_pasarela
      pago.save(update_fields=["estado","mensaje","id_pasarela","actualizado"])
      return pago,"monto_no_coincide"

    if (datos.get("moneda") or "COP")!=pago.moneda:
      pago.estado="Error"
      pago.mensaje=f"Moneda no coincide: {datos.get('moneda')}"
      pago.save(update_fields=["estado","mensaje","actualizado"])
      return pago,"moneda_no_coincide"

    pago.id_pasarela=datos.get("id") or pago.id_pasarela
    pago.metodo_detalle=datos.get("metodo") or pago.metodo_detalle
    pago.metodo=pago.metodo or _nombre_metodo(pago.metodo_detalle)
    pago.mensaje=datos.get("mensaje") or ""
    if datos.get("correo"):
      pago.correo_pagador=datos["correo"]
    pago.estado=datos.get("estado") or "Pendiente"

    if pago.estado!="Aprobado" or pago.aplicado:
      pago.save()
      return pago,"actualizado_sin_otorgar"

    #---- A partir de aca el pago esta aprobado y todavia no otorgo nada ----
    plan=obtener_plan(pago.clave_plan) or {}
    dias=int(plan.get("dias") or 0)
    if dias<=0:
      pago.estado="Error"
      pago.mensaje="Plan desconocido, no se pudo calcular la vigencia"
      pago.save()
      return pago,"plan_desconocido"

    suscripcion,creada=Suscripcion.objects.select_for_update().get_or_create(usuario=pago.usuario)
    vencimiento_anterior=suscripcion.vencimiento
    era_vigente=suscripcion.esta_vigente()

    #Los dias siempre se suman, pero el NOMBRE del plan se queda en el de
    #mayor nivel: comprar un mensual encima de un trimestral vigente no puede
    #degradar la etiqueta de la suscripcion.
    nombre=plan["nombre"]
    precio=plan["precio"]
    if era_vigente and nivel_de_plan(suscripcion.plan)>plan["nivel"]:
      nombre=suscripcion.plan
      precio=suscripcion.precio
    suscripcion.activar(nombre,precio,dias)

    if not pago.numero_factura:
      pago.numero_factura=Consecutivo.siguiente("factura",prefijo="FAC",ancho=5)
    pago.comision=pasarela.comision_estimada(pago.monto,pago.metodo_detalle)
    pago.neto=pago.monto-pago.comision
    pago.aplicado=True
    pago.dias_otorgados=dias
    pago.vigencia_inicio=suscripcion.inicio
    pago.vigencia_fin=suscripcion.vencimiento
    pago.aprobado_en=timezone.now()
    pago.save()

    MovimientoSuscripcion.objects.create(
      usuario=pago.usuario,
      tipo="Renovacion" if era_vigente else "Activacion",
      plan=plan["nombre"],
      dias=dias,
      vencimiento_anterior=vencimiento_anterior,
      vencimiento_nuevo=suscripcion.vencimiento,
      pago=pago,
      actor=actor,
      nota=f"{pago.pasarela} {pago.metodo_detalle}".strip(),
    )
    enviar_correo=True

  if enviar_correo:
    #Fuera de la transaccion: si el SMTP se cae, el pago ya quedo guardado.
    transaction.on_commit(lambda: _enviar_factura(pago.id))
  return pago,"aplicado"


def _nombre_metodo(detalle):
  nombres={
    "CARD":"Tarjeta","PSE":"PSE","NEQUI":"Nequi",
    "BANCOLOMBIA_TRANSFER":"Bancolombia","BANCOLOMBIA_COLLECT":"Corresponsal",
    "DAVIPLATA":"Daviplata","BANCOLOMBIA_QR":"QR Bancolombia",
  }
  return nombres.get((detalle or "").upper(),detalle or "Otro")


def _enviar_factura(id_pago):
  try:
    from pagos.correo import enviar_factura_correo
    pago=Pago.objects.filter(id=id_pago).first()
    if pago is not None:
      enviar_factura_correo(pago)
  except Exception:
    pass


# ============================================================
#  CONCILIACION — red de seguridad cuando el webhook no llega
# ============================================================
def conciliar_pendientes(minutos=10,tope=50):
  #Le pregunta a la pasarela por los pagos que siguen pendientes. PSE es
  #asincrono y un webhook puede perderse: sin esto, un usuario que pago de
  #verdad se queda sin acceso.
  limite=timezone.now()-timedelta(minutes=minutos)
  pendientes=Pago.objects.filter(estado="Pendiente",creado__lte=limite).exclude(id_pasarela="")[:tope]
  revisados=0
  aplicados=0
  for pago in pendientes:
    crudo,error=pasarela.consultar_transaccion(pago.id_pasarela)
    revisados=revisados+1
    if error or not crudo:
      continue
    datos=pasarela.leer_transaccion(crudo)
    resultado_pago,resultado=aplicar_transaccion(datos,ambiente_evento=settings.WOMPI_AMBIENTE)
    if resultado=="aplicado":
      aplicados=aplicados+1
  return revisados,aplicados


def caducar_pendientes(horas=24):
  #Un intento de pago que nunca llego a la pasarela no puede quedarse
  #"Pendiente" para siempre ensuciando el reporte de pendientes.
  limite=timezone.now()-timedelta(hours=horas)
  return Pago.objects.filter(estado="Pendiente",id_pasarela="",creado__lte=limite).update(
    estado="Anulado",mensaje="Caducado sin llegar a la pasarela")


def marcar_vencidas():
  #Apaga la bandera activa de las suscripciones cuya fecha ya paso y deja
  #constancia del vencimiento.
  hoy=timezone.now().date()
  vencidas=Suscripcion.objects.filter(activa=True,vencimiento__lt=hoy)
  total=0
  for suscripcion in vencidas:
    suscripcion.activa=False
    suscripcion.save(update_fields=["activa"])
    MovimientoSuscripcion.objects.create(
      usuario=suscripcion.usuario,
      tipo="Vencimiento",
      plan=suscripcion.plan,
      vencimiento_anterior=suscripcion.vencimiento,
      vencimiento_nuevo=suscripcion.vencimiento,
      nota="Vencimiento automatico",
    )
    total=total+1
  return total


# ============================================================
#  REEMBOLSOS
# ============================================================
def registrar_reembolso(pago,monto,motivo,actor=None,revoca_dias=True):
  #El reembolso del dinero se ejecuta desde el panel de Wompi. Aca se deja el
  #registro contable y, si se pide, se le quitan a la suscripcion los dias que
  #ese pago habia otorgado.
  with transaction.atomic():
    pago=Pago.objects.select_for_update().get(pk=pago.pk)
    reembolso=Reembolso.objects.create(
      pago=pago,monto=monto,motivo=motivo[:200],
      estado="Aprobado",revoca_dias=revoca_dias,creado_por=actor,
    )
    pago.estado="Reembolsado"
    pago.save(update_fields=["estado","actualizado"])

    if revoca_dias and pago.dias_otorgados>0:
      suscripcion=Suscripcion.objects.select_for_update().filter(usuario=pago.usuario).first()
      if suscripcion is not None and suscripcion.vencimiento is not None:
        anterior=suscripcion.vencimiento
        suscripcion.vencimiento=anterior-timedelta(days=pago.dias_otorgados)
        if suscripcion.vencimiento<timezone.now().date():
          suscripcion.activa=False
        suscripcion.save(update_fields=["vencimiento","activa"])
        MovimientoSuscripcion.objects.create(
          usuario=pago.usuario,tipo="Reembolso",plan=pago.plan,
          dias=-pago.dias_otorgados,vencimiento_anterior=anterior,
          vencimiento_nuevo=suscripcion.vencimiento,pago=pago,actor=actor,
          nota=motivo[:200],
        )
  return reembolso