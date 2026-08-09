from allauth.account.adapter import DefaultAccountAdapter

#Anula unicamente el mensaje de bienvenida al iniciar sesion (Google/allauth). Todo lo demas de allauth sigue igual.
class AdaptadorCuenta(DefaultAccountAdapter):

    def add_message(self,request,level,message_template=None,message_context=None,extra_tags="",message=None):
        if message_template=="account/messages/logged_in.txt":
            return
        super().add_message(request,level,message_template,message_context,extra_tags,message)