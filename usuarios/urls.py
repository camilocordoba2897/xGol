from django.urls import path
from usuarios.views import registro,ingresar,salir,panel_admin,editar_perfil,admin_eliminar_usuario,admin_editar_usuario,admin_estado_usuario,admin_crear_usuario

urlpatterns = [
    path('registro', registro, name="Registro"),
    path('ingresar', ingresar, name="Ingresar"),
    path('salir', salir, name="Salir"),
    path('panel-admin', panel_admin, name="PanelAdmin"),
    path('editar-perfil', editar_perfil, name="EditarPerfil"),
    path('admin-panel/usuario/crear', admin_crear_usuario, name="AdminCrearUsuario"),
    path('admin-panel/usuario/editar/<int:id>', admin_editar_usuario, name="AdminEditarUsuario"),
    path('admin-panel/usuario/eliminar/<int:id>', admin_eliminar_usuario, name="AdminEliminarUsuario"),
    path('admin-panel/usuario/estado/<int:id>', admin_estado_usuario, name="AdminEstadoUsuario"),
]