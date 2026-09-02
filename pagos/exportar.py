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


#Indices de la lista <cellXfs> de la hoja de estilos, con nombre para no
#andar poniendo numeros sueltos por el codigo. El orden tiene que coincidir
#exactamente con el de esa lista, mas abajo en este mismo archivo.
ESTILO_BASE=0
ESTILO_ENCABEZADO=1
ESTILO_TITULO=2
ESTILO_SUBTITULO=3
ESTILO_TEXTO=4
ESTILO_TEXTO_PAR=5
ESTILO_NUMERO=6
ESTILO_NUMERO_PAR=7
ESTILO_MONEDA=8
ESTILO_MONEDA_PAR=9
ESTILO_TOTAL_TXT=10
ESTILO_TOTAL_NUM=11


def a_xlsx(cabeceras,filas,hoja="Reporte",titulo=None,subtitulo=None,
           columnas_moneda=None,totalizar=None,columna_estado=None):
  """Genera un .xlsx presentable.

  Antes salia una tabla pelada: encabezado verde y nada mas, las cifras sin
  separador de miles y todas las columnas del mismo ancho. Ahora lleva:
    - un titulo y una linea con los filtros aplicados
    - encabezado en su fila, con filtro automatico y paneles congelados
    - filas alternas para poder seguirlas con la vista
    - las cifras con formato de pesos y las fechas como fecha
    - una fila de TOTALES al final
    - anchos de columna segun el contenido de cada una

  'columnas_moneda' y 'totalizar' son listas de indices de columna.
  'columna_estado' es el indice de la columna Estado: cuando se pasa, la
  fila de TOTALES suma UNICAMENTE las filas aprobadas. Sin esto se estaban
  sumando tambien los pagos pendientes y rechazados, que no son plata que
  haya entrado y descuadraban el total.
  """
  columnas_moneda=set(columnas_moneda or [])
  totalizar=set(totalizar or [])
  ancho=len(cabeceras) or 1
  filas=list(filas)

  def _cuenta_en_total(fila):
    if columna_estado is None:
      return True
    if columna_estado>=len(fila):
      return False
    return str(fila[columna_estado] or "").strip().lower()=="aprobado"

  lineas=[]
  fila_actual=1

  # ---- Titulo ----
  if titulo:
    lineas.append('<row r="%d" ht="24" customHeight="1">%s</row>' % (
      fila_actual,_celda_xml("A%d"%fila_actual,titulo,ESTILO_TITULO)))
    fila_actual+=1
  if subtitulo:
    lineas.append('<row r="%d" ht="16" customHeight="1">%s</row>' % (
      fila_actual,_celda_xml("A%d"%fila_actual,subtitulo,ESTILO_SUBTITULO)))
    fila_actual+=1
  if titulo or subtitulo:
    fila_actual+=1   # una fila en blanco de aire

  # ---- Encabezado ----
  fila_encabezado=fila_actual
  celdas="".join(_celda_xml("%s%d"%(_columna(i),fila_encabezado),valor,ESTILO_ENCABEZADO)
                 for i,valor in enumerate(cabeceras))
  lineas.append('<row r="%d" ht="20" customHeight="1">%s</row>'%(fila_encabezado,celdas))
  fila_actual+=1

  # ---- Datos ----
  primera_dato=fila_actual
  sumas={i:0 for i in totalizar}
  for numero,fila in enumerate(filas):
    r=fila_actual+numero
    par=(numero%2==1)
    suma_esta=_cuenta_en_total(fila)
    partes=[]
    for i,valor in enumerate(fila):
      es_numero=isinstance(valor,(int,float)) and not isinstance(valor,bool)
      es_fecha=isinstance(valor,(datetime,date))
      if es_numero and i in columnas_moneda:
        estilo=ESTILO_MONEDA_PAR if par else ESTILO_MONEDA
      elif es_numero:
        estilo=ESTILO_NUMERO_PAR if par else ESTILO_NUMERO
      elif es_fecha:
        estilo=ESTILO_TEXTO_PAR if par else ESTILO_TEXTO
      else:
        estilo=ESTILO_TEXTO_PAR if par else ESTILO_TEXTO
      partes.append(_celda_xml("%s%d"%(_columna(i),r),valor,estilo))
      if es_numero and i in totalizar and suma_esta:
        sumas[i]=sumas[i]+valor
    lineas.append('<row r="%d">%s</row>'%(r,"".join(partes)))
  fila_actual=fila_actual+len(filas)
  ultima_dato=fila_actual-1

  # ---- Fila de totales ----
  if totalizar and filas:
    rotulo="TOTAL APROBADO" if columna_estado is not None else "TOTAL"
    partes=[]
    for i in range(ancho):
      if i==0:
        partes.append(_celda_xml("%s%d"%(_columna(i),fila_actual),rotulo,ESTILO_TOTAL_TXT))
      elif i in totalizar:
        partes.append(_celda_xml("%s%d"%(_columna(i),fila_actual),sumas[i],ESTILO_TOTAL_NUM))
      else:
        partes.append(_celda_xml("%s%d"%(_columna(i),fila_actual),"",ESTILO_TOTAL_TXT))
    lineas.append('<row r="%d" ht="19" customHeight="1">%s</row>'%(fila_actual,"".join(partes)))

  # ---- Anchos: segun el titulo y el contenido de cada columna ----
  cols=[]
  for i,cabecera in enumerate(cabeceras):
    largo=len(str(cabecera))
    for fila in filas[:200]:          # una muestra basta para calcular el ancho
      if i<len(fila):
        largo=max(largo,len(_texto(fila[i])))
    cols.append('<col min="%d" max="%d" width="%d" customWidth="1"/>'
                %(i+1,i+1,min(max(largo+3,10),40)))

  #Los paneles se congelan bajo el encabezado y se activa el autofiltro
  congelar=fila_encabezado
  rango_filtro="%s%d:%s%d"%(_columna(0),fila_encabezado,_columna(ancho-1),
                            ultima_dato if filas else fila_encabezado)

  hoja_xml=(
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
    '<sheetViews><sheetView showGridLines="0" workbookViewId="0">'
    '<pane ySplit="%d" topLeftCell="A%d" activePane="bottomLeft" state="frozen"/>'
    '</sheetView></sheetViews>'
    '<sheetFormatPr defaultRowHeight="15"/>'
    '<cols>%s</cols>'
    '<sheetData>%s</sheetData>'
    '<autoFilter ref="%s"/>'
    '</worksheet>'
  )%(congelar,congelar+1,"".join(cols),"".join(lineas),rango_filtro)

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
    #164 = miles, 165 = pesos, 166 = fecha con hora
    '<numFmts count="3">'
    '<numFmt numFmtId="164" formatCode="#,##0"/>'
    '<numFmt numFmtId="165" formatCode="&quot;$&quot;\\ #,##0"/>'
    '<numFmt numFmtId="166" formatCode="dd/mm/yyyy\\ hh:mm"/>'
    '</numFmts>'
    #0 normal · 1 encabezado · 2 titulo · 3 subtitulo · 4 total
    '<fonts count="5">'
    '<font><sz val="10"/><color rgb="FF1E293B"/><name val="Calibri"/></font>'
    '<font><b/><sz val="10"/><color rgb="FFFFFFFF"/><name val="Calibri"/></font>'
    '<font><b/><sz val="16"/><color rgb="FF0F1F44"/><name val="Calibri"/></font>'
    '<font><sz val="10"/><color rgb="FF64748B"/><name val="Calibri"/></font>'
    '<font><b/><sz val="10"/><color rgb="FF0F1F44"/><name val="Calibri"/></font>'
    '</fonts>'
    #0 ninguno · 1 gris125 · 2 azul encabezado · 3 fila alterna · 4 fila total
    '<fills count="5">'
    '<fill><patternFill patternType="none"/></fill>'
    '<fill><patternFill patternType="gray125"/></fill>'
    '<fill><patternFill patternType="solid"><fgColor rgb="FF0F1F44"/><bgColor indexed="64"/></patternFill></fill>'
    '<fill><patternFill patternType="solid"><fgColor rgb="FFF8FAFC"/><bgColor indexed="64"/></patternFill></fill>'
    '<fill><patternFill patternType="solid"><fgColor rgb="FFDCFCE7"/><bgColor indexed="64"/></patternFill></fill>'
    '</fills>'
    #0 sin borde · 1 linea inferior suave · 2 linea superior marcada
    '<borders count="3">'
    '<border><left/><right/><top/><bottom/><diagonal/></border>'
    '<border><left/><right/><top/><bottom style="thin"><color rgb="FFE2E8F0"/></bottom><diagonal/></border>'
    '<border><left/><right/><top style="medium"><color rgb="FF0F1F44"/></top><bottom/><diagonal/></border>'
    '</borders>'
    '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
    '<cellXfs count="12">'
    #0 base
    '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
    #1 encabezado
    '<xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1" applyAlignment="1">'
    '<alignment vertical="center"/></xf>'
    #2 titulo
    '<xf numFmtId="0" fontId="2" fillId="0" borderId="0" xfId="0" applyFont="1" applyAlignment="1">'
    '<alignment vertical="center"/></xf>'
    #3 subtitulo
    '<xf numFmtId="0" fontId="3" fillId="0" borderId="0" xfId="0" applyFont="1"/>'
    #4 texto normal
    '<xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyBorder="1"/>'
    #5 texto en fila alterna
    '<xf numFmtId="0" fontId="0" fillId="3" borderId="1" xfId="0" applyFill="1" applyBorder="1"/>'
    #6 numero
    '<xf numFmtId="164" fontId="0" fillId="0" borderId="1" xfId="0" applyNumberFormat="1" applyBorder="1"/>'
    #7 numero en fila alterna
    '<xf numFmtId="164" fontId="0" fillId="3" borderId="1" xfId="0" applyNumberFormat="1" applyFill="1" applyBorder="1"/>'
    #8 moneda
    '<xf numFmtId="165" fontId="0" fillId="0" borderId="1" xfId="0" applyNumberFormat="1" applyBorder="1"/>'
    #9 moneda en fila alterna
    '<xf numFmtId="165" fontId="0" fillId="3" borderId="1" xfId="0" applyNumberFormat="1" applyFill="1" applyBorder="1"/>'
    #10 texto de la fila de totales
    '<xf numFmtId="0" fontId="4" fillId="4" borderId="2" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1">'
    '<alignment vertical="center"/></xf>'
    #11 numero de la fila de totales
    '<xf numFmtId="165" fontId="4" fillId="4" borderId="2" xfId="0" applyNumberFormat="1" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1">'
    '<alignment vertical="center"/></xf>'
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

#Indices de las columnas de arriba que llevan formato de pesos y las que
#ademas se suman en la fila de TOTALES.
MONEDA_TRANSACCIONES=[9,10,11,12,13]        # Subtotal, IVA, Total, Comision, Neto
TOTALIZAR_TRANSACCIONES=[9,10,11,12,13]
#Indice de la columna "Estado": la fila de totales solo suma lo aprobado.
COLUMNA_ESTADO_TRANSACCIONES=8


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

MONEDA_RESUMEN=[2,3,4]
#El resumen NO se totaliza: sus filas son acumulados que se solapan
#(lo de hoy ya esta dentro de lo del mes), sumarlas no significaria nada.
TOTALIZAR_RESUMEN=[]


def filas_resumen(resumen):
  nombres=[("hoy","Hoy"),("semana","Esta semana"),("mes","Este mes"),
           ("trimestre","Este trimestre"),("anio","Este ano"),("historico","Historico")]
  for llave,titulo in nombres:
    dato=resumen.get(llave) or {}
    yield [titulo,dato.get("cuenta",0),dato.get("total",0),dato.get("comision",0),dato.get("neto",0)]