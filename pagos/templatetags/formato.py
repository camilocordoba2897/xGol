from django import template

register=template.Library()

@register.filter
def pesos(valor):
  try:
    entero=int(round(float(valor)))
  except (TypeError,ValueError):
    return valor
  return f"{entero:,}".replace(",",".")
