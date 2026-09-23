from django.contrib.auth.decorators import login_required
from usuarios.decoradores import rol_requerido
from django.shortcuts import render,redirect,get_object_or_404
from django.contrib.auth.models import User
from django.contrib.auth import authenticate,login,logout
from django.contrib import messages
from usuarios.models import Rol,Perfil,Bitacora
from usuarios.validaciones import (validar_registro, validar_usuario,
                                    validar_correo, validar_nombre,
                                    validar_contrasena, validar_documento,
                                    validar_telefono, validar_avatar,
                                    completar_identidad)
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.http import JsonResponse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST
from django.contrib.auth import update_session_auth_hash


def _datos_escritos(request):
    #Se devuelven los datos escritos para que el usuario no tenga que
    #teclearlos otra vez. La contraseña NO se devuelve nunca.
    return {campo:request.POST.get(campo,"") for campo in
            ("nombre","apellidos","username","email","documento","fecha_nacimiento")}


def registro(request):
    if request.method!="POST":
        return render(request,"registro.html")

    #Se valida TODO en el servidor: los pattern del HTML son comodidad,
    #pero se saltan desde la consola del navegador o con curl.
    limpios,errores=validar_registro(request.POST)

    if errores:
        for error in errores:
            messages.error(request,error)
        return render(request,"registro.html",{"datos":_datos_escritos(request)})

    #Dos personas pueden mandar el mismo usuario a la vez: las dos pasan la
    #validacion y la segunda choca en la base. Todo va en una transaccion
    #para que ese choque no deje un User creado sin su Perfil.
    try:
        with transaction.atomic():
            usuario=User.objects.create_user(
                username=limpios["username"],
                email=limpios["email"],
                password=limpios["password"]
            )
            usuario.first_name=limpios["nombre"]
            usuario.last_name=limpios["apellidos"]
            usuario.save()

            rol=Rol.objects.filter(nombre="usuario").first()
            Perfil.objects.create(
                usuario=usuario,
                rol=rol,
                proveedor="local",
                nombre=limpios["nombre"],
                apellidos=limpios["apellidos"],
                #Se guardan los valores YA validados y limpios: la cedula sin puntos
                #y la fecha como objeto date, no lo que vino crudo del POST.
                tipo_documento=request.POST.get("tipo_documento") or "CC",
                documento=limpios["documento"],
                fecha_nacimiento=limpios["fecha_nacimiento"],
                ciudad=request.POST.get("ciudad"),
                pais=request.POST.get("pais"),
                telefono=request.POST.get("telefono")
            )
    except IntegrityError:
        #Otro registro gano la carrera. Se valida de nuevo para decir QUE dato
        #quedo tomado (usuario o cedula), no un error generico.
        _,errores=validar_registro(request.POST)
        for error in errores or ["Alguno de tus datos ya está registrado, revisa el formulario."]:
            messages.error(request,error)
        return render(request,"registro.html",{"datos":_datos_escritos(request)})

    messages.success(request,"Cuenta creada correctamente, ya puedes iniciar sesion")
    return redirect("Ingresar")


# ============================================================
#  DISPONIBILIDAD EN VIVO (registro)
#  El formulario pregunta aqui, mientras la persona escribe, si el usuario,
#  el correo o la cedula ya estan tomados. Usa las MISMAS funciones que el
#  registro, asi que el mensaje es identico al que saldria al enviarlo.
#
#  Va por POST con CSRF y con tope por IP: responder "ese correo ya existe"
#  sirve para averiguar quien tiene cuenta. El registro ya lo dice al
#  enviar, pero sin tope esta ruta seria una forma comoda de probar miles.
# ============================================================
VALIDADORES_DISPONIBLES={
    "username":validar_usuario,
    "email":validar_correo,
    "documento":validar_documento,
}
TOPE_CONSULTAS=40   #por IP y por minuto

@require_POST
def disponible(request):
    llave=f"disponible_{obtener_ip(request)}"
    consultas=cache.get(llave,0)
    if consultas>=TOPE_CONSULTAS:
        return JsonResponse({"error":"Demasiadas consultas, espera un momento."},status=429)
    cache.set(llave,consultas+1,60)

    validar=VALIDADORES_DISPONIBLES.get(request.POST.get("campo"))
    if validar is None:
        return JsonResponse({"error":"Campo no valido."},status=400)
    _,error=validar(request.POST.get("valor"))
    return JsonResponse({"disponible":error is None,"mensaje":error or ""})


def obtener_ip(request):
    #Recortada a 40, lo que mide la columna de la Bitacora.
    adelante=request.META.get("HTTP_X_FORWARDED_FOR")
    if adelante:
        return adelante.split(",")[0].strip()[:40]
    return (request.META.get("REMOTE_ADDR") or "")[:40]


#Tope de intentos fallidos de inicio de sesion. Sin esto cualquiera podia
#probar contrasenas sin limite contra una cuenta. Se cuenta por IP y usuario
#(para no bloquear a toda una red por un vecino) y tambien por IP sola (para
#que no se puedan barrer muchas cuentas desde el mismo equipo).
FALLOS_POR_CUENTA=5
FALLOS_POR_IP=20
BLOQUEO_SEGUNDOS=15*60

def _llaves_fallos(request,username):
    ip=obtener_ip(request)
    return f"login_fallos_{ip}_{username.lower()[:150]}",f"login_fallos_{ip}"

def ingresar(request):
    #A donde volver despues de entrar: login_required manda ?next=/ruta. Solo
    #se aceptan rutas de este mismo sitio, nunca un dominio externo.
    siguiente=request.POST.get("next") or request.GET.get("next") or ""
    if not url_has_allowed_host_and_scheme(siguiente,allowed_hosts={request.get_host()},
                                           require_https=request.is_secure()):
        siguiente=""

    if request.method=="POST":
        username=(request.POST.get("username") or "").strip()
        password=request.POST.get("password") or ""

        llave_cuenta,llave_ip=_llaves_fallos(request,username)
        if cache.get(llave_cuenta,0)>=FALLOS_POR_CUENTA or cache.get(llave_ip,0)>=FALLOS_POR_IP:
            messages.error(request,"Demasiados intentos fallidos. Espera 15 minutos e intentalo de nuevo.")
            return render(request,"ingresar.html",{"next":siguiente})

        usuario=authenticate(request,username=username,password=password)

        if usuario is not None:
            cache.delete(llave_cuenta)
            login(request,usuario)

            #Recortados al tamano de sus columnas: el navegador de Instagram,
            #por ejemplo, manda un agente de mas de 200 caracteres y MySQL en
            #modo estricto rechazaba el guardado, tumbando el inicio de sesion.
            Bitacora.objects.create(
                usuario=usuario,
                accion="Inicio de sesion",
                ip=obtener_ip(request),
                agente=(request.META.get("HTTP_USER_AGENT") or "")[:200]
            )

            if siguiente:
                return redirect(siguiente)
            perfil=getattr(usuario,"perfil",None)
            if usuario.is_superuser or (perfil is not None and perfil.rol is not None and perfil.rol.nombre=="administrador"):
                return redirect("PanelAdmin")
            return redirect("Inicio")

        cache.set(llave_cuenta,cache.get(llave_cuenta,0)+1,BLOQUEO_SEGUNDOS)
        cache.set(llave_ip,cache.get(llave_ip,0)+1,BLOQUEO_SEGUNDOS)
        messages.error(request,"Usuario o contraseña incorrectos")
        return render(request,"ingresar.html",{"next":siguiente})

    return render(request,"ingresar.html",{"next":siguiente})


def salir(request):
    logout(request)
    return redirect("Ingresar")

@rol_requerido("administrador")
def panel_admin(request):
    #El panel absorbe el control financiero: antes eran dos pantallas con las
    #mismas cifras. Aca se muestran en pestanas independientes.
    from django.conf import settings
    from django.core.paginator import Paginator
    from datetime import datetime
    from usuarios import tablero
    from suscripciones.planes import PLANES
    from pagos import pasarela,reportes

    def _fecha(nombre):
        crudo=(request.GET.get(nombre) or "").strip()
        if not crudo:
            return None
        try:
            return datetime.strptime(crudo,"%Y-%m-%d").date()
        except ValueError:
            return None

    filtros={
        "estado":request.GET.get("estado","todos"),
        "plan":request.GET.get("plan","todos"),
        "metodo":request.GET.get("metodo","todos"),
        "desde":_fecha("desde"),
        "hasta":_fecha("hasta"),
        "q":request.GET.get("q",""),
    }
    #Los pendientes son intentos de checkout abandonados, no transacciones:
    #ensucian el historial y parecen un error del sistema. Se excluyen.
    consulta=reportes.transacciones(filtros).exclude(estado="Pendiente")
    paginas=Paginator(consulta,25)
    pagina=paginas.get_page(request.GET.get("pagina"))

    #Sin las cuentas de administracion: el admin no es un cliente y no
    #tiene sentido que se liste con botones de Bloquear o Eliminar.
    perfiles=(tablero.perfiles_clientes()
              .select_related("usuario","rol").order_by("-creado"))

    accesos=Bitacora.objects.select_related("usuario").all().order_by("-creado")[:12]

    usuarios=tablero.resumen_usuarios()
    dinero=tablero.resumen_dinero()
    modelo=tablero.resumen_modelo()

    return render(request,"panel_admin.html",{
        "perfiles": perfiles,
        "accesos": accesos,
        "usuarios": usuarios,
        "dinero": dinero,
        "modelo": modelo,
        "calibracion": tablero.calibracion(),
        "mercados": tablero.por_mercado(),
        "grafica_ingresos": tablero.barras(tablero.serie_ingresos(12)),
        "grafica_usuarios": tablero.barras(tablero.serie_usuarios(12)),

        #Todo lo que antes vivia en la pantalla de control financiero
        "ingresos": reportes.resumen_ingresos(),
        "suscripciones": reportes.resumen_suscripciones(),
        "por_plan": reportes.ventas_por_plan(),
        "por_metodo": reportes.ventas_por_metodo(),
        "renovaciones": reportes.proximas_renovaciones(),
        "movimientos": reportes.movimientos(),
        "pagina": pagina,
        "filtros": filtros,
        "planes": PLANES,
        "total_filtrado": consulta.count(),
        "ambiente": settings.WOMPI_AMBIENTE,
        "pasarela_lista": pasarela.configurada(),
    })

@login_required(login_url="Ingresar")
def editar_perfil(request):
    from allauth.socialaccount.models import SocialAccount
    perfil,creado=Perfil.objects.get_or_create(usuario=request.user)
    es_google=SocialAccount.objects.filter(user=request.user,provider="google").exists()

    if request.method=="POST":
        accion=request.POST.get("accion")

        if accion=="datos":
            #Se validan con las mismas reglas del registro. excluir_id evita
            #que el usuario choque consigo mismo al guardar sin cambiar nada.
            #Ninguno lleva required en el formulario, asi que solo se revisa
            #lo que venga escrito; si viene, tiene que ser valido.
            nombre_crudo=(request.POST.get("nombre") or "").strip()
            if nombre_crudo:
                nombre,e_nombre=validar_nombre(nombre_crudo,"El nombre")
                if e_nombre:
                    messages.error(request,e_nombre)
                    return redirect("EditarPerfil")
            else:
                nombre=""

            if not es_google:
                nuevo_usuario=request.POST.get("username","").strip()
                if nuevo_usuario and nuevo_usuario!=request.user.username:
                    #Antes usaba filter(username=...) exacto: dejaba pasar
                    #"Juan" existiendo "juan", que el usuario lee igual.
                    limpio,error=validar_usuario(nuevo_usuario,excluir_id=request.user.pk)
                    if error:
                        messages.error(request,error)
                        return redirect("EditarPerfil")
                    request.user.username=limpio

                #El correo no se validaba: por aca tambien se podian repetir.
                #El correo es obligatorio: es donde le llega la factura de
                #su plan y por donde recupera la contrasena.
                correo,e_correo=validar_correo(request.POST.get("correo"),
                                                excluir_id=request.user.pk)
                if e_correo:
                    messages.error(request,e_correo)
                    return redirect("EditarPerfil")
                request.user.email=correo

            telefono,e_telefono=validar_telefono(request.POST.get("telefono"))
            if e_telefono:
                messages.error(request,e_telefono)
                return redirect("EditarPerfil")
            avatar=request.FILES.get("avatar")
            if avatar:
                e_avatar=validar_avatar(avatar)
                if e_avatar:
                    messages.error(request,e_avatar)
                    return redirect("EditarPerfil")

            request.user.first_name=nombre
            request.user.save()

            perfil.telefono=telefono
            if avatar:
                perfil.avatar=avatar
            perfil.save()

            messages.success(request,"Tus datos se actualizaron correctamente")
            return redirect("EditarPerfil")

        if accion=="identidad":
            error=completar_identidad(perfil,request.POST.get("documento"),
                                      request.POST.get("fecha_nacimiento"))
            if error:
                messages.error(request,error)
            else:
                messages.success(request,"Tus datos de identidad quedaron registrados")
            return redirect("EditarPerfil")

        if accion=="clave":
            actual=request.POST.get("clave_actual") or ""
            nueva=request.POST.get("clave_nueva") or ""
            confirmar=request.POST.get("clave_confirmar") or ""

            if not request.user.check_password(actual):
                messages.error(request,"La contraseña actual no es correcta")
                return redirect("EditarPerfil")

            if nueva!=confirmar:
                messages.error(request,"Las contraseñas nuevas no coinciden")
                return redirect("EditarPerfil")

            #Las mismas reglas del registro, desde el mismo sitio
            _,error=validar_contrasena(nueva)
            if error:
                messages.error(request,error)
                return redirect("EditarPerfil")

            request.user.set_password(nueva)
            request.user.save()
            update_session_auth_hash(request,request.user)
            messages.success(request,"Tu contraseña se cambió correctamente")
            return redirect("EditarPerfil")

    return render(request,"editar_perfil.html",{"perfil": perfil,"es_google": es_google})


@rol_requerido("administrador")
def admin_eliminar_usuario(request,id):
    usuario=get_object_or_404(User,id=id)

    if usuario==request.user:
        messages.error(request,"No puedes eliminar tu propia cuenta")
        return redirect("PanelAdmin")

    #Tampoco a OTRO administrador: ya no salen en la lista, pero la URL se
    #puede escribir a mano y sin esto quedaria abierta.
    from usuarios import tablero
    if tablero.es_administrador(usuario):
        messages.error(request,"No se puede eliminar una cuenta de administracion")
        return redirect("PanelAdmin")

    #Borrar el usuario borra en cascada sus pagos y facturas, y esos registros
    #contables se tienen que conservar. Quien ya pago se bloquea, no se borra.
    #Solo cuentan los pagos de PRODUCCION: los del sandbox de Wompi (y las
    #activaciones manuales hechas en modo prueba) no movieron dinero real, y
    #sin esta distincion no habia forma de limpiar las cuentas de prueba.
    if usuario.pagos.filter(estado__in=("Aprobado","Reembolsado"),ambiente="prod").exists():
        messages.error(request,f"{usuario.username} tiene pagos registrados y sus facturas deben conservarse. "
                               "Bloquea la cuenta en lugar de eliminarla.")
        return redirect("PanelAdmin")

    if request.method=="POST":
        nombre=usuario.username
        usuario.delete()
        messages.success(request,f"El usuario {nombre} se elimino correctamente")
        return redirect("PanelAdmin")

    return render(request,"admin_eliminar_usuario.html",{"usuario": usuario})

@rol_requerido("administrador")
def admin_editar_usuario(request,id):
    usuario=get_object_or_404(User,id=id)
    perfil,creado=Perfil.objects.get_or_create(usuario=usuario)

    if request.method=="POST":
        #Aca tampoco se validaba nada. Se excluye al propio usuario para que
        #no choque consigo mismo al guardar sin cambiar el correo.
        #El nombre si puede quedar vacio (hay cuentas viejas sin el), asi que
        #solo se revisa cuando viene escrito.
        nombre_crudo=(request.POST.get("nombre") or "").strip()
        if nombre_crudo:
            nombre,e_nombre=validar_nombre(nombre_crudo,"El nombre")
        else:
            nombre,e_nombre="",None

        #El correo si es obligatorio: es donde llega la factura.
        correo,e_correo=validar_correo(request.POST.get("correo"),excluir_id=usuario.pk)
        telefono,e_telefono=validar_telefono(request.POST.get("telefono"))

        errores=[e for e in (e_nombre,e_correo,e_telefono) if e]
        if errores:
            for error in errores:
                messages.error(request,error)
            return render(request,"admin_editar_usuario.html",{
                "usuario":usuario,"perfil":perfil,
            })

        usuario.first_name=nombre
        usuario.email=correo
        usuario.save()

        perfil.telefono=telefono
        perfil.save()

        messages.success(request,f"Los datos de {usuario.username} se actualizaron")
        return redirect("PanelAdmin")

    return render(request,"admin_editar_usuario.html",{"usuario": usuario,"perfil": perfil})

#Solo por POST: con un enlace GET, cualquier pagina que visitara el
#administrador podia bloquear cuentas con una simple imagen apuntando aca.
@rol_requerido("administrador")
@require_POST
def admin_estado_usuario(request,id):
    usuario=get_object_or_404(User,id=id)

    if usuario==request.user:
        messages.error(request,"No puedes desactivar tu propia cuenta")
        return redirect("PanelAdmin")

    #Ni bloquear a otro administrador: dejaria el panel sin quien lo maneje
    from usuarios import tablero
    if tablero.es_administrador(usuario):
        messages.error(request,"No se puede bloquear una cuenta de administracion")
        return redirect("PanelAdmin")

    usuario.is_active=not usuario.is_active
    usuario.save()

    estado="activada" if usuario.is_active else "desactivada"
    messages.success(request,f"La cuenta de {usuario.username} fue {estado}")
    return redirect("PanelAdmin")


@rol_requerido("administrador")
def admin_crear_usuario(request):
    if request.method=="POST":
        #Aca no se validaba el correo: por eso quedaron dos cuentas con el
        #mismo. Ahora usa las MISMAS reglas del registro publico, que ya
        #estaban escritas en usuarios/validaciones.py.
        #El correo es OBLIGATORIO: es la direccion a la que se envia la
        #factura cuando el usuario compra un plan. Una cuenta sin correo se
        #queda sin comprobante y sin forma de recuperar la contrasena.
        username,e_usuario=validar_usuario(request.POST.get("username"))
        email,e_correo=validar_correo(request.POST.get("email"))
        password,e_clave=validar_contrasena(request.POST.get("password"))

        errores=[e for e in (e_usuario,e_correo,e_clave) if e]
        if errores:
            for error in errores:
                messages.error(request,error)
            #Se devuelve lo que ya habia escrito para no teclearlo de nuevo
            return render(request,"admin_crear_usuario.html",{"datos":{
                "username":request.POST.get("username",""),
                "email":request.POST.get("email",""),
            }})

        usuario=User.objects.create_user(username=username,email=email,password=password)
        rol=Rol.objects.filter(nombre="usuario").first()
        Perfil.objects.create(usuario=usuario,rol=rol,proveedor="local")

        messages.success(request,f"El usuario {username} se creo correctamente")
        return redirect("PanelAdmin")

    return render(request,"admin_crear_usuario.html")