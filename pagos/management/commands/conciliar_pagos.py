#Mantenimiento diario del dinero. Se programa con cron (o el Programador de
#tareas de Windows) y hace tres cosas que el flujo normal no cubre:
#
#  1. Conciliar: le pregunta a la pasarela por los pagos que siguen pendientes.
#     PSE es asincrono y un webhook puede perderse; sin esto un usuario que
#     pago de verdad se queda sin acceso y reclama.
#  2. Caducar: cierra los intentos que nunca llegaron a la pasarela para que
#     no ensucien el reporte de pendientes.
#  3. Vencer: apaga las suscripciones cuya fecha ya paso y lo deja anotado.
#
#Uso:
#  python manage.py conciliar_pagos
#  python manage.py conciliar_pagos --minutos 30 --solo-conciliar
from django.core.management.base import BaseCommand
from pagos import servicios


class Command(BaseCommand):
    help="Concilia los pagos pendientes con la pasarela y actualiza el estado de las suscripciones."

    def add_arguments(self,parser):
        parser.add_argument("--minutos",type=int,default=10,
            help="Antiguedad minima de un pago pendiente para consultarlo. Por defecto 10.")
        parser.add_argument("--horas-caducidad",type=int,default=24,
            help="Horas tras las cuales un intento que nunca llego a la pasarela se anula. Por defecto 24.")
        parser.add_argument("--tope",type=int,default=50,
            help="Maximo de pagos a consultar en una corrida. Por defecto 50.")
        parser.add_argument("--solo-conciliar",action="store_true",
            help="No caduca intentos ni vence suscripciones.")

    def handle(self,*args,**opciones):
        revisados,aplicados=servicios.conciliar_pendientes(
            minutos=opciones["minutos"],tope=opciones["tope"])
        self.stdout.write(f"Conciliacion: {revisados} consultados, {aplicados} aplicados")

        if opciones["solo_conciliar"]:
            return

        caducados=servicios.caducar_pendientes(horas=opciones["horas_caducidad"])
        self.stdout.write(f"Intentos caducados: {caducados}")

        vencidas=servicios.marcar_vencidas()
        self.stdout.write(self.style.SUCCESS(f"Suscripciones vencidas: {vencidas}"))