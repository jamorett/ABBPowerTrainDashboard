import os
import datetime
import pandas as pd
from api_service import ApiService
import warnings
warnings.filterwarnings("ignore")

def main():
    api = ApiService()
    
    print("\n[1/4] Iniciando Autenticacion...")
    try:
        api.authenticate()
        print("--> Autenticado exitosamente.")
    except Exception as e:
        print(f"Error critico de autenticacion: {e}")
        return

    KNOWN_ASSETS = [
        "105727", "103479", "103517", "103519", "105728", 
        "105729", "105730", "103518", "104486", "104487",
        "103480", "103481", "105725", "105726"
    ]

    output_dir = "powerbi_data"
    os.makedirs(output_dir, exist_ok=True)
    file_path = os.path.join(output_dir, "ML_Master_Dataset.csv")
    
    existing_df = None
    last_timestamps = {}
    
    if os.path.exists(file_path):
        print(f"\n[2/4] Archivo Maestro detectado '{file_path}'. Leyendo historial existente para Carga Incremental...")
        try:
            existing_df = pd.read_csv(file_path)
            existing_df['timestamp'] = pd.to_datetime(existing_df['timestamp'], utc=True)
            # Agrupar el ultimo registro conocido de cada equipo
            last_timestamps = existing_df.groupby('assetId')['timestamp'].max().to_dict()
            print(f"--> Historial previo base cargado ({len(existing_df)} filas). No se descargará data repetida.")
        except Exception as e:
            print(f"Error al leer historial existente: {e}")
            existing_df = None
    else:
        print(f"\n[2/4] No hay Master dataset previo. Se iniciara una extraccion total de cero (Full Extraction).")

    total_days = 365
    chunk_days = 30
    now = datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc)
    
    all_data_frames = []
    if existing_df is not None:
        all_data_frames.append(existing_df)

    for idx, asset_id in enumerate(KNOWN_ASSETS):
        print(f"\n====================================================")
        print(f"[{idx+1}/{len(KNOWN_ASSETS)}] EXTRACCION INCREMENTAL PARA: {asset_id}")
        print(f"====================================================")

        # Si el CSV ya existia, sacamos la ultima fecha conocida
        asset_id_str = str(asset_id)
        
        last_t = None
        if existing_df is not None:
            # Buscar llave (evitar KeyError por type mismatch pandas int/str)
            keys_matching = [k for k in last_timestamps.keys() if str(k) == asset_id_str]
            if keys_matching:
                last_t = last_timestamps[keys_matching[0]]

        if last_t is not None and not pd.isna(last_t):
            start_date_global = last_t
            print(f"  -> Retomando extraccion desde la ultima fecha conocida: {start_date_global}")
        else:
            start_date_global = now - datetime.timedelta(days=total_days)
            print(f"  -> Equipo virgen. Extrayendo los 365 dias permitidos maximos: {start_date_global}")

        if start_date_global >= now:
            print("  -> El equipo está totalmente al día con la API. Omitiendo llamadas...")
            continue

        asset_kpi_rows = []
        asset_fft_rows = []
        asset_ts_rows = []

        # Bucle incremental (Hacia el futuro) por fragmentos de chunk_days para no abrumar a la API
        current_start = start_date_global
        
        while current_start < now:
            current_end = current_start + datetime.timedelta(days=chunk_days)
            if current_end > now:
                current_end = now
                
            d_from = current_start.strftime("%Y-%m-%dT%H:%M:%SZ")
            d_to = current_end.strftime("%Y-%m-%dT%H:%M:%SZ")
            
            print(f"  -> Descargando bloque temporal: {d_from[:10]} al {d_to[:10]}...")
            
            # --- 1. HISTORIAL DE KPIs ---
            try:
                history = api.get_condition_history(asset_id, d_from, d_to)
                if history:
                    overall = history.get("currentOverallCondition", "Unknown")
                    for k in history.get("KPIs", []):
                        kpi_name = k.get("name")
                        kpi_cond_actual = k.get("currentCondition", "Unknown")
                        
                        if "trend" in k and isinstance(k["trend"], list):
                            for pt in k["trend"]:
                                if "value" in pt:
                                    asset_kpi_rows.append({
                                        "assetId": asset_id,
                                        "timestamp": pt.get("timestamp"),
                                        "kpiName": kpi_name,
                                        "kpiValue": pt.get("value"),
                                        f"cond_{kpi_name}": kpi_cond_actual, 
                                        "overallCondition": overall
                                    })
            except Exception as e:
                print(f"    - Error API History: {e}")

            # --- 2. HISTORIAL FFT ---
            try:
                url_fft = f"{api.base_powertrain_url}/fft/FFT/{asset_id}/FFTFiles"
                res_fft = api.session.get(url_fft, params={"startTime": d_from, "endTime": d_to})
                if res_fft.status_code == 200:
                    fft_files = res_fft.json()
                    if isinstance(fft_files, list):
                        for f_meta in fft_files:
                            asset_fft_rows.append({
                                "assetId": asset_id,
                                "timestamp": f_meta.get("timestamp"),
                                "FFT_speed": f_meta.get("speed"),
                                "FFT_lineFrequency": f_meta.get("lineFrequency"),
                                "FFT_skinTemperature": f_meta.get("skinTemperature")
                            })
            except Exception as e:
                pass # Si no hay FFT, seguimos transparente

            # --- 3. HISTORIAL TIMESERIES (Power & Speed) ---
            for t_key, t_col in [("EnergyConsumption", "Output Power"), ("Speed", "Motor Speed")]:
                try:
                    ts_data = api.get_operational_timeseries(asset_id, d_from, d_to, timeseries_key=t_key)
                    if isinstance(ts_data, list) and len(ts_data) > 0:
                        for obj in ts_data:
                            for pt in obj.get("values", []):
                                asset_ts_rows.append({
                                    "assetId": asset_id,
                                    "timestamp": pt.get("timestamp"),
                                    t_col: pt.get("value")
                                })
                except Exception as e:
                    pass # Tolerancia a falla temporal

            current_start = current_end

        # --- 3. PROCESAMIENTO PANDAS PARA EL DELTA NUEVO ---
        print("\n  [+] Empaquetando nuevo delta de datos...")
        df_kpi = pd.DataFrame(asset_kpi_rows)
        df_fft = pd.DataFrame(asset_fft_rows)
        df_ts = pd.DataFrame(asset_ts_rows)

        if not df_kpi.empty:
            df_kpi['timestamp'] = pd.to_datetime(df_kpi['timestamp'], utc=True)
            df_val = df_kpi.pivot_table(index=['assetId', 'timestamp', 'overallCondition'], 
                                        columns='kpiName', values='kpiValue', aggfunc='mean').reset_index()
            
            def first_non_null(s): return s.dropna().iloc[0] if len(s.dropna()) > 0 else "Unknown"
            
            cond_cols = [c for c in df_kpi.columns if str(c).startswith("cond_")]
            if len(cond_cols) > 0:
                df_cond = df_kpi.groupby(['timestamp'])[cond_cols].agg(first_non_null).reset_index()
                df_asset_merged = pd.merge(df_val, df_cond, on='timestamp', how='left')
            else:
                df_asset_merged = df_val

            df_asset_merged['timestamp'] = df_asset_merged['timestamp'].dt.round('H')
            
            agg_funcs = {'assetId':'first'}
            if 'overallCondition' in df_asset_merged.columns:
                agg_funcs['overallCondition'] = 'first'
                
            for col in df_asset_merged.columns:
                if col not in ['timestamp', 'assetId', 'overallCondition']:
                    if str(col).startswith('cond_'):
                        agg_funcs[col] = 'first'
                    else:
                        agg_funcs[col] = 'mean'
                        
            df_asset_merged = df_asset_merged.groupby('timestamp').agg(agg_funcs).reset_index()

            if not df_fft.empty:
                df_fft['timestamp'] = pd.to_datetime(df_fft['timestamp'], utc=True)
                df_fft = df_fft.sort_values('timestamp')
                df_asset_merged = df_asset_merged.sort_values('timestamp')
                
                df_asset_merged = pd.merge_asof(
                    df_asset_merged, 
                    df_fft.drop(columns=['assetId']), 
                    on='timestamp', 
                    direction='nearest', 
                    tolerance=pd.Timedelta('2h')
                )

            if not df_ts.empty:
                df_ts['timestamp'] = pd.to_datetime(df_ts['timestamp'], utc=True)
                df_ts = df_ts.groupby(['assetId', 'timestamp']).mean().reset_index()
                df_ts = df_ts.sort_values('timestamp')
                df_asset_merged = df_asset_merged.sort_values('timestamp')
                
                df_asset_merged = pd.merge_asof(
                    df_asset_merged, 
                    df_ts.drop(columns=['assetId']), 
                    on='timestamp', 
                    direction='nearest', 
                    tolerance=pd.Timedelta('2h')
                )

            df_asset_merged.sort_values('timestamp', inplace=True)
            df_asset_merged.ffill(inplace=True)
            df_asset_merged.bfill(inplace=True)

            # Evitar inyectar filas duplicadas (recortamos el delta estrictamente superior a last_t)
            if last_t is not None:
                df_asset_merged = df_asset_merged[df_asset_merged['timestamp'] > last_t]

            if not df_asset_merged.empty:
                all_data_frames.append(df_asset_merged)
                print(f"  -> {len(df_asset_merged)} registros NUEVOS listos para el DataLake.")
            else:
                print("  -> Delta competamente vacio (No se detectaron series mas recientes).")
        else:
            print("  -> Sin lecturas nuevas por la API de ABB en el peridodo consultado.")

    # --- 4. ENSAMBLAJE FINAL ---
    if all_data_frames:
        print("\n[4/4] Adhesion final: Fusionando historico original con el nuevo Delta Incremental...")
        master_df = pd.concat(all_data_frames, ignore_index=True)
        master_df.sort_values(by=['assetId', 'timestamp'], inplace=True)
        
        # Super precaución: destrozar duplicaciones en caso de traslapes en pandas temporales
        master_df.drop_duplicates(subset=['assetId', 'timestamp'], keep='last', inplace=True)
        
        master_df.to_csv(file_path, index=False, encoding='utf-8')
        
        print(f"\n✅ EXITOSO: Master DataFrame preservado asincrónicamente -> {master_df.shape[0]} filas totales.")
        print(f"Con esta implementacion, si el archivo sigue corriendo año a año, jamas perderas los historiales de fatiga de las extrusoras que superen la limitante de la API de ABB.")
    else:
        print("\n❌ Error: Estructuracion de Pandas fallida en todos los equipos.")

if __name__ == "__main__":
    main()
