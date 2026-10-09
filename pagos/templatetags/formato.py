from django import template
from django.utils.translation import get_language

register=template.Library()

@register.filter
def pesos(valor):
  #Miles con punto ($20.000), como se escribe en Colombia, en Brasil y en
  #Alemania. En ingles de Estados Unidos los miles van con coma ($20,000).
  try:
    entero=int(round(float(valor)))
  except (TypeError,ValueError):
    return valor
  con_comas=f"{entero:,}"
  return con_comas if get_language()=="en" else con_comas.replace(",",".")
