@echo off
REM ============================================================
REM  Arranca xGol en local con el tunel de ngrok.
REM  Doble clic en este archivo y listo.
REM
REM  Si algun dia cambias de dominio en ngrok, solo edita la
REM  linea DOMINIO de abajo y las tres del archivo .env.
REM ============================================================
set DOMINIO=mosaic-mortally-confetti.ngrok-free.dev

cd /d "%~dp0"

echo.
echo  Levantando el tunel en https://%DOMINIO%
start "xGol - Tunel ngrok" cmd /k ngrok.exe http 8000 --url=https://%DOMINIO%

REM Le damos unos segundos al tunel antes de arrancar Django
timeout /t 4 /nobreak >nul

echo  Arrancando el servidor...
echo.
call venv\Scripts\activate.bat
python manage.py runserver

REM Si Django se cae, la ventana no se cierra de golpe
pause
