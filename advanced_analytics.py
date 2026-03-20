import pandas as pd
import numpy as np
import scipy.signal as signal
import datetime

def analyze_fft(fft_raw):
    """
    Analiza el último espectro FFT buscando picos de armónicos ISO y fallas eléctricas.
    Aplica análisis por eje individual (Reglas 1-3) y análisis cruzado multi-eje (Regla 4).
    Norma de referencia: ISO 13373-2 Sección 7.3 (Diagnóstico por espectro vibracional).
    Retorna una lista de alertas (strings) si encuentra anomalías.
    """
    if not fft_raw or "spectrum" not in fft_raw or "sensors" not in fft_raw:
        return []

    alerts = []

    for sensor in fft_raw.get("sensors", []):
        # Recolectar picos 1X y 2X por nombre de eje para análisis cruzado posterior
        peaks_by_axis = {}   # { axis_label: {"mag_1x": float, "f_1x": float, "mag_2x": float} }

        for axis_data in sensor.get("dataValues", []):
            vals = axis_data.get("sensorAxisDataValues", [])
            if not vals:
                continue

            df_fft = pd.DataFrame(vals)
            if df_fft.empty or 'frequency' not in df_fft or 'magnitude' not in df_fft:
                continue

            axis_name = axis_data.get("sensorAxisName", "Desconocido")

            # Ventana 20-35 Hz para el 1X (evita contaminación eléctrica de 50/60 Hz)
            window_1x = df_fft[(df_fft['frequency'] >= 20) & (df_fft['frequency'] <= 35)]
            if window_1x.empty:
                continue

            idx_1x = window_1x['magnitude'].idxmax()
            f_1x  = df_fft.loc[idx_1x, 'frequency']
            mag_1x = df_fft.loc[idx_1x, 'magnitude']

            if mag_1x < 0.1:  # Ruido base — motor apagado
                continue

            # Buscar 2X
            f_2x_target = f_1x * 2
            window_2x = df_fft[(df_fft['frequency'] >= f_2x_target * 0.95) &
                                (df_fft['frequency'] <= f_2x_target * 1.05)]
            mag_2x = 0.0
            f_2x   = f_2x_target
            if not window_2x.empty:
                idx_2x = window_2x['magnitude'].idxmax()
                mag_2x = df_fft.loc[idx_2x, 'magnitude']
                f_2x   = df_fft.loc[idx_2x, 'frequency']

            # Guardar para análisis cruzado multi-eje
            # Normalizar el nombre a minúsculas para comparación robusta
            axis_key = axis_name.lower()
            peaks_by_axis[axis_key] = {
                "label": axis_name, "mag_1x": mag_1x,
                "f_1x": f_1x, "mag_2x": mag_2x, "f_2x": f_2x
            }

            # ── REGLA 1: Desbalanceo (ISO 10816-3) ──────────────────────────────────
            # Un pico 1X muy dominante en todos los ejes radiales indica masa excéntrica.
            # Umbral: mag_1x > 1.5 (aprox. Zona C de ISO 10816-3 para máquinas medianas)
            if mag_1x > 1.5:
                alerts.append(
                    f"[FFT {axis_name}] 💥 Desbalanceo Severo detectado — "
                    f"Pico 1X en {f_1x:.1f} Hz con magnitud {mag_1x:.2f}. "
                    f"(ISO 10816-3: supera umbral Zona C)"
                )

            # ── REGLA 2: Desalineación por armónico intra-eje (ISO 13373-2 §7.3) ───
            # Si el 2X supera el 50% del 1X en el mismo eje, hay energía anómala en 2X.
            if mag_2x > (0.5 * mag_1x):
                alerts.append(
                    f"[FFT {axis_name}] 🗜️ Señal de Desalineación — "
                    f"Armónico 2X en {f_2x:.1f} Hz supera el 50% del 1X "
                    f"({mag_2x:.2f} vs {mag_1x:.2f}). (ISO 13373-2 §7.3)"
                )

            # ── REGLA 3: Interferencia Eléctrica (IEC 60034-14) ─────────────────────
            # Picos en 100/120 Hz indican vibración electromagnética de la red
            # (2 × frecuencia de línea: 2×50=100 Hz o 2×60=120 Hz)
            for f_linea in [100, 120]:
                window_el = df_fft[(df_fft['frequency'] >= f_linea - 1.5) &
                                   (df_fft['frequency'] <= f_linea + 1.5)]
                if not window_el.empty:
                    idx_el = window_el['magnitude'].idxmax()
                    mag_el = df_fft.loc[idx_el, 'magnitude']
                    if mag_el > 0.8:
                        alerts.append(
                            f"[FFT {axis_name}] ⚡ Interferencia Eléctrica — "
                            f"Pico detectado en {f_linea} Hz (2× red) con magnitud {mag_el:.2f}. "
                            f"Revisar estator o barra de rotor. (IEC 60034-14)"
                        )

            # ── REGLA 5: Sub-armónico 0.5X — Holgura / Oil Whirl (ISO 13373-2 §7.4) ─
            # Un pico significativo en la mitad de la frecuencia fundamental (0.5X)
            # puede indicar: partes sueltas, resonancias o inestabilidad de película
            # de aceite en cojinetes de tipo fluido-dinámico.
            # Umbral: mag_05x > 25% del 1X (señal relevante, no ruido de fondo)
            f_05x_target = f_1x * 0.5
            window_05x = df_fft[(df_fft['frequency'] >= f_05x_target * 0.85) &
                                 (df_fft['frequency'] <= f_05x_target * 1.15)]
            if not window_05x.empty:
                idx_05x = window_05x['magnitude'].idxmax()
                mag_05x = df_fft.loc[idx_05x, 'magnitude']
                f_05x   = df_fft.loc[idx_05x, 'frequency']
                if mag_05x > (0.25 * mag_1x):
                    alerts.append(
                        f"[FFT {axis_name}] 🔩 Sub-armónico detectado (0.5X) — "
                        f"Pico en {f_05x:.1f} Hz con magnitud {mag_05x:.2f} "
                        f"({mag_05x/mag_1x*100:.0f}% del 1X). "
                        f"Posible holgura mecánica o inestabilidad de cojinete. "
                        f"(ISO 13373-2 §7.4)"
                    )

            # ── REGLA 6: Patrón de Holgura Estructural — familia de armónicos ────────
            # (ISO 13373-2 §7.5, Patrón de Falla A5)
            # La presencia simultánea de 3 o más armónicos (1X, 2X, 3X, 4X) con
            # amplitudes significativas indica vibración por holgura:
            # tornillos flojos, base mal fijada, chumaceras desgastadas.
            threshold_harmonic = 0.20 * mag_1x  # Armónico debe tener > 20% del 1X
            harmonics_present = 0
            harmonic_details  = []

            for n_harm, label in [(2, "2X"), (3, "3X"), (4, "4X")]:
                f_target = f_1x * n_harm
                w_harm = df_fft[(df_fft['frequency'] >= f_target * 0.95) &
                                (df_fft['frequency'] <= f_target * 1.05)]
                if not w_harm.empty:
                    m_harm = df_fft.loc[w_harm['magnitude'].idxmax(), 'magnitude']
                    if m_harm > threshold_harmonic:
                        harmonics_present += 1
                        harmonic_details.append(f"{label}={m_harm:.2f}")

            if harmonics_present >= 2:
                # 3 o más armónicos simultáneos (1X + al menos 2X y 3X) = patrón de holgura
                alerts.append(
                    f"[FFT {axis_name}] 🔧 Patrón de Holgura Estructural — "
                    f"Familia de armónicos activa: 1X={mag_1x:.2f}, {', '.join(harmonic_details)}. "
                    f"Verificar fijación de base, tornillería y chumaceras. "
                    f"(ISO 13373-2 §7.5 Patrón A5)"
                )

        # ── REGLA 4: Desalineación Angular por comparación cruzada (ISO 13373-2 §7.3.2) ──
        # "Un pico 1X en la dirección axial igual o superior al 70% del pico 1X radial
        #  es indicador primario de desalineación angular entre ejes acoplados."
        # Fuente: ISO 13373-2:2016, Tabla 1, Patrón de falla tipo A3.
        axial_data  = None
        radial_data = None
        for key, data in peaks_by_axis.items():
            if "axial" in key:
                axial_data = data
            elif "radial" in key:
                radial_data = data

        if axial_data and radial_data:
            ratio = axial_data["mag_1x"] / radial_data["mag_1x"] if radial_data["mag_1x"] > 0 else 0
            if ratio >= 0.70:
                severity = "Severa" if ratio >= 1.20 else "Moderada"
                alerts.append(
                    f"[FFT Multi-Eje] 📐 Desalineación Angular {severity} detectada — "
                    f"Axial-1X ({axial_data['mag_1x']:.2f}) = {ratio*100:.0f}% del Radial-1X "
                    f"({radial_data['mag_1x']:.2f}). "
                    f"Verificar acoplamiento y alineación del eje. (ISO 13373-2 §7.3.2)"
                )

            # Refinamiento: Desalineación Paralela (2XRadial elevado + axial elevado)
            # ISO 13373-2 §7.3.3: La desalineación paralela produce 2X dominante en radial.
            if radial_data["mag_2x"] > (0.5 * radial_data["mag_1x"]) and ratio >= 0.40:
                alerts.append(
                    f"[FFT Multi-Eje] 🔀 Posible Desalineación Paralela — "
                    f"2X Radial ({radial_data['mag_2x']:.2f}) elevado con componente axial presente. "
                    f"Revisar offset lateral en el acoplamiento. (ISO 13373-2 §7.3.3)"
                )

    return list(dict.fromkeys(alerts))


def get_fft_peaks(fft_raw):
    """
    Extrae las coordenadas de los picos detectados (1X, 2X, Electrico) para anotar visualmente
    en las graficas del espectro FFT del Tab de Analisis Manual.
    Retorna: dict { axis_name: [(frequency, magnitude, label), ...] }
    """
    if not fft_raw or "sensors" not in fft_raw:
        return {}

    result = {}
    for sensor in fft_raw.get("sensors", []):
        for axis_data in sensor.get("dataValues", []):
            vals = axis_data.get("sensorAxisDataValues", [])
            if not vals:
                continue
            axis_name = axis_data.get("sensorAxisName", "Desconocido")
            df_fft = pd.DataFrame(vals)
            if df_fft.empty or 'frequency' not in df_fft or 'magnitude' not in df_fft:
                continue

            peaks = []
            # 1X  — frecuencia fundamental
            w1x = df_fft[(df_fft['frequency'] >= 20) & (df_fft['frequency'] <= 35)]
            if not w1x.empty:
                idx1x = w1x['magnitude'].idxmax()
                f1x = df_fft.loc[idx1x, 'frequency']
                m1x = df_fft.loc[idx1x, 'magnitude']
                if m1x >= 0.1:
                    peaks.append((f1x, m1x, '1X'))

                    # 2X  — segundo armónico
                    f2x_t = f1x * 2
                    w2x = df_fft[(df_fft['frequency'] >= f2x_t * 0.95) &
                                 (df_fft['frequency'] <= f2x_t * 1.05)]
                    if not w2x.empty:
                        idx2x = w2x['magnitude'].idxmax()
                        m2x = df_fft.loc[idx2x, 'magnitude']
                        if m2x >= 0.1:
                            peaks.append((df_fft.loc[idx2x, 'frequency'], m2x, '2X'))

            # Frecuencias electricas 100 / 120 Hz
            for f_line in [100, 120]:
                wel = df_fft[(df_fft['frequency'] >= f_line - 1.5) &
                             (df_fft['frequency'] <= f_line + 1.5)]
                if not wel.empty:
                    idxel = wel['magnitude'].idxmax()
                    mel = df_fft.loc[idxel, 'magnitude']
                    if mel >= 0.3:
                        peaks.append((f_line, mel, f'~{f_line}Hz'))

            if peaks:
                result[axis_name] = peaks

    return result

def analyze_volatility(df_trends, current_value, kpi_name):
    """
    Analiza el historial telemétrico de un KPI para interceptar volatilidades anormales y
    tasas de aceleración críticas (Derivadas) previo a una falla mecánica catastrófica.
    Returns: (is_anomalous_bool, list_of_alerts, df_with_bollinger_bands)
    """
    if df_trends.empty:
        return False, [], df_trends
        
    df = df_trends.copy()
    if 'timestamp' not in df.columns or 'value' not in df.columns:
        return False, [], df
        
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df = df.sort_values('timestamp')
    df = df.set_index('timestamp')
    
    is_anomalous = False
    alerts = []
    
    # =========================================================================
    # CÁLCULO DE BANDAS ESTADÍSTICAS AVANZADAS (BOLLINGER)
    # Rellena una media móvil temporal ajustada a ventanas de 12 horas 
    # =========================================================================
    # Se usa min_periods=2 garantizando que con mínimo 2 puntos calcule varianza
    rolling_mean = df['value'].rolling('12h', min_periods=2).mean()
    rolling_std = df['value'].rolling('12h', min_periods=2).std()
    
    df['Bollinger_Upper'] = rolling_mean + (2.5 * rolling_std)
    df['Bollinger_Lower'] = rolling_mean - (2.5 * rolling_std)
    
    if not df['Bollinger_Upper'].empty and not pd.isna(df['Bollinger_Upper'].iloc[-1]):
        upper_limit = df['Bollinger_Upper'].iloc[-1]
        std_val = rolling_std.iloc[-1]
        
        # Filtro de ruido con floor absoluto: 5% del valor actual O mínimo 0.1 unidades,
        # lo que sea mayor. Evita que valores de KPI casi-cero disparen alertas triviales.
        noise_floor = max(0.05 * abs(current_value), 0.1)
        if std_val > noise_floor:
            if current_value > upper_limit:
                alerts.append(f"📈 El KPI [{kpi_name}] rompió abruptamente el túnel estadístico histórico (+2.5σ). Riesgo en escalada.")
                is_anomalous = True

    # =========================================================================
    # CÁLCULO DE POTENCIA DERIVADA (Embalamiento y Fallos Inminentes)
    # Ignora los arranques (Startups) cuando las maquinas brincan de cero
    # =========================================================================
    min_value = df['value'].min()
    is_startup = False
    
    # Umbral de startup diferenciado por tipo de KPI para evitar falsos positivos:
    # - Temperatura: < 5°C es físicamente imposible en un motor activo → startup real
    # - Vibración: < 0.05 mm/s es reposo total → startup real (0.2 era demasiado alto)
    # - Otros: se conserva el criterio estricto de valor casi cero
    if 'Temperature' in kpi_name or 'temperatura' in kpi_name.lower():
        is_startup = min_value < 5.0
    elif 'Vibration' in kpi_name or 'vibration' in kpi_name.lower():
        is_startup = min_value < 0.05
    else:
        is_startup = min_value < 0.2
        
    if len(df) >= 4 and not is_startup:
        # Calcular derivadas de los últimos 4 intervalos consecutivos
        # Usar la MEDIANA en lugar del último valor para eliminar spikes por muestreo irregular
        derivatives = []
        for i in range(len(df) - 1, max(len(df) - 5, 0), -1):
            dt_h = (df.index[i] - df.index[i - 1]).total_seconds() / 3600.0
            if 0 < dt_h < 24:  # Ignorar saltos generacionales masivos
                dy = df['value'].iloc[i] - df['value'].iloc[i - 1]
                derivatives.append(dy / dt_h)
        
        if derivatives:
            # Mediana robusta ante outliers por gaps irregulares de API
            derivatives.sort()
            mid = len(derivatives) // 2
            dy_dt = derivatives[mid] if len(derivatives) % 2 != 0 else (derivatives[mid - 1] + derivatives[mid]) / 2.0
            
            # Filtro riguroso: Derivadas criticas por tipo de KPI
            if 'Temperature' in kpi_name and dy_dt > 5.0:
                alerts.append(f"🔥 Peligro de Embalamiento Térmico: Temperatura subiendo a una tasa anormal de +{dy_dt:.1f}°C por hora.")
                is_anomalous = True
            elif 'Vibration' in kpi_name and dy_dt > 2.0:
                alerts.append(f"💥 Aceleración Mecánica Aguda: La Vibración se está disparando a +{dy_dt:.1f} mm/s cada hora.")
                is_anomalous = True
                
    # Retornar DF reseteado
    df = df.reset_index()
    return is_anomalous, alerts, df
