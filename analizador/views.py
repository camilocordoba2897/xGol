from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.db import transaction
import json
from suscripciones.decoradores import suscripcion_requerida
from analizador.models import PartidoRegistrado,RegistroApuesta
from analizador import api_datos
from analizador import api_cuotas

#Iconos por mercado para reconstruir la apuesta si viene sin icono (ej. CSV importado)
ICONOS_MERCADO={
    "1X2":"🏆","Goles":"⚽","BTTS":"🤝","Córners":"🚩",
    "Tiros a puerta":"🎯","Tiros":"💥","Tarjetas":"🟨","Mitades":"⏱️",
}

def _referencia_a_ts(valor):
    #betLog usa ts numerico; se devuelve int si es un numero, si no el texto tal cual
    texto=str(valor)
    return int(texto) if texto.isdigit() else texto

#Mostrar el analizador solo a los usuarios que iniciaron sesion
@login_required(login_url="Ingresar")
@suscripcion_requerida
def analizador(request):
    return render(request,"analizador.html")


# ============================================================
#  REGISTRO DE APUESTAS (antes: 'fba_betlog_v1' + 'fba_betlogmeta_v1')
# ============================================================
@login_required(login_url="Ingresar")
def cargar_apuestas(request):
    apuestas=[]
    for a in RegistroApuesta.objects.filter(usuario=request.user).order_by("creado","id"):
        fila={
            "ts":_referencia_a_ts(a.referencia),
            "date":a.fecha,
            "team1":a.equipo_local,
            "team2":a.equipo_visitante,
            "league":a.liga,
            "market":a.mercado,
            "icon":a.icono or ICONOS_MERCADO.get(a.mercado,"🎯"),
            "label":a.etiqueta,
            "prob":a.probabilidad,
            "hit":a.acierto,
        }
        if a.propia:
            fila["mine"]=True
        if a.cuota is not None:
            fila["odds"]=a.cuota
        apuestas.append(fila)
    metadatos={}
    for p in PartidoRegistrado.objects.filter(usuario=request.user):
        metadatos[p.referencia]={
            "a":p.datos,
            "league":p.liga,
            "date":p.fecha,
            "team1":p.equipo_local,
            "team2":p.equipo_visitante,
        }
    return JsonResponse({"betLog":apuestas,"betLogMeta":metadatos})

@login_required(login_url="Ingresar")
@require_POST
def guardar_apuestas(request):
    try:
        cuerpo=json.loads(request.body)
    except Exception:
        return JsonResponse({"ok":False},status=400)
    apuestas=cuerpo.get("betLog",[]) if isinstance(cuerpo,dict) else None
    metadatos=cuerpo.get("betLogMeta",{}) if isinstance(cuerpo,dict) else None
    #Con otra forma, el .get() y el .items() de abajo tumbaban la vista con 500
    if not isinstance(apuestas,list) or not isinstance(metadatos,dict):
        return JsonResponse({"ok":False},status=400)
    apuestas=[r for r in apuestas if isinstance(r,dict)]
    metadatos={k:m for k,m in metadatos.items() if isinstance(m,dict)}
    with transaction.atomic():
        RegistroApuesta.objects.filter(usuario=request.user).delete()
        PartidoRegistrado.objects.filter(usuario=request.user).delete()

        filas=[]
        for r in apuestas:
            cuota=r.get("odds")
            try:
                cuota=float(cuota) if cuota not in (None,"",0) else None
            except (TypeError,ValueError):
                cuota=None
            try:
                prob=float(r.get("prob") or 0)
            except (TypeError,ValueError):
                prob=0
            filas.append(RegistroApuesta(
                usuario=request.user,
                referencia=str(r.get("ts",""))[:30],
                fecha=str(r.get("date","") or "")[:12],
                equipo_local=str(r.get("team1","") or "")[:80],
                equipo_visitante=str(r.get("team2","") or "")[:80],
                liga=str(r.get("league","") or "")[:80],
                mercado=str(r.get("market","") or "")[:30],
                icono=str(r.get("icon","") or "")[:8],
                etiqueta=str(r.get("label","") or "")[:120],
                probabilidad=prob,
                acierto=bool(r.get("hit")),
                propia=bool(r.get("mine")),
                cuota=cuota
            ))
        RegistroApuesta.objects.bulk_create(filas)

        partidos=[]
        for referencia,m in metadatos.items():
            partidos.append(PartidoRegistrado(
                usuario=request.user,
                referencia=str(referencia)[:30],
                fecha=str(m.get("date","") or "")[:12],
                equipo_local=str(m.get("team1","") or "")[:80],
                equipo_visitante=str(m.get("team2","") or "")[:80],
                liga=str(m.get("league","") or "")[:80],
                datos=m.get("a",{})
            ))
        PartidoRegistrado.objects.bulk_create(partidos)
    return JsonResponse({"ok":True})


# ============================================================
#  ANALIZADOR AUTOMATICO — datos en vivo desde la API
#  El motor no cambia: estos endpoints solo le entregan las filas
#  ya armadas en el mismo esquema que venia del CSV.
# ============================================================
@login_required(login_url="Ingresar")
@suscripcion_requerida
def auto_partidos(request):
    liga=request.GET.get("liga","BSA")
    if liga not in api_datos.LIGAS:
        return JsonResponse({"partidos":[],"error":"liga_no_cubierta"},status=400)
    partidos,error=api_datos.partidos_liga(liga)
    if error:
        return JsonResponse({"partidos":[],"error":error})
    return JsonResponse({"partidos":partidos})

@login_required(login_url="Ingresar")
@suscripcion_requerida
def auto_enfrentamiento(request):
    try:
        id_local=int(request.GET.get("local",""))
        id_visitante=int(request.GET.get("visitante",""))
    except (TypeError,ValueError):
        return JsonResponse({"error":"faltan los equipos"},status=400)
    nombre_local=(request.GET.get("nombre_local") or "Local")[:80]
    nombre_visitante=(request.GET.get("nombre_visitante") or "Visitante")[:80]
    #La liga solo se usa como respaldo: si un equipo viene con pocos partidos
    #(arranque de temporada o ascendido), el historial se completa desde
    #datos_historicos/<liga>.csv sin gastar ni una peticion a la API.
    liga=(request.GET.get("liga") or "").strip()[:10]
    #El nombre largo llega ademas del corto: football-data dice "PSG" y "Barca"
    #donde el historico dice "Paris SG" y "Barcelona". Contra el largo
    #("Paris Saint-Germain FC", "FC Barcelona") si emparejan.
    largo_local=(request.GET.get("largo_local") or "")[:120]
    largo_visitante=(request.GET.get("largo_visitante") or "")[:120]
    datos=api_datos.enfrentamiento(id_local,nombre_local,id_visitante,nombre_visitante,
        liga=liga or None,largo_local=largo_local or None,largo_visitante=largo_visitante or None)
    return JsonResponse(datos)


@login_required(login_url="Ingresar")
@suscripcion_requerida
def auto_resultados(request):
    #Marcadores reales de partidos ya jugados, para evaluar predicciones solas
    crudo=request.GET.get("ids","")
    ids=[]
    for parte in crudo.split(","):
        parte=parte.strip()
        if parte.isdigit():
            ids.append(int(parte))
    if not ids:
        return JsonResponse({"resultados":{}})
    resultados,error=api_datos.resultados_partidos(ids)
    if error:
        return JsonResponse({"resultados":resultados,"error":error})
    return JsonResponse({"resultados":resultados})

@login_required(login_url="Ingresar")
@suscripcion_requerida
def auto_cuotas(request):
    #Cuotas reales de casas de apuestas para un partido concreto.
    #Si no hay clave configurada devuelve error y el frontend no pinta nada.
    liga=request.GET.get("liga","")
    local=request.GET.get("nombre_local","")
    visitante=request.GET.get("nombre_visitante","")
    if not liga or not local or not visitante:
        return JsonResponse({"cuotas":None,"error":"parametros"})
    cuotas,error=api_cuotas.cuotas_partido(liga,local,visitante)
    if error:
        return JsonResponse({"cuotas":None,"error":error})
    return JsonResponse({"cuotas":cuotas})