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


def validar_usuario(valor):
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
    if User.objects.filter(username__iexact=limpio).exists():
        return valor, "Ese nombre de usuario ya está en uso, elige otro."

    return limpio, None


def validar_correo(valor):
    limpio = str(valor or "").strip().lower()

    if not limpio:
        return valor, "El correo no puede quedar vacío."

    if len(limpio) > 254:
        return valor, "El correo es demasiado largo."

    if not PATRON_CORREO.match(limpio):
        return valor, "Escribe un correo válido, por ejemplo: nombre@correo.com"

    if User.objects.filter(email__iexact=limpio).exists():
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

    return limpios, errores