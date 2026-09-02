from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("analizador", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="AjusteMotor",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True,
                                           serialize=False, verbose_name="ID")),
                ("liga", models.CharField(max_length=10, unique=True)),
                ("parametros", models.JSONField(default=dict)),
                ("elo", models.JSONField(default=dict)),
                ("partidos_usados", models.IntegerField(default=0)),
                ("temporadas", models.IntegerField(default=2)),
                ("creado", models.DateTimeField(auto_now_add=True)),
                ("actualizado", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "ajuste del motor",
                "verbose_name_plural": "ajustes del motor",
            },
        ),
        migrations.CreateModel(
            name="PrediccionMotor",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True,
                                           serialize=False, verbose_name="ID")),
                ("liga", models.CharField(blank=True, max_length=10)),
                ("id_partido", models.CharField(db_index=True, max_length=30)),
                ("fecha", models.CharField(blank=True, max_length=12)),
                ("equipo_local", models.CharField(max_length=80)),
                ("equipo_visitante", models.CharField(max_length=80)),
                ("prob_local", models.FloatField(default=0)),
                ("prob_empate", models.FloatField(default=0)),
                ("prob_visitante", models.FloatField(default=0)),
                ("por_fuente", models.JSONField(default=dict)),
                ("pesos", models.JSONField(default=dict)),
                ("mercados", models.JSONField(default=dict)),
                ("cuotas", models.JSONField(default=dict)),
                ("goles_local", models.IntegerField(blank=True, null=True)),
                ("goles_visitante", models.IntegerField(blank=True, null=True)),
                ("resultado", models.CharField(blank=True, max_length=12)),
                ("evaluado", models.BooleanField(default=False)),
                ("creado", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "verbose_name": "prediccion del motor",
                "verbose_name_plural": "predicciones del motor",
                "ordering": ["-creado"],
                "unique_together": {("liga", "id_partido")},
            },
        ),
        migrations.CreateModel(
            name="PesosMotor",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True,
                                           serialize=False, verbose_name="ID")),
                ("liga", models.CharField(max_length=10, unique=True)),
                ("pesos", models.JSONField(default=dict)),
                ("temperatura", models.FloatField(default=1.0)),
                ("tramos", models.JSONField(default=dict)),
                ("partidos_evaluados", models.IntegerField(default=0)),
                ("log_perdida", models.FloatField(blank=True, null=True)),
                ("rps", models.FloatField(blank=True, null=True)),
                ("acierto", models.FloatField(blank=True, null=True)),
                ("ece", models.FloatField(blank=True, null=True)),
                ("creado", models.DateTimeField(auto_now_add=True)),
                ("actualizado", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "pesos del motor",
                "verbose_name_plural": "pesos del motor",
            },
        ),
    ]