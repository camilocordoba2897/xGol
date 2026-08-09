from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.pdfgen import canvas
from io import BytesIO

#Definiremos los datos de la empresa en un solo lugar para cambiarlos facil despues
EMPRESA = {
  "nombre": "xGol",
  "razon_social": "xGol Análisis Deportivo S.A.S.",
  "nit": "901.456.789-0",
  "correo": "soporte@xgol.com",
  "telefono": "+57 300 123 4567",
  "ciudad": "Medellín, Colombia",
  "web": "www.xgol.com"
}

#Generaremos el PDF de la factura y lo devolveremos como bytes en memoria
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
    c.drawString(2*cm,alto-3.4*cm,f"{EMPRESA['ciudad']}")

    #Titulo FACTURA y numero a la derecha
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold",18)
    c.drawRightString(ancho-2*cm,alto-1.9*cm,"FACTURA")
    c.setFillColor(lima)
    c.setFont("Helvetica-Bold",12)
    c.drawRightString(ancho-2*cm,alto-2.5*cm,pago.numero_factura)
    c.setFillColor(gris_claro)
    c.setFont("Helvetica",8)
    c.drawRightString(ancho-2*cm,alto-3*cm,f"Emitida: {pago.creado.strftime('%d/%m/%Y')}")
    c.drawRightString(ancho-2*cm,alto-3.4*cm,f"{EMPRESA['correo']} · {EMPRESA['telefono']}")

    # ====================================================
    # DATOS DEL CLIENTE Y DE LA SUSCRIPCIÓN (dos columnas)
    # ====================================================
    y=alto-6.5*cm

    #Columna izquierda: cliente
    c.setFillColor(texto)
    c.setFont("Helvetica-Bold",11)
    c.drawString(2*cm,y,"FACTURAR A")
    c.setFont("Helvetica",10)
    c.setFillColor(gris)
    nombre=f"{pago.usuario.first_name} {pago.usuario.last_name}".strip()
    if not nombre:
        nombre=pago.usuario.username
    c.drawString(2*cm,y-0.65*cm,nombre)
    c.drawString(2*cm,y-1.15*cm,f"Usuario: {pago.usuario.username}")
    c.drawString(2*cm,y-1.65*cm,pago.usuario.email)

    #Columna derecha: datos del pago
    c.setFillColor(texto)
    c.setFont("Helvetica-Bold",11)
    c.drawString(11*cm,y,"DETALLES DEL PAGO")
    c.setFont("Helvetica",10)
    c.setFillColor(gris)
    c.drawString(11*cm,y-0.65*cm,f"Método: {pago.metodo}")
    c.drawString(11*cm,y-1.15*cm,f"Estado: {pago.estado}")
    c.drawString(11*cm,y-1.65*cm,f"Ref: {pago.referencia}")

    # ====================================================
    # TABLA DE LA SUSCRIPCIÓN
    # ====================================================
    y=y-2.9*cm

    #Encabezado de la tabla (franja gris)
    c.setFillColor(azul_claro)
    c.rect(2*cm,y-0.2*cm,ancho-4*cm,0.9*cm,fill=1,stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold",9)
    c.drawString(2.4*cm,y+0.1*cm,"DESCRIPCIÓN")
    c.drawRightString(ancho-2.4*cm,y+0.1*cm,"VALOR")

    #Fila del plan
    y=y-1.2*cm
    c.setFillColor(texto)
    c.setFont("Helvetica-Bold",11)
    c.drawString(2.4*cm,y,f"Suscripción {pago.plan}")
    c.setFont("Helvetica",9)
    c.setFillColor(gris)
    c.drawString(2.4*cm,y-0.5*cm,f"Vigencia: {pago.usuario.suscripcion.inicio.strftime('%d/%m/%Y')} - {pago.usuario.suscripcion.vencimiento.strftime('%d/%m/%Y')}")
    c.setFillColor(texto)
    c.setFont("Helvetica",11)
    c.drawRightString(ancho-2.4*cm,y,f"$ {pago.subtotal:,.0f}")

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
    c.drawString(x_etiqueta,y,"Subtotal")
    c.setFillColor(texto)
    c.drawRightString(x_valor,y,f"$ {pago.subtotal:,.0f}")

    y=y-0.6*cm
    c.setFillColor(gris)
    c.drawString(x_etiqueta,y,"IVA (19%)")
    c.setFillColor(texto)
    c.drawRightString(x_valor,y,f"$ {pago.iva:,.0f}")

    #Recuadro del total
    y=y-1.1*cm
    c.setFillColor(azul)
    c.rect(11.5*cm,y-0.35*cm,ancho-2*cm-11.5*cm,1.1*cm,fill=1,stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold",11)
    c.drawString(12*cm,y-0.05*cm,"TOTAL")
    c.setFillColor(lima)
    c.setFont("Helvetica-Bold",14)
    c.drawRightString(x_valor,y-0.08*cm,f"$ {pago.monto:,.0f}")

    #Nota COP
    c.setFillColor(gris_claro)
    c.setFont("Helvetica",8)
    c.drawRightString(x_valor,y-0.9*cm,"Valores en pesos colombianos (COP)")

    
    # ====================================================
    # PIE DE PÁGINA
    # ====================================================
    c.setStrokeColor(linea_color)
    c.line(2*cm,2.4*cm,ancho-2*cm,2.4*cm)
    c.setFillColor(gris_claro)
    c.setFont("Helvetica",8)
    c.drawCentredString(ancho/2,1.9*cm,f"{EMPRESA['razon_social']} · NIT {EMPRESA['nit']} · {EMPRESA['correo']} · {EMPRESA['telefono']}")
    c.drawCentredString(ancho/2,1.5*cm,f"{EMPRESA['web']} · Documento generado automáticamente · Factura de demostración")

    c.showPage()
    c.save()
    buffer.seek(0)
    return buffer