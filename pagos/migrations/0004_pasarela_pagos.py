#Sistema de pagos con pasarela: bitacora de eventos, reembolsos, movimientos
#de suscripcion y consecutivo de facturas.

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


#Nombre del plan visible -> clave en suscripciones.planes
CLAVES_PLAN={"Mensual":"mensual","Trimestral":"trimestral"}


def normalizar_pagos(apps,schema_editor):
    """Deja los pagos que ya existian coherentes con el modelo nuevo.

    - Los pagos aprobados de antes YA otorgaron dias, asi que se marcan como
      aplicados. Si no, la primera conciliacion volveria a sumarlos.
    - numero_factura vacio pasa a NULL (MySQL admite varios NULL en un indice
      unico, pero no varias cadenas vacias iguales).
    - Si hubiera numeros repetidos de verdad, se les agrega un sufijo para que
      el UNIQUE del paso siguiente no falle. Queda visible en el propio numero
      para poder auditarlo despues.
    """
    Pago=apps.get_model("pagos","Pago")
    Consecutivo=apps.get_model("pagos","Consecutivo")

    vistos=set()
    mayor=0
    for pago in Pago.objects.all().order_by("id").iterator():
        cambios=["pasarela","ambiente"]
        pago.pasarela="manual"
        pago.ambiente="historico"

        if not pago.clave_plan:
            pago.clave_plan=CLAVES_PLAN.get(pago.plan,"")
            cambios.append("clave_plan")

        if not pago.monto_centavos:
            pago.monto_centavos=(pago.monto or 0)*100
            cambios.append("monto_centavos")

        if pago.estado=="Aprobado" and not pago.aplicado:
            pago.aplicado=True
            pago.aprobado_en=pago.creado
            cambios.append("aplicado")
            cambios.append("aprobado_en")

        numero=(pago.numero_factura or "").strip()
        if not numero:
            pago.numero_factura=None
            cambios.append("numero_factura")
        else:
            #El consecutivo se calcula sobre el numero ORIGINAL, antes de
            #desduplicar: si se hiciera despues, el sufijo "-D7" se leeria
            #como parte del numero y dispararia la numeracion.
            digitos="".join(c for c in numero if c.isdigit())
            if digitos:
                mayor=max(mayor,int(digitos))
            if numero in vistos:
                numero=f"{numero}-D{pago.id}"
                pago.numero_factura=numero
                cambios.append("numero_factura")
            vistos.add(numero)

        pago.save(update_fields=list(dict.fromkeys(cambios)))

    #El consecutivo arranca donde quedo la numeracion vieja para no repetir
    #numeros de factura ya emitidos.
    Consecutivo.objects.update_or_create(nombre="factura",defaults={"valor":mayor})


def revertir_normalizacion(apps,schema_editor):
    #Al revertir solo hay que devolver los NULL a cadena vacia; el resto de
    #campos desaparecen con las AddField.
    Pago=apps.get_model("pagos","Pago")
    Pago.objects.filter(numero_factura=None).update(numero_factura="")


class Migration(migrations.Migration):

    dependencies = [
        ('pagos', '0003_pago_iva_pago_subtotal'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Consecutivo',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nombre', models.CharField(max_length=40, unique=True)),
                ('valor', models.BigIntegerField(default=0)),
                ('actualizado', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Consecutivo',
                'verbose_name_plural': 'Consecutivos',
            },
        ),
        migrations.CreateModel(
            name='EventoPasarela',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('pasarela', models.CharField(default='wompi', max_length=20)),
                ('tipo', models.CharField(blank=True, max_length=40)),
                ('ambiente', models.CharField(blank=True, max_length=10)),
                ('id_pasarela', models.CharField(blank=True, db_index=True, max_length=60)),
                ('referencia', models.CharField(blank=True, db_index=True, max_length=40)),
                ('estado_reportado', models.CharField(blank=True, max_length=30)),
                ('monto_centavos', models.BigIntegerField(default=0)),
                ('checksum', models.CharField(max_length=80, unique=True)),
                ('firma_valida', models.BooleanField(default=False)),
                ('procesado', models.BooleanField(default=False)),
                ('detalle', models.TextField(blank=True)),
                ('cuerpo', models.JSONField(default=dict)),
                ('ip', models.CharField(blank=True, max_length=45)),
                ('creado', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'verbose_name': 'Evento de pasarela',
                'verbose_name_plural': 'Eventos de pasarela',
                'ordering': ['-creado'],
            },
        ),
        migrations.CreateModel(
            name='MovimientoSuscripcion',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('tipo', models.CharField(choices=[('Activacion', 'Activacion'), ('Renovacion', 'Renovacion'), ('Cancelacion', 'Cancelacion'), ('Vencimiento', 'Vencimiento'), ('Reembolso', 'Reembolso'), ('AjusteAdmin', 'AjusteAdmin')], max_length=20)),
                ('plan', models.CharField(blank=True, max_length=30)),
                ('dias', models.IntegerField(default=0)),
                ('vencimiento_anterior', models.DateField(blank=True, null=True)),
                ('vencimiento_nuevo', models.DateField(blank=True, null=True)),
                ('nota', models.CharField(blank=True, max_length=200)),
                ('creado', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'verbose_name': 'Movimiento de suscripcion',
                'verbose_name_plural': 'Movimientos de suscripcion',
                'ordering': ['-creado'],
            },
        ),
        migrations.CreateModel(
            name='Reembolso',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('monto', models.IntegerField(default=0)),
                ('motivo', models.CharField(blank=True, max_length=200)),
                ('estado', models.CharField(choices=[('Solicitado', 'Solicitado'), ('Aprobado', 'Aprobado'), ('Rechazado', 'Rechazado')], default='Solicitado', max_length=20)),
                ('referencia_externa', models.CharField(blank=True, max_length=60)),
                ('revoca_dias', models.BooleanField(default=True)),
                ('creado', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'verbose_name': 'Reembolso',
                'verbose_name_plural': 'Reembolsos',
                'ordering': ['-creado'],
            },
        ),
        migrations.AddField(
            model_name='pago',
            name='actualizado',
            field=models.DateTimeField(auto_now=True),
        ),
        migrations.AddField(
            model_name='pago',
            name='ambiente',
            field=models.CharField(default='test', max_length=10),
        ),
        migrations.AddField(
            model_name='pago',
            name='aplicado',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='pago',
            name='aprobado_en',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='pago',
            name='clave_plan',
            field=models.CharField(blank=True, max_length=30),
        ),
        migrations.AddField(
            model_name='pago',
            name='comision',
            field=models.IntegerField(default=0),
        ),
        migrations.AddField(
            model_name='pago',
            name='correo_pagador',
            field=models.EmailField(blank=True, max_length=254),
        ),
        migrations.AddField(
            model_name='pago',
            name='dias_otorgados',
            field=models.IntegerField(default=0),
        ),
        migrations.AddField(
            model_name='pago',
            name='id_pasarela',
            field=models.CharField(blank=True, db_index=True, max_length=60),
        ),
        migrations.AddField(
            model_name='pago',
            name='ip',
            field=models.CharField(blank=True, max_length=45),
        ),
        migrations.AddField(
            model_name='pago',
            name='mensaje',
            field=models.CharField(blank=True, max_length=200),
        ),
        migrations.AddField(
            model_name='pago',
            name='metodo_detalle',
            field=models.CharField(blank=True, max_length=40),
        ),
        migrations.AddField(
            model_name='pago',
            name='moneda',
            field=models.CharField(default='COP', max_length=3),
        ),
        migrations.AddField(
            model_name='pago',
            name='monto_centavos',
            field=models.BigIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='pago',
            name='neto',
            field=models.IntegerField(default=0),
        ),
        migrations.AddField(
            model_name='pago',
            name='pasarela',
            field=models.CharField(default='wompi', max_length=20),
        ),
        migrations.AddField(
            model_name='pago',
            name='vigencia_fin',
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='pago',
            name='vigencia_inicio',
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='pago',
            name='estado',
            field=models.CharField(choices=[('Pendiente', 'Pendiente'), ('Aprobado', 'Aprobado'), ('Rechazado', 'Rechazado'), ('Anulado', 'Anulado'), ('Error', 'Error'), ('Reembolsado', 'Reembolsado')], default='Pendiente', max_length=20),
        ),
        #--- numero_factura: se hace en tres pasos porque las filas viejas
        #--- tienen "" repetido y un UNIQUE directo reventaria la migracion.
        migrations.AlterField(
            model_name='pago',
            name='numero_factura',
            field=models.CharField(blank=True, max_length=30, null=True),
        ),
        migrations.RunPython(normalizar_pagos, revertir_normalizacion),
        migrations.AlterField(
            model_name='pago',
            name='numero_factura',
            field=models.CharField(blank=True, max_length=30, null=True, unique=True),
        ),
        migrations.AddIndex(
            model_name='pago',
            index=models.Index(fields=['estado', 'creado'], name='pagos_pago_estado_0fe640_idx'),
        ),
        migrations.AddIndex(
            model_name='pago',
            index=models.Index(fields=['usuario', 'estado'], name='pagos_pago_usuario_28c03c_idx'),
        ),
        migrations.AddField(
            model_name='movimientosuscripcion',
            name='actor',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='movimientos_ejecutados', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='movimientosuscripcion',
            name='pago',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='movimientos', to='pagos.pago'),
        ),
        migrations.AddField(
            model_name='movimientosuscripcion',
            name='usuario',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='movimientos_suscripcion', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='reembolso',
            name='creado_por',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='reembolsos_creados', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='reembolso',
            name='pago',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='reembolsos', to='pagos.pago'),
        ),
    ]
