#Consultas del panel financiero. Todo lo que se muestra sale de la base de
#datos con agregaciones, no de contar filas en Python: con miles de pagos la
#diferencia entre las dos cosas es el panel abriendo en 80 ms o en 40 s.
#
#Solo se suma lo que esta en estado "Aprobado". Un pago pendiente NO es una
#venta, y un reembolsado dejo de serlo.
from datetime import timedelta,date,datetime,time
from django.db.models import Sum,Count,Q
from django.utils import timezone
from django.contrib.auth.models import User

from pagos.models import Pago,Reembolso,MovimientoSuscripcion,EventoPasarela
from suscripciones.models import Suscripcion

MESES=["ene","feb","mar","abr","may","jun","jul","ago","sep","oct","nov","dic"]


def _sumar(consulta):
  datos=consulta.aggregate(total=Sum("monto"),neto=Sum("neto"),comision=Sum("comision"),cuenta=Count("id"))
  return {
    "total":datos["total"] or 0,
    "neto":datos["neto"] or 0,
    "comision":datos["comision"] or 0,
    "cuenta":datos["cuenta"] or 0,
  }


# ============================================================
#  FECHAS SIN CONVERT_TZ
#  El proyecto guarda en UTC (USE_TZ=True) y muestra en America/Bogota.
#  Con esa combinacion, el atajo "creado__date" hace que Django le pida a
#  MySQL un CONVERT_TZ(...). MySQL solo sabe hacer esa conversion si tiene
#  cargadas sus tablas de zonas horarias, que NO vienen cargadas por
#  defecto; cuando faltan devuelve NULL y entonces NINGUNA fila coincide:
#  el panel mostraba $0 en hoy, semana, mes, trimestre y ano mientras el
#  historico (que no filtra por fecha) si traia las 22 ventas.
#
#  Por eso aca no se usa "creado__date". Se calcula en Python el instante
#  exacto en que empieza y termina cada periodo y se compara contra el
#  campo tal cual. Asi funciona con o sin esas tablas cargadas, y ademas
#  puede aprovechar el indice de la columna.
#  Es el mismo criterio que ya usaba usuarios/tablero.py en _inicio_dia.
# ============================================================
def _inicio_dia(fecha):
  #Instante 00:00:00 de esa fecha, en la zona horaria del proyecto.
  momento=datetime.combine(fecha,time.min)
  if timezone.is_naive(momento):
    try:
      momento=timezone.make_aware(momento)
    except Exception:
      pass
  return momento


def _fin_dia(fecha):
  #Primer instante del dia SIGUIENTE. Se usa con "menor que" para incluir
  #el dia completo sin depender de milisegundos ni de 23:59:59.
  return _inicio_dia(fecha+timedelta(days=1))


def _fecha_local(momento):
  #Pasa un datetime guardado a la fecha que ve el usuario en Colombia.
  if momento is None:
    return None
  return timezone.localtime(momento).date() if timezone.is_aware(momento) else momento.date()


def inicio_trimestre(hoy):
  mes=3*((hoy.month-1)//3)+1
  return date(hoy.year,mes,1)


def resumen_ingresos():
  #Los seis cortes de tiempo que pide el panel, calculados sobre la fecha
  #local del servidor (America/Bogota).
  hoy=timezone.localdate()
  aprobados=Pago.objects.filter(estado="Aprobado")

  #Cada corte va desde el inicio de su periodo hasta el fin del dia de hoy.
  fin=_fin_dia(hoy)
  cortes={
    "historico":aprobados,
    "hoy":aprobados.filter(creado__gte=_inicio_dia(hoy),creado__lt=fin),
    "semana":aprobados.filter(creado__gte=_inicio_dia(hoy-timedelta(days=hoy.weekday())),creado__lt=fin),
    "mes":aprobados.filter(creado__gte=_inicio_dia(hoy.replace(day=1)),creado__lt=fin),
    "trimestre":aprobados.filter(creado__gte=_inicio_dia(inicio_trimestre(hoy)),creado__lt=fin),
    "anio":aprobados.filter(creado__gte=_inicio_dia(date(hoy.year,1,1)),creado__lt=fin),
  }
  return {llave:_sumar(consulta) for llave,consulta in cortes.items()}


def resumen_suscripciones():
  hoy=timezone.localdate()
  todas=Suscripcion.objects.all()
  vigentes=todas.filter(activa=True,vencimiento__gte=hoy)
  return {
    "activas":vigentes.count(),
    "vencidas":todas.filter(vencimiento__lt=hoy).count(),
    "por_vencer":vigentes.filter(vencimiento__lte=hoy+timedelta(days=5)).count(),
    "renovacion_automatica":vigentes.filter(renovacion_automatica=True).count(),
    "sin_suscripcion":User.objects.filter(suscripcion__isnull=True).count(),
    "canceladas":todas.filter(cancelada_en__isnull=False).count(),
  }


def resumen_incidencias():
  #Lo que hay que vigilar: dinero que no entro, dinero que salio y firmas que
  #no cuadraron.
  hace_30=timezone.now()-timedelta(days=30)
  reembolsos=Reembolso.objects.filter(estado="Aprobado")
  return {
    "pendientes":Pago.objects.filter(estado="Pendiente").count(),
    "rechazados_30":Pago.objects.filter(estado="Rechazado",creado__gte=hace_30).count(),
    "errores_30":Pago.objects.filter(estado="Error",creado__gte=hace_30).count(),
    "reembolsos":reembolsos.count(),
    "reembolsado_total":reembolsos.aggregate(t=Sum("monto"))["t"] or 0,
    "eventos_invalidos":EventoPasarela.objects.filter(firma_valida=False).count(),
    "eventos_sin_procesar":EventoPasarela.objects.filter(procesado=False,firma_valida=True).count(),
  }


def serie_mensual(meses=12):
  #Serie para la grafica. Devuelve siempre los N meses completos, incluidos
  #los que no tuvieron ventas, para que las barras no mientan por omision.
  #Se agrupa en Python y no con TruncMonth porque esa funcion tambien le
  #pide un CONVERT_TZ a MySQL (ver la nota de arriba) y dejaba la grafica
  #plana. Es el mismo criterio de usuarios/tablero.py:serie_ingresos.
  hoy=timezone.localdate()
  primero=hoy.replace(day=1)
  for _ in range(meses-1):
    primero=(primero-timedelta(days=1)).replace(day=1)

  crudo=(Pago.objects.filter(estado="Aprobado",creado__gte=_inicio_dia(primero))
         .values_list("creado","monto"))
  mapa={}
  for creado,monto in crudo:
    fecha=_fecha_local(creado)
    llave=(fecha.year,fecha.month)
    total,cuenta=mapa.get(llave,(0,0))
    mapa[llave]=(total+(monto or 0),cuenta+1)

  serie=[]
  cursor=primero
  for _ in range(meses):
    total,cuenta=mapa.get((cursor.year,cursor.month),(0,0))
    serie.append({
      "etiqueta":f"{MESES[cursor.month-1]} {str(cursor.year)[2:]}",
      "total":total,
      "cuenta":cuenta,
    })
    cursor=(cursor.replace(day=28)+timedelta(days=4)).replace(day=1)
  return serie


def serie_diaria(dias=30):
  #Igual que arriba: se agrupa por dia en Python, no con TruncDay.
  hoy=timezone.localdate()
  desde=hoy-timedelta(days=dias-1)
  crudo=(Pago.objects.filter(estado="Aprobado",creado__gte=_inicio_dia(desde))
         .values_list("creado","monto"))
  mapa={}
  for creado,monto in crudo:
    fecha=_fecha_local(creado)
    mapa[fecha]=mapa.get(fecha,0)+(monto or 0)
  return [{"fecha":desde+timedelta(days=i),
           "total":mapa.get(desde+timedelta(days=i),0)} for i in range(dias)]


def ventas_por_plan():
  return list(Pago.objects.filter(estado="Aprobado").values("plan")
              .annotate(total=Sum("monto"),cuenta=Count("id")).order_by("-total"))


def ventas_por_metodo():
  return list(Pago.objects.filter(estado="Aprobado").values("metodo")
              .annotate(total=Sum("monto"),cuenta=Count("id")).order_by("-total"))


def barras(serie,alto=120,ancho=560,separacion=8):
  #Prepara la geometria de la grafica en el servidor: alturas, posiciones y
  #anchos ya calculados. Asi la plantilla solo pinta un <svg> y el proyecto no
  #gana ninguna libreria de graficos.
  total_barras=len(serie) or 1
  paso=ancho/total_barras
  grosor=max(6,paso-separacion)
  maximo=max([fila["total"] for fila in serie] or [0]) or 1
  salida=[]
  for i,fila in enumerate(serie):
    altura=max(2,int(round(fila["total"]/maximo*alto)))
    salida.append({
      "etiqueta":fila["etiqueta"],
      "total":fila["total"],
      "cuenta":fila.get("cuenta",0),
      "alto":altura,
      "y":alto-altura,
      "x":round(i*paso+(paso-grosor)/2,1),
      "centro":round(i*paso+paso/2,1),
      "ancho":round(grosor,1),
    })
  return salida


def transacciones(filtros=None):
  #Historial filtrable. Devuelve un queryset, no una lista: quien lo llame
  #decide si pagina, exporta o cuenta.
  filtros=filtros or {}
  consulta=Pago.objects.select_related("usuario").all()

  estado=filtros.get("estado")
  if estado and estado!="todos":
    consulta=consulta.filter(estado=estado)

  plan=filtros.get("plan")
  if plan and plan!="todos":
    consulta=consulta.filter(plan=plan)

  metodo=filtros.get("metodo")
  if metodo and metodo!="todos":
    consulta=consulta.filter(metodo=metodo)

  desde=filtros.get("desde")
  if desde:
    consulta=consulta.filter(creado__gte=_inicio_dia(desde))

  hasta=filtros.get("hasta")
  if hasta:
    #_fin_dia es el arranque del dia siguiente, asi que con "menor que"
    #queda incluido el dia de "hasta" completo.
    consulta=consulta.filter(creado__lt=_fin_dia(hasta))

  busqueda=(filtros.get("q") or "").strip()
  if busqueda:
    consulta=consulta.filter(
      Q(referencia__icontains=busqueda)|
      Q(numero_factura__icontains=busqueda)|
      Q(id_pasarela__icontains=busqueda)|
      Q(usuario__username__icontains=busqueda)|
      Q(usuario__email__icontains=busqueda)
    )
  return consulta.order_by("-creado")


def usuarios_pendientes(limite=20):
  #Gente que abrio el checkout y no completo. Es la lista de recuperacion de
  #ventas, no una lista de morosos.
  return list(Pago.objects.filter(estado="Pendiente").select_related("usuario").order_by("-creado")[:limite])


def proximas_renovaciones(dias=7):
  hoy=timezone.localdate()
  return list(Suscripcion.objects.filter(
    activa=True,vencimiento__gte=hoy,vencimiento__lte=hoy+timedelta(days=dias)
  ).select_related("usuario").order_by("vencimiento"))


def movimientos(limite=30):
  return list(MovimientoSuscripcion.objects.select_related("usuario","pago").all()[:limite])