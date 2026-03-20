import os
import requests
import datetime
from dotenv import load_dotenv

class ApiService:
    def __init__(self):
        load_dotenv()
        self.base_powertrain_url = "https://api.powertrain.abb.com/api"
        self.base_url = f"{self.base_powertrain_url}/analytics"
        self.api_key = os.getenv("ABB_API_KEY")
        self.access_token = os.getenv("API_TOKEN")
        self.organization_id = os.getenv("ORGANIZATION_ID")
        self.session = requests.Session()
        
        self.token_expires_at = datetime.datetime.min
        
        if self.access_token and not self.api_key:
            # Only trust the .env token if there is no API Key available to auto-refresh
            self._update_headers()
            self.token_expires_at = datetime.datetime.now() + datetime.timedelta(minutes=55)

    def _update_headers(self):
        self.session.headers.update({
            "Authorization": f"Bearer {self.access_token}",
            "api-version": "1.0",
            "User-Agent": "MyApp/1.0",
            "Content-Type": "application/json"
        })

    def authenticate(self, force=False):
        if not force and datetime.datetime.now() < self.token_expires_at:
            return self.access_token
            
        if not self.api_key:
            if not self.access_token:
                raise ValueError("No se encontró ABB_API_KEY en el archivo .env")
            return self.access_token
            
        # Exchange API Key for a fresh Access Token
        url = "https://api.accessmanagement.motion.abb.com/polaris/oidc/token"
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        data = {
            "grant_type": "api_key",
            "ApiKey": self.api_key
        }
        res = requests.post(url, headers=headers, data=data)
        res.raise_for_status()
        
        token_data = res.json()
        self.access_token = token_data.get("access_token")
        
        # Save expiration with a 5-minute safety margin
        expires_in = token_data.get("expires_in", 3600)
        self.token_expires_at = datetime.datetime.now() + datetime.timedelta(seconds=expires_in - 300)
        
        self._update_headers()
        return self.access_token

    def _ensure_auth(self):
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
            
        response = self.session.get(url, params=params)
        response.raise_for_status()
        return response.json()

    def get_condition_history(self, asset_id, start_time, end_time):
        self._ensure_auth()
        url = f"{self.base_url}/Analytics/Condition/History/{asset_id}"
        params = {
            "startTime": start_time,
            "endTime": end_time
        }
        response = self.session.get(url, params=params)
        response.raise_for_status()
        return response.json()

    def get_asset_details(self, asset_id):
        self._ensure_auth()
        url = f"{self.base_powertrain_url}/asset/{asset_id}"
        response = self.session.get(url)
        response.raise_for_status()
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
        response = self.session.post(url, json=payload)
        response.raise_for_status()
        return response.json()

    def get_last_fft(self, asset_id):
        self._ensure_auth()
        url = f"{self.base_powertrain_url}/fft/FFT/{asset_id}/LastFFTFile"
        response = self.session.get(url)
        response.raise_for_status()
        return response.json()
