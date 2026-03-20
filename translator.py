def translate_condition(cond):
    if not isinstance(cond, str): return "Desconocido"
    mapping = {
        "Good": "Óptimo",
        "Normal": "Normal",
        "OK": "OK",
        "Tolerable": "Tolerable",
        "Warning": "Advertencia",
        "Alarm": "Alarma Crítica",
        "Error": "Fallo",
        "Poor": "Deficiente",
        "Bad": "Malo",
        "Critical": "Crítico"
    }
    return mapping.get(cond, cond)

def translate_severity(sev):
    if not isinstance(sev, str): return "Sin Clasificar"
    mapping = {
        "Warning": "Advertencia",
        "Alert": "Alerta",
        "Error": "Error",
        "Alarm": "Alarma",
        "Info": "Información",
        "Unknown": "Desconocido",
        "Open": "Abierto",
        "Closed": "Cerrado"
    }
    return mapping.get(sev, sev)

def translate_kpi_name(name):
    if not isinstance(name, str): return "Desconocido"
    mapping = {
        "Overall Vibration": "Vibración General",
        "Skin Temperature": "Temperatura Superficial",
        "Temperature": "Temperatura",
        "Bearing condition": "Condición de Rodamientos",
        "Motor Anomaly Detection": "Detección de Anomalías",
        "Vibration RMS Axial": "Vibración RMS Axial",
        "Vibration RMS Radial": "Vibración RMS Radial",
        "Vibration RMS Tangential": "Vibración RMS Tangencial",
        "Vibration RMS Axial (long term)": "Vibración Axial (Largo Plazo)",
        "Vibration RMS Radial (long term)": "Vibración Radial (Largo Plazo)",
        "Vibration RMS Tangential (long term)": "Vibración Tangencial (Largo Plazo)",
        "Vibration RMS Axial (short term)": "Vibración Axial (Corto Plazo)",
        "Vibration RMS Radial (short term)": "Vibración Radial (Corto Plazo)",
        "Vibration RMS Tangential (short term)": "Vibración Tangencial (Corto Plazo)",
        "Operating Speed": "Velocidad de Operación",
        "Operating speed": "Velocidad de Operación"
    }
    for eng, spa in mapping.items():
        if eng.lower() == name.lower():
            return spa
    return name.title()

def translate_message(msg):
    if not isinstance(msg, str): return str(msg)
    
    # Reemplazo de Nombres de Variables insertadas en los Strings
    kpi_map = {
        "Overall Vibration": "Vibración General",
        "Skin Temperature": "Temperatura Superficial",
        "Bearing condition": "Condición de Rodamientos",
        "Motor Anomaly Detection": "Detección de Anomalías",
        "Vibration RMS Axial": "Vibración RMS Axial",
        "Vibration RMS Radial": "Vibración RMS Radial",
        "Vibration RMS Tangential": "Vibración RMS Tangencial"
    }
    for eng, spa in kpi_map.items():
        # Captura tanto palabras solas como palabras entre comillas
        msg = msg.replace(f"'{eng}'", f"'{spa}'")
        msg = msg.replace(eng, spa)
        
    replacements = [
        ("value", "valor"),
        (" returned to normal between limits", " se normalizó dentro de los rangos"),
        (" returned to normal below upper limit ", " se normalizó por debajo del límite de "),
        (" returned to normal above lower limit ", " se normalizó por encima del límite de "),
        (" is above upper limit ", " excedió el límite superior de "),
        (" is below lower limit ", " cayó por debajo del límite de "),
        ("exceed upper limit", "excedió el límite superior"),
        ("drop below lower limit", "cayó por debajo del límite inferior"),
        ("Confirm with detailed vibration analysis", "Se sugiere confirmar con análisis detallado de vibración"),
        ("WarningLimit", "Límite de Advertencia"),
        ("ErrorLimit", "Límite de Error"),
        ("Warning", "Advertencia"),
        ("Error", "Error"),
        ("Alarm", "Alarma")
    ]
    
    for eng, spa in replacements:
        msg = msg.replace(eng, spa)
        
    # Limpieza final de espacios o basura en el logger
    return msg.strip()
