import json
from api_service import ApiService
import datetime

api = ApiService()
api.authenticate()

a = 103517
date_to = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
date_from = (datetime.datetime.now() - datetime.timedelta(days=21)).strftime("%Y-%m-%dT%H:%M:%SZ")

url = f"{api.base_powertrain_url}/event/Event/Search"

payload = {
    "assetIds": [a],
    "timestampFrom": date_from,
    "timestampTo": date_to,
    "pageSize": 50
}
res = api.session.post(url, json=payload)
data = res.json()
print("Data type:", type(data))
if isinstance(data, dict):
    print("Data keys:", data.keys())
    items = data.get("items", [])
    print(f"Items length: {len(items)}")
    print("Items:", json.dumps(items, indent=2))
else:
    print("Data:", data)
