from allauth.account.adapter import DefaultAccountAdapter
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.contrib import messages
from django.shortcuts import redirect

try:
    from allauth.core.exceptions import ImmediateHttpResponse
except ImportError:                      #allauth antiguo
    from allauth.exceptions import ImmediateHttpResponse


#Anula unicamente el mensaje de bienvenida al iniciar sesion (Google/allauth). Todo lo demas de allauth sigue igual.
class AdaptadorCuenta(DefaultAccountAdapter):

    def add_message(self,request,level,message_template=None,message_context=None,extra_tags="",message=None):
        if message_template=="account/messages/logged_in.txt":
            return
        super().add_message(request,level,message_template,message_context,extra_tags,message)


# ============================================================
#  ENTRADA CON GOOGLE: NUNCA A UNA CUENTA ADMINISTRATIVA
#
#  settings.py tiene encendido SOCIALACCOUNT_EMAIL_AUTHENTICATION, que hace
#  algo muy comodo y muy peligroso a la vez: cuando alguien entra con Google,
#  allauth busca una cuenta local con ESE MISMO CORREO y lo mete dentro de
#  ella. Para un usuario normal esta bien: se registro con correo y clave, un
#  dia entra con Google y cae en su propia cuenta de siempre.
#
#  El problema es cuando la cuenta que coincide es la del administrador. Ahi
#  ese comportamiento se convierte en una puerta de atras: quien controle ese
#  correo de Google entra al panel de administracion sin saber la clave. Y sin
#  darse cuenta, porque entra "con su Gmail de siempre".
#
#  Asi que la cuenta administrativa se abre SOLO con usuario y contrasena.
#  Es un clic mas para una sola persona, a cambio de que el panel no dependa
#  de quien tenga acceso a una cuenta de correo.
# ============================================================
class AdaptadorSocial(DefaultSocialAccountAdapter):

    def pre_social_login(self,request,sociallogin):
        usuario=getattr(sociallogin,"user",None)
        #Solo interesa cuando allauth ya emparejo con una cuenta que EXISTE.
        #En un registro nuevo todavia no hay pk y no hay nada que proteger.
        if usuario is not None and usuario.pk and self._es_administrativa(usuario):
            messages.error(request,
                "Esta cuenta es administrativa y no se puede abrir con Google. "
                "Entra con tu usuario y contrasena.")
            raise ImmediateHttpResponse(redirect("Ingresar"))
        return super().pre_social_login(request,sociallogin)

    @staticmethod
    def _es_administrativa(usuario):
        if usuario.is_superuser or usuario.is_staff:
            return True
        #Tambien el rol propio del proyecto, que no siempre va con is_staff.
        perfil=getattr(usuario,"perfil",None)
        rol=getattr(perfil,"rol",None)
        return getattr(rol,"nombre","")=="administrador"