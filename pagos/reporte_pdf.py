#Reporte PDF del historial de transacciones.
#
#Reusa la identidad visual de pagos/factura.py (mismos colores, mismo logo,
#mismo pie) para que los dos documentos que salen de xGol se vean de la
#misma familia. Se dibuja con reportlab, que ya es dependencia del proyecto:
#no se agrega ninguna libreria nueva.
#
#Sale en el idioma que eligio quien lo descarga (textos, fechas y montos).
from io import BytesIO
from datetime import datetime
from django.utils import timezone
from django.utils.formats import date_format
from django.utils.translation import gettext, gettext_lazy, ngettext

from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.pdfgen import canvas

from pagos.factura import EMPRESA
from pagos.templatetags.formato import pesos

# ---- Paleta: la misma de la factura ----
AZUL = colors.HexColor("#0f1f44")
AZUL_CLARO = colors.HexColor("#16294f")
LIMA = colors.HexColor("#22c55e")
GRIS = colors.HexColor("#64748b")
GRIS_CLARO = colors.HexColor("#94a3b8")
TEXTO = colors.HexColor("#1e293b")
LINEA = colors.HexColor("#e2e8f0")
FILA_PAR = colors.HexColor("#f8fafc")
ROJO = colors.HexColor("#dc2626")
AMBAR = colors.HexColor("#d97706")

#Horizontal: son 9 columnas y en vertical quedarian apretadas
PAGINA = landscape(A4)
ANCHO, ALTO = PAGINA

MARGEN = 1.4 * cm
ALTO_FILA = 0.62 * cm

# Columnas: (clave, titulo, ancho en cm, alineacion). La clave es fija; el
# titulo va en el idioma de quien descarga el reporte.
# La suma debe acercarse al ancho util de la hoja (A4 horizontal menos los
# margenes = 26.9 cm) para que la tabla no quede corta contra el borde.
# FECHA necesita 3.2 cm: con menos se cortaba la hora ("31/08/2026 15...").
COLUMNAS = [
  ("fecha",    gettext_lazy("FECHA"),     3.2, "izq"),
  ("factura",  gettext_lazy("FACTURA"),   2.4, "izq"),
  ("usuario",  gettext_lazy("USUARIO"),   4.6, "izq"),
  ("plan",     gettext_lazy("PLAN"),      2.2, "izq"),
  ("metodo",   gettext_lazy("MÉTODO"),    2.2, "izq"),
  ("estado",   gettext_lazy("ESTADO"),    2.4, "izq"),
  ("subtotal", gettext_lazy("SUBTOTAL"),  2.9, "der"),
  ("iva",      gettext_lazy("IVA"),       2.5, "der"),
  ("total",    gettext_lazy("TOTAL"),     3.1, "der"),
]


def _pesos(valor):
  #Miles con punto (con coma en ingles), igual que en el resto del sitio
  try:
    return "$ " + pesos(valor or 0)
  except (TypeError, ValueError):
    return "$ 0"


def _fecha(valor):
  return date_format(valor, "SHORT_DATE_FORMAT")


def _fecha_hora(valor):
  return date_format(timezone.localtime(valor) if timezone.is_aware(valor) else valor,
                     "SHORT_DATETIME_FORMAT")


def _color_estado(estado):
  e = (estado or "").lower()
  if e == "aprobado":
    return colors.HexColor("#15803d")
  if e in ("rechazado", "fallido", "error"):
    return ROJO
  if e == "pendiente":
    return AMBAR
  return GRIS


def _recortar(c, texto, ancho_disponible, fuente, tamano):
  #Si el texto no cabe en su columna se corta con puntos suspensivos, en
  #vez de invadir la columna de al lado.
  texto = str(texto or "")
  if c.stringWidth(texto, fuente, tamano) <= ancho_disponible:
    return texto
  while texto and c.stringWidth(texto + "…", fuente, tamano) > ancho_disponible:
    texto = texto[:-1]
  return texto + "…"


def _cabecera_pagina(c, filtros, totales, pagina):
  """Franja azul superior con logo, titulo y datos del reporte."""
  c.setFillColor(AZUL)
  c.rect(0, ALTO - 3.1 * cm, ANCHO, 3.1 * cm, fill=1, stroke=0)

  #Logo xGol, igual que en la factura
  c.setFont("Helvetica-Bold", 22)
  c.setFillColor(LIMA)
  c.drawString(MARGEN, ALTO - 1.6 * cm, "x")
  ancho_x = c.stringWidth("x", "Helvetica-Bold", 22)
  c.setFillColor(colors.white)
  c.drawString(MARGEN + ancho_x, ALTO - 1.6 * cm, "Gol")

  c.setFillColor(GRIS_CLARO)
  c.setFont("Helvetica", 7.5)
  c.drawString(MARGEN, ALTO - 2.15 * cm, EMPRESA["razon_social"])
  c.drawString(MARGEN, ALTO - 2.55 * cm, "NIT: %s · %s" % (EMPRESA["nit"], gettext(EMPRESA["ciudad"])))

  #Titulo del reporte
  c.setFillColor(colors.white)
  c.setFont("Helvetica-Bold", 15)
  c.drawCentredString(ANCHO / 2, ALTO - 1.5 * cm, gettext("REPORTE DE TRANSACCIONES"))
  c.setFillColor(GRIS_CLARO)
  c.setFont("Helvetica", 8)
  c.drawCentredString(ANCHO / 2, ALTO - 2.05 * cm, _linea_filtros(filtros))

  #Fecha de emision y pagina, a la derecha
  c.setFillColor(colors.white)
  c.setFont("Helvetica", 8)
  c.drawRightString(ANCHO - MARGEN, ALTO - 1.4 * cm,
                    gettext("Emitido: %(fecha)s") % {"fecha": _fecha_hora(timezone.now())})
  c.setFillColor(GRIS_CLARO)
  c.drawRightString(ANCHO - MARGEN, ALTO - 1.85 * cm, gettext("Página %(n)d") % {"n": pagina})
  c.drawRightString(ANCHO - MARGEN, ALTO - 2.3 * cm,
                    ngettext("%(n)d pago aprobado", "%(n)d pagos aprobados", totales["cuenta"])
                    % {"n": totales["cuenta"]})


def _linea_filtros(filtros):
  """Una linea que deja claro QUE contiene el reporte."""
  if not filtros:
    return gettext("Todos los pagos aprobados")
  partes = []
  estado = (filtros.get("estado") or "todos")
  if estado and estado != "todos":
    partes.append(gettext("Estado: %(estado)s") % {"estado": gettext(estado.capitalize())})
  plan = (filtros.get("plan") or "todos")
  if plan and plan != "todos":
    partes.append(gettext("Plan: %(plan)s") % {"plan": gettext(str(plan).capitalize())})
  metodo = (filtros.get("metodo") or "todos")
  if metodo and metodo != "todos":
    partes.append(gettext("Método: %(metodo)s") % {"metodo": gettext(str(metodo))})
  desde, hasta = filtros.get("desde"), filtros.get("hasta")
  if desde and hasta:
    partes.append(gettext("Del %(desde)s al %(hasta)s") % {"desde": _fecha(desde), "hasta": _fecha(hasta)})
  elif desde:
    partes.append(gettext("Desde %(fecha)s") % {"fecha": _fecha(desde)})
  elif hasta:
    partes.append(gettext("Hasta %(fecha)s") % {"fecha": _fecha(hasta)})
  busqueda = (filtros.get("q") or "").strip()
  if busqueda:
    partes.append(gettext("Búsqueda: “%(texto)s”") % {"texto": busqueda})
  return " · ".join(partes) if partes else gettext("Todos los pagos aprobados")


def _cabecera_tabla(c, y):
  """Franja con los titulos de las columnas."""
  c.setFillColor(AZUL_CLARO)
  c.rect(MARGEN, y - 0.15 * cm, ANCHO - MARGEN * 2, 0.72 * cm, fill=1, stroke=0)
  c.setFillColor(colors.white)
  c.setFont("Helvetica-Bold", 7.5)

  x = MARGEN + 0.25 * cm
  for clave, titulo, ancho, alineacion in COLUMNAS:
    if alineacion == "der":
      c.drawRightString(x + ancho * cm - 0.25 * cm, y + 0.05 * cm, str(titulo))
    else:
      c.drawString(x, y + 0.05 * cm, str(titulo))
    x += ancho * cm
  return y - 0.72 * cm


def _pie_pagina(c):
  c.setStrokeColor(LINEA)
  c.setLineWidth(0.5)
  c.line(MARGEN, 1.5 * cm, ANCHO - MARGEN, 1.5 * cm)
  c.setFillColor(GRIS_CLARO)
  c.setFont("Helvetica", 7)
  c.drawCentredString(ANCHO / 2, 1.05 * cm,
                      "%s · NIT %s · %s · %s" % (EMPRESA["razon_social"], EMPRESA["nit"],
                                                 EMPRESA["correo"], EMPRESA["telefono"]))
  c.drawCentredString(ANCHO / 2, 0.7 * cm,
                      gettext("%(web)s · Documento generado automáticamente · Valores en pesos colombianos (COP)")
                      % {"web": EMPRESA["web"]})


def _resumen(c, y, totales):
  """Bloque de totales al final del reporte."""
  alto_caja = 2.5 * cm
  c.setFillColor(FILA_PAR)
  c.setStrokeColor(LINEA)
  c.setLineWidth(0.5)
  c.rect(MARGEN, y - alto_caja, ANCHO - MARGEN * 2, alto_caja, fill=1, stroke=1)

  c.setFillColor(TEXTO)
  c.setFont("Helvetica-Bold", 9)
  c.drawString(MARGEN + 0.5 * cm, y - 0.75 * cm, gettext("RESUMEN DEL REPORTE"))

  #Cuatro cifras repartidas a lo ancho
  datos = [
    (gettext("Pagos aprobados"), str(totales["cuenta"]), TEXTO),
    (gettext("Ingreso bruto"), _pesos(totales["bruto"]), TEXTO),
    (gettext("Comisión estimada"), "- " + _pesos(totales["comision"]), ROJO),
    (gettext("Neto estimado"), _pesos(totales["neto"]), colors.HexColor("#15803d")),
  ]
  paso = (ANCHO - MARGEN * 2 - 1 * cm) / 4
  x = MARGEN + 0.5 * cm
  for etiqueta, valor, color in datos:
    c.setFillColor(GRIS)
    c.setFont("Helvetica", 7.5)
    c.drawString(x, y - 1.45 * cm, etiqueta.upper())
    c.setFillColor(color)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(x, y - 2.05 * cm, valor)
    x += paso

  #Aviso: la comision es estimada, igual que dice el panel
  c.setFillColor(GRIS_CLARO)
  c.setFont("Helvetica-Oblique", 6.5)
  c.drawRightString(ANCHO - MARGEN - 0.5 * cm, y - 0.75 * cm,
                    gettext("La comisión es estimada; el valor exacto lo confirma el extracto de la pasarela."))


def _sin_datos(c, y):
  c.setFillColor(GRIS)
  c.setFont("Helvetica-Oblique", 10)
  c.drawCentredString(ANCHO / 2, y - 1.2 * cm,
                      gettext("No hay pagos aprobados que coincidan con los filtros seleccionados."))


def generar_reporte_pdf(pagos, filtros=None):
  """Devuelve los bytes de un PDF con todas las transacciones recibidas.

  'pagos' puede ser una lista o un iterador de objetos Pago.
  'filtros' es el diccionario del panel, solo para dejar constancia en el
  encabezado de que el reporte esta filtrado.
  """
  buffer = BytesIO()
  c = canvas.Canvas(buffer, pagesize=PAGINA)
  c.setTitle(gettext("xGol · Reporte de transacciones"))
  c.setAuthor(EMPRESA["razon_social"])
  c.setSubject(gettext("Historial de transacciones"))

  #Un reporte de comprobantes de pago solo puede llevar dinero que de verdad
  #entro. Los pendientes y los rechazados NO tienen factura emitida y sumarlos
  #cuadraria mal el total contra la contabilidad, asi que se dejan fuera.
  filas = [p for p in pagos if (p.estado or "").strip().lower() == "aprobado"]
  totales = {
    "cuenta": len(filas),
    "bruto": sum(p.monto or 0 for p in filas),
    "comision": sum(p.comision or 0 for p in filas),
    "neto": sum(p.neto or 0 for p in filas),
  }

  pagina = 1
  _cabecera_pagina(c, filtros, totales, pagina)
  y = _cabecera_tabla(c, ALTO - 4.1 * cm)

  #Espacio que hay que dejar abajo para el pie y el resumen
  LIMITE = 1.9 * cm

  if not filas:
    _sin_datos(c, y)
    #El mensaje ocupa su espacio: sin esto la caja del resumen se dibujaba
    #encima y lo tapaba por completo.
    y -= 2.2 * cm

  for indice, pago in enumerate(filas):
    #Salto de pagina cuando ya no cabe otra fila
    if y - ALTO_FILA < LIMITE:
      _pie_pagina(c)
      c.showPage()
      pagina += 1
      _cabecera_pagina(c, filtros, totales, pagina)
      y = _cabecera_tabla(c, ALTO - 4.1 * cm)

    #Fondo alterno para poder seguir la fila con la vista
    if indice % 2 == 1:
      c.setFillColor(FILA_PAR)
      c.rect(MARGEN, y - ALTO_FILA + 0.16 * cm, ANCHO - MARGEN * 2, ALTO_FILA, fill=1, stroke=0)

    nombre = (pago.usuario.get_full_name() or pago.usuario.username) if pago.usuario_id else "—"
    valores = [
      _fecha_hora(pago.creado) if pago.creado else "",
      pago.numero_factura or "—",
      nombre,
      gettext(pago.plan) if pago.plan else "",
      gettext(pago.metodo) if pago.metodo else "",
      pago.get_estado_display() if pago.estado else "",
      _pesos(pago.subtotal),
      _pesos(pago.iva),
      _pesos(pago.monto),
    ]

    x = MARGEN + 0.25 * cm
    base = y - ALTO_FILA + 0.34 * cm
    for i, (clave, titulo, ancho, alineacion) in enumerate(COLUMNAS):
      texto = valores[i]
      #El estado va en color; el total en negrita
      if clave == "estado":
        c.setFillColor(_color_estado(pago.estado))
        c.setFont("Helvetica-Bold", 7.5)
      elif clave == "total":
        c.setFillColor(TEXTO)
        c.setFont("Helvetica-Bold", 8)
      else:
        c.setFillColor(TEXTO if clave in ("factura", "usuario") else GRIS)
        c.setFont("Helvetica", 7.5)

      util = ancho * cm - 0.5 * cm
      fuente = c._fontname
      tamano = c._fontsize
      texto = _recortar(c, texto, util, fuente, tamano)

      if alineacion == "der":
        c.drawRightString(x + ancho * cm - 0.25 * cm, base, texto)
      else:
        c.drawString(x, base, texto)
      x += ancho * cm

    #Linea fina bajo cada fila
    c.setStrokeColor(LINEA)
    c.setLineWidth(0.3)
    c.line(MARGEN, y - ALTO_FILA + 0.1 * cm, ANCHO - MARGEN, y - ALTO_FILA + 0.1 * cm)

    y -= ALTO_FILA

  #El resumen va al final; si no cabe, se abre una hoja para el
  if y - 3.0 * cm < LIMITE:
    _pie_pagina(c)
    c.showPage()
    pagina += 1
    _cabecera_pagina(c, filtros, totales, pagina)
    y = ALTO - 4.1 * cm

  _resumen(c, y - 0.4 * cm, totales)
  _pie_pagina(c)

  c.showPage()
  c.save()
  return buffer.getvalue()