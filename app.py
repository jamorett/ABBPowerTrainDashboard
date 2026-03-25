import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import datetime
import time
import extra_streamlit_components as stx
import os
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()
# --- CONFIGURACION DE PAGINA ---
st.set_page_config(page_title="ABB Powertrain Dashboard", layout="wide", initial_sidebar_state="collapsed", page_icon="⚡")

# ---------------------------------------------------------
# AUTENTICACIÓN Y COOKIES
# ---------------------------------------------------------

# Inicializar manejador de cookies
cookie_manager = stx.CookieManager(key="ia_cookie_manager")

# Verificar estado de sesión y cookies
auth_cookie = cookie_manager.get(cookie="abb_dashboard_auth")

if not st.session_state.get('autenticado', False):
    if auth_cookie == "true":
        st.session_state.autenticado = True
    else:
        # PANTALLA DE LOGIN
        st.markdown("<h1 style='text-align: center; margin-top: 50px;'>🔒 Acceso Restringido</h1>", unsafe_allow_html=True)
        st.markdown("<h4 style='text-align: center; font-weight: 300;'>Sistema de Monitoreo Predictivo ABB</h4>", unsafe_allow_html=True)
        
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            st.write("---")
            username = st.text_input("Usuario")
            password = st.text_input("Contraseña", type="password")
            
            if st.button("Iniciar Sesión", use_container_width=True, type="primary"):
                env_user = os.getenv("DASHBOARD_USERNAME")
                env_pass = os.getenv("DASHBOARD_PASSWORD")
                
                if env_user and env_pass and username == env_user and password == env_pass:
                    st.session_state.autenticado = True
                    # Guardar cookie que expira en 10 años (3650 días)
                    cookie_manager.set("abb_dashboard_auth", "true", expires_at=datetime.datetime.now() + datetime.timedelta(days=3650))
                    st.rerun()
                else:
                    st.error("❌ Usuario o contraseña incorrectos")
        
        # Detener la ejecución del resto del script hasta que inicie sesión
        st.stop()

# --- FIN DE AUTENTICACIÓN ---

from api_service import ApiService
import advanced_analytics
import translator as tr
import notification_manager as nm

# --- CONFIGURACION DE PAGINA ---
st.set_page_config(page_title="ABB Powertrain Dashboard", layout="wide", initial_sidebar_state="collapsed", page_icon="⚡")

# Ocultar footer y menu por defecto para una experiencia Kiosko inmersiva
hide_st_style = """
            <style>
            #MainMenu {visibility: hidden;}
            footer {visibility: hidden;}
            </style>
            """
st.markdown(hide_st_style, unsafe_allow_html=True)

@st.cache_resource
def get_api():
    return ApiService()

api = get_api()

@st.cache_data(ttl=3600)
def fetch_history(_api, asset, date_from, date_to):
    return _api.get_condition_history(asset, date_from, date_to)

@st.cache_data(ttl=3600)
def fetch_events(_api, asset, date_from, date_to):
    return _api.search_events(asset, start_time=date_from, end_time=date_to)

@st.cache_data(ttl=3600)
def fetch_details(_api, asset):
    return _api.get_asset_details(asset)

@st.cache_data(ttl=3600)
def fetch_fft(_api, asset):
    return _api.get_last_fft(asset)

KNOWN_ASSETS = {
    "105727": "Molino 1 S12",
    "103479": "Molino 2 S12",
    "103517": "Molino 4 S12",
    "103519": "Molino 4 S34",
    "105728": "Molino 3 S12",
    "105729": "Molino 1 S34",
    "105730": "Molino 3 S34",
    "103518": "Molino 2 S32",
    "104486": "Molino 1 Linea 5",
    "104487": "Molino 2 Linea 5",
    "103480": "Extrusora Linea 2",
    "103481": "Extrusora Linea 3",
    "105725": "Prensa 1 Linea 1",
    "105726": "Prensa 2 Linea 1"
}

# Inicializar estados para el Kiosko
if "kiosk_index" not in st.session_state:
    st.session_state.kiosk_index = 0
if "kiosk_paused" not in st.session_state:
    st.session_state.kiosk_paused = False
if "asset_statuses" not in st.session_state:
    st.session_state.asset_statuses = {a: "Desconocido" for a in KNOWN_ASSETS}
nm.init_notification_state()

# --- BARRA LATERAL ---
st.sidebar.title("⚡ Navegación")
modo = st.sidebar.radio("Modo Visual:", ["📺 Kiosko (TV Carousel)", "🔍 Análisis Manual (Tabs)"])

today = datetime.datetime.now()
past_7_days = today - datetime.timedelta(days=7)

date_range = st.sidebar.date_input(
    "Selecciona el rango de fechas (Telemetría)",
    value=(past_7_days.date(), today.date()),
    max_value=today.date()
)

if len(date_range) != 2:
    st.sidebar.warning("Por favor selecciona una fecha de inicio y una de fin.")
    st.stop()

date_from_str = f"{date_range[0]}T00:00:00Z"
date_to_str = f"{date_range[1]}T23:59:59Z"

try:
    api.authenticate()
except Exception as e:
    st.error(f"Error de conexión autenticando API: {str(e)}")
    st.stop()


def render_kiosk_mode():
    st.markdown("<h1 style='text-align: center; color: white;'>📺 Panel de Monitoreo General</h1>", unsafe_allow_html=True)
    
    # Auto-Rotación Asíncrona (No Bloqueante)
    if not st.session_state.kiosk_paused:
        from streamlit_autorefresh import st_autorefresh
        count = st_autorefresh(interval=30000, limit=None, key="kioskotimer")
        last_count = st.session_state.get('last_kiosk_tick', -1)
        
        # Si count < last_count, el componente se desmontó (usuario cambió de pestaña). Sincronizamos:
        if count < last_count:
            last_count = -1
            st.session_state.last_kiosk_tick = -1
            
        # Si el tick del reloj subió, incrementamos el carrusel ANTES de renderizar la página
        if count > last_count:
            st.session_state.kiosk_index = (st.session_state.kiosk_index + 1) % len(KNOWN_ASSETS)
            st.session_state.last_kiosk_tick = count
    
    # Grid de Semáforo Global en la parte superior
    st.markdown("---")
    
    n_cols = 7
    filas = (len(KNOWN_ASSETS) + n_cols - 1) // n_cols
    items_list = list(KNOWN_ASSETS.items())
    
    for fila_n in range(filas):
        cols = st.columns(n_cols)
        items_fila = items_list[fila_n * n_cols : (fila_n + 1) * n_cols]
        for j, (a_id, a_name) in enumerate(items_fila):
            global_idx = fila_n * n_cols + j
            s_status = st.session_state.asset_statuses.get(a_id, "Desconocido")
            color = "🟢" if s_status in ["Good", "Normal", "OK"] else ("🟡" if s_status in ["Tolerable", "Warning"] else ("🔴" if s_status in ["Alarm", "Error", "Poor", "Bad", "Critical"] else "⚪"))
            
            # Efecto visual de resaltado para el equipo actualmente enfocado en pantalla
            style = f"border: 2px solid cyan; border-radius: 5px; padding: 5px; text-align: center; background-color: rgba(0,255,255,0.1);" if global_idx == st.session_state.kiosk_index else "padding: 5px; text-align: center;"
            cols[j].markdown(f"<div style='{style}; font-size: 0.85rem; margin-bottom: 5px;'><b>{a_name}</b><br>{color} {tr.translate_condition(s_status)}</div>", unsafe_allow_html=True)
            
            # Botón interactivo para saltar al equipo rápidamente
            btn_label = "📍 En Pantalla" if global_idx == st.session_state.kiosk_index else "🔍 Ir ahora"
            if cols[j].button(btn_label, key=f"btn_jump_{a_id}", disabled=(global_idx == st.session_state.kiosk_index), use_container_width=True):
                st.session_state.kiosk_index = global_idx
                st.session_state.kiosk_paused = True  # Pausar para que el usuario pueda analizar con calma tras hacer clic
                st.rerun()
            
    st.markdown("---")

    # Boton de Pausa/Reanudar
    col_btn1, col_btn2, _ = st.columns([2, 2, 8])
    if st.session_state.kiosk_paused:
        if col_btn1.button("▶️ Reanudar Carrusel", type="primary"):
            st.session_state.kiosk_paused = False
            st.rerun()
        if col_btn2.button("⏭️ Saltar al Siguiente"):
            st.session_state.kiosk_index = (st.session_state.kiosk_index + 1) % len(KNOWN_ASSETS)
            st.rerun()
    else:
        if col_btn1.button("⏸️ Pausar Carrusel en este Equipo"):
            st.session_state.kiosk_paused = True
            st.rerun()
            
    

    # Activo en foco
    current_asset = list(KNOWN_ASSETS.keys())[st.session_state.kiosk_index]
    current_name = KNOWN_ASSETS[current_asset]
    st.markdown(f"<h2 style='text-align: center;'>Enfocado en Activo: {current_name} (ID: {current_asset})</h2>", unsafe_allow_html=True)
    
    # 1. Extraer Condition History y actualizar semáforo global
    history = fetch_history(api, current_asset, date_from_str, date_to_str)
    if history:
        current_cond = history.get("currentOverallCondition", "Desconocida")
        st.session_state.asset_statuses[current_asset] = current_cond
        kpis = history.get("KPIs", [])
        
        # Detectar KPIs en umbral critico sostenido
        nm.check_persistent_breach(current_asset, current_name, kpis)
        
        col1, col2 = st.columns([1, 4])
        cond_color = "🟢" if current_cond in ["Good", "Normal", "OK"] else ("🟡" if current_cond in ["Tolerable", "Warning"] else ("🔴" if current_cond in ["Alarm", "Error", "Poor", "Bad", "Critical"] else "⚪"))
        col1.metric("Condición Integral", f"{cond_color} {tr.translate_condition(current_cond)}")
        
        # 2. Descargar Eventos Globales (Ultimas 3 Semanas)
        d_to_dt = datetime.datetime.strptime(date_to_str, "%Y-%m-%dT%H:%M:%SZ")
        d_events_from = (d_to_dt - datetime.timedelta(days=21)).strftime("%Y-%m-%dT00:00:00Z")
        events_raw = fetch_events(api, current_asset, d_events_from, date_to_str) or {}
        api_items = events_raw.get("events", []) if isinstance(events_raw, dict) else events_raw
        
        event_items = []
        if isinstance(api_items, list):
            for ev in api_items:
                event_items.append({
                    "timestamp": ev.get("deviceTimestamp", ev.get("timestamp")),
                    "eventType": f"Evento ABB ({ev.get('sourceCode', 'Sistema')})",
                    "severity": tr.translate_severity(ev.get("severityCode", "Unknown")),
                    "message": tr.translate_message(ev.get("messageText", "Sin mensaje"))
                })
                
        for k in kpis:
            if "conditionEvents" in k and k["conditionEvents"]:
                for ce in k["conditionEvents"]:
                    event_items.append({
                        "eventType": f"Alarma de Umbral Roto ({k.get('name')})",
                        "severity": tr.translate_severity(ce.get("type", "Warning")),
                        "timestamp": ce.get("timestamp"),
                        "message": tr.translate_message(f"KPI {k.get('name')} reporta {ce.get('type')}: {ce.get('valueDouble')}")
                    })
        
        if event_items:
            # Ordenamos por fecha mas reciente
            try:
                event_items = sorted(event_items, key=lambda x: str(x.get("timestamp", "")), reverse=True)
            except:
                pass
            with col2:
                st.error(f"⚠️ **Atención: Hay {len(event_items)} Eventos/Alarmas recientes.**")
                # Mostramos solo los ultimos 3 en un dataframe pequeño para no saturar pantalla
                st.dataframe(pd.DataFrame(event_items[:3])[['timestamp', 'eventType', 'severity', 'message']], use_container_width=True)
        else:
            with col2:
                st.success("✅ Log Limpio: No hay eventos ni alarmas en las últimas 3 semanas para este activo.")

        # 2.B Pre-procesamiento Inteligencia Matemática (FFT y Volatilidad)
        try:
            fft_raw = fetch_fft(api, current_asset)
            fft_alerts = advanced_analytics.analyze_fft(fft_raw)
            for fa in fft_alerts:
                sev = "Error" if "Posible" not in fa else "Warning"
                event_items.append({
                    "timestamp": datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "eventType": "Pre-Diagnóstico FFT (IA)",
                    "severity": sev,
                    "message": fa
                })
                # También como notificacion flotante IA
                nm.add_notification(current_asset, current_name, "Pre-Diagnóstico FFT", fa, sev)
        except Exception:
            pass

        for k in kpis:
            name = k.get('name')
            trend_data_temp = []
            if 'trend' in k and len(k['trend']) > 0:
                for pt in k['trend']:
                    if 'value' in pt: trend_data_temp.append({'timestamp': pt['timestamp'], 'value': pt['value']})
            
            k['is_anomalous_ia'] = False
            k['df_trends_ia'] = None

            if trend_data_temp:
                df_temp = pd.DataFrame(trend_data_temp)
                curr_val = trend_data_temp[-1]['value']
                try:
                    is_anom, alertas, df_res = advanced_analytics.analyze_volatility(df_temp, curr_val, name)
                    k['is_anomalous_ia'] = is_anom
                    k['df_trends_ia'] = df_res
                    
                    for al in alertas:
                        event_items.append({
                            "timestamp": datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
                            "eventType": f"Detector IA ({name})",
                            "severity": "Warning",
                            "message": al
                        })
                        # También como notificacion flotante IA
                        nm.add_notification(current_asset, current_name,
                                            f"Análisis Estadístico", al, "Warning")
                except Exception:
                    pass

        # Notificaciones flotantes IA — se renderizan aquí, después del análisis,
        # para que las alertas del activo actual ya estén en session_state.
        # position:fixed en CSS garantiza que aparezcan arriba a la derecha sin importar
        # dónde queden en el flujo del layout de Streamlit.
        nm.render_floating_notifications(asset_id=current_asset)

        # 3. Graficas (Prioridad: Alarm > Tolerable > Good)
        # Asignar peso a cada condicion para ordenarlas inteligentemente
        def priority_score(kpi_dict):
            cond = kpi_dict.get("currentCondition", "Unknown")
            name = kpi_dict.get("name", "")
            
            score = 30
            if cond in ["Alarm", "Error", "Poor", "Bad", "Critical"]: score = 0
            elif cond in ["Tolerable", "Warning"]: score = 10
            elif cond in ["Good", "Normal", "OK"]: score = 20
            
            # Si The IA local detectó que escapó el túnel de Bollinger o se embaleó, GANA prioridad total
            if kpi_dict.get('is_anomalous_ia'): score = -10
            
            # Sub-prioridad (Desempate) para que variables clave siempre ganen espacio en pantalla
            if name == "Bearing condition": score -= 5
            elif name == "Skin Temperature": score -= 4
            elif "RMS" in name and "term" not in name: score -= 3
            
            
            return score
            
        # Filtramos los duplicados agregados de ABB (largo/corto plazo) porque ya tenemos los crudos
        kpis_reales = [k for k in kpis if "(long term)" not in k.get("name", "") and "(short term)" not in k.get("name", "")]
        kpis_sorted = sorted(kpis_reales, key=priority_score)
        
        # Seleccionamos maximo 6 graficas de mayor riesgo para aprovechar la TV a pantalla completa
        top_kpis = kpis_sorted[:6]
        
        st.markdown("### 📉 Variables Prioritarias (Ordenadas por nivel de riesgo)")
        grid_cols = st.columns(3)
        idx = 0
        
        for k in top_kpis:
            name = k.get('name')
            unit = k.get('unit', '').strip() if k.get('unit') is not None else ''
            c_cond = k.get("currentCondition", "Desconocido")
            
            trend_data = []
            var_name = f"{tr.translate_kpi_name(name)}" + (f" ({unit})" if unit else "")
            
            # Valores Reales y Túnel de Bollinger (Si está disponible)
            if k.get('df_trends_ia') is not None and not k['df_trends_ia'].empty:
                df_ia = k['df_trends_ia']
                for row_idx, row in df_ia.iterrows():
                    trend_data.append({'Tipo': 'Valor Real', 'timestamp': row['timestamp'], 'value': row['value']})
                    if 'Bollinger_Upper' in row and pd.notna(row['Bollinger_Upper']):
                        trend_data.append({'Tipo': 'Límite Superior (Bollinger +2.5σ)', 'timestamp': row['timestamp'], 'value': row['Bollinger_Upper']})
            elif 'trend' in k and len(k['trend']) > 0:
                for pt in k['trend']:
                    if 'value' in pt:
                        trend_data.append({'Tipo': 'Valor Real', 'timestamp': pt['timestamp'], 'value': pt['value']})
                        
            # Limites API ABB
            if 'conditionTrends' in k:
                for ct in k['conditionTrends']:
                    t_type = ct.get('type')
                    if t_type in ["High Warning Threshold", "High Error Threshold", "Low Warning Threshold", "Low Error Threshold"]:
                        t_type_es = t_type.replace("High Warning Threshold", "Límite Superior (Advertencia)").replace("High Error Threshold", "Límite Superior (Error)").replace("Low Warning Threshold", "Límite Inferior (Advertencia)").replace("Low Error Threshold", "Límite Inferior (Error)")
                        for pt in ct.get('values', []):
                            if 'valueDouble' in pt:
                                trend_data.append({'Tipo': t_type_es, 'timestamp': pt['timestamp'], 'value': pt['valueDouble']})
            
            if trend_data:
                df_trends = pd.DataFrame(trend_data)
                df_trends['timestamp'] = pd.to_datetime(df_trends['timestamp'])
                df_trends = df_trends.sort_values('timestamp')
                color_map = {
                    'Valor Real': '#1f77b4',
                    'Límite Superior (Advertencia)': '#ff7f0e',
                    'Límite Superior (Error)': '#d62728',
                    'Límite Inferior (Advertencia)': '#ffbb78',
                    'Límite Inferior (Error)': '#ff9896',
                    'Límite Superior (Bollinger +2.5σ)': '#cccccc',
                }
                
                cond_icon = "🟢" if c_cond in ["Good", "Normal", "OK"] else ("🟡" if c_cond in ["Tolerable", "Warning"] else ("🔴" if c_cond in ["Alarm", "Error", "Poor", "Bad", "Critical"] else "⚪"))
                fig = px.line(df_trends, x="timestamp", y="value", color="Tipo", title=f"{cond_icon} {var_name}", markers=False, color_discrete_map=color_map)
                fig.update_layout(margin=dict(l=20, r=20, t=40, b=20), height=250)
                grid_cols[idx % 3].plotly_chart(fig, use_container_width=True)
                idx += 1

    else:
        st.warning("No se pudo obtener el historial de salud para este activo.")

    # Panel de historial de alertas IA (plegable, antes del auto-refresh)
    nm.render_alert_history_panel(current_asset)

    if not st.session_state.kiosk_paused:
        st.info("⏱️ Modo Carrusel Automático Activado (Rotando cada 30 segundos...) - Navegación completamente libre para clics inmediatos.")



def render_manual_mode():
    nm.clear_floating_notifications()
    st.title("⚡ ABB Powertrain API - Análisis Manual")
    selected_asset_id = st.sidebar.selectbox("🎯 Activo a analizar a fondo", list(KNOWN_ASSETS.keys()), format_func=lambda x: f"{KNOWN_ASSETS[x]} (ID: {x})")
    
    if st.sidebar.button("⚙️ Cargar Datos del Activo", type="primary"):
        with st.spinner("Descargando historial completo..."):
            st.session_state['active_asset_manual'] = selected_asset_id

    if 'active_asset_manual' in st.session_state:
        asset_id = st.session_state['active_asset_manual']
        
        st.markdown(f"### 🔍 Exploración Profunda: {KNOWN_ASSETS.get(asset_id, asset_id)} (ID: {asset_id})")
        tab_condicion, tab_telemetria, tab_master, tab_eventos, tab_fft = st.tabs([
            "📊 Condición General", 
            "📈 Tendencias y Límites",
            "📋 Master Data",
            "⚠️ Registro de Eventos",
            "🎧 Análisis Vibracional (FFT)"
        ])
        
        # Extract from API to serve tabs
        history = fetch_history(api, asset_id, date_from_str, date_to_str)
        kpis = history.get("KPIs", []) if history else []
        
        # --- TAB 1: CONDICION GENERAL ---
        with tab_condicion:
            st.subheader("Estado de Salud")
            if history:
                overall_cond = history.get("currentOverallCondition", "Desconocida")
                status_color = "🟢" if overall_cond in ["Good", "Normal", "OK"] else ("🟡" if overall_cond in ["Tolerable", "Warning"] else ("🔴" if overall_cond in ["Alarm", "Error", "Poor", "Bad", "Critical"] else "⚪"))
                st.metric(label="Condición Integral del Activo", value=f"{status_color} {tr.translate_condition(overall_cond)}")
                if kpis:
                    st.markdown("### Resumen de Indicadores (KPIs)")
                    cols = st.columns(3)
                    idx = 0
                    for k in kpis:
                        kpi_name = k.get("name")
                        kpi_cond = k.get("currentCondition")
                        if kpi_cond:
                            col_icon = "🟢" if kpi_cond in ["Good", "Normal", "OK"] else ("🟡" if kpi_cond in ["Tolerable", "Warning"] else ("🔴" if kpi_cond in ["Alarm", "Error", "Poor", "Bad", "Critical"] else "⚪"))
                            cols[idx % 3].metric(label=tr.translate_kpi_name(kpi_name), value=f"{col_icon} {tr.translate_condition(kpi_cond)}")
                            idx += 1

        # --- TAB 2: TELEMETRIA COMPLETA ---
        with tab_telemetria:
            st.subheader("Gráficas Telemétricas (Todas las Variables)")
            if kpis:
                trend_data = []
                for k in kpis:
                    _unit = (k.get('unit') or '').strip()
                    var_name = f"{tr.translate_kpi_name(k.get('name'))}" + (f" ({_unit})" if _unit else "")
                    if 'trend' in k:
                        for pt in k['trend']:
                            if 'value' in pt: trend_data.append({'Variable': var_name, 'Tipo': 'Valor Real', 'timestamp': pt['timestamp'], 'value': pt['value']})
                    if 'conditionTrends' in k:
                        for ct in k['conditionTrends']:
                            t_type = ct.get('type')
                            if t_type in ["High Warning Threshold", "High Error Threshold", "Low Warning Threshold", "Low Error Threshold"]:
                                t_type_es = t_type.replace("High Warning Threshold", "Límite Superior (Advertencia)").replace("High Error Threshold", "Límite Superior (Error)").replace("Low Warning Threshold", "Límite Inferior (Advertencia)").replace("Low Error Threshold", "Límite Inferior (Error)")
                                for pt in ct.get('values', []):
                                    if 'valueDouble' in pt: trend_data.append({'Variable': var_name, 'Tipo': t_type_es, 'timestamp': pt['timestamp'], 'value': pt['valueDouble']})
                if trend_data:
                    df_trends = pd.DataFrame(trend_data)
                    df_trends['timestamp'] = pd.to_datetime(df_trends['timestamp'])
                    df_trends = df_trends.sort_values('timestamp')
                    variables = df_trends['Variable'].unique()
                    selected_vars = st.multiselect("Selecciona variables a graficar:", options=variables, default=variables[:1] if len(variables) > 0 else variables)
                    if selected_vars:
                        for var in selected_vars:
                            df_var = df_trends[df_trends['Variable'] == var]
                            color_map = {'Valor Real': '#1f77b4', 'Límite Superior (Advertencia)': '#ff7f0e', 'Límite Superior (Error)': '#d62728', 'Límite Inferior (Advertencia)': '#ffbb78', 'Límite Inferior (Error)': '#ff9896'}
                            fig = px.line(df_var, x="timestamp", y="value", color="Tipo", title=f"Tendencia de {var}", markers=False, color_discrete_map=color_map)
                            st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("No se encontraron tendencias.")

        # --- TAB 3: MASTER DATA ---
        with tab_master:
            st.subheader("Hoja de Vida del Activo")
            details = fetch_details(api, asset_id)
            if details:
                c1, c2, c3 = st.columns(3)
                c1.metric("Tipo Específico", details.get("assetTypeDescription", "N/A"))
                c2.metric("Id Legado", details.get("legacyAssetId", "N/A"))
                c3.metric("Estado API", details.get("connectionStatus", "N/A"))
                if details.get("assetProperties"):
                    df_props = pd.DataFrame(details["assetProperties"])
                    df_props = df_props.dropna(subset=['propertyValue'])
                    st.dataframe(df_props[['propertyName', 'propertyValue', 'propertyDefaultUnit']], use_container_width=True)

        # --- TAB 4: EVENTOS COMPLETOS ---
        with tab_eventos:
            st.subheader("Registro Histórico de Eventos")
            d_to_dt = datetime.datetime.strptime(date_to_str, "%Y-%m-%dT%H:%M:%SZ")
            d_events_from = (d_to_dt - datetime.timedelta(days=21)).strftime("%Y-%m-%dT00:00:00Z")
            events_raw = fetch_events(api, asset_id, d_events_from, date_to_str) or {}
            api_items = events_raw.get("events", []) if isinstance(events_raw, dict) else events_raw
            
            items = []
            if isinstance(api_items, list):
                for ev in api_items:
                    items.append({
                        "timestamp": ev.get("deviceTimestamp", ev.get("timestamp")),
                        "eventType": f"Evento ABB ({ev.get('sourceCode', 'Sistema')})",
                        "severity": tr.translate_severity(ev.get("severityCode", "Unknown")),
                        "message": tr.translate_message(ev.get("messageText", "Sin mensaje"))
                    })
                    
            for k in kpis:
                if "conditionEvents" in k and k["conditionEvents"]:
                    for ce in k["conditionEvents"]:
                        items.append({"eventType": f"Alarma KPI: {k.get('name')}", "severity": tr.translate_severity(ce.get("type", "Warning")), "timestamp": ce.get("timestamp"), "message": f"Umbral Roto: {ce.get('valueDouble')}"})
            if items:
                st.dataframe(pd.DataFrame(items), use_container_width=True)
            else:
                st.success("No hay eventos ni alarmas registrados.")

        # --- TAB 5: FFT ---
        with tab_fft:
            st.subheader("Último Análisis Vibracional Completo (FFT)")
            try:
                fft_raw = fetch_fft(api, asset_id)
                if not fft_raw:
                    st.warning("No hay datos de FFT para este activo.")
                else:
                    # ── Espectro por eje de sensor ──────────────────────────────────
                    if "spectrum" in fft_raw and "sensors" in fft_raw:
                        # Obtener picos detectados por nuestro motor analítico
                        fft_peaks = advanced_analytics.get_fft_peaks(fft_raw)
                        for sensor in fft_raw["sensors"]:
                            for axis_data in sensor.get("dataValues", []):
                                axis_name = axis_data.get("sensorAxisName", "Desconocido")
                                vals = axis_data.get("sensorAxisDataValues", [])
                                if vals:
                                    df_fft = pd.DataFrame(vals)
                                    
                                    # Construir figura base con la curva del espectro
                                    fig_fft = go.Figure()
                                    fig_fft.add_trace(go.Scatter(
                                        x=df_fft["frequency"], y=df_fft["magnitude"],
                                        mode='lines', name='Espectro',
                                        line=dict(color='#1f77b4', width=1.5),
                                        fill='tozeroy', fillcolor='rgba(31,119,180,0.08)'
                                    ))
                                    
                                    # Anotar picos detectados (1X, 2X, Eléctrico)
                                    peaks = fft_peaks.get(axis_name, [])
                                    if peaks:
                                        px_freqs = [p[0] for p in peaks]
                                        px_mags  = [p[1] for p in peaks]
                                        px_labels = [p[2] for p in peaks]
                                        fig_fft.add_trace(go.Scatter(
                                            x=px_freqs, y=px_mags,
                                            mode='markers+text',
                                            name='Picos Detectados',
                                            marker=dict(color='red', size=10, symbol='circle',
                                                        line=dict(color='white', width=1.5)),
                                            text=px_labels,
                                            textposition='top center',
                                            textfont=dict(color='red', size=12)
                                        ))
                                    
                                    title_suffix = f" — {len(peaks)} pico(s) detectado(s)" if peaks else ""
                                    fig_fft.update_layout(
                                        title=f"Espectro FFT — Eje {axis_name}{title_suffix}",
                                        xaxis_title="Frecuencia (Hz)",
                                        yaxis_title="Magnitud",
                                        hovermode='x unified',
                                        template='plotly_dark',
                                        margin=dict(l=20, r=20, t=50, b=30)
                                    )
                                    st.plotly_chart(fig_fft, use_container_width=True)
                    elif "sensors" not in fft_raw:
                        st.info("ℹ️ No hay datos de espectro por eje disponibles para este activo.")

                    # ── Armónicos Dominantes ─────────────────────────────────────────
                    # Verificados independientemente del espectro
                    harmonics = fft_raw.get("harmonicsHighestPeaks") or []
                    if harmonics:
                        st.markdown("### 🎵 Armónicos Dominantes")
                        df_harm = pd.DataFrame(harmonics)

                        # Validar columnas mínimas esperadas
                        if "magnitude" in df_harm.columns and "name" in df_harm.columns:
                            df_harm = df_harm.dropna(subset=["magnitude"])
                            df_harm["magnitude"] = pd.to_numeric(df_harm["magnitude"], errors="coerce")
                            df_harm = df_harm.dropna(subset=["magnitude"])

                            # Transformación Data Science: castear a float y ordenar lógicamente el espectro
                            if "value" in df_harm.columns:
                                df_harm["value"] = pd.to_numeric(df_harm["value"], errors="coerce")
                                df_harm = df_harm.sort_values(by="value", ascending=True)

                                # Etiqueta enriquecida usando salto HTML nativo (<br> en lugar de \n)
                                df_harm["label"] = df_harm.apply(
                                    lambda r: f"{r['name']}<br>{r['value']:.1f} Hz"
                                              if pd.notna(r.get("value")) else r["name"],
                                    axis=1
                                )
                            else:
                                df_harm = df_harm.sort_values(by="name", ascending=True)
                                df_harm["label"] = df_harm["name"]

                            if not df_harm.empty:
                                fig_harm = px.bar(
                                    df_harm, x="label", y="magnitude",
                                    title="Magnitud de Armónicos Dominantes",
                                    color="magnitude",
                                    color_continuous_scale="Inferno",
                                    labels={"label": "Armónico", "magnitude": "Magnitud"},
                                    text="magnitude"
                                )
                                fig_harm.update_traces(
                                    texttemplate="%{text:.3f}",
                                    textposition="outside"
                                )
                                fig_harm.update_layout(
                                    margin=dict(l=20, r=20, t=50, b=60),
                                    coloraxis_showscale=False,
                                    xaxis_tickangle=-30
                                )
                                st.plotly_chart(fig_harm, use_container_width=True)
                            else:
                                st.info("Los armónicos no tienen valores de magnitud válidos.")
                        else:
                            st.warning(f"Formato inesperado en armónicos. Columnas disponibles: {list(df_harm.columns)}")
                            st.dataframe(df_harm)
                    else:
                        st.info("ℹ️ No hay datos de armónicos dominantes para este activo.")
            except Exception as e:
                st.error(f"Error al obtener FFT: {e}")
    else:
        st.info("👈 Selecciona un Activo y haz clic en Cargar.")


# --- RUTEADOR PRINCIPAL ---
if "Kiosko" in modo:
    render_kiosk_mode()
else:
    render_manual_mode()
