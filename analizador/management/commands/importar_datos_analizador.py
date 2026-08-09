import csv
import json
from datetime import datetime,timezone
from pathlib import Path
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.conf import settings
from analizador.models import BibliotecaEquipo,PartidoRegistrado,RegistroApuesta

ICONOS_MERCADO={
    "1X2":"🏆","Goles":"⚽","BTTS":"🤝","Córners":"🚩",
    "Tiros a puerta":"🎯","Tiros":"💥","Tarjetas":"🟨","Mitades":"⏱️",
}

def _ts_desde_fecha(fecha,indice):
    #Genera un ts numerico plausible (ms) a partir de la fecha del partido
    try:
        d=datetime.strptime(fecha,"%Y-%m-%d").replace(hour=12,tzinfo=timezone.utc)
        return int(d.timestamp()*1000)+indice
    except (ValueError,TypeError):
        return 1000000000000+indice

class Command(BaseCommand):
    help="Importa la biblioteca de equipos (JSON) y el registro de apuestas (CSV) a MySQL para un usuario."

    def add_arguments(self,parser):
        parser.add_argument("--usuario",type=str,default=None,
            help="Username destino. Por defecto, el primer superusuario.")
        parser.add_argument("--biblioteca",type=str,default=None,
            help="Ruta al JSON de biblioteca. Por defecto: biblioteca_equipos.json en la raiz.")
        parser.add_argument("--apuestas",type=str,default=None,
            help="Ruta al CSV de apuestas. Por defecto: registro_apuestas_.csv en la raiz.")

    def handle(self,*args,**opciones):
        #1) Resolver usuario destino
        if opciones["usuario"]:
            usuario=User.objects.filter(username=opciones["usuario"]).first()
            if not usuario:
                self.stderr.write(self.style.ERROR(f"No existe el usuario '{opciones['usuario']}'."))
                return
        else:
            usuario=User.objects.filter(is_superuser=True).order_by("id").first()
            if not usuario:
                self.stderr.write(self.style.ERROR("No hay superusuarios. Crea uno o pasa --usuario."))
                return
        self.stdout.write(f"Usuario destino: {usuario.username}")

        #2) Rutas de los archivos
        raiz=Path(settings.BASE_DIR)
        ruta_biblioteca=Path(opciones["biblioteca"]) if opciones["biblioteca"] else raiz/"biblioteca_equipos.json"
        ruta_apuestas=Path(opciones["apuestas"]) if opciones["apuestas"] else raiz/"registro_apuestas_.csv"

        #3) Limpiar los datos previos de este usuario (reemplazo total)
        BibliotecaEquipo.objects.filter(usuario=usuario).delete()
        PartidoRegistrado.objects.filter(usuario=usuario).delete()
        RegistroApuesta.objects.filter(usuario=usuario).delete()

        #4) Importar biblioteca de equipos
        if ruta_biblioteca.exists():
            with open(ruta_biblioteca,encoding="utf-8") as f:
                biblioteca=json.load(f)
            equipos=[]
            for nombre,info in biblioteca.items():
                equipos.append(BibliotecaEquipo(
                    usuario=usuario,
                    nombre=str(nombre)[:80],
                    partidos=info.get("rows",[]),
                    guardado=str(info.get("savedAt",""))[:40]
                ))
            BibliotecaEquipo.objects.bulk_create(equipos)
            self.stdout.write(self.style.SUCCESS(f"Biblioteca: {len(equipos)} equipos importados."))
        else:
            self.stdout.write(self.style.WARNING(f"No se encontro {ruta_biblioteca.name}, se omite la biblioteca."))

        #5) Importar registro de apuestas (agrupando por partido para el ts)
        if ruta_apuestas.exists():
            grupos={}
            orden=[]
            with open(ruta_apuestas,newline="",encoding="utf-8") as f:
                lector=csv.DictReader(f)
                for fila in lector:
                    clave=(fila.get("fecha",""),fila.get("team1",""),fila.get("team2",""),fila.get("league",""))
                    if clave not in grupos:
                        grupos[clave]=[]
                        orden.append(clave)
                    grupos[clave].append(fila)

            apuestas=[]
            for indice,clave in enumerate(orden):
                fecha,team1,team2,league=clave
                ts=_ts_desde_fecha(fecha,indice)
                for fila in grupos[clave]:
                    cuota=fila.get("cuota","").strip()
                    try:
                        cuota=float(cuota) if cuota else None
                    except ValueError:
                        cuota=None
                    try:
                        prob=float(fila.get("prob","") or 0)
                    except ValueError:
                        prob=0
                    mercado=str(fila.get("market","") or "")[:30]
                    apuestas.append(RegistroApuesta(
                        usuario=usuario,
                        referencia=str(ts),
                        fecha=str(fecha)[:12],
                        equipo_local=str(team1)[:80],
                        equipo_visitante=str(team2)[:80],
                        liga=str(league)[:80],
                        mercado=mercado,
                        icono=ICONOS_MERCADO.get(mercado,"🎯"),
                        etiqueta=str(fila.get("label","") or "")[:120],
                        probabilidad=prob,
                        acierto=str(fila.get("hit","")).strip()=="1",
                        propia=str(fila.get("mia","")).strip()=="1",
                        cuota=cuota
                    ))
            RegistroApuesta.objects.bulk_create(apuestas)
            self.stdout.write(self.style.SUCCESS(
                f"Apuestas: {len(apuestas)} registros importados en {len(orden)} partidos."))
        else:
            self.stdout.write(self.style.WARNING(f"No se encontro {ruta_apuestas.name}, se omite el registro."))

        self.stdout.write(self.style.SUCCESS("Importacion terminada."))