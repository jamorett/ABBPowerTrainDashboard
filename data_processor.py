import pandas as pd
import os

class DataProcessor:
    def __init__(self, output_dir="output"):
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)

    def flatten_and_export(self, raw_data, filename):
        """Aplanado basico de listas/dict anidados."""
        if not raw_data:
            print(f"No hay datos para exportar a {filename}.")
            return pd.DataFrame()
            
        df = pd.json_normalize(raw_data)
        filepath = os.path.join(self.output_dir, f"{filename}.csv")
        df.to_csv(filepath, index=False, encoding='utf-8')
        print(f"--> Exportado exitosamente: {filepath}")
        return df

    def process_history(self, history_data, filename):
        """Desempaqueta el JSON estructurado de History aislando las tendencias para Power BI."""
        if not history_data:
            return pd.DataFrame()
        
        asset_id = history_data.get("assetId")
        overall = history_data.get("currentOverallCondition")
        
        rows = []
        for k in history_data.get("KPIs", []):
            kpi_name = k.get("name")
            unit = k.get("unit")
            curr_cond = k.get("currentCondition")
            
            # Extraer puntos de serie de tiempo numéricos
            if "trend" in k and isinstance(k["trend"], list):
                for pt in k["trend"]:
                    if "value" in pt:
                        rows.append({
                            "assetId": asset_id,
                            "overallCondition": overall,
                            "kpiName": kpi_name,
                            "kpiUnit": unit,
                            "kpiCurrentCondition": curr_cond,
                            "timestamp": pt.get("timestamp"),
                            "value": pt.get("value")
                        })
        
        if not rows:
            print(f"No se encontraron tendencias numéricas para exportar en {filename}.")
            return pd.DataFrame()
            
        df = pd.DataFrame(rows)
        filepath = os.path.join(self.output_dir, f"{filename}.csv")
        df.to_csv(filepath, index=False, encoding='utf-8')
        print(f"--> Exportado exitosamente tendencias limpias a: {filepath}")
        return df
