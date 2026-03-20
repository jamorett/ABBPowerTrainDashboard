import os
import datetime
from api_service import ApiService
from data_processor import DataProcessor

def main():
    api = ApiService()
    processor = DataProcessor(output_dir="powerbi_data")
    
    print("\n[1/4] Iniciando Autenticacion...")
    try:
        api.authenticate()
        print("--> Autenticado exitosamente con token API_TOKEN.")
    except Exception as e:
        print(f"Error critico de autenticacion: {e}")
        return

    # Usamos los assets fijos directamente sin llamar a Maintenance/Summary
    KNOWN_ASSETS = [
        "105727", "103479", "103517", "103519", "105728", 
        "105729", "105730", "103518", "104486", "104487"
    ]

    # Definimos el rango temporal
    date_to = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
    date_from = (datetime.datetime.now() - datetime.timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
    date_events_from = (datetime.datetime.now() - datetime.timedelta(days=21)).strftime("%Y-%m-%dT%H:%M:%SZ")
    
    for test_asset_id in KNOWN_ASSETS:
        print(f"\n====================================================")
        print(f"   EXTRAYENDO DATOS PARA EL ACTIVO: {test_asset_id}")
        print(f"====================================================")

        print(f"\n[2/4] Descargando Historial de Estado (KPI y Tendencias)...")
        history_raw = None
        try:
            history_raw = api.get_condition_history(test_asset_id, date_from, date_to)
            processor.process_history(history_raw, f"condition_history_{test_asset_id}_cleaned")
        except Exception as e:
            print(f"Error: {e}")

        print(f"\n[3/4] Descargando Registro de Eventos y Alarmas...")
        try:
            events_raw = api.search_events(test_asset_id, date_events_from, date_to)
            api_items = events_raw.get("events", []) if isinstance(events_raw, dict) else events_raw
            items = api_items if isinstance(api_items, list) else []
            
            # Recolectar alarmas (conditionEvents) generadas en el Historial del paso 2
            if history_raw and "KPIs" in history_raw:
                for k in history_raw["KPIs"]:
                    if "conditionEvents" in k and k["conditionEvents"]:
                        for ce in k["conditionEvents"]:
                            items.append({
                                "eventType": f"Alarma KPI: {k.get('name')}",
                                "severity": ce.get("type", "Warning"),
                                "timestamp": ce.get("timestamp"),
                                "message": f"KPI {k.get('name')} reporta {ce.get('type')} con valor {ce.get('valueDouble')}",
                                "source": "ConditionHistory"
                            })

            if items:
                processor.flatten_and_export(items, f"events_{test_asset_id}")
        except Exception as e:
            print(f"Error: {e}")

        print(f"\n[4/4] Descargando Hoja de Vida (Master Data)...")
        try:
            details_raw = api.get_asset_details(test_asset_id)
            processor.flatten_and_export([details_raw], f"master_data_{test_asset_id}")
        except Exception as e:
            print(f"Error descargando detalles: {e}")

    print("\n====================================================")
    print("Proceso MASIVO completado. Revisa la carpeta 'powerbi_data'.")

if __name__ == "__main__":
    main()
