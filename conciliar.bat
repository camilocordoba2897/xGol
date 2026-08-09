@echo off
REM ============================================================
REM  Conciliacion diaria de pagos de xGol.
REM  Lo llama el Programador de tareas de Windows.
REM  Deja constancia de cada corrida en conciliacion.log
REM ============================================================
cd /d "%~dp0"
call venv\Scripts\activate.bat
echo. >> conciliacion.log
echo ===== %DATE% %TIME% ===== >> conciliacion.log
python manage.py conciliar_pagos >> conciliacion.log 2>&1
