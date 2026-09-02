#DIAGNOSTICO DE LA DESCARGA DEL HISTORICO.
#
#Se corre solo, sin Django:
#
#   python probar_csv.py
#
#Sirve para ver el error DE VERDAD. El comando verificar_historico dice "red"
#para cualquier fallo, y "red" no distingue entre que te bloquearon, que el
#archivo no existe todavia o que no hay salida a internet. Aqui se ve cual es.
#
#Cuando ya funcione, este archivo se puede borrar: no lo usa nada del proyecto.
import requests

#Se prueban las dos temporadas mas probables y las dos formas de la direccion.
#Se prueba tambien con y sin navegador simulado: si SIN navegador falla y CON
#navegador funciona, el sitio esta filtrando por User-Agent y eso ya lo arregla
#la version nueva de api_historico.py.
NAVEGADOR = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/126.0.0.0 Safari/537.36"),
    "Accept": "text/csv,text/plain,*/*",
}

PRUEBAS = [
    ("temporada actual  ", "https://www.football-data.co.uk/mmz4281/2627/E0.csv"),
    ("temporada anterior", "https://www.football-data.co.uk/mmz4281/2526/E0.csv"),
    ("temporada 24/25   ", "https://www.football-data.co.uk/mmz4281/2425/E0.csv"),
    ("sin www           ", "https://football-data.co.uk/mmz4281/2425/E0.csv"),
    ("http en vez de s  ", "http://www.football-data.co.uk/mmz4281/2425/E0.csv"),
    ("Brasil            ", "https://www.football-data.co.uk/new/BRA.csv"),
]


def intentar(url, cabeceras, etiqueta):
    try:
        r = requests.get(url, headers=cabeceras, timeout=30)
        tam = len(r.content)
        if r.status_code == 200 and tam > 200:
            #Se muestra la primera linea para confirmar que llego un CSV de
            #verdad y no una pagina de error disfrazada de exito.
            primera = r.content[:120].decode("latin-1", errors="replace").split("\n")[0]
            print(f"      {etiqueta}: OK  {tam} bytes  |  {primera[:70]}")
            return True
        print(f"      {etiqueta}: codigo {r.status_code}, {tam} bytes")
        return False
    except requests.exceptions.SSLError as e:
        print(f"      {etiqueta}: FALLO DE SSL -> {str(e)[:90]}")
    except requests.exceptions.ConnectTimeout:
        print(f"      {etiqueta}: se agoto el tiempo al conectar")
    except requests.exceptions.ConnectionError as e:
        print(f"      {etiqueta}: NO CONECTA -> {str(e)[:90]}")
    except Exception as e:
        print(f"      {etiqueta}: {type(e).__name__} -> {str(e)[:90]}")
    return False


print()
print("Probando football-data.co.uk ...")
print()
algo_funciono = False
for nombre, url in PRUEBAS:
    print(f"  {nombre}  {url}")
    a = intentar(url, None, "sin navegador ")
    b = intentar(url, NAVEGADOR, "con navegador ")
    algo_funciono = algo_funciono or a or b
    print()

print("-" * 70)
if algo_funciono:
    print("Algo si descargo. Copiame la salida y ajusto api_historico.py a eso.")
else:
    print("No descargo nada. Copiame la salida completa: el tipo de error dice")
    print("si es bloqueo del sitio, SSL de Windows, o algo de tu red/antivirus.")
print()