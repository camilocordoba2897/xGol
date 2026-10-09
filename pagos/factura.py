from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.pdfgen import canvas
from io import BytesIO

from django.utils.formats import date_format
from django.utils.translation import gettext, gettext_noop

from pagos.templatetags.formato import pesos

#Definiremos los datos de la empresa en un solo lugar para cambiarlos facil despues
EMPRESA = {
  "nombre": "xGol",
  "razon_social": "xGol Análisis Deportivo S.A.S.",
  "nit": "901.456.789-0",
  "correo": "soporte@xgol.com",
  "telefono": "+57 300 123 4567",
  "ciudad": gettext_noop("Medellín, Colombia"),
  "web": "www.xgol.com"
}

def _fecha(valor):
    #Fecha corta al estilo del idioma activo (dd/mm/aaaa, mm/dd/aaaa...)
    return date_format(valor,"SHORT_DATE_FORMAT")


#Generaremos el PDF de la factura y lo devolveremos como bytes en memoria.
#Sale en el idioma activo: el de la visita al descargarla, o el que la
#persona eligio la ultima vez cuando se envia por correo (pagos/correo.py).
def generar_factura_pdf(pago):
    buffer=BytesIO()
    c=canvas.Canvas(buffer,pagesize=A4)
    ancho,alto=A4

    #Definiremos los colores de la marca
    azul=colors.HexColor("#0f1f44")
    azul_claro=colors.HexColor("#16294f")
    lima=colors.HexColor("#22c55e")
    gris=colors.HexColor("#64748b")
    gris_claro=colors.HexColor("#94a3b8")
    texto=colors.HexColor("#1e293b")
    linea_color=colors.HexColor("#e2e8f0")

    # ====================================================
    # ENCABEZADO — franja azul con logo y datos de empresa
    # ====================================================
    c.setFillColor(azul)
    c.rect(0,alto-4.2*cm,ancho,4.2*cm,fill=1,stroke=0)

    #Logo xGol: la x en lima y Gol en blanco como en la aplicacion
    c.setFont("Helvetica-Bold",26)
    c.setFillColor(lima)
    c.drawString(2*cm,alto-2*cm,"x")
    ancho_x=c.stringWidth("x","Helvetica-Bold",26)
    c.setFillColor(colors.white)
    c.drawString(2*cm+ancho_x,alto-2*cm,"Gol")
    
    #Datos de la empresa bajo el logo
    c.setFillColor(gris_claro)
    c.setFont("Helvetica",8)
    c.drawString(2*cm,alto-2.6*cm,EMPRESA["razon_social"])
    c.drawString(2*cm,alto-3*cm,f"NIT: {EMPRESA['nit']}")
    c.drawString(2*cm,alto-3.4*cm,gettext(EMPRESA["ciudad"]))

    #Titulo FACTURA y numero a la derecha
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold",18)
    c.drawRightString(ancho-2*cm,alto-1.9*cm,gettext("FACTURA"))
    c.setFillColor(lima)
    c.setFont("Helvetica-Bold",12)
    c.drawRightString(ancho-2*cm,alto-2.5*cm,pago.numero_factura or pago.referencia)
    c.setFillColor(gris_claro)
    c.setFont("Helvetica",8)
    c.drawRightString(ancho-2*cm,alto-3*cm,gettext("Emitida: %(fecha)s") % {"fecha":_fecha(pago.creado)})
    c.drawRightString(ancho-2*cm,alto-3.4*cm,f"{EMPRESA['correo']} · {EMPRESA['telefono']}")

    # ====================================================
    # DATOS DEL CLIENTE Y DE LA SUSCRIPCIÓN (dos columnas)
    # ====================================================
    y=alto-6.5*cm

    #Columna izquierda: cliente
    c.setFillColor(texto)
    c.setFont("Helvetica-Bold",11)
    c.drawString(2*cm,y,gettext("FACTURAR A"))
    c.setFont("Helvetica",10)
    c.setFillColor(gris)
    nombre=f"{pago.usuario.first_name} {pago.usuario.last_name}".strip()
    if not nombre:
        nombre=pago.usuario.username
    c.drawString(2*cm,y-0.65*cm,nombre)
    c.drawString(2*cm,y-1.15*cm,gettext("Usuario: %(usuario)s") % {"usuario":pago.usuario.username})
    c.drawString(2*cm,y-1.65*cm,pago.usuario.email)

    #Columna derecha: datos del pago
    c.setFillColor(texto)
    c.setFont("Helvetica-Bold",11)
    c.drawString(11*cm,y,gettext("DETALLES DEL PAGO"))
    c.setFont("Helvetica",10)
    c.setFillColor(gris)
    c.drawString(11*cm,y-0.65*cm,gettext("Método: %(metodo)s") % {"metodo":gettext(pago.metodo) if pago.metodo else "—"})
    c.drawString(11*cm,y-1.15*cm,gettext("Estado: %(estado)s") % {"estado":pago.get_estado_display()})
    c.drawString(11*cm,y-1.65*cm,gettext("Ref: %(referencia)s") % {"referencia":pago.referencia})

    # ====================================================
    # TABLA DE LA SUSCRIPCIÓN
    # ====================================================
    y=y-2.9*cm

    #Encabezado de la tabla (franja gris)
    c.setFillColor(azul_claro)
    c.rect(2*cm,y-0.2*cm,ancho-4*cm,0.9*cm,fill=1,stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold",9)
    c.drawString(2.4*cm,y+0.1*cm,gettext("DESCRIPCIÓN"))
    c.drawRightString(ancho-2.4*cm,y+0.1*cm,gettext("VALOR"))

    #Fila del plan
    y=y-1.2*cm
    c.setFillColor(texto)
    c.setFont("Helvetica-Bold",11)
    c.drawString(2.4*cm,y,gettext("Suscripción %(nombre)s") % {"nombre":gettext(pago.plan)})
    c.setFont("Helvetica",9)
    c.setFillColor(gris)
    #La vigencia que compro ESTE pago, guardada al aplicarlo. Antes salia la
    #de la suscripcion actual: una factura vieja mostraba fechas que no eran
    #suyas, y si la suscripcion no tenia fecha la descarga se caia con 500.
    if pago.vigencia_inicio and pago.vigencia_fin:
        c.drawString(2.4*cm,y-0.5*cm,gettext("Vigencia: %(desde)s - %(hasta)s")
                     % {"desde":_fecha(pago.vigencia_inicio),"hasta":_fecha(pago.vigencia_fin)})
    c.setFillColor(texto)
    c.setFont("Helvetica",11)
    c.drawRightString(ancho-2.4*cm,y,f"$ {pesos(pago.subtotal)}")

    #Linea separadora
    y=y-1*cm
    c.setStrokeColor(linea_color)
    c.line(2*cm,y,ancho-2*cm,y)

    # ====================================================
    # TOTALES (alineados a la derecha)
    # ====================================================
    y=y-0.8*cm
    x_etiqueta=12*cm
    x_valor=ancho-2.4*cm

    c.setFont("Helvetica",10)
    c.setFillColor(gris)
    c.drawString(x_etiqueta,y,gettext("Subtotal"))
    c.setFillColor(texto)
    c.drawRightString(x_valor,y,f"$ {pesos(pago.subtotal)}")

    y=y-0.6*cm
    c.setFillColor(gris)
    c.drawString(x_etiqueta,y,gettext("IVA (19%)"))
    c.setFillColor(texto)
    c.drawRightString(x_valor,y,f"$ {pesos(pago.iva)}")

    #Recuadro del total
    y=y-1.1*cm
    c.setFillColor(azul)
    c.rect(11.5*cm,y-0.35*cm,ancho-2*cm-11.5*cm,1.1*cm,fill=1,stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold",11)
    c.drawString(12*cm,y-0.05*cm,gettext("TOTAL"))
    c.setFillColor(lima)
    c.setFont("Helvetica-Bold",14)
    c.drawRightString(x_valor,y-0.08*cm,f"$ {pesos(pago.monto)}")

    #Nota COP
    c.setFillColor(gris_claro)
    c.setFont("Helvetica",8)
    c.drawRightString(x_valor,y-0.9*cm,gettext("Valores en pesos colombianos (COP)"))

    
    # ====================================================
    # PIE DE PÁGINA
    # ====================================================
    c.setStrokeColor(linea_color)
    c.line(2*cm,2.4*cm,ancho-2*cm,2.4*cm)
    c.setFillColor(gris_claro)
    c.setFont("Helvetica",8)
    c.drawCentredString(ancho/2,1.9*cm,f"{EMPRESA['razon_social']} · NIT {EMPRESA['nit']} · {EMPRESA['correo']} · {EMPRESA['telefono']}")
    c.drawCentredString(ancho/2,1.5*cm,gettext("%(web)s · Documento generado automáticamente · Factura de demostración")
                        % {"web":EMPRESA["web"]})

    c.showPage()
    c.save()
    buffer.seek(0)
    return buffer