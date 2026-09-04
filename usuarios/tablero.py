#Calculos del tablero del panel de administracion.
#Misma idea que pagos/reportes.py: todo sale de la base de datos con
#agregaciones y la geometria de las graficas se arma aca, para que la
#plantilla solo pinte un <svg> y el proyecto no gane ninguna libreria.
from datetime import timedelta
from django.db.models import Sum,Count
from django.utils import timezone
from django.contrib.auth.models import User

from suscripciones.models import Suscripcion
from pagos.models import Pago
from analizador.models import RegistroApuesta

MESES=["ene","feb","mar","abr","may","jun","jul","ago","sep","oct","nov","dic"]


# ============================================================
#  QUIEN CUENTA COMO CLIENTE
# ============================================================
#  El administrador no es un cliente: no paga, no compra plan y no se
#  gestiona a si mismo. Si se cuenta junto a los demas, ensucia el total
#  de cuentas, el porcentaje de conversion y la grafica de registros, y
#  ademas aparecia en la lista con botones de Bloquear y Eliminar que no
#  tenian sentido.
#
#  En este proyecto alguien es administrador de dos formas (las mismas
#  que revisa usuarios/decoradores.py):
#     - is_superuser = True
#     - su perfil tiene el rol llamado "administrador"
#  Se contemplan las dos para que no se cuele ninguno.
ROL_ADMIN = "administrador"


def es_administrador(usuario):
    #True si esa cuenta es de administracion y no de un cliente.
    if usuario is None:
        return False
    if getattr(usuario, "is_superuser", False) or getattr(usuario, "is_staff", False):
        return True
    perfil = getattr(usuario, "perfil", None)
    rol = getattr(perfil, "rol", None) if perfil is not None else None
    return rol is not None and (rol.nombre or "").strip().lower() == ROL_ADMIN


def usuarios_clientes():
    #Todas las cuentas MENOS las de administracion. Es el conjunto que se
    #cuenta y se lista en el panel.
    return (User.objects
            .exclude(is_superuser=True)
            .exclude(is_staff=True)
            .exclude(perfil__rol__nombre__iexact=ROL_ADMIN))


def perfiles_clientes():
    #Lo mismo pero desde Perfil, que es lo que pinta la tabla del panel.
    from usuarios.models import Perfil
    return (Perfil.objects
            .exclude(usuario__is_superuser=True)
            .exclude(usuario__is_staff=True)
            .exclude(rol__nombre__iexact=ROL_ADMIN))

#Cortes de probabilidad para medir la calibracion del modelo
RANGOS=[(0.30,0.50),(0.50,0.60),(0.60,0.70),(0.70,0.80),(0.80,0.90),(0.90,1.01)]

#Minimo de apuestas para que un rango o un mercado se pueda juzgar. Con menos
#que esto el porcentaje es ruido, no informacion.
MINIMO_FIABLE=10

#Referencias publicadas de acierto en prediccion de futbol. Sirven para saber
#si nuestro porcentaje es bueno o malo, en vez de inventar una meta.
#  1X2: mejor resultado documentado en la literatura comparable
#       (CatBoost + pi-ratings, 55.82%; Random Forest, 55.9%).
#  Over/Under 2.5: el mismo estudio reporta 62.7%, mas alto porque son dos
#       resultados posibles en vez de tres.
#  Suelo: apostar siempre al local acierta ~41% de las veces. Cualquier
#       modelo por debajo de eso no aporta nada.
#  Techo honesto: por encima de 70% sostenido no hay modelo publico creible.
REFERENCIAS={
  "suelo":41.0,
  "tope_1x2":55.9,
  "tope_ou":62.7,
  "sospechoso":70.0,
}


def veredicto_global(tasa):
  #Compara nuestro acierto con las referencias publicadas.
  if tasa<=0:
    return {"texto":"Sin datos","nivel":"vacio"}
  if tasa<REFERENCIAS["suelo"]:
    return {"texto":"Bajo el suelo","nivel":"malo"}
  if tasa<REFERENCIAS["tope_1x2"]:
    return {"texto":"En rango normal","nivel":"normal"}
  if tasa<REFERENCIAS["sospechoso"]:
    return {"texto":"Sobre la referencia","nivel":"bueno"}
  return {"texto":"Revisar la muestra","nivel":"alerta"}


def _variacion(actual,anterior):
  #Cambio porcentual contra el periodo anterior. Sin base no hay comparacion
  #posible: se devuelve None y la plantilla no pinta la flecha.
  if not anterior:
    return None
  return round((actual-anterior)/anterior*100,1)


def _primer_dia(hoy,meses_atras=0):
  cursor=hoy.replace(day=1)
  for _ in range(meses_atras):
    cursor=(cursor-timedelta(days=1)).replace(day=1)
  return cursor


def _inicio_dia(fecha):
  #Convierte una fecha en el instante 00:00 de ese dia, con zona horaria si el
  #proyecto la usa. Se compara contra datetime y no con el lookup __date
  #porque en MySQL ese lookup exige tener cargadas las tablas de zona horaria;
  #sin ellas la consulta devuelve vacio y la grafica sale plana.
  from datetime import datetime,time
  momento=datetime.combine(fecha,time.min)
  if timezone.is_naive(momento):
    try:
      momento=timezone.make_aware(momento)
    except Exception:
      pass
  return momento


def _mes_siguiente(fecha):
  return (fecha.replace(day=28)+timedelta(days=4)).replace(day=1)


def _probabilidad(valor):
  #El registro del analizador guarda la probabilidad entre 0 y 1. Si alguna
  #fila entro en porcentaje se reescala para que no rompa los promedios.
  try:
    p=float(valor or 0)
  except (TypeError,ValueError):
    return 0.0
  if p>1:
    p=p/100.0
  return min(max(p,0.0),1.0)


# ============================================================
#  USUARIOS
# ============================================================
def resumen_usuarios():
  hoy=timezone.localdate()
  hace_30=timezone.now()-timedelta(days=30)
  hace_60=timezone.now()-timedelta(days=60)

  #Sin las cuentas de administracion: no son clientes (ver arriba)
  usuarios=usuarios_clientes()
  total=usuarios.count()
  nuevos=usuarios.filter(date_joined__gte=hace_30).count()
  previos=usuarios.filter(date_joined__gte=hace_60,date_joined__lt=hace_30).count()
  bloqueados=usuarios.filter(is_active=False).count()

  vigentes=Suscripcion.objects.filter(activa=True,vencimiento__gte=hoy)
  activas=vigentes.count()

  sin_suscripcion=max(total-activas-bloqueados,0)
  base=total or 1

  return {
    "total":total,
    "nuevos":nuevos,
    "variacion":_variacion(nuevos,previos),
    "bloqueados":bloqueados,
    "con_suscripcion":activas,
    "sin_suscripcion":sin_suscripcion,
    #Porcentajes ya calculados: la barra apilada solo pinta anchos
    "pct_con":round(activas/base*100,1),
    "pct_sin":round(sin_suscripcion/base*100,1),
    "pct_bloq":round(bloqueados/base*100,1),
    "conversion":round(activas/total*100,1) if total else 0,
    "vencidas":Suscripcion.objects.filter(vencimiento__lt=hoy).count(),
    "por_vencer":list(vigentes.filter(vencimiento__lte=hoy+timedelta(days=5))
                      .select_related("usuario").order_by("vencimiento")),
  }


# ============================================================
#  DINERO
# ============================================================
def resumen_dinero():
  hoy=timezone.localdate()
  aprobados=Pago.objects.filter(estado="Aprobado")

  inicio_mes=_primer_dia(hoy)
  inicio_anterior=_primer_dia(hoy,1)

  #Se compara contra datetime (no con el lookup __date) por lo que explica
  #_inicio_dia: con MySQL ese atajo necesita las tablas de zona horaria
  #cargadas y, sin ellas, esta tarjeta mostraba $0 aunque hubiera ventas.
  mes=aprobados.filter(creado__gte=_inicio_dia(inicio_mes)).aggregate(t=Sum("monto"),n=Count("id"))
  anterior=aprobados.filter(creado__gte=_inicio_dia(inicio_anterior),
                            creado__lt=_inicio_dia(inicio_mes))\
                    .aggregate(t=Sum("monto"))
  historico=aprobados.aggregate(t=Sum("monto"),n=Count("id"),neto=Sum("neto"))
  pendientes=Pago.objects.filter(estado="Pendiente").aggregate(t=Sum("monto"),n=Count("id"))

  intentos=Pago.objects.count()
  ventas=historico["n"] or 0
  total_mes=mes["t"] or 0

  return {
    "mes":total_mes,
    "mes_cuenta":mes["n"] or 0,
    "variacion":_variacion(total_mes,anterior["t"] or 0),
    "historico":historico["t"] or 0,
    "neto":historico["neto"] or 0,
    "ventas":ventas,
    "ticket":int((historico["t"] or 0)/ventas) if ventas else 0,
    "pendientes":pendientes["n"] or 0,
    "pendiente_monto":pendientes["t"] or 0,
    "efectividad":round(ventas/intentos*100,1) if intentos else 0,
  }


# ============================================================
#  MODELO / CASA DE APUESTAS
#  Sale de RegistroApuesta, que es lo que el analizador ya guarda cada vez
#  que se registra un partido con su resultado real.
# ============================================================
def resumen_modelo():
  filas=list(RegistroApuesta.objects.all().values("probabilidad","acierto","cuota","propia"))
  total=len(filas)

  vacio={"total":0,"aciertos":0,"tasa":0,"esperado":0,"sesgo":0,"veredicto":"Sin datos",
         "con_cuota":0,"ganancia":0,"roi":None,"propias":0,"cuota_media":0,
         "referencias":REFERENCIAS,"comparado":veredicto_global(0)}
  if total==0:
    return vacio

  aciertos=sum(1 for f in filas if f["acierto"])
  esperado=sum(_probabilidad(f["probabilidad"]) for f in filas)/total*100
  tasa=aciertos/total*100

  con_cuota=[f for f in filas if f["cuota"]]
  ganancia=0.0
  for f in con_cuota:
    ganancia=ganancia+((float(f["cuota"])-1) if f["acierto"] else -1)

  sesgo=tasa-esperado
  if abs(sesgo)<=3:
    veredicto="Calibrado"
  elif sesgo<0:
    veredicto="Optimista"
  else:
    veredicto="Conservador"

  return {
    "total":total,
    "aciertos":aciertos,
    "tasa":round(tasa,1),
    "esperado":round(esperado,1),
    "sesgo":round(sesgo,1),
    "veredicto":veredicto,
    "con_cuota":len(con_cuota),
    "ganancia":round(ganancia,2),
    "roi":round(ganancia/len(con_cuota)*100,1) if con_cuota else None,
    "propias":sum(1 for f in filas if f["propia"]),
    "referencias":REFERENCIAS,
    "comparado":veredicto_global(tasa),
    "cuota_media":round(sum(float(f["cuota"]) for f in con_cuota)/len(con_cuota),2) if con_cuota else 0,
  }


def calibracion():
  #Compara lo que el modelo prometio con lo que de verdad paso, por tramos de
  #probabilidad. Es la unica grafica que dice si el modelo se puede creer.
  datos=[(_probabilidad(f["probabilidad"]),f["acierto"])
         for f in RegistroApuesta.objects.all().values("probabilidad","acierto")]

  salida=[]
  for bajo,alto in RANGOS:
    grupo=[d for d in datos if bajo<=d[0]<alto]
    cuenta=len(grupo)
    predicho=sum(d[0] for d in grupo)/cuenta*100 if cuenta else 0
    real=sum(1 for d in grupo if d[1])/cuenta*100 if cuenta else 0
    diferencia=real-predicho

    if cuenta<MINIMO_FIABLE:
      veredicto="Pocos datos"
    elif abs(diferencia)<=5:
      veredicto="Ajustado"
    elif diferencia<0:
      veredicto="Optimista"
    else:
      veredicto="Conservador"

    salida.append({
      "etiqueta":f"{int(bajo*100)}–{min(int(alto*100),100)}%",
      "cuenta":cuenta,
      "predicho":round(predicho,1),
      "real":round(real,1),
      "diferencia":round(diferencia,1),
      "veredicto":veredicto,
      "fiable":cuenta>=MINIMO_FIABLE,
    })
  return salida


def por_mercado():
  #Que tipo de apuesta acierta y cual pierde plata. Ordenado por volumen para
  #que arriba quede lo que mas se usa, no lo que mejor se ve.
  mapa={}
  for f in RegistroApuesta.objects.all().values("mercado","probabilidad","acierto","cuota"):
    clave=f["mercado"] or "Sin mercado"
    fila=mapa.setdefault(clave,{"mercado":clave,"cuenta":0,"aciertos":0,
                                "con_cuota":0,"ganancia":0.0,"predicho":0.0})
    fila["cuenta"]=fila["cuenta"]+1
    fila["predicho"]=fila["predicho"]+_probabilidad(f["probabilidad"])
    if f["acierto"]:
      fila["aciertos"]=fila["aciertos"]+1
    if f["cuota"]:
      fila["con_cuota"]=fila["con_cuota"]+1
      fila["ganancia"]=fila["ganancia"]+((float(f["cuota"])-1) if f["acierto"] else -1)

  salida=[]
  for fila in mapa.values():
    cuenta=fila["cuenta"]
    salida.append({
      "mercado":fila["mercado"],
      "cuenta":cuenta,
      "aciertos":fila["aciertos"],
      "tasa":round(fila["aciertos"]/cuenta*100,1),
      "predicho":round(fila["predicho"]/cuenta*100,1),
      "ganancia":round(fila["ganancia"],2),
      "roi":round(fila["ganancia"]/fila["con_cuota"]*100,1) if fila["con_cuota"] else None,
      "fiable":cuenta>=MINIMO_FIABLE,
    })
  return sorted(salida,key=lambda f:-f["cuenta"])


# ============================================================
#  SERIES Y GEOMETRIA DE GRAFICAS
# ============================================================
def serie_ingresos(meses=12):
  #Siempre devuelve los N meses completos, incluidos los que no vendieron:
  #un mes en cero tiene que verse, no desaparecer.
  hoy=timezone.localdate()
  desde=_primer_dia(hoy,meses-1)

  crudo=(Pago.objects.filter(estado="Aprobado",creado__gte=_inicio_dia(desde))
         .values_list("creado","monto"))
  mapa={}
  for creado,monto in crudo:
    fecha=timezone.localtime(creado).date() if timezone.is_aware(creado) else creado.date()
    llave=(fecha.year,fecha.month)
    acumulado=mapa.get(llave,[0,0])
    acumulado[0]=acumulado[0]+(monto or 0)
    acumulado[1]=acumulado[1]+1
    mapa[llave]=acumulado

  serie=[]
  cursor=desde
  for _ in range(meses):
    total,cuenta=mapa.get((cursor.year,cursor.month),[0,0])
    serie.append({"etiqueta":MESES[cursor.month-1],
                  "detalle":f"{MESES[cursor.month-1]} {str(cursor.year)[2:]}",
                  "valor":total,"cuenta":cuenta})
    cursor=_mes_siguiente(cursor)
  return serie


def serie_usuarios(meses=12):
  hoy=timezone.localdate()
  desde=_primer_dia(hoy,meses-1)

  mapa={}
  for creado in usuarios_clientes().filter(date_joined__gte=_inicio_dia(desde)).values_list("date_joined",flat=True):
    fecha=timezone.localtime(creado).date() if timezone.is_aware(creado) else creado.date()
    llave=(fecha.year,fecha.month)
    mapa[llave]=mapa.get(llave,0)+1

  serie=[]
  cursor=desde
  for _ in range(meses):
    cuenta=mapa.get((cursor.year,cursor.month),0)
    serie.append({"etiqueta":MESES[cursor.month-1],
                  "detalle":f"{MESES[cursor.month-1]} {str(cursor.year)[2:]}",
                  "valor":cuenta,"cuenta":cuenta})
    cursor=_mes_siguiente(cursor)
  return serie


def barras(serie,alto=150,ancho=620,separacion=10):
  #Alturas y posiciones calculadas en el servidor. La plantilla solo pinta.
  total=len(serie) or 1
  paso=ancho/total
  grosor=max(6,paso-separacion)
  maximo=max([f["valor"] for f in serie] or [0]) or 1

  salida=[]
  for i,fila in enumerate(serie):
    altura=max(2,int(round(fila["valor"]/maximo*alto)))
    salida.append({
      "etiqueta":fila["etiqueta"],
      "detalle":fila["detalle"],
      "valor":fila["valor"],
      "cuenta":fila.get("cuenta",0),
      "alto":altura,
      "y":alto-altura,
      "x":round(i*paso+(paso-grosor)/2,1),
      "centro":round(i*paso+paso/2,1),
      "ancho":round(grosor,1),
      "pico":fila["valor"]>=maximo and maximo>0,
    })
  return {"barras":salida,"maximo":maximo,"alto":alto,"ancho":ancho}