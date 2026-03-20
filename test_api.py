import json
from api_service import ApiService
import datetime

api = ApiService()
api.authenticate()

asset_id = "103517"
date_to = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
date_from = (datetime.datetime.now() - datetime.timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")

with open("tmp_output2.txt", "w", encoding="utf-8") as f:
    f.write("=== HISTORIAL THRESHOLDS ===\n")
    hist = api.get_condition_history(asset_id, date_from, date_to)
    if hist and "KPIs" in hist:
        for k in hist["KPIs"]:
            if "Vibration" in k.get("name", ""):
                f.write(f"KPI: {k.get('name')}\n")
                if "conditionTrends" in k:
                    f.write(f"  conditionTrends count: {len(k['conditionTrends'])}\n")
                    for ct in k["conditionTrends"][:2]:
                        f.write(f"    - Type: {ct.get('type')}, Values count: {len(ct.get('values', []))}\n")
                        if ct.get('values'):
                            f.write(f"      Sample: {ct['values'][-1]}\n")
                else:
                    f.write("  No conditionTrends\n")
                break

    f.write("\n=== FFT FILE ===\n")
    try:
        fft = api.get_last_fft(asset_id)
        f.write(f"Keys found: {list(fft.keys())}\n")
        if "sensors" in fft:
            for s in fft["sensors"]:
                f.write(f"Sensor Type: {s.get('sensorType')}\n")
                for dv in s.get("dataValues", []):
                    axis = dv.get("sensorAxisName")
                    vals = dv.get("sensorAxisDataValues", [])
                    f.write(f" Axis {axis} has {len(vals)} values\n")
        if "harmonicsHighestPeaks" in fft:
            f.write(f"harmonicsHighestPeaks size: {len(fft['harmonicsHighestPeaks'])}\n")
        if "spectrum" in fft:
            f.write(f"spectrum type: {type(fft['spectrum'])}\n")
    except Exception as e:
        f.write(f"Error: {e}\n")
