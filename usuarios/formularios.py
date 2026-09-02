#Formularios de la app usuarios.
#
#Django trae su propio SetPasswordForm para el cambio de contraseña por
#correo, pero ese solo aplica los AUTH_PASSWORD_VALIDATORS de settings.py,
#que NO son las reglas de xGol (8 a 16, mayuscula, minuscula, numero y
#caracter especial). Sin esto, alguien podria registrarse con una clave
#fuerte y luego cambiarla por una debil desde el enlace de recuperacion.
#
#Aqui se reutiliza validar_contrasena() para que la regla viva en UN solo
#sitio: si mañana cambia, cambia en registro y en recuperacion a la vez.
from django.contrib.auth.forms import SetPasswordForm
from django import forms

from usuarios.validaciones import validar_contrasena


class FormularioNuevaContrasena(SetPasswordForm):
    def clean_new_password1(self):
        clave = self.cleaned_data.get("new_password1")
        _, error = validar_contrasena(clave)
        if error:
            raise forms.ValidationError(error)
        return clave