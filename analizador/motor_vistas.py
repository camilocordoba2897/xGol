#Endpoints del motor de pronostico.
#
#Archivo NUEVO: no toca views.py ni el frontend actual. Se conecta solo con
#tres lineas en urls.py.
#
#   GET /analizador/motor/pronostico?liga=PD&local=Real Madrid&visitante=Barcelona
#   GET /analizador/motor/fuerzas?liga=PD
#   GET /analizador/motor/rendimiento?liga=PD
#
#El primero devuelve TODOS los mercados, la opinion de cada fuente por
#separado, los pesos usados, el nivel de confianza y las apuestas con valor.
#El frontend pinta lo que quiera de ahi.
import math

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse

from suscripciones.decoradores import suscripcion_requerida
from analizador import motor_datos
from analizador.models import AjusteMotor,PesosMotor,PrediccionMotor
from analizador.motor import combinacion,elo as mod_elo,evaluacion,nucleo,tasas
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
        return dict(combinacion.PESOS_POR_DEFECTO),1.0,None
    return (fila.pesos or dict(combinacion.PESOS_POR_DEFECTO),
            fila.temperatura or 1.0,fila)


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

    ajuste,tabla,mapa,error=_cargar_ajuste(liga)
    if ajuste is None:
        return JsonResponse({"error":error or "sin_datos"},status=503)

    local=motor_datos.nombre_de_equipo(bruto_local,mapa)
    visitante=motor_datos.nombre_de_equipo(bruto_visitante,mapa)

    casas,error_cuotas=motor_datos.casas_desde_api(liga,local,visitante)
    pesos,temperatura,fila_pesos=_pesos_y_calibracion(liga)

    try:
        resultado=nucleo.pronosticar(
            local,visitante,
            ajuste_liga=ajuste,tabla_elo=tabla,casas=casas or None,
            pesos=pesos,temperatura=temperatura,cancha_neutral=neutral,
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
    salida["apuestas_con_valor"]=nucleo.apuestas_con_valor(resultado,casas)
    if error_cuotas:
        salida["diagnostico"]["avisos"].append(f"sin cuotas ({error_cuotas})")

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


@login_required(login_url="Ingresar")
@suscripcion_requerida
def motor_fuerzas(request):
    #Tabla de ataque y defensa de la liga.
    #  ataque  1.30 = mete un 30% MAS de goles que el equipo promedio
    #  defensa 0.70 = encaja un 30% MENOS que el promedio  (MENOR ES MEJOR)
    #Es lo que hay que enseñar para que se entienda de donde sale el pronostico.
    liga=(request.GET.get("liga") or "").strip()
    if not liga:
        return JsonResponse({"error":"faltan_parametros"},status=400)
    ajuste,tabla,mapa,error=_cargar_ajuste(liga)
    if ajuste is None:
        return JsonResponse({"error":error or "sin_datos"},status=503)
    return JsonResponse({
        "liga":liga,
        "media_goles":math.exp(ajuste.mu),
        "ventaja_local":math.exp(ajuste.ventaja_local),
        "rho":ajuste.rho,
        "partidos_usados":ajuste.partidos_usados,
        "fuerzas":ajuste.tabla_fuerzas(),
        "elo":tabla.clasificacion() if tabla else [],
    })


@login_required(login_url="Ingresar")
@suscripcion_requerida
def motor_rendimiento(request):
    #Como le ha ido al motor de verdad, con los pronosticos que guardo ANTES
    #de cada partido. Esta es la pantalla que convence a quien pregunte.
    liga=(request.GET.get("liga") or "").strip()
    consulta=PrediccionMotor.objects.filter(evaluado=True).exclude(resultado="")
    if liga:
        consulta=consulta.filter(liga=liga)
    filas=list(consulta.order_by("creado")[:2000])
    if not filas:
        return JsonResponse({"partidos":0,"mensaje":"aun no hay partidos evaluados"})

    casos=[{
        "probabilidades":{"local":f.prob_local,"empate":f.prob_empate,
                          "visitante":f.prob_visitante},
        "real":f.resultado,
        "cuotas":f.cuotas or {},
    } for f in filas]

    informe=evaluacion.informe(casos,liga or "todas las ligas")
    informe["apuestas"]=evaluacion.rendimiento_apuestas(casos)
    #Referencias reales para que el numero signifique algo
    informe["referencia"]={
        "sin_saber_nada":1.0986,
        "solo_localia":1.0300,
        "modelo_decente":0.9900,
        "mercado_de_apuestas":0.9600,
    }
    return JsonResponse(informe)