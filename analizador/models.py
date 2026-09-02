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

#=============================================================================
#  MOTOR DE PRONOSTICO 
#=============================================================================


#Foto de las fuerzas de una liga en un momento dado (ataque y defensa de cada
#equipo, ventaja local, rho y ratings Elo). Se regenera con el comando
#"python manage.py ajustar_motor". Una vez al dia sobra: las fuerzas de un
#equipo no cambian entre el jueves y el viernes.
class AjusteMotor(models.Model):
  liga=models.CharField(max_length=10,unique=True)
  parametros=models.JSONField(default=dict)
  elo=models.JSONField(default=dict)
  partidos_usados=models.IntegerField(default=0)
  temporadas=models.IntegerField(default=2)
  creado=models.DateTimeField(auto_now_add=True)
  actualizado=models.DateTimeField(auto_now=True)

  class Meta:
    verbose_name="ajuste del motor"
    verbose_name_plural="ajustes del motor"

  def __str__(self):
    return self.liga


#Cada pronostico que emite el motor queda guardado ANTES de que se juegue el
#partido. Esto es lo que hace posible la retroalimentacion honesta: sin el
#registro previo no hay forma de medirse de verdad, y "recordar" los aciertos
#a posteriori es justo la trampa que invalida a estas herramientas.
#Ojo: NO lleva usuario. El rendimiento del motor es del motor, no de quien
#pidio el pronostico; si se guardara por usuario, el mismo partido se contaria
#varias veces y las metricas saldrian infladas.
class PrediccionMotor(models.Model):
  liga=models.CharField(max_length=10,blank=True)
  id_partido=models.CharField(max_length=30,db_index=True)
  fecha=models.CharField(max_length=12,blank=True)
  equipo_local=models.CharField(max_length=80)
  equipo_visitante=models.CharField(max_length=80)
  prob_local=models.FloatField(default=0)
  prob_empate=models.FloatField(default=0)
  prob_visitante=models.FloatField(default=0)
  por_fuente=models.JSONField(default=dict)
  pesos=models.JSONField(default=dict)
  mercados=models.JSONField(default=dict)
  cuotas=models.JSONField(default=dict)
  goles_local=models.IntegerField(null=True,blank=True)
  goles_visitante=models.IntegerField(null=True,blank=True)
  resultado=models.CharField(max_length=12,blank=True)
  evaluado=models.BooleanField(default=False)
  creado=models.DateTimeField(auto_now_add=True)

  class Meta:
    verbose_name="prediccion del motor"
    verbose_name_plural="predicciones del motor"
    unique_together=("liga","id_partido")
    ordering=["-creado"]

  def __str__(self):
    return f"{self.equipo_local} vs {self.equipo_visitante}"


#Pesos de cada fuente y calibracion aprendidos por liga. Los recalcula el
#comando "python manage.py evaluar_motor" a partir de las predicciones ya
#evaluadas. Si esta tabla esta vacia el motor funciona igual, con los valores
#de fabrica: mercado 0.50, dixon_coles 0.35, elo 0.15.
class PesosMotor(models.Model):
  liga=models.CharField(max_length=10,unique=True)
  pesos=models.JSONField(default=dict)
  temperatura=models.FloatField(default=1.0)
  tramos=models.JSONField(default=dict)
  partidos_evaluados=models.IntegerField(default=0)
  log_perdida=models.FloatField(null=True,blank=True)
  rps=models.FloatField(null=True,blank=True)
  acierto=models.FloatField(null=True,blank=True)
  ece=models.FloatField(null=True,blank=True)
  creado=models.DateTimeField(auto_now_add=True)
  actualizado=models.DateTimeField(auto_now=True)

  class Meta:
    verbose_name="pesos del motor"
    verbose_name_plural="pesos del motor"

  def __str__(self):
    return self.liga