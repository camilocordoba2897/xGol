#Capa de pasarela de pagos.
#
#Hoy: Wompi (grupo Bancolombia). Toda la conversacion con el proveedor pasa
#por aqui; el resto del proyecto solo llama a las funciones de la seccion
#"API PUBLICA" de abajo.
#
#CAMBIO DE PROVEEDOR (Mercado Pago, ePayco, PayU...):
#  1. Escribir otro modulo con las mismas cinco funciones publicas y la misma
#     firma: url_checkout, consultar_transaccion, verificar_evento,
#     leer_transaccion, comision_estimada.
#  2. Cambiar PASARELA en .env.
#Ni las vistas, ni los modelos, ni los templates se tocan.
#
#Nunca se reciben datos de tarjeta en este servidor: el usuario los escribe
#dentro del checkout de Wompi. Eso saca al proyecto del alcance duro de
#PCI-DSS y elimina la responsabilidad de custodiar tarjetas.
import hashlib
import hmac
import re
import urllib.parse
import requests
from django.conf import settings

PROVEEDOR="wompi"

#Wompi usa el mismo checkout para los dos ambientes: la llave publica decide
#si la transaccion es de prueba (pub_test_) o real (pub_prod_).
URL_CHECKOUT="https://checkout.wompi.co/p/"
API_SANDBOX="https://sandbox.wompi.co/v1"
API_PRODUCCION="https://production.wompi.co/v1"

#Errores que el frontend necesita distinguir para dar un mensaje util,
#con el mismo criterio que analizador/api_datos.py
ERROR_RED="red"
ERROR_CONFIG="config"
ERROR_AUTH="auth"
ERROR_NO_ENCONTRADA="no_encontrada"

#Estados que devuelve Wompi -> estados internos del modelo Pago
MAPA_ESTADOS={
  "APPROVED":"Aprobado",
  "DECLINED":"Rechazado",
  "VOIDED":"Anulado",
  "ERROR":"Error",
  "PENDING":"Pendiente",
}


def _api():
  return API_PRODUCCION if settings.WOMPI_AMBIENTE=="prod" else API_SANDBOX


def configurada():
  #True solo si estan las cuatro llaves. Si falta alguna, el checkout se
  #bloquea en vez de mandar al usuario a una pantalla rota.
  return bool(settings.WOMPI_LLAVE_PUBLICA and settings.WOMPI_SECRETO_INTEGRIDAD
              and settings.WOMPI_SECRETO_EVENTOS and settings.WOMPI_LLAVE_PRIVADA)


def firma_integridad(referencia,centavos,moneda="COP",expiracion=None):
  #SHA256 de <referencia><monto_en_centavos><moneda>[<expiracion>]<secreto>.
  #Se calcula SIEMPRE en el servidor: si se calculara en el navegador habria
  #que exponer el secreto de integridad.
  cadena=f"{referencia}{centavos}{moneda}"
  if expiracion:
    cadena=cadena+expiracion
  cadena=cadena+settings.WOMPI_SECRETO_INTEGRIDAD
  return hashlib.sha256(cadena.encode("utf-8")).hexdigest()


def url_checkout(pago,url_retorno,expiracion=None):
  #Arma la URL del Web Checkout de Wompi para un Pago ya guardado.
  #Se usa redireccion (no widget) para que ni una linea de JavaScript nuestra
  #toque el flujo del dinero.
  parametros={
    "public-key":settings.WOMPI_LLAVE_PUBLICA,
    "currency":pago.moneda,
    "amount-in-cents":str(pago.monto_centavos),
    "reference":pago.referencia,
    "signature:integrity":firma_integridad(pago.referencia,pago.monto_centavos,pago.moneda,expiracion),
    "redirect-url":url_retorno,
  }
  if expiracion:
    parametros["expiration-time"]=expiracion
  #El IVA que se manda NO se suma al total: solo viaja como informacion
  #tributaria hacia el procesador.
  if pago.iva>0:
    parametros["tax-in-cents:vat"]=str(pago.iva*100)
  if pago.usuario.email:
    parametros["customer-data:email"]=pago.usuario.email
  nombre=f"{pago.usuario.first_name} {pago.usuario.last_name}".strip()
  if nombre:
    parametros["customer-data:full-name"]=nombre
  telefono=_telefono_colombiano(getattr(pago.usuario,"perfil",None))
  if telefono:
    parametros["customer-data:phone-number"]=telefono
    parametros["customer-data:phone-number-prefix"]="+57"
  return URL_CHECKOUT+"?"+urllib.parse.urlencode(parametros)


def _telefono_colombiano(perfil):
  #Wompi espera solo digitos. El perfil puede traer "+57 300 123 4567" o
  #"(604) 444-5566"; se limpia y se descarta si no queda un celular de 10.
  if perfil is None or not perfil.telefono:
    return ""
  digitos=re.sub(r"\D","",str(perfil.telefono))
  if digitos.startswith("57") and len(digitos)==12:
    digitos=digitos[2:]
  return digitos if len(digitos)==10 else ""


def consultar_transaccion(id_transaccion):
  #Devuelve (datos,error). Se usa para la pantalla de retorno y para el
  #comando de conciliacion. NUNCA se usa la redireccion como unica fuente de
  #verdad: la fuente de verdad es el webhook, esto es la red de seguridad.
  if not settings.WOMPI_LLAVE_PUBLICA:
    return None,ERROR_CONFIG
  try:
    r=requests.get(
      f"{_api()}/transactions/{id_transaccion}",
      headers={"Authorization":f"Bearer {settings.WOMPI_LLAVE_PUBLICA}"},
      timeout=12,
    )
    if r.status_code==404:
      return None,ERROR_NO_ENCONTRADA
    if r.status_code in (401,403):
      #Llave equivocada o de otro ambiente. Se separa de ERROR_RED porque el
      #arreglo es distinto: uno se resuelve en .env, el otro esperando.
      return None,ERROR_AUTH
    if r.status_code!=200:
      return None,ERROR_RED
    return (r.json() or {}).get("data") or {},None
  except Exception:
    return None,ERROR_RED


def verificar_evento(cuerpo,checksum_cabecera=""):
  #Valida la firma del webhook segun el procedimiento de Wompi:
  #concatena los valores apuntados por signature.properties, luego timestamp,
  #luego el secreto de eventos, y compara el SHA256 contra el checksum.
  #Devuelve (valido, checksum_recibido).
  firma=(cuerpo.get("signature") or {})
  propiedades=firma.get("properties") or []
  recibido=(firma.get("checksum") or checksum_cabecera or "").strip()
  if not propiedades or not recibido or not settings.WOMPI_SECRETO_EVENTOS:
    return False,recibido

  datos=cuerpo.get("data") or {}
  partes=[]
  for ruta in propiedades:
    valor=datos
    for llave in str(ruta).split("."):
      if not isinstance(valor,dict):
        valor=None
        break
      valor=valor.get(llave)
    if valor is None:
      return False,recibido
    partes.append(str(valor))

  cadena="".join(partes)+str(cuerpo.get("timestamp",""))+settings.WOMPI_SECRETO_EVENTOS
  calculado=hashlib.sha256(cadena.encode("utf-8")).hexdigest()
  #Comparacion en tiempo constante: un == normal se corta en el primer byte
  #distinto y deja adivinar el checksum midiendo tiempos.
  return hmac.compare_digest(calculado.lower(),recibido.lower()),recibido


def leer_transaccion(transaccion):
  #Normaliza el objeto de Wompi al vocabulario del proyecto. Lo consumen por
  #igual el webhook y la conciliacion, asi que el resto del codigo nunca ve
  #nombres en ingles del proveedor.
  transaccion=transaccion or {}
  crudo=str(transaccion.get("status") or "").upper()
  return {
    "id":transaccion.get("id") or "",
    "referencia":transaccion.get("reference") or "",
    "estado":MAPA_ESTADOS.get(crudo,"Error"),
    "estado_crudo":crudo,
    "centavos":int(transaccion.get("amount_in_cents") or 0),
    "moneda":transaccion.get("currency") or "",
    "metodo":str(transaccion.get("payment_method_type") or "")[:40],
    "correo":str(transaccion.get("customer_email") or "")[:200],
    "mensaje":str(transaccion.get("status_message") or "")[:200],
  }


def comision_estimada(monto,metodo_detalle=""):
  #Estimacion del costo de la pasarela para proyectar el neto en los reportes.
  #Las tarifas viven en settings.TARIFAS_PASARELA porque cambian sin avisar y
  #se negocian por volumen. La cifra REAL es la que liquida Wompi: esto es una
  #proyeccion, nunca un dato contable.
  tarifas=getattr(settings,"TARIFAS_PASARELA",{})
  clave=(metodo_detalle or "").upper()
  tarifa=tarifas.get(clave) or tarifas.get("DEFECTO") or {}
  porcentaje=float(tarifa.get("porcentaje",0))
  fijo=int(tarifa.get("fijo",0))
  iva=float(tarifa.get("iva",0.19))
  base=monto*porcentaje/100.0+fijo
  return int(round(base*(1+iva)))