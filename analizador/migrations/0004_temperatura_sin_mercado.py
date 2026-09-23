from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("analizador", "0003_vaciar_registro_inflado"),
    ]

    operations = [
        migrations.AddField(
            model_name="pesosmotor",
            name="temperatura_sin_mercado",
            field=models.FloatField(default=1.0),
        ),
    ]
