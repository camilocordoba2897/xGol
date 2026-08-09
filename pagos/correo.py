from django.core.mail import EmailMessage
from django.conf import settings
from pagos.factura import generar_factura_pdf

#Enviaremos la factura en PDF al correo del usuario que realizo el pago
def enviar_factura_correo(pago):
    #Si el usuario no tiene correo no intentamos enviar nada
    if not pago.usuario.email:
        return False

    try:
        asunto=f"Factura {pago.numero_factura} - xGol"
        nombre=pago.usuario.first_name or pago.usuario.username

        #Armaremos el cuerpo del mensaje
        cuerpo=(
            f"Hola {nombre},\n\n"
            f"Gracias por tu compra en xGol. Tu suscripcion al plan {pago.plan} ya esta activa.\n\n"
            f"Adjuntamos tu factura {pago.numero_factura} en formato PDF.\n\n"
            f"Resumen:\n"
            f"- Plan: {pago.plan}\n"
            f"- Total pagado: $ {pago.monto:,.0f} COP\n"
            f"- Referencia: {pago.referencia}\n\n"
            f"Disfruta del acceso completo al analizador de futbol.\n\n"
            f"El equipo de xGol"
        )

        #Crearemos el correo
        mensaje=EmailMessage(
            asunto,
            cuerpo,
            settings.DEFAULT_FROM_EMAIL,
            [pago.usuario.email]
        )

        #Generaremos el PDF y lo adjuntaremos
        pdf=generar_factura_pdf(pago)
        mensaje.attach(f"{pago.numero_factura}.pdf",pdf.getvalue(),"application/pdf")

        #Enviaremos el correo
        mensaje.send()
        return True

    except Exception:
        #Si algo falla, no rompemos el pago: solo devolvemos False
        return False