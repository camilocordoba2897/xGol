import re

from django.db import migrations, models


def limpiar_documentos(apps, schema_editor):
    #Antes de crear el indice unico hay que dejar los datos en orden: si en la
    #base quedara una cedula repetida, el migrate fallaria y, como corre en el
    #Procfile antes de gunicorn, el sitio no arrancaria.
    #
    #  - "" pasa a NULL: dos cadenas vacias chocarian, dos NULL no.
    #  - Se dejan solo los digitos, igual que hace validar_documento():
    #    "1.234.567" y "1234567" son la misma persona.
    #  - Si aun asi hay repetidas, la conserva la cuenta MAS ANTIGUA y a las
    #    demas se les quita (queda NULL). Se imprime cada caso en el log del
    #    despliegue para que el administrador lo revise a mano.
    Perfil = apps.get_model("usuarios", "Perfil")
    vistos = {}
    for perfil in Perfil.objects.exclude(documento__isnull=True).order_by("creado", "id"):
        limpio = re.sub(r"\D", "", perfil.documento or "") or None
        if limpio is not None and limpio in vistos:
            print(f"\n  [usuarios] Cedula {limpio} repetida: se conserva en el perfil "
                  f"{vistos[limpio]} y se quita del perfil {perfil.id}. Revisar a mano.")
            limpio = None
        if limpio is not None:
            vistos[limpio] = perfil.id
        if limpio != perfil.documento:
            Perfil.objects.filter(pk=perfil.pk).update(documento=limpio)


class Migration(migrations.Migration):

    dependencies = [
        ('usuarios', '0003_perfil_apellidos_perfil_ciudad_perfil_documento_and_more'),
    ]

    operations = [
        migrations.RunPython(limpiar_documentos, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='perfil',
            name='documento',
            field=models.CharField(blank=True, max_length=30, null=True, unique=True),
        ),
    ]
