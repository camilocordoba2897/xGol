#Prueba del webhook de pagos. Archivo temporal: se puede borrar al terminar.
#
#Se ejecuta como script suelto y no dentro de "manage.py shell" porque la
#consola interactiva rompe los bloques de varias lineas al pegarlos.
#
#Uso:  python prueba_webhook.py
import os
import json
import hashlib

os.environ.setdefault("DJANGO_SETTINGS_MODULE","xgol.settings")

import django
django.setup()

from django.conf import settings
from django.test import Client
from django.contrib.auth.models import User

#El cliente de pruebas manda Host: testserver, que no esta en ALLOWED_HOSTS.
#Solo afecta a este proceso; el archivo settings.py no se toca.
settings.ALLOWED_HOSTS=["*"]

from pagos.models import Pago,EventoPasarela
from pagos import servicios
from suscripciones.models import Suscripcion

SECRETO=settings.WOMPI_SECRETO_EVENTOS
URL="/pago/eventos/wompi/x7k2"
cliente=Client()

resultados=[]


def revisar(titulo,obtenido,esperado):
  bien=obtenido==esperado
  resultados.append(bien)
  marca="OK   " if bien else "FALLA"
  print(f"  [{marca}] {titulo}")
  print(f"          obtenido: {obtenido}")
  if not bien:
    print(f"          esperado: {esperado}")


def evento(pago,estado="APPROVED",centavos=None,ambiente="test",id_tx="1-555-5",ts=1750000000,secreto=None):
  transaccion={
    "id":id_tx,
    "reference":pago.referencia,
    "status":estado,
    "amount_in_cents":centavos if centavos is not None else pago.monto_centavos,
    "currency":"COP",
    "payment_method_type":"CARD",
    "customer_email":"prueba@xgol.com",
    "status_message":"Aprobada",
  }
  cadena=f"{transaccion['id']}{transaccion['status']}{transaccion['amount_in_cents']}{ts}{secreto or SECRETO}"
  return {
    "event":"transaction.updated",
    "data":{"transaction":transaccion},
    "environment":ambiente,
    "signature":{
      "properties":["transaction.id","transaction.status","transaction.amount_in_cents"],
      "checksum":hashlib.sha256(cadena.encode()).hexdigest().upper(),
    },
    "timestamp":ts,
  }


def enviar(cuerpo):
  return cliente.post(URL,data=json.dumps(cuerpo),content_type="application/json")


def limpiar(usuario):
  Pago.objects.filter(usuario=usuario).delete()
  Suscripcion.objects.filter(usuario=usuario).delete()
  EventoPasarela.objects.filter(referencia__startswith="XGOL").delete()
  usuario.delete()


print("="*62)
print(" PRUEBA DEL WEBHOOK DE PAGOS")
print("="*62)

if not SECRETO:
  print("  WOMPI_SECRETO_EVENTOS esta vacio. Revisa el .env antes de seguir.")
  raise SystemExit(1)

usuario,creado=User.objects.get_or_create(username="pruebapagos",defaults={"email":"prueba@xgol.com"})
limpiar(usuario)
usuario=User.objects.create_user("pruebapagos",email="prueba@xgol.com",password="x")

try:
  print("\n1. Webhook con firma valida")
  p1,_=servicios.crear_pago_pendiente(usuario,"mensual","1.1.1.1")
  r=enviar(evento(p1))
  p1.refresh_from_db()
  s=Suscripcion.objects.get(usuario=usuario)
  revisar("otorga los dias y aprueba el pago",
          (r.status_code,r.json().get("resultado"),p1.estado,s.dias_restantes()),
          (200,"aplicado","Aprobado",30))

  print("\n2. Reintento identico de Wompi")
  antes=s.vencimiento
  r=enviar(evento(p1))
  s.refresh_from_db()
  revisar("no vuelve a sumar dias",
          (r.status_code,r.json().get("duplicado"),s.vencimiento==antes,EventoPasarela.objects.count()),
          (200,True,True,1))

  print("\n3. Firma falsificada")
  p2,_=servicios.crear_pago_pendiente(usuario,"trimestral","1.1.1.1")
  r=enviar(evento(p2,secreto="soy_un_atacante",id_tx="1-666-6"))
  p2.refresh_from_db()
  ultimo=EventoPasarela.objects.order_by("-id").first()
  revisar("rechaza y deja constancia",
          (r.status_code,p2.estado,ultimo.firma_valida,ultimo.detalle),
          (400,"Pendiente",False,"Firma invalida"))

  print("\n4. Monto manipulado con firma valida")
  r=enviar(evento(p2,centavos=100,id_tx="1-777-7"))
  p2.refresh_from_db()
  revisar("marca error y no otorga nada",
          (r.status_code,r.json().get("resultado"),p2.estado),
          (200,"monto_no_coincide","Error"))

  print("\n5. Evento de produccion contra ambiente de pruebas")
  p3,_=servicios.crear_pago_pendiente(usuario,"mensual","1.1.1.1")
  r=enviar(evento(p3,ambiente="prod",id_tx="1-888-8"))
  p3.refresh_from_db()
  revisar("lo descarta",
          (r.status_code,r.json().get("resultado"),p3.estado),
          (200,"ambiente_no_coincide (prod)","Pendiente"))

  print("\n6. Cuerpo que no es JSON")
  revisar("responde 400",
          cliente.post(URL,data="{roto",content_type="application/json").status_code,
          400)

  print("\n7. GET al webhook")
  revisar("responde 405",cliente.get(URL).status_code,405)

  print("\n8. Evento de un tipo que no manejamos")
  p4,_=servicios.crear_pago_pendiente(usuario,"mensual","1.1.1.1")
  cuerpo=evento(p4,id_tx="1-999-9")
  cuerpo["event"]="nequi_token.updated"
  r=enviar(cuerpo)
  p4.refresh_from_db()
  revisar("lo ignora sin tocar el pago",(r.status_code,p4.estado),(200,"Pendiente"))

  print("\n"+"-"*62)
  print(" EVENTOS GUARDADOS EN LA BITACORA")
  print("-"*62)
  for e in EventoPasarela.objects.order_by("id"):
    print(f"  #{e.id} {e.tipo:22} {e.estado_reportado:9} firma={str(e.firma_valida):5} procesado={str(e.procesado):5} {e.detalle}")

finally:
  limpiar(usuario)
  print("\n  (datos de prueba borrados)")

print("\n"+"="*62)
if all(resultados):
  print(f" TODO BIEN: {len(resultados)}/{len(resultados)} pruebas pasaron")
else:
  print(f" HAY FALLAS: {sum(resultados)}/{len(resultados)} pruebas pasaron")
print("="*62)