#Validaciones del formulario de registro.
#
#Van en su propio modulo por dos motivos: la vista queda legible y estas
#reglas se pueden reutilizar tal cual en el alta de usuarios del panel de
#administracion, que hoy no valida nada.
#
#Cada funcion devuelve el valor limpio y un mensaje de error:
#   (valor_limpio, None)      -> valido
#   (valor_original, "texto") -> invalido, "texto" es lo que ve el usuario
#
#IMPORTANTE: estas comprobaciones son de SERVIDOR. Los atributos pattern
#del HTML son solo comodidad: cualquiera puede saltarselos desde la consola
#del navegador o enviando el formulario con curl, asi que la validacion
#real tiene que estar aqui.
import re
from datetime import date, datetime

import unicodedata
from django.contrib.auth.models import User

#Letras con tildes y ñ incluidas. Se permiten espacios, guion y apostrofo
#porque hay apellidos reales que los llevan: "Ana María", "Del Río",
#"O'Connor", "Sánchez-Prieto".
LETRAS = "A-Za-zÁÉÍÓÚÜÑáéíóúüñ"
PATRON_NOMBRE = re.compile(r"^[" + LETRAS + r"]+(?:[ '\-][" + LETRAS + r"]+)*$")
PATRON_USUARIO = re.compile(r"^[A-Za-z0-9]+$")
PATRON_CORREO = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")

NOMBRE_MIN = 2
NOMBRE_MAX = 40
USUARIO_MIN = 3
USUARIO_MAX = 20


def _tiene_repeticion_absurda(texto):
    #Tres letras iguales seguidas no aparecen en ningun nombre real en
    #español. Es lo que separa "Ana" de "aaaa" sin bloquear nombres validos.
    return re.search(r"(.)\1\1", texto.lower()) is not None


def validar_nombre(valor, etiqueta="El nombre"):
    limpio = " ".join(str(valor or "").split())

    if not limpio:
        return valor, f"{etiqueta} no puede quedar vacío."

    if len(limpio) < NOMBRE_MIN:
        return valor, f"{etiqueta} debe tener al menos {NOMBRE_MIN} letras."

    if len(limpio) > NOMBRE_MAX:
        return valor, f"{etiqueta} no puede pasar de {NOMBRE_MAX} caracteres."

    if not PATRON_NOMBRE.match(limpio):
        return valor, (
            f"{etiqueta} solo puede tener letras. "
            "No se admiten números ni símbolos como %, #, $ o ()."
        )

    if _tiene_repeticion_absurda(limpio):
        return valor, f"{etiqueta} no parece un nombre válido."

    #Se guarda con mayuscula inicial en cada parte. No sirve capitalize()
    #a secas: convertiria "O'Connor" en "O'connor" y "Sánchez-Prieto" en
    #"Sánchez-prieto", porque baja todo lo que va tras la primera letra.
    return _capitalizar(limpio), None


def _capitalizar(texto):
    #Mayuscula despues del inicio y despues de espacio, guion o apostrofo
    salida = []
    nueva_palabra = True
    for caracter in texto.lower():
        if nueva_palabra and caracter.isalpha():
            salida.append(caracter.upper())
            nueva_palabra = False
        else:
            salida.append(caracter)
            if caracter in " -'":
                nueva_palabra = True
    return "".join(salida)


def validar_usuario(valor, excluir_id=None):
    #excluir_id se usa al EDITAR: sin el, el usuario chocaria consigo mismo
    #al guardar sin cambiar el nombre.
    limpio = str(valor or "").strip()

    if not limpio:
        return valor, "El nombre de usuario no puede quedar vacío."

    if len(limpio) < USUARIO_MIN:
        return valor, f"El nombre de usuario debe tener al menos {USUARIO_MIN} caracteres."

    if len(limpio) > USUARIO_MAX:
        return valor, f"El nombre de usuario no puede pasar de {USUARIO_MAX} caracteres."

    if not PATRON_USUARIO.match(limpio):
        return valor, (
            "El nombre de usuario solo puede tener letras y números, "
            "sin espacios ni símbolos."
        )

    if not re.search(r"[A-Za-z]", limpio):
        return valor, "El nombre de usuario debe tener al menos una letra."

    #iexact: si existe "Juan" no se deja crear "juan". Serian dos cuentas
    #distintas para Django, pero el usuario las leeria como la misma y no
    #sabria con cual entra.
    repetidos = User.objects.filter(username__iexact=limpio)
    if excluir_id is not None:
        repetidos = repetidos.exclude(pk=excluir_id)
    if repetidos.exists():
        return valor, "Ese nombre de usuario ya está en uso, elige otro."

    return limpio, None


def validar_correo(valor, excluir_id=None):
    #excluir_id se usa al EDITAR, igual que en validar_usuario.
    limpio = str(valor or "").strip().lower()

    if not limpio:
        return valor, "El correo no puede quedar vacío."

    if len(limpio) > 254:
        return valor, "El correo es demasiado largo."

    if not PATRON_CORREO.match(limpio):
        return valor, "Escribe un correo válido, por ejemplo: nombre@correo.com"

    #iexact porque Juan@Correo.com y juan@correo.com son el MISMO buzon:
    #si se dejan las dos, el usuario no sabria con cual entra ni a cual le
    #llega el correo de recuperar contrasena.
    repetidos = User.objects.filter(email__iexact=limpio)
    if excluir_id is not None:
        repetidos = repetidos.exclude(pk=excluir_id)
    if repetidos.exists():
        return valor, "Ese correo ya tiene una cuenta registrada."

    return limpio, None


def validar_contrasena(valor):
    clave = str(valor or "")

    if len(clave) < 8 or len(clave) > 16:
        return clave, "La contraseña debe tener entre 8 y 16 caracteres."

    if not re.search(r"[a-z]", clave):
        return clave, "La contraseña debe tener al menos una letra minúscula."

    if not re.search(r"[A-Z]", clave):
        return clave, "La contraseña debe tener al menos una letra mayúscula."

    if not re.search(r"[0-9]", clave):
        return clave, "La contraseña debe tener al menos un número."

    if not re.search(r"[^A-Za-z0-9]", clave):
        return clave, "La contraseña debe tener al menos un carácter especial."

    return clave, None


# ============================================================
#  CEDULA
# ============================================================
#  La cedula colombiana NO trae digito de verificacion (eso lo tiene el
#  NIT de las empresas, no la cedula de una persona). Por eso no existe
#  ninguna cuenta matematica que diga si un numero es real: la unica forma
#  de confirmarlo de verdad seria consultar a la Registraduria.
#
#  Lo que si se puede hacer, y es lo que hace esto, es descartar lo que
#  seguro NO es una cedula: letras, simbolos, largos imposibles, ceros al
#  inicio y numeros de relleno (1111111). Ojo: esto valida el FORMATO, no
#  confirma que la cedula exista.
DOCUMENTO_MIN = 6
DOCUMENTO_MAX = 10


def validar_documento(valor, excluir_id=None):
    #Se quitan puntos, espacios y guiones: mucha gente la escribe 1.234.567.890
    limpio = re.sub(r"[.\s\-]", "", str(valor or "").strip())

    if not limpio:
        return valor, "El numero de cedula no puede quedar vacio."

    if not limpio.isdigit():
        return valor, "La cedula solo puede tener numeros, sin letras ni simbolos."

    if limpio.startswith("0"):
        return valor, "El numero de cedula no puede empezar por cero."

    if len(limpio) < DOCUMENTO_MIN:
        return valor, "La cedula debe tener al menos %d digitos." % DOCUMENTO_MIN

    if len(limpio) > DOCUMENTO_MAX:
        return valor, "La cedula no puede pasar de %d digitos." % DOCUMENTO_MAX

    #Solo se descarta el relleno evidente: 1111111, 2222222. No se
    #descartan secuencias como 1234567 porque ESE numero si le puede haber
    #tocado a alguien de verdad, y bloquear a una persona real es peor que
    #dejar pasar un numero inventado (que igual se puede inventar otro).
    if len(set(limpio)) == 1:
        return valor, "Ese numero de cedula no es valido."

    #Se guarda solo el numero, sin puntos, para que no queden dos formas
    #distintas del mismo documento en la base.
    from usuarios.models import Perfil
    repetidos = Perfil.objects.filter(documento=limpio)
    if excluir_id is not None:
        repetidos = repetidos.exclude(usuario_id=excluir_id)
    if repetidos.exists():
        return valor, "Ya hay una cuenta registrada con esa cedula."

    return limpio, None


# ============================================================
#  FECHA DE NACIMIENTO — solo mayores de edad
# ============================================================
EDAD_MINIMA = 18
EDAD_MAXIMA = 110


def calcular_edad(fecha, hoy=None):
    #Los anos cumplidos de verdad: si todavia no llego el cumpleanos de
    #este ano, se resta uno. Sin esto, alguien que cumple 18 en diciembre
    #podria entrar desde enero.
    if hoy is None:
        hoy = date.today()
    anos = hoy.year - fecha.year
    if (hoy.month, hoy.day) < (fecha.month, fecha.day):
        anos -= 1
    return anos


def validar_fecha_nacimiento(valor, hoy=None):
    crudo = str(valor or "").strip()

    if not crudo:
        return valor, "La fecha de nacimiento no puede quedar vacia."

    #El input type=date manda AAAA-MM-DD. Se aceptan tambien las formas
    #que la gente escribe a mano cuando teclea la fecha.
    fecha = None
    for formato in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            fecha = datetime.strptime(crudo, formato).date()
            break
        except ValueError:
            continue

    if fecha is None:
        return valor, "Escribe una fecha de nacimiento valida."

    if hoy is None:
        hoy = date.today()

    if fecha > hoy:
        return valor, "La fecha de nacimiento no puede ser futura."

    edad = calcular_edad(fecha, hoy)

    if edad > EDAD_MAXIMA:
        return valor, "Revisa la fecha de nacimiento, no parece correcta."

    if edad < EDAD_MINIMA:
        return valor, ("Debes ser mayor de %d anos para crear una cuenta en xGol." % EDAD_MINIMA)

    #Se devuelve como objeto date: asi el modelo lo guarda sin depender
    #del formato con que venga escrito.
    return fecha, None


def validar_registro(datos):
    #Valida el formulario completo. Devuelve (limpios, errores).
    #Se revisa TODO y no se corta en el primer fallo: si el usuario se
    #equivoco en tres campos, prefiere verlos los tres de una vez.
    limpios = {}
    errores = []

    limpios["nombre"], error = validar_nombre(datos.get("nombre"), "El nombre")
    if error:
        errores.append(error)

    limpios["apellidos"], error = validar_nombre(datos.get("apellidos"), "Los apellidos")
    if error:
        errores.append(error)

    limpios["username"], error = validar_usuario(datos.get("username"))
    if error:
        errores.append(error)

    limpios["email"], error = validar_correo(datos.get("email"))
    if error:
        errores.append(error)

    limpios["password"], error = validar_contrasena(datos.get("password"))
    if error:
        errores.append(error)

    limpios["documento"], error = validar_documento(datos.get("documento"))
    if error:
        errores.append(error)

    limpios["fecha_nacimiento"], error = validar_fecha_nacimiento(datos.get("fecha_nacimiento"))
    if error:
        errores.append(error)

    return limpios, errores