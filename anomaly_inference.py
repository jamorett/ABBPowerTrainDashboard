import os
import pandas as pd
import numpy as np
import joblib
import warnings
import json

warnings.filterwarnings('ignore')

try:
    from tensorflow.keras.models import load_model
    TF_AVAILABLE = True
except ImportError:
    TF_AVAILABLE = False

class LiveAnomalyDetector:
    def __init__(self):
        self.model = None
        self.scaler = None
        self.threshold = 1.0 # Failsafe limit
        self.is_autoencoder = False
        self.ready = False
        self.expected_cols = []
        
        try:
            if os.path.exists('anomaly_scaler.pkl'):
                self.scaler = joblib.load('anomaly_scaler.pkl')
                if hasattr(self.scaler, 'feature_names_in_'):
                    self.expected_cols = list(self.scaler.feature_names_in_)
                    
            if os.path.exists('anomaly_threshold.json'):
                with open('anomaly_threshold.json', 'r') as f:
                    data = json.load(f)
                    self.threshold = data.get("mse_threshold", 1.0)
                
            if TF_AVAILABLE and os.path.exists('anomaly_autoencoder.h5'):
                # Carga modelo neural sin optimizador por ser de prediccion asincrona
                self.model = load_model('anomaly_autoencoder.h5', compile=False)
                self.is_autoencoder = True
                self.ready = True if self.scaler else False
                
            elif os.path.exists('anomaly_if_model.pkl'):
                self.model = joblib.load('anomaly_if_model.pkl')
                self.ready = True if self.scaler else False
                
        except Exception as e:
            print(f"Error nativo vinculando el I.A Scanner Unsupervised: {e}")

    def get_health_score_percent(self, kpis_api_list):
        """
        1. Recibe la ráfaga de vibraciones desde ABB Cloud.
        2. Intenta "comprimirla" y regresarla a su forma inicial
        3. Si la API envió comportamientos que la Red Neuronal jamás observó en la vida (Dificultad de Compresión/Expansión), 
           Mide esa fricción (MSE Mean Squared Error) y la retorna graduada sobre el Threshold Máximo.
        """
        if not self.ready or not kpis_api_list:
            return None
            
        try:
            # Transformar series temporales largas en Matrices Tensoriales Indexables
            rows = []
            for k in kpis_api_list:
                name = k.get("name")
                if "trend" in k and isinstance(k["trend"], list):
                    for pt in k["trend"]:
                        if "value" in pt:
                            rows.append({"timestamp": pt["timestamp"], "name": name, "value": pt["value"]})
                            
            if not rows: return None
            
            df = pd.DataFrame(rows)
            df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True)
            df_val = df.pivot_table(index='timestamp', columns='name', values='value', aggfunc='mean').reset_index()
            df_val['timestamp'] = df_val['timestamp'].dt.round('H')
            df_val = df_val.groupby('timestamp').mean().reset_index()
            df_val.sort_values('timestamp', inplace=True)
            
            core_cols = [c for c in df_val.columns if c != 'timestamp']
            
            df_val.ffill(inplace=True)
            df_val.fillna(0, inplace=True)
            
            # Incorporar dinamismo rodante (Identico a Isolation en train_algo)
            for col in core_cols:
                df_val[f'{col}_mean_24h'] = df_val[col].rolling(window=24, min_periods=1).mean()
                df_val[f'{col}_std_24h']  = df_val[col].rolling(window=24, min_periods=1).std().fillna(0)
                df_val[f'{col}_mean_7d']  = df_val[col].rolling(window=168, min_periods=1).mean()
                
            for c in self.expected_cols:
                if c not in df_val.columns:
                    df_val[c] = 0.0
                    
            df_val = df_val[self.expected_cols]
            df_val.ffill(inplace=True)
            df_val.fillna(0, inplace=True)
            
            X_scaled = self.scaler.transform(df_val)
            
            if self.is_autoencoder:
                # Pedimos al Autoencoder desentramar su propia reconstruccion de todas las ultimas filas
                preds = self.model.predict(X_scaled, verbose=0)
                
                # Error Cuadratico Medio. 0.0 significa un Match perfecto con la linea base "Sana".
                mse_block = np.mean(np.power(X_scaled - preds, 2), axis=1)
                
                # Despachamos el dato mas "caliente", el ultimo latido enviado
                current_mse = mse_block[-1]
                
                # Una Anomalia por encima del 100% significa que excedio categoricamente 
                # la maxima desviacion que el motor tuvo durante su tiempo "Sano".
                anomaly_percent = (current_mse / self.threshold) * 100.0
                
            else:
                score = self.model.decision_function(X_scaled[-1:])
                anomaly_percent = max(0, (0.0 - score[0]) * 1000) 
                
            return round(anomaly_percent, 1)
            
        except Exception as e:
            return None
