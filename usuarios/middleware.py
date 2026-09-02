class SinCacheEnPaginasPrivadas:
    #El problema que resuelve: al cerrar sesion y darle a la flecha de
    #"devolverse", el navegador volvia a mostrar la pagina con el usuario
    #logueado. La sesion SI estaba cerrada en el servidor: lo que se veia era
    #una copia que el navegador habia guardado en su memoria (bfcache).
    #
    #La solucion es pedirle al navegador que NO guarde esas paginas. Se hace
    #con las cabeceras de abajo, que son las que respeta el bfcache.
    #
    #Solo se aplica al HTML de las paginas. Los archivos estaticos (CSS, JS,
    #imagenes) se dejan cachear normal para no volver lento el sitio.

    def __init__(self,get_response):
        self.get_response=get_response

    def __call__(self,request):
        respuesta=self.get_response(request)

        #Las descargas (facturas en PDF) no son paginas de navegacion: si se
        #les mete no-store algunos navegadores dañan la descarga.
        if respuesta.has_header("Content-Disposition"):
            return respuesta

        tipo=respuesta.get("Content-Type","")
        if not tipo.startswith("text/html"):
            return respuesta

        #no-store es la que impide que la pagina quede guardada.
        #must-revalidate y max-age=0 cubren navegadores viejos.
        respuesta["Cache-Control"]="no-store, no-cache, must-revalidate, max-age=0"
        respuesta["Pragma"]="no-cache"
        respuesta["Expires"]="0"
        return respuesta