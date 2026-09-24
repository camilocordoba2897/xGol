#Endpoint del motor de pronostico.
#
#   GET /analizador/motor/pronostico?liga=PD&local=Real Madrid&visitante=Barcelona
#
#Devuelve TODOS los mercados (de una sola matriz de marcadores), la opinion de
#cada fuente por separado, los pesos usados y el nivel de confianza. Lo pinta
#static/js/motor.js.
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse

from suscripciones.decoradores import suscripcion_requerida
from analizador import api_datos,motor_datos
from analizador.models import AjusteMotor,PesosMotor,PrediccionMotor
from analizador.motor import combinacion,elo as mod_elo,nucleo,tasas
from analizador.motor.probabilidad import resumen_mercados


def _cargar_ajuste(liga):
    #Primero la base de datos, que es instantaneo. Si aun no se corrio el
    #comando ajustar_motor, se ajusta al vuelo y se deja en cache 6 horas.
    fila=AjusteMotor.objects.filter(liga=liga).first()
    if fila and fila.parametros:
        return (tasas.AjusteLiga.desde_dict(fila.parametros),
                mod_elo.TablaElo.desde_dict(fila.elo or {}),
                (fila.parametros.get("mapa_ids") or {}),None)
    return motor_datos.ajuste_en_cache(liga)


def _pesos_y_calibracion(liga):
    #Lo aprendido por evaluar_motor. Si aun no hay nada se usan los valores de
    #fabrica: el motor funciona desde el primer dia, solo que sin afinar.
    fila=PesosMotor.objects.filter(liga=liga).first()
    if not fila:
        #Sin calibracion propia (la Champions): los pesos que ganaron en las
        #ligas medidas. Las temperaturas NO se trasladan: cambian mucho de una
        #liga a otra y sin medir aqui no hay con que elegir una.
        return motor_datos.pesos_de_referencia(),1.0,1.0,None
    return (fila.pesos or dict(combinacion.PESOS_POR_DEFECTO),
            fila.temperatura or 1.0,fila.temperatura_sin_mercado or 1.0,fila)


def _guardar_prediccion(liga,id_partido,fecha,local,visitante,resultado,casas):
    #Se guarda ANTES de que se juegue el partido, y NO se sobrescribe: el
    #primer pronostico es el que vale. Si se pudiera reescribir, bastaria con
    #volver a pedirlo despues del partido para que el historial pareciera
    #perfecto, y las metricas no valdrian nada.
    from analizador.motor import mercado as mod_mercado
    r=resultado.mercados["1x2"]
    cuotas={}
    if casas:
        mejor=mod_mercado.mejor_cuota(casas)
        cuotas={k:v["cuota"] for k,v in mejor.items() if v}
    try:
        _,creado=PrediccionMotor.objects.get_or_create(
            liga=liga,id_partido=str(id_partido),
            defaults={
                "fecha":fecha or "",
                "equipo_local":local[:80],
                "equipo_visitante":visitante[:80],
                "prob_local":r["local"],
                "prob_empate":r["empate"],
                "prob_visitante":r["visitante"],
                "por_fuente":resultado.fuentes,
                "pesos":resultado.pesos,
                "mercados":resultado.mercados,
                "cuotas":cuotas,
            },
        )
        return bool(creado)
    except Exception:
        return False


@login_required(login_url="Ingresar")
@suscripcion_requerida
def motor_pronostico(request):
    liga=(request.GET.get("liga") or "").strip()
    #Se acepta el id numerico del equipo o su nombre: los dos funcionan.
    bruto_local=(request.GET.get("local") or request.GET.get("nombre_local") or "").strip()
    bruto_visitante=(request.GET.get("visitante") or request.GET.get("nombre_visitante") or "").strip()
    neutral=request.GET.get("neutral") in ("1","true","si")
    if not liga or not bruto_local or not bruto_visitante:
        return JsonResponse({"error":"faltan_parametros"},status=400)
    #Solo las ligas que cubre xGol: un codigo inventado disparaba el ajuste
    #completo de una liga inexistente y gastaba cupo de la API en nada.
    if liga not in api_datos.LIGAS:
        return JsonResponse({"error":"liga_no_cubierta"},status=400)

    ajuste,tabla,mapa,error=_cargar_ajuste(liga)
    if ajuste is None:
        return JsonResponse({"error":error or "sin_datos"},status=503)

    local=motor_datos.nombre_de_equipo(bruto_local,mapa)
    visitante=motor_datos.nombre_de_equipo(bruto_visitante,mapa)

    #El motivo por el que no hay cuotas (sin_partido, limite de la API...) ya
    #no se manda a la pantalla: salia como "sin cuotas (sin_partido)", que es
    #un codigo interno y no le dice nada al usuario. Si hay cuotas, la tarjeta
    #de cuotas y la tabla de fuentes las muestran; si no, simplemente no salen.
    casas,_motivo_sin_cuotas=motor_datos.casas_desde_api(liga,local,visitante)
    pesos,temperatura,temperatura_sm,fila_pesos=_pesos_y_calibracion(liga)

    try:
        resultado=nucleo.pronosticar(
            local,visitante,
            ajuste_liga=ajuste,tabla_elo=tabla,casas=casas or None,
            pesos=pesos,temperatura=temperatura,cancha_neutral=neutral,
            temperatura_sin_mercado=temperatura_sm,
        )
    except ValueError as e:
        return JsonResponse({"error":str(e)},status=503)

    #UNA SOLA MATRIZ PARA TODO.
    #El motor calcula internamente con marcadores de 0 a 10, pero al frontend
    #solo le hace falta hasta 7 (la probabilidad de que un equipo meta 8 goles
    #es de una entre un millon). Se recorta a 8x8 y SE RENORMALIZA, y despues
    #TODOS los mercados se vuelven a calcular desde esa matriz recortada.
    #
    #Por que este detalle importa: si se mandara la matriz recortada pero los
    #mercados calculados con la completa, el frontend pintaria un 1X2 y una
    #tabla de marcadores que no cuadran entre si por unas milesimas. Serian
    #dos numeros distintos para lo mismo, que es justo lo que hay que evitar.
    #Asi, lo que se guarda, lo que se manda y lo que se pinta es identico.
    matriz=[fila[:8] for fila in resultado.matriz[:8]]
    total=sum(sum(fila) for fila in matriz)
    matriz=[[v/total for v in fila] for fila in matriz]
    resultado.matriz=matriz
    resultado.mercados=resumen_mercados(matriz)

    salida=resultado.a_dict()
    salida["matriz"]=matriz
    salida["liga"]=liga
    salida["local"]=local
    salida["visitante"]=visitante

    id_partido=(request.GET.get("id_partido") or "").strip()
    if id_partido:
        salida["guardado"]=_guardar_prediccion(
            liga,id_partido,request.GET.get("fecha",""),
            local,visitante,resultado,casas)

    if fila_pesos:
        salida["rendimiento_historico"]={
            "partidos":fila_pesos.partidos_evaluados,
            "log_perdida":fila_pesos.log_perdida,
            "rps":fila_pesos.rps,
            "acierto":fila_pesos.acierto,
            "ece":fila_pesos.ece,
        }
    return JsonResponse(salida)
