#QUIEN ES ADMINISTRADOR — una sola regla para todo el proyecto.
#
#Antes cada parte lo decidia a su manera: el panel contaba tambien a is_staff,
#los decoradores no, y el home no lo miraba. Por eso el administrador acababa
#en la pagina de planes al tocar "Pronostico completo". Aqui se decide una vez
#y lo usan el context processor, los decoradores, las vistas de planes y pago,
#y el tablero del panel.
#
#Alguien es administrador si:
#   - es superusuario, o
#   - es staff (entra al admin de Django), o
#   - su perfil tiene el rol "administrador".
ROL_ADMIN = "administrador"


def es_administrador(usuario):
    if usuario is None or not getattr(usuario, "is_authenticated", False):
        return False
    if getattr(usuario, "is_superuser", False) or getattr(usuario, "is_staff", False):
        return True
    perfil = getattr(usuario, "perfil", None)
    rol = getattr(perfil, "rol", None) if perfil is not None else None
    return rol is not None and (rol.nombre or "").strip().lower() == ROL_ADMIN


def tiene_acceso(usuario):
    #Puede ver el pronostico completo: administrador o suscripcion vigente
    if es_administrador(usuario):
        return True
    if usuario is None or not getattr(usuario, "is_authenticated", False):
        return False
    from suscripciones.models import Suscripcion
    suscripcion = Suscripcion.objects.filter(usuario=usuario).first()
    return suscripcion is not None and suscripcion.esta_vigente()
