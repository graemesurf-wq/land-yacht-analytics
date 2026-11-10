import pandas as pd
from fitparse import FitFile

def extract_fit_data(uploaded_file):
    try:
        uploaded_file.seek(0)
        fitfile = FitFile(uploaded_file.read())
        records = []
        for record in fitfile.get_messages('record'):
            lat = record.get_value('position_lat')
            lon = record.get_value('position_long')
            speed = record.get_value('speed')
            timestamp = record.get_value('timestamp')
            
            if timestamp is not None:
                row = {
                    "Time": pd.to_datetime(timestamp).time(), 
                    "Timestamp": pd.to_datetime(timestamp)
                }
                if lat is not None and lon is not None:
                    row["Lat"] = lat * (180.0 / 2**31)
                    row["Lon"] = lon * (180.0 / 2**31)
                if speed is not None:
                    row["Kph"] = speed * 3.6
                else:
                    row["Kph"] = 0.0
                records.append(row)
        df = pd.DataFrame(records)
        if not df.empty:
            df = df.sort_values("Timestamp").reset_index(drop=True)
        return df
    except:
        return pd.DataFrame()
