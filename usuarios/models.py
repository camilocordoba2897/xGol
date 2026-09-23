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
  #unique: la validacion del registro ya lo revisa, pero dos registros
  #simultaneos pasarian los dos. El indice de la base es la garantia final.
  #Las cuentas sin cedula (Google, alta del panel) guardan NULL, y en MySQL
  #varios NULL no chocan entre si.
  documento=models.CharField(max_length=30,null=True,blank=True,unique=True)
  fecha_nacimiento=models.DateField(null=True,blank=True)
  ciudad=models.CharField(max_length=60,null=True,blank=True)
  pais=models.CharField(max_length=60,null=True,blank=True)
  telefono=models.CharField(max_length=20,null=True,blank=True)
  #La foto va EN LA BASE DE DATOS, reducida a 256 px y en WebP (10-25 KB),
  #como data URI. En Railway el disco se borra en cada despliegue: guardada
  #como archivo, la foto de perfil desaparecia con cada actualizacion.
  foto=models.TextField(blank=True,default="")
  proveedor=models.CharField(max_length=20,default='local')
  creado=models.DateTimeField(auto_now_add=True)

  class Meta:
    verbose_name='Perfil'
    verbose_name_plural='Perfiles'

  def __str__(self):
    return self.usuario.username

  @property
  def foto_url(self):
    #Lo que se pone en el src de la imagen. Sin foto, la plantilla pinta la
    #inicial. (El archivo viejo "avatar" ya no existe: la migracion 0005 paso
    #las fotos a la base, y en Railway esos archivos se borraban en cada
    #despliegue, asi que solo daban imagenes rotas.)
    return self.foto or ""

  def identidad_completa(self):
    #Cedula y fecha de nacimiento: sin ellas no se puede comprar un plan.
    #El registro normal las exige, pero las cuentas de Google y las que crea
    #el administrador no pasan por ahi.
    return bool(self.documento and self.fecha_nacimiento)


def falta_identidad(usuario):
  perfil=getattr(usuario,"perfil",None)
  return perfil is None or not perfil.identidad_completa()


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