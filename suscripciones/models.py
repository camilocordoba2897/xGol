from django.db import models
from django.contrib.auth.models import User
from datetime import timedelta
from django.utils import timezone

class Suscripcion(models.Model):
  usuario=models.OneToOneField(User,on_delete=models.CASCADE,related_name="suscripcion")
  plan=models.CharField(max_length=30,default="Mensual")
  precio=models.IntegerField(default=50000)
  inicio=models.DateField(null=True,blank=True)
  vencimiento=models.DateField(null=True,blank=True)
  activa=models.BooleanField(default=False)

  #De donde salio el acceso: un pago real, una activacion manual del admin o
  #una cortesia. Sin esto no se puede separar la venta del regalo en el
  #reporte de ingresos.
  origen=models.CharField(max_length=20,default="pago")

  #Bandera de renovacion automatica. Queda apagada mientras no se habiliten
  #fuentes de pago tokenizadas en la pasarela; el panel la usa para saber a
  #quien hay que avisarle antes de que venza.
  renovacion_automatica=models.BooleanField(default=False)
  #Identificador de la fuente de pago guardada en la pasarela (tokenizacion).
  #Nunca guarda datos de tarjeta: solo el identificador que devuelve Wompi.
  fuente_pago=models.CharField(max_length=60,blank=True)

  cancelada_en=models.DateField(null=True,blank=True)
  creado=models.DateTimeField(auto_now_add=True)

  class Meta:
    verbose_name='Suscripcion'
    verbose_name_plural='Suscripciones'
    indexes=[
      models.Index(fields=["activa","vencimiento"]),
    ]

  def esta_vigente(self):
    if not self.activa or self.vencimiento is None:
      return False
    return self.vencimiento>=timezone.now().date()

  def activar(self,nombre_plan,precio_plan,dias_plan):
    hoy=timezone.now().date()

    if self.esta_vigente():
      self.vencimiento=self.vencimiento+timedelta(days=dias_plan)
    else:
      self.inicio=hoy
      self.vencimiento=hoy+timedelta(days=dias_plan)

    self.plan=nombre_plan
    self.precio=precio_plan
    self.activa=True
    self.cancelada_en=None
    self.save()

  def cancelar(self):
    #Cancelar no borra los dias ya pagados: apaga la renovacion y deja la
    #marca. Quitar el acceso que el usuario ya pago seria un cobro sin
    #contraprestacion.
    self.renovacion_automatica=False
    self.cancelada_en=timezone.now().date()
    self.save(update_fields=["renovacion_automatica","cancelada_en"])

  def dias_restantes(self):
    if not self.esta_vigente():
      return 0
    return (self.vencimiento-timezone.now().date()).days

  def __str__(self):
    return f"{self.usuario.username} - {self.plan} - {'Activa' if self.activa else 'Inactiva'}"