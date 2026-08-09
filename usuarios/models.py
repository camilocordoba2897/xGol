from django.db import models
from django.contrib.auth.models import User

class Rol(models.Model):
  nombre=models.CharField(max_length=30,verbose_name="Rol")
  descripcion=models.CharField(max_length=120,blank=True,null=True)
  creado=models.DateTimeField(auto_now_add=True)

  class Meta:
    verbose_name="Rol"
    verbose_name_plural="Roles"

  def __str__(self):
    return self.nombre

class Perfil(models.Model):
  usuario=models.OneToOneField(User,on_delete=models.CASCADE,related_name="perfil")
  rol=models.ForeignKey(Rol,on_delete=models.SET_NULL,null=True,blank=True)
  nombre=models.CharField(max_length=60,null=True,blank=True)
  apellidos=models.CharField(max_length=60,null=True,blank=True)
  tipo_documento=models.CharField(max_length=20,null=True,blank=True)
  documento=models.CharField(max_length=30,null=True,blank=True)
  fecha_nacimiento=models.DateField(null=True,blank=True)
  ciudad=models.CharField(max_length=60,null=True,blank=True)
  pais=models.CharField(max_length=60,null=True,blank=True)
  telefono=models.CharField(max_length=20,null=True,blank=True)
  avatar=models.ImageField(upload_to='avatares',null=True,blank=True)
  proveedor=models.CharField(max_length=20,default='local')
  creado=models.DateTimeField(auto_now_add=True)

  class Meta:
    verbose_name='Perfil'
    verbose_name_plural='Perfiles'

  def __str__(self):
    return self.usuario.username


class Bitacora(models.Model):
  usuario=models.ForeignKey(User,on_delete=models.CASCADE,blank=True,null=True)
  accion=models.CharField(max_length=120)
  ip=models.CharField(max_length=40,blank=True,null=True)
  agente=models.CharField(max_length=200,blank=True,null=True)
  creado=models.DateTimeField(auto_now_add=True)

  class Meta:
    verbose_name="Bitacora"
    verbose_name_plural="Bitacoras"

  def __str__(self):
    return f"{self.accion} — {self.usuario}"