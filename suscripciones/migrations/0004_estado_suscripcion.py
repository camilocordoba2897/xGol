#Estado de renovacion, cancelacion y origen de la suscripcion.

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('suscripciones', '0003_remove_suscripcion_fecha_solicitud_and_more'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='suscripcion',
            name='cancelada_en',
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='suscripcion',
            name='fuente_pago',
            field=models.CharField(blank=True, max_length=60),
        ),
        migrations.AddField(
            model_name='suscripcion',
            name='origen',
            field=models.CharField(default='pago', max_length=20),
        ),
        migrations.AddField(
            model_name='suscripcion',
            name='renovacion_automatica',
            field=models.BooleanField(default=False),
        ),
        migrations.AddIndex(
            model_name='suscripcion',
            index=models.Index(fields=['activa', 'vencimiento'], name='suscripcion_activa_28d09f_idx'),
        ),
    ]
