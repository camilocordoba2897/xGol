from django.db import models
from django.contrib.auth.models import User

#Cada equipo guardado en la biblioteca del analizador (antes vivia en localStorage)
class BibliotecaEquipo(models.Model):
  usuario=models.ForeignKey(User,on_delete=models.CASCADE,related_name="equipos_biblioteca")
  nombre=models.CharField(max_length=80)
  partidos=models.JSONField(default=list)
  guardado=models.CharField(max_length=40,blank=True)
  creado=models.DateTimeField(auto_now_add=True)

  class Meta:
    verbose_name="equipo de biblioteca"
    verbose_name_plural="biblioteca de equipos"
    unique_together=("usuario","nombre")
    ordering=["nombre"]

  def __str__(self):
    return self.nombre


#Partido registrado en el historial de apuestas (datos crudos para poder editarlo)
class PartidoRegistrado(models.Model):
  usuario=models.ForeignKey(User,on_delete=models.CASCADE,related_name="partidos_registrados")
  referencia=models.CharField(max_length=30)
  fecha=models.CharField(max_length=12,blank=True)
  equipo_local=models.CharField(max_length=80)
  equipo_visitante=models.CharField(max_length=80)
  liga=models.CharField(max_length=80,blank=True)
  datos=models.JSONField(default=dict)
  creado=models.DateTimeField(auto_now_add=True)

  class Meta:
    verbose_name="partido registrado"
    verbose_name_plural="partidos registrados"
    unique_together=("usuario","referencia")

  def __str__(self):
    return f"{self.equipo_local} vs {self.equipo_visitante}"


#Cada apuesta evaluada del registro (retroalimenta la calibracion del modelo)
class RegistroApuesta(models.Model):
  usuario=models.ForeignKey(User,on_delete=models.CASCADE,related_name="apuestas_registradas")
  referencia=models.CharField(max_length=30)
  fecha=models.CharField(max_length=12,blank=True)
  equipo_local=models.CharField(max_length=80)
  equipo_visitante=models.CharField(max_length=80)
  liga=models.CharField(max_length=80,blank=True)
  mercado=models.CharField(max_length=30)
  icono=models.CharField(max_length=8,blank=True)
  etiqueta=models.CharField(max_length=120)
  probabilidad=models.FloatField(default=0)
  acierto=models.BooleanField(default=False)
  propia=models.BooleanField(default=False)
  cuota=models.FloatField(null=True,blank=True)
  creado=models.DateTimeField(auto_now_add=True)

  class Meta:
    verbose_name="apuesta registrada"
    verbose_name_plural="apuestas registradas"
    ordering=["-creado"]

  def __str__(self):
    return f"{self.etiqueta} ({self.mercado})"
