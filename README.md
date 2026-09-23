# xGol — Analizador de Goles

Plataforma web de predicción de fútbol. Un motor estadístico propio (Dixon-Coles,
Elo y cuotas del mercado, calibrado con histórico) calcula probabilidades para
las nueve ligas que cubre, y el acceso al pronóstico completo se vende por
suscripción con pago en línea (Wompi).

## Tecnologías

| Capa | Herramienta |
|---|---|
| Backend | Python 3.12, Django 6, django-allauth (entrada con Google) |
| Base de datos | MySQL 8 (conector PyMySQL) |
| Datos de fútbol | football-data.org v4, The Odds API |
| Pagos | Wompi Web Checkout + webhook firmado |
| Producción | gunicorn + whitenoise, arranque definido en `Procfile` |

## Estructura

| App | Qué hace |
|---|---|
| `inicio` | Home: partidos próximos y en vivo, tablas de posiciones, tarjeta destacada. Páginas legales. |
| `usuarios` | Registro, ingreso, perfil, panel de administración. Las reglas de validación viven en `usuarios/validaciones.py`. |
| `analizador` | Motor de predicción (`analizador/motor/`) y la herramienta de análisis para suscriptores. |
| `suscripciones` | Planes, precios y vigencia. |
| `pagos` | Checkout, webhook, conciliación, facturas PDF y panel de finanzas. |

## Puesta en marcha local

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py createcachetable
python manage.py runserver
```

`iniciar.bat` hace lo mismo y además levanta el túnel de ngrok, que es
necesario para probar pagos: Wompi rechaza (403 de CloudFront) cualquier pago
cuya dirección de regreso sea `127.0.0.1` o `localhost`, y su webhook necesita
una URL pública.

## Variables de entorno (`.env`)

El archivo `.env` no se sube al repositorio. Variables que usa `xgol/settings.py`:

| Variable | Para qué |
|---|---|
| `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS` | Django |
| `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT` | MySQL |
| `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD` | Correo (recuperar contraseña, facturas) |
| `FOOTBALL_DATA_TOKEN`, `ODDS_API_KEY` | Datos de partidos y cuotas |
| `WOMPI_AMBIENTE`, `WOMPI_LLAVE_PUBLICA`, `WOMPI_LLAVE_PRIVADA`, `WOMPI_SECRETO_INTEGRIDAD`, `WOMPI_SECRETO_EVENTOS` | Pasarela de pagos |
| `PAGOS_URL_BASE` | URL pública https del sitio (dirección de regreso tras pagar) |

## Pruebas automáticas

```bash
python manage.py test
```

Son más de 120 pruebas sobre las 5 apps. Crean una base de datos temporal (`test_<DB_NAME>`) y no llaman a ninguna API
externa: football-data.org y Wompi se sustituyen por datos de ejemplo.
Cubren:

- **usuarios**: formato de cada campo del registro, rechazo de usuario, correo
  y cédula repetidos (también a nivel de base de datos), la consulta de
  disponibilidad en vivo y su tope por IP.
- **inicio**: la lista de próximos partidos (incluido el parón de selecciones)
  y que la tarjeta del home no deje salir ningún número de pronóstico.
- **pagos**: firma de integridad, verificación del webhook, dirección de
  regreso https en producción y el precio tomado siempre del servidor.
- **suscripciones**: desglose del IVA, vigencia y renovación, cancelación sin
  perder días pagados, acceso al analizador y compra solo de planes superiores.
- **analizador**: el motor (matriz Dixon-Coles, mercados, margen de la casa,
  mezcla de fuentes, Elo, Kelly), que las 8 rutas de pago exijan suscripción y
  que cada usuario vea solo sus propias apuestas.

Correr las pruebas antes de cada despliegue.

## Comandos de mantenimiento

| Comando | Qué hace |
|---|---|
| `python manage.py conciliar_pagos` | Concilia pagos pendientes con Wompi. **No hace falta programarlo**: el sitio lo ejecuta solo una vez por hora (`pagos/middleware.py`). Se puede apagar con `CONCILIACION_AUTOMATICA=False`. |
| `python manage.py ajustar_motor` | Ajusta Dixon-Coles y Elo por liga. **Automático**: el sitio lo corre cada madrugada (3–6 a. m.) y afina cada liga una vez al mes (`analizador/middleware.py`). |
| `python manage.py descargar_historico` | Descarga el histórico de partidos con cuotas. |
| `python manage.py calibrar_con_historico` | Aprende pesos y calibración sobre el histórico. **Automático** si la base no tiene calibración (por ejemplo, un despliegue nuevo). |
| `python manage.py evaluar_motor` | Evalúa los pronósticos guardados y reaprende. **Automático** cada madrugada. |
| `python manage.py verificar_historico` | Avisa de equipos del histórico sin emparejar. |

## Despliegue

Las fotos de perfil se guardan en la base de datos (reducidas a 256 px, WebP),
no en disco: en Railway el disco se borra en cada despliegue.

El `Procfile` aplica migraciones, crea la tabla de caché, recoge los estáticos
y arranca gunicorn. Con `DEBUG=False` se activan HTTPS obligatorio, HSTS y
cookies seguras.
