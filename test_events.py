import json
from api_service import ApiService

api = ApiService()
api.authenticate()

asset_id = 103517
payload = {
    "assetIds": [asset_id],
    "pageSize": 50
}
print("Payload:", payload)
url = f"{api.base_powertrain_url}/event/Event/Search"
res = api.session.post(url, json=payload)
print("Status:", res.status_code)
if res.ok:
    data = res.json()
    if isinstance(data, dict):
        print("Keys:", data.keys())
        if "items" in data:
            print("Items count:", len(data["items"]))
            if data["items"]:
                print("Sample:", data["items"][0])
        else:
            print("Data dict:", data)
    elif isinstance(data, list):
        print("List length:", len(data))
        if data:
            print("Sample:", data[0])
else:
    print("Error text:", res.text)
