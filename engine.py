import pandas as pd
from fitparse import FitFile

def extract_track_points(uploaded_file):
    try:
        uploaded_file.seek(0)
        fitfile = FitFile(uploaded_file.read())
        records = []
        for record in fitfile.get_messages('record'):
            lat = record.get_value('position_lat')
            lon = record.get_value('position_long')
            if lat is not None and lon is not None:
                records.append({
                    "Latitude": lat * (180.0 / 2**31),
                    "Longitude": lon * (180.0 / 2**31)
                })
        return pd.DataFrame(records)
    except:
        return pd.DataFrame()
