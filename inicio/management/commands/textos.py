#python manage.py textos            -> extrae los textos, actualiza los .po y compila los .mo
#python manage.py textos --revisar  -> solo revisa; falla si falta traducir algo
#Ver xgol/textos.py
from django.core.management.base import BaseCommand, CommandError

from xgol import textos

NOMBRES = {"en": "inglés", "pt-br": "portugués", "de": "alemán"}


class Command(BaseCommand):
    help = "Extrae los textos traducibles, actualiza locale/*.po y compila los .mo"

    def add_arguments(self, parser):
        parser.add_argument("--revisar", action="store_true",
                            help="No escribe nada: avisa si falta traducir o compilar algo")

    def handle(self, *args, revisar=False, **opciones):
        try:
            informe = textos.actualizar(escribir=not revisar)
        except textos.TextoNoExtraible as e:
            raise CommandError(str(e))
        total = sum(len(c) for c in informe["textos"].values())
        self.stdout.write(f"Textos del sitio: {total}")
        for archivo in informe["cambios"]:
            self.stdout.write(("Desactualizado: " if revisar else "Actualizado: ") + archivo)
        problemas = bool(revisar and informe["cambios"])
        for idioma, dominios in informe["faltan"].items():
            for dominio, claves in dominios.items():
                problemas = True
                self.stdout.write(self.style.WARNING(
                    f"Sin traducir al {NOMBRES[idioma]} ({dominio}): {len(claves)}"))
                for _, texto, _ in claves[:10]:
                    self.stdout.write(f"   - {texto[:90]}")
        if problemas and revisar:
            raise CommandError("Faltan traducciones o compilar: corre 'python manage.py textos'")
        if not problemas:
            self.stdout.write(self.style.SUCCESS("Todo traducido y compilado."))
