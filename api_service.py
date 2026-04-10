import os
import requests
import datetime
import threading
from dotenv import load_dotenv

class ApiService:
    def __init__(self):
        self._auth_lock = threading.Lock()
        load_dotenv(override=True)
        self.base_powertrain_url = "https://api.powertrain.abb.com/api"
        self.base_url = f"{self.base_powertrain_url}/analytics"
        raw_api_key = os.getenv("ABB_API_KEY")
        self.api_key = raw_api_key.strip() if raw_api_key else None
        self.access_token = os.getenv("API_TOKEN")
        self.organization_id = os.getenv("ORGANIZATION_ID")
        self.session = requests.Session()
        
        self.token_expires_at = datetime.datetime.min
        
        if self.access_token:
            self._update_headers()

    def _update_headers(self):
        self.session.headers.update({
            "Authorization": f"Bearer {self.access_token}",
            "api-version": "1.0",
            "User-Agent": "MyApp/1.0"
        })

    def _safe_request(self, method, url, **kwargs):
        """
        Wrapper centralizado con timeout obligatorio y manejo estructurado de errores.
        Diferencia entre timeout de conexión (10s) y timeout de lectura (30s).
        Previene bloqueo indefinido de hilos en caso de degradación del API gateway.
        """
        kwargs.setdefault('timeout', (10, 30))
        try:
            response = self.session.request(method, url, **kwargs)
            response.raise_for_status()
            return response
        except requests.exceptions.Timeout:
            raise TimeoutError(
                f"ABB API timeout on {method.upper()} {url} — "
                "gateway is degraded or reverse proxy dropped connection."
            )
        except requests.exceptions.ConnectionError as e:
            raise ConnectionError(f"ABB API connection error on {method.upper()} {url}: {e}") from e
        except requests.exceptions.HTTPError as e:
            raise RuntimeError(
                f"ABB API HTTP error {e.response.status_code} on {method.upper()} {url}: {e}"
            ) from e

    def authenticate(self, force=False):
        if not force and datetime.datetime.now() < self.token_expires_at:
            return self.access_token
            
        if not self.api_key:
            if not self.access_token:
                raise ValueError("No se encontró ABB_API_KEY en el archivo .env")
            return self.access_token
            
        # Exchange API Key for a fresh Bearer Token via OIDC
        url = "https://api.accessmanagement.motion.abb.com/polaris/oidc/token"
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        data = {
            "grant_type": "api_key",
            "ApiKey": self.api_key
        }
        try:
            res = requests.post(url, headers=headers, data=data, timeout=(10, 30))
        except requests.exceptions.RequestException as e:
            raise ConnectionError(f"OIDC token request failed: {e}") from e
        
        # HTTP 400 = API Key inválido o revocado — no suprimir.
        if res.status_code == 400:
            raise ValueError(
                f"AuthorizationError: Fallo al renovar el token OIDC (HTTP 400). "
                f"Verifica ABB_API_KEY. Detalle: {res.text}"
            )
            
        res.raise_for_status()
        
        token_data = res.json()
        self.access_token = token_data.get("access_token")
        
        # Safety margin: 5 minutes before true expiry
        expires_in = token_data.get("expires_in", 3600)
        self.token_expires_at = datetime.datetime.now() + datetime.timedelta(seconds=expires_in - 300)
        
        self._update_headers()
        return self.access_token

    def _ensure_auth(self):
        with self._auth_lock:
            self.authenticate()

    def get_maintenance_summary(self, organization_id=None, site_id=None):
        self._ensure_auth()
        org_id = organization_id or self.organization_id
        if not org_id:
            raise ValueError("Se requiere organization_id o definir ORGANIZATION_ID en el archivo .env")
            
        url = f"{self.base_url}/Analytics/Maintenance/Summary"
        params = {"organizationId": org_id}
        if site_id:
            params["siteId"] = site_id
            
        response = self._safe_request('get', url, params=params)
        return response.json()

    def get_condition_history(self, asset_id, start_time, end_time):
        self._ensure_auth()
        url = f"{self.base_url}/Analytics/Condition/History/{asset_id}"
        params = {
            "startTime": start_time,
            "endTime": end_time
        }
        response = self._safe_request('get', url, params=params)
        return response.json()

    def get_asset_details(self, asset_id):
        self._ensure_auth()
        url = f"{self.base_powertrain_url}/asset/{asset_id}"
        response = self._safe_request('get', url)
        return response.json()

    def search_events(self, asset_id, start_time, end_time, page_size=100):
        self._ensure_auth()
        url = f"{self.base_powertrain_url}/event/Event/Search"
        payload = {
            "assetIds": [int(asset_id)],
            "timestampFrom": start_time,
            "timestampTo": end_time,
            "pageSize": page_size
        }
        response = self._safe_request('post', url, json=payload)
        return response.json()

    def get_operational_timeseries(self, asset_id, start_time, end_time, timeseries_key="EnergyConsumption"):
        """
        [DOCUMENTED API ENDPOINT]
        Obtiene parámetros operativos inferidos (como Output Power en kW) de la API oficial de Timeseries.
        """
        self._ensure_auth()
        url = f"{self.base_powertrain_url}/timeseries/Timeseries/Aggregated"
        params = {
            "from": start_time,
            "to": end_time
        }
        payload = [{
            "assetId": int(asset_id),
            "timeseries": {
                "timeseriesKey": timeseries_key
            }
        }]
        response = self._safe_request('post', url, params=params, json=payload)
        return response.json()

    def get_last_fft(self, asset_id):
        self._ensure_auth()
        url = f"{self.base_powertrain_url}/fft/FFT/{asset_id}/LastFFTFile"
        response = self._safe_request('get', url)
        return response.json()
