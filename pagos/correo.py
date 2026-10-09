from django.core.mail import EmailMessage
from django.conf import settings
from django.utils import translation
from django.utils.translation import gettext
from pagos.factura import generar_factura_pdf
from pagos.templatetags.formato import pesos
from xgol.idioma import idioma_de_usuario

#Enviaremos la factura en PDF al correo del usuario que realizo el pago.
#Va en el idioma que la persona eligio la ultima vez en el sitio (correo y
#PDF): este envio casi nunca ocurre durante su visita, sino cuando Wompi
#avisa que el pago se aprobo.
def enviar_factura_correo(pago):
    #Si el usuario no tiene correo no intentamos enviar nada
    if not pago.usuario.email:
        return False

    try:
        with translation.override(idioma_de_usuario(pago.usuario)):
            asunto=gettext("Factura %(numero)s - xGol") % {"numero":pago.numero_factura}
            nombre=pago.usuario.first_name or pago.usuario.username
            plan=gettext(pago.plan)

            #Armaremos el cuerpo del mensaje
            cuerpo=gettext(
                "Hola %(nombre)s,\n\n"
                "Gracias por tu compra en xGol. Tu suscripción al plan %(plan)s ya está activa.\n\n"
                "Adjuntamos tu factura %(numero)s en formato PDF.\n\n"
                "Resumen:\n"
                "- Plan: %(plan)s\n"
                "- Total pagado: $ %(total)s COP\n"
                "- Referencia: %(referencia)s\n\n"
                "Disfruta del acceso completo al analizador de fútbol.\n\n"
                "El equipo de xGol"
            ) % {"nombre":nombre,"plan":plan,"numero":pago.numero_factura,
                 "total":pesos(pago.monto),"referencia":pago.referencia}

            #Crearemos el correo
            mensaje=EmailMessage(
                asunto,
                cuerpo,
                settings.DEFAULT_FROM_EMAIL,
                [pago.usuario.email]
            )

            #Generaremos el PDF (en el mismo idioma) y lo adjuntaremos
            pdf=generar_factura_pdf(pago)
            mensaje.attach(f"{pago.numero_factura}.pdf",pdf.getvalue(),"application/pdf")

        #Enviaremos el correo
        mensaje.send()
        return True

    except Exception:
        #Si algo falla, no rompemos el pago: solo devolvemos False
        return False
