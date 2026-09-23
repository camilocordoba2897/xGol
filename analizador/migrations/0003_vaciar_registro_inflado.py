from django.db import migrations


#Hasta el commit ff21e59 el seguimiento evaluaba cada partido RECALCULANDO
#las probabilidades despues de jugado, con un historial que ya traia ese
#resultado. Esas filas inflaban el "Acierto del modelo" del panel (72,4 %).
#No hay forma de separarlas de las buenas (guardar_apuestas reescribe todo el
#registro en cada guardado y "creado" se renueva), asi que se vacia entero
#una sola vez. Lo que se evalue de aqui en adelante ya usa la foto previa.
def vaciar(apps, schema_editor):
    apps.get_model("analizador", "RegistroApuesta").objects.all().delete()
    apps.get_model("analizador", "PartidoRegistrado").objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("analizador", "0002_motor"),
    ]

    operations = [
        migrations.RunPython(vaciar, migrations.RunPython.noop),
    ]
