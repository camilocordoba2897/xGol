PLANES = {
  "mensual": {
    "nombre": "Mensual",
    "precio": 20000,
    "dias": 30,
    "nivel": 1,
    "etiqueta": "Plan Mensual",
    "descripcion": "Acceso completo por 30 dias"
  },
  "trimestral": {
    "nombre": "Trimestral",
    "precio": 50000,
    "dias": 90,
    "nivel": 2,
    "etiqueta": "Plan Trimestral",
    "descripcion": "Acceso completo por 90 dias",
    "ahorro": "Ahorras $10.000"
  }
}

def obtener_plan(clave):
  return PLANES.get(clave)

#Nivel a partir del nombre visible ("Mensual" -> 1). Devuelve 0 si el nombre
#no corresponde a ningun plan, que es lo que pasa con una suscripcion nueva.
def nivel_de_plan(nombre_plan):
  for clave,plan in PLANES.items():
    if plan["nombre"]==nombre_plan:
      return plan["nivel"]
  return 0

IVA_PORCENTAJE = 19

def desglosar_precio(precio_final):
  divisor=1+(IVA_PORCENTAJE/100)
  subtotal=round(precio_final/divisor)
  iva=precio_final-subtotal
  return {
    "subtotal": subtotal,
    "iva": iva,
    "iva_porcentaje": IVA_PORCENTAJE,
    "total": precio_final
  }