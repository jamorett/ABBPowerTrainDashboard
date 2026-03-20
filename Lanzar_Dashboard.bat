@echo off
echo ==============================================
echo    Abriendo Aplicacion de ABB Powertrain...
echo ==============================================
echo.
echo La aplicacion web con graficas y paneles se abrira en tu navegador por defecto (como Chrome o Edge).
echo.
echo IMPORTANTE: No cierres esta ventana negra mientras estes usando la aplicacion.
echo Cuando termines de usarla, puedes cerrar esta ventana.
echo.
python -m streamlit run app.py
pause
