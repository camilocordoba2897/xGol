#Exportacion de reportes a CSV y a Excel.
#
#El .xlsx se escribe con la libreria estandar (zipfile + xml). Es a proposito:
#el proyecto no gana una dependencia nueva (openpyxl/xlsxwriter) ni un paso
#extra al desplegar, y el archivo abre igual en Excel, LibreOffice y Sheets.
import csv
import io
import zipfile
from datetime import datetime,date
from xml.sax.saxutils import escape

#Excel en español interpreta la coma como separador decimal: con ";" el CSV
#se abre en columnas sin tener que usar el asistente de importacion.
SEPARADOR_CSV=";"
#El BOM le dice a Excel que el archivo es UTF-8 y evita que "Bogotá" salga
#como "BogotÃ¡".
BOM="\ufeff"


def _texto(valor):
  if valor is None:
    return ""
  if isinstance(valor,datetime):
    return valor.strftime("%Y-%m-%d %H:%M")
  if isinstance(valor,date):
    return valor.strftime("%Y-%m-%d")
  return str(valor)


def a_csv(cabeceras,filas):
  buffer=io.StringIO()
  buffer.write(BOM)
  escritor=csv.writer(buffer,delimiter=SEPARADOR_CSV,quoting=csv.QUOTE_MINIMAL,lineterminator="\r\n")
  escritor.writerow(cabeceras)
  for fila in filas:
    escritor.writerow([_texto(celda) for celda in fila])
  return buffer.getvalue().encode("utf-8")


# ============================================================
#  ESCRITOR MINIMO DE XLSX
# ============================================================
def _columna(indice):
  #0 -> A, 25 -> Z, 26 -> AA
  nombre=""
  indice=indice+1
  while indice>0:
    indice,resto=divmod(indice-1,26)
    nombre=chr(65+resto)+nombre
  return nombre


def _celda_xml(referencia,valor,estilo):
  if isinstance(valor,bool):
    valor="Si" if valor else "No"
  if isinstance(valor,(int,float)) and not isinstance(valor,bool):
    return f'<c r="{referencia}" s="{estilo}"><v>{valor}</v></c>'
  texto=escape(_texto(valor))
  return f'<c r="{referencia}" s="{estilo}" t="inlineStr"><is><t xml:space="preserve">{texto}</t></is></c>'


def a_xlsx(cabeceras,filas,hoja="Reporte"):
  lineas=[]
  #Fila de encabezado (estilo 1: negrita)
  celdas="".join(_celda_xml(f"{_columna(i)}1",valor,1) for i,valor in enumerate(cabeceras))
  lineas.append(f'<row r="1">{celdas}</row>')

  for numero,fila in enumerate(filas,start=2):
    partes=[]
    for i,valor in enumerate(fila):
      #Estilo 2: formato de miles para los numeros
      estilo=2 if isinstance(valor,(int,float)) and not isinstance(valor,bool) else 0
      partes.append(_celda_xml(f"{_columna(i)}{numero}",valor,estilo))
    lineas.append(f'<row r="{numero}">{"".join(partes)}</row>')

  ancho=len(cabeceras) or 1
  hoja_xml=(
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
    f'<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>'
    f'<cols><col min="1" max="{ancho}" width="20" customWidth="1"/></cols>'
    f'<sheetData>{"".join(lineas)}</sheetData>'
    '</worksheet>'
  )

  tipos=(
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
    '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
    '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
    '</Types>'
  )

  relaciones=(
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
    '</Relationships>'
  )

  libro=(
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
    'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
    f'<sheets><sheet name="{escape(hoja[:31])}" sheetId="1" r:id="rId1"/></sheets>'
    '</workbook>'
  )

  relaciones_libro=(
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
    '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
    '</Relationships>'
  )

  estilos=(
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
    '<numFmts count="1"><numFmt numFmtId="164" formatCode="#,##0"/></numFmts>'
    '<fonts count="2">'
    '<font><sz val="11"/><name val="Calibri"/></font>'
    '<font><b/><sz val="11"/><color rgb="FFFFFFFF"/><name val="Calibri"/></font>'
    '</fonts>'
    '<fills count="3">'
    '<fill><patternFill patternType="none"/></fill>'
    '<fill><patternFill patternType="gray125"/></fill>'
    '<fill><patternFill patternType="solid"><fgColor rgb="FF15803D"/><bgColor indexed="64"/></patternFill></fill>'
    '</fills>'
    '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
    '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
    '<cellXfs count="3">'
    '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
    '<xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1"/>'
    '<xf numFmtId="164" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>'
    '</cellXfs>'
    '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
    '</styleSheet>'
  )

  buffer=io.BytesIO()
  with zipfile.ZipFile(buffer,"w",zipfile.ZIP_DEFLATED) as z:
    z.writestr("[Content_Types].xml",tipos)
    z.writestr("_rels/.rels",relaciones)
    z.writestr("xl/workbook.xml",libro)
    z.writestr("xl/_rels/workbook.xml.rels",relaciones_libro)
    z.writestr("xl/styles.xml",estilos)
    z.writestr("xl/worksheets/sheet1.xml",hoja_xml)
  return buffer.getvalue()


# ============================================================
#  CONJUNTOS DE DATOS EXPORTABLES
# ============================================================
CABECERAS_TRANSACCIONES=[
  "Fecha","Factura","Referencia","ID pasarela","Usuario","Correo","Plan",
  "Metodo","Estado","Subtotal","IVA","Total","Comision estimada","Neto estimado",
  "Dias","Vigencia hasta","Ambiente",
]


def filas_transacciones(pagos):
  for pago in pagos:
    yield [
      pago.creado,
      pago.numero_factura or "",
      pago.referencia,
      pago.id_pasarela,
      pago.usuario.username,
      pago.correo_pagador or pago.usuario.email or "",
      pago.plan,
      pago.metodo,
      pago.estado,
      pago.subtotal,
      pago.iva,
      pago.monto,
      pago.comision,
      pago.neto,
      pago.dias_otorgados,
      pago.vigencia_fin,
      pago.ambiente,
    ]


CABECERAS_RESUMEN=["Periodo","Transacciones","Ingreso bruto","Comision estimada","Neto estimado"]


def filas_resumen(resumen):
  nombres=[("hoy","Hoy"),("semana","Esta semana"),("mes","Este mes"),
           ("trimestre","Este trimestre"),("anio","Este ano"),("historico","Historico")]
  for llave,titulo in nombres:
    dato=resumen.get(llave) or {}
    yield [titulo,dato.get("cuenta",0),dato.get("total",0),dato.get("comision",0),dato.get("neto",0)]