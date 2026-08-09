from django.contrib.auth.decorators import login_required
from usuarios.decoradores import rol_requerido
from django.shortcuts import render,redirect,get_object_or_404
from django.contrib.auth.models import User
from django.contrib.auth import authenticate,login,logout
from django.contrib import messages
from usuarios.models import Rol,Perfil,Bitacora
from django.contrib.auth import update_session_auth_hash


def registro(request):
    if request.method=="POST":
        username=request.POST["username"]
        email=request.POST["email"]
        password=request.POST["password"]

        if User.objects.filter(username=username).exists():
            messages.error(request,"Ese nombre de usuario ya esta registrado")
            return render(request,"registro.html")

        import re
        if len(password)<8 or len(password)>16:
            messages.error(request,"La contraseña debe tener entre 8 y 16 caracteres")
            return render(request,"registro.html")

        if not re.search(r"[a-z]",password):
            messages.error(request,"La contraseña debe tener al menos una letra minúscula")
            return render(request,"registro.html")

        if not re.search(r"[A-Z]",password):
            messages.error(request,"La contraseña debe tener al menos una letra mayúscula")
            return render(request,"registro.html")

        if not re.search(r"[0-9]",password):
            messages.error(request,"La contraseña debe tener al menos un número")
            return render(request,"registro.html")

        if not re.search(r"[^A-Za-z0-9]",password):
            messages.error(request,"La contraseña debe tener al menos un carácter especial")
            return render(request,"registro.html")

        usuario=User.objects.create_user(username=username,email=email,password=password)

        usuario.first_name=request.POST.get("nombre","")
        usuario.last_name=request.POST.get("apellidos","")
        usuario.save()

        rol=Rol.objects.filter(nombre="usuario").first()
        Perfil.objects.create(
            usuario=usuario,
            rol=rol,
            proveedor="local",
            nombre=request.POST.get("nombre"),
            apellidos=request.POST.get("apellidos"),
            tipo_documento=request.POST.get("tipo_documento"),
            documento=request.POST.get("documento"),
            fecha_nacimiento=request.POST.get("fecha_nacimiento") or None,
            ciudad=request.POST.get("ciudad"),
            pais=request.POST.get("pais"),
            telefono=request.POST.get("telefono")
        )

        messages.success(request,"Cuenta creada correctamente, ya puedes iniciar sesion")
        return redirect("Ingresar")

    return render(request,"registro.html")


def obtener_ip(request):
    adelante=request.META.get("HTTP_X_FORWARDED_FOR")
    if adelante:
        return adelante.split(",")[0]
    return request.META.get("REMOTE_ADDR")

def ingresar(request):
    if request.method=="POST":
        username=request.POST["username"]
        password=request.POST["password"]

        usuario=authenticate(request,username=username,password=password)

        if usuario is not None:
            login(request,usuario)

            Bitacora.objects.create(
                usuario=usuario,
                accion="Inicio de sesion",
                ip=obtener_ip(request),
                agente=request.META.get("HTTP_USER_AGENT")
            )

            perfil=getattr(usuario,"perfil",None)
            if usuario.is_superuser or (perfil is not None and perfil.rol is not None and perfil.rol.nombre=="administrador"):
                return redirect("PanelAdmin")
            return redirect("Inicio")

        messages.error(request,"Usuario o contraseña incorrectos")
        return render(request,"ingresar.html")

    return render(request,"ingresar.html")


def salir(request):
    logout(request)
    return redirect("Ingresar")


@rol_requerido("administrador")
def panel_admin(request):
    from suscripciones.models import Suscripcion
    from django.utils import timezone
    from datetime import timedelta

    perfiles=Perfil.objects.all().order_by("-creado")
    accesos=Bitacora.objects.all().order_by("-creado")[:15]
    total_usuarios=User.objects.count()

    suscripciones=Suscripcion.objects.all()
    activas=0
    por_vencer=[]
    hoy=timezone.now().date()
    limite=hoy+timedelta(days=5)
    for i in suscripciones:
        if i.esta_vigente():
            activas=activas+1
            if i.vencimiento<=limite:
                por_vencer.append(i)

    return render(request,"panel_admin.html",{
        "perfiles": perfiles,
        "accesos": accesos,
        "total_usuarios": total_usuarios,
        "suscripciones_activas": activas,
        "por_vencer": por_vencer
    })

@login_required(login_url="Ingresar")
def editar_perfil(request):
    from allauth.socialaccount.models import SocialAccount
    perfil,creado=Perfil.objects.get_or_create(usuario=request.user)
    es_google=SocialAccount.objects.filter(user=request.user,provider="google").exists()

    if request.method=="POST":
        accion=request.POST.get("accion")

        if accion=="datos":
            request.user.first_name=request.POST.get("nombre","")

            if not es_google:
                nuevo_usuario=request.POST.get("username","").strip()
                if nuevo_usuario and nuevo_usuario!=request.user.username:
                    if User.objects.filter(username=nuevo_usuario).exclude(pk=request.user.pk).exists():
                        messages.error(request,"Ese nombre de usuario ya esta en uso")
                        return redirect("EditarPerfil")
                    request.user.username=nuevo_usuario

                request.user.email=request.POST.get("correo","")

            request.user.save()

            perfil.telefono=request.POST.get("telefono")
            if request.FILES.get("avatar"):
                perfil.avatar=request.FILES["avatar"]
            perfil.save()

            messages.success(request,"Tus datos se actualizaron correctamente")
            return redirect("EditarPerfil")

        if accion=="clave":
            import re

            actual=request.POST.get("clave_actual")
            nueva=request.POST.get("clave_nueva")
            confirmar=request.POST.get("clave_confirmar")

            if not request.user.check_password(actual):
                messages.error(request,"La contraseña actual no es correcta")
                return redirect("EditarPerfil")

            if nueva!=confirmar:
                messages.error(request,"Las contraseñas nuevas no coinciden")
                return redirect("EditarPerfil")

            if len(nueva)<8 or len(nueva)>16:
                messages.error(request,"La contraseña debe tener entre 8 y 16 caracteres")
                return redirect("EditarPerfil")

            if not re.search(r"[a-z]",nueva):
                messages.error(request,"La contraseña debe tener al menos una letra minúscula")
                return redirect("EditarPerfil")

            if not re.search(r"[A-Z]",nueva):
                messages.error(request,"La contraseña debe tener al menos una letra mayúscula")
                return redirect("EditarPerfil")

            if not re.search(r"[0-9]",nueva):
                messages.error(request,"La contraseña debe tener al menos un número")
                return redirect("EditarPerfil")

            if not re.search(r"[^A-Za-z0-9]",nueva):
                messages.error(request,"La contraseña debe tener al menos un carácter especial")
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
        usuario.first_name=request.POST.get("nombre","")
        usuario.email=request.POST.get("correo","")
        usuario.save()

        perfil.telefono=request.POST.get("telefono")
        perfil.save()

        messages.success(request,f"Los datos de {usuario.username} se actualizaron")
        return redirect("PanelAdmin")

    return render(request,"admin_editar_usuario.html",{"usuario": usuario,"perfil": perfil})

@rol_requerido("administrador")
def admin_estado_usuario(request,id):
    usuario=get_object_or_404(User,id=id)

    if usuario==request.user:
        messages.error(request,"No puedes desactivar tu propia cuenta")
        return redirect("PanelAdmin")

    usuario.is_active=not usuario.is_active
    usuario.save()

    estado="activada" if usuario.is_active else "desactivada"
    messages.success(request,f"La cuenta de {usuario.username} fue {estado}")
    return redirect("PanelAdmin")


@rol_requerido("administrador")
def admin_crear_usuario(request):
    if request.method=="POST":
        username=request.POST.get("username")
        email=request.POST.get("email")
        password=request.POST.get("password")

        if User.objects.filter(username=username).exists():
            messages.error(request,"Ese nombre de usuario ya esta registrado")
            return redirect("AdminCrearUsuario")

        usuario=User.objects.create_user(username=username,email=email,password=password)
        rol=Rol.objects.filter(nombre="usuario").first()
        Perfil.objects.create(usuario=usuario,rol=rol,proveedor="local")

        messages.success(request,f"El usuario {username} se creo correctamente")
        return redirect("PanelAdmin")

    return render(request,"admin_crear_usuario.html")

