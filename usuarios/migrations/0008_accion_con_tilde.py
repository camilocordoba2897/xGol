from django.db import migrations


def poner_tilde(apps, schema_editor):
    #Los accesos viejos se guardaron como "Inicio de sesion". Con la tilde
    #coinciden con el texto que el panel traduce al idioma elegido.
    Bitacora = apps.get_model("usuarios", "Bitacora")
    Bitacora.objects.filter(accion="Inicio de sesion").update(accion="Inicio de sesión")


class Migration(migrations.Migration):

    dependencies = [
        ('usuarios', '0007_perfil_idioma'),
    ]

    operations = [
        migrations.RunPython(poner_tilde, migrations.RunPython.noop),
    ]
