from django.db import models
from django.db.models import F
from django.contrib.auth.models import User

#Estados canonicos de un pago. Se dejan capitalizados como estaban antes para
#no tener que reescribir las filas que ya existen en la base de datos.
ESTADOS_PAGO=[
  ("Pendiente","Pendiente"),
  ("Aprobado","Aprobado"),
  ("Rechazado","Rechazado"),
  ("Anulado","Anulado"),
  ("Error","Error"),
  ("Reembolsado","Reembolsado"),
]

#Estados que la pasarela considera finales: ya no van a cambiar solos
ESTADOS_FINALES=("Aprobado","Rechazado","Anulado","Error","Reembolsado")


class Consecutivo(models.Model):
  #Contador atomico para numerar facturas. Antes el numero salia de
  #Pago.objects.count()+1: con dos pagos simultaneos o con un borrado el
  #numero se repetia. Aca se incrementa con un UPDATE ... SET valor=valor+1
  #dentro de una transaccion, que la base de datos serializa por nosotros.
  nombre=models.CharField(max_length=40,unique=True)
  valor=models.BigIntegerField(default=0)
  actualizado=models.DateTimeField(auto_now=True)

  class Meta:
    verbose_name="Consecutivo"
    verbose_name_plural="Consecutivos"

  def __str__(self):
    return f"{self.nombre}: {self.valor}"

  @classmethod
  def siguiente(cls,nombre,prefijo="FAC",ancho=6):
    #Devuelve el proximo numero formateado. Llamar SIEMPRE dentro de un
    #transaction.atomic() para que el incremento y su uso viajen juntos.
    fila,creada=cls.objects.get_or_create(nombre=nombre)
    cls.objects.filter(pk=fila.pk).update(valor=F("valor")+1)
    fila.refresh_from_db()
    return f"{prefijo}-{fila.valor:0{ancho}d}"


class Pago(models.Model):
  usuario=models.ForeignKey(User,on_delete=models.CASCADE,related_name="pagos")
  plan=models.CharField(max_length=30,default="Mensual")
  #Clave del plan en suscripciones.planes (mensual/trimestral). Se guarda para
  #poder recalcular los dias sin adivinar a partir del nombre visible.
  clave_plan=models.CharField(max_length=30,blank=True)

  monto=models.IntegerField(default=50000)
  subtotal=models.IntegerField(default=0)
  iva=models.IntegerField(default=0)
  #Monto exacto que se le manda a la pasarela. Wompi trabaja en centavos y el
  #webhook lo devuelve en centavos: se guarda tal cual para poder comparar sin
  #redondeos y detectar manipulacion del monto.
  monto_centavos=models.BigIntegerField(default=0)
  moneda=models.CharField(max_length=3,default="COP")

  metodo=models.CharField(max_length=30,default="Tarjeta")
  #Medio real reportado por la pasarela: CARD, PSE, NEQUI, BANCOLOMBIA_TRANSFER...
  metodo_detalle=models.CharField(max_length=40,blank=True)

  estado=models.CharField(max_length=20,default="Pendiente",choices=ESTADOS_PAGO)
  referencia=models.CharField(max_length=40,unique=True)
  numero_factura=models.CharField(max_length=30,unique=True,null=True,blank=True)

  pasarela=models.CharField(max_length=20,default="wompi")
  #test o prod. Evita que un evento de sandbox active una suscripcion real.
  ambiente=models.CharField(max_length=10,default="test")
  id_pasarela=models.CharField(max_length=60,blank=True,db_index=True)
  mensaje=models.CharField(max_length=200,blank=True)

  correo_pagador=models.EmailField(blank=True)
  ip=models.CharField(max_length=45,blank=True)

  #Comision estimada segun las tarifas configuradas. La cifra real la liquida
  #la pasarela: esto sirve para proyectar el neto, no para contabilidad oficial.
  comision=models.IntegerField(default=0)
  neto=models.IntegerField(default=0)

  #Llave de idempotencia: True significa que este pago YA extendio la
  #suscripcion. Un reintento del webhook lo encuentra en True y no vuelve a
  #sumar dias.
  aplicado=models.BooleanField(default=False)
  dias_otorgados=models.IntegerField(default=0)
  vigencia_inicio=models.DateField(null=True,blank=True)
  vigencia_fin=models.DateField(null=True,blank=True)

  aprobado_en=models.DateTimeField(null=True,blank=True)
  creado=models.DateTimeField(auto_now_add=True)
  actualizado=models.DateTimeField(auto_now=True)

  class Meta:
    verbose_name='Pago'
    verbose_name_plural='Pagos'
    ordering=['-creado']
    indexes=[
      models.Index(fields=["estado","creado"]),
      models.Index(fields=["usuario","estado"]),
    ]

  def __str__(self):
    return f"{self.referencia} - {self.usuario.username} - {self.plan}"

  def esta_aprobado(self):
    return self.estado=="Aprobado"

  def es_final(self):
    return self.estado in ESTADOS_FINALES


class EventoPasarela(models.Model):
  #Bitacora cruda de todo lo que manda la pasarela. Se guarda ANTES de
  #procesar, incluso si la firma es invalida: si manana hay una disputa, la
  #evidencia esta aca tal como llego.
  pasarela=models.CharField(max_length=20,default="wompi")
  tipo=models.CharField(max_length=40,blank=True)
  ambiente=models.CharField(max_length=10,blank=True)
  id_pasarela=models.CharField(max_length=60,blank=True,db_index=True)
  referencia=models.CharField(max_length=40,blank=True,db_index=True)
  estado_reportado=models.CharField(max_length=30,blank=True)
  monto_centavos=models.BigIntegerField(default=0)
  #El checksum es unico por evento: los reintentos de Wompi repiten el mismo
  #valor, asi que sirve de llave anti-duplicados.
  checksum=models.CharField(max_length=80,unique=True)
  firma_valida=models.BooleanField(default=False)
  procesado=models.BooleanField(default=False)
  detalle=models.TextField(blank=True)
  cuerpo=models.JSONField(default=dict)
  ip=models.CharField(max_length=45,blank=True)
  creado=models.DateTimeField(auto_now_add=True)

  class Meta:
    verbose_name="Evento de pasarela"
    verbose_name_plural="Eventos de pasarela"
    ordering=["-creado"]

  def __str__(self):
    return f"{self.tipo} {self.referencia} ({self.estado_reportado})"


class Reembolso(models.Model):
  ESTADOS=[("Solicitado","Solicitado"),("Aprobado","Aprobado"),("Rechazado","Rechazado")]

  pago=models.ForeignKey(Pago,on_delete=models.PROTECT,related_name="reembolsos")
  monto=models.IntegerField(default=0)
  motivo=models.CharField(max_length=200,blank=True)
  estado=models.CharField(max_length=20,default="Solicitado",choices=ESTADOS)
  referencia_externa=models.CharField(max_length=60,blank=True)
  #Si es True, al aprobarlo se le quitan a la suscripcion los dias que ese
  #pago habia otorgado.
  revoca_dias=models.BooleanField(default=True)
  creado_por=models.ForeignKey(User,on_delete=models.SET_NULL,null=True,blank=True,related_name="reembolsos_creados")
  creado=models.DateTimeField(auto_now_add=True)

  class Meta:
    verbose_name="Reembolso"
    verbose_name_plural="Reembolsos"
    ordering=["-creado"]

  def __str__(self):
    return f"Reembolso {self.pago.referencia} - ${self.monto}"


class MovimientoSuscripcion(models.Model):
  #Historia de cada cambio de estado de una suscripcion. Sin esto no hay forma
  #de responder "por que este usuario tiene acceso hasta el 30 de septiembre".
  TIPOS=[
    ("Activacion","Activacion"),
    ("Renovacion","Renovacion"),
    ("Cancelacion","Cancelacion"),
    ("Vencimiento","Vencimiento"),
    ("Reembolso","Reembolso"),
    ("AjusteAdmin","AjusteAdmin"),
  ]

  usuario=models.ForeignKey(User,on_delete=models.CASCADE,related_name="movimientos_suscripcion")
  tipo=models.CharField(max_length=20,choices=TIPOS)
  plan=models.CharField(max_length=30,blank=True)
  dias=models.IntegerField(default=0)
  vencimiento_anterior=models.DateField(null=True,blank=True)
  vencimiento_nuevo=models.DateField(null=True,blank=True)
  pago=models.ForeignKey(Pago,on_delete=models.SET_NULL,null=True,blank=True,related_name="movimientos")
  actor=models.ForeignKey(User,on_delete=models.SET_NULL,null=True,blank=True,related_name="movimientos_ejecutados")
  nota=models.CharField(max_length=200,blank=True)
  creado=models.DateTimeField(auto_now_add=True)

  class Meta:
    verbose_name="Movimiento de suscripcion"
    verbose_name_plural="Movimientos de suscripcion"
    ordering=["-creado"]

  def __str__(self):
    return f"{self.tipo} {self.usuario.username} ({self.creado:%d/%m/%Y})"