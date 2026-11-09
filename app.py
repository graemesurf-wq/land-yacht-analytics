import streamlit as st
import pandas as pd
import numpy as np
from fitparse import FitFile

st.set_page_config(page_title="Land Yacht Analytics", layout="wide")
st.title("⛵ Land Yacht VMC Performance Analyzer")

# Initialize memory banks safely
if 'sailor_registry' not in st.session_state: st.session_state.sailor_registry = {}
if 'race_specs' not in st.session_state: st.session_state.race_specs = {}
if 'manual_course' not in st.session_state: st.session_state.manual_course = {}

def extract_fit_data(uploaded_file):
    """Decodes the binary FIT file records safely into a data table."""
    try:
        uploaded_file.seek(0)
        fitfile = FitFile(uploaded_file.read())
        records = []
        for record in fitfile.get_messages('record'):
            lat = record.get_value('position_lat')
            lon = record.get_value('position_long')
            speed = record.get_value('speed') # raw m/s from device
            timestamp = record.get_value('timestamp')
            
            if timestamp is not None:
                row = {"Timestamp": pd.to_datetime(timestamp)}
                if lat is not None and lon is not None:
                    row["Latitude"] = lat * (180.0 / 2**31)
                    row["Longitude"] = lon * (180.0 / 2**31)
                if speed is not None:
                    row["Speed_Kph"] = speed * 3.6
                records.append(row)
        df = pd.DataFrame(records)
        if not df.empty:
            df = df.sort_values("Timestamp").reset_index(drop=True)
        return df
    except:
        return pd.DataFrame()

# --- SIDEBAR: FLUID RACE CONTROLS & TUNING ---
st.sidebar.header("🕹️ Race Configuration")
total_races = st.sidebar.number_input("Total Races", min_value=1, max_value=20, value=3)
race_options = [f"Race {i}" for i in range(1, total_races + 1)]
active_race = st.sidebar.selectbox("Active Race", options=race_options)

# FIXED: Explicitly filled out the duration values
duration_choices = [10, 15, 20, 25, 30]
allocated_duration = st.sidebar.selectbox("Duration (Mins)", options=duration_choices, index=2)

st.sidebar.divider()
st.sidebar.header("📥 Sailor Setup Profile")
uploaded_file = st.sidebar.file_uploader("Upload XOSS .fit file", type=["fit"])
sailor_name = st.sidebar.text_input("Sailor Name / Yacht Number", placeholder="e.g., Yacht 42")

df_raw = pd.DataFrame()
if uploaded_file:
    df_raw = extract_fit_data(uploaded_file)

if sailor_name:
    if sailor_name not in st.session_state.sailor_registry: st.session_state.sailor_registry[sailor_name] = True
    if active_race not in st.session_state.race_specs: st.session_state.race_specs[active_race] = {}
    if sailor_name not in st.session_state.race_specs[active_race]:
        st.session_state.race_specs[active_race][sailor_name] = {"tire_pressure": 1.4, "boom_height": 25, "sail_size": "5.5", "race_weight": 85}

    specs = st.session_state.race_specs[active_race][sailor_name]
    specs["tire_pressure"] = st.sidebar.selectbox("Tires (Bar)", [1.0, 1.2, 1.4, 1.6, 1.8, 2.0], index=[1.0, 1.2, 1.4, 1.6, 1.8, 2.0].index(specs["tire_pressure"]))
    
    # FIXED: Explicitly filled out the boom heights values
    bh_options = [15, 17, 19, 22, 25, 28, 32, 36, 40, 44, 48]
    specs["boom_height"] = st.sidebar.selectbox("Boom (cm)", bh_options, index=bh_options.index(specs["boom_height"]))
    
    specs["sail_size"] = st.sidebar.selectbox("Sail Size", ["3", "3.5", "4.5", "5.5", "6.2"], index=["3", "3.5", "4.5", "5.5", "6.2"].index(specs["sail_size"]))
    specs["race_weight"] = st.sidebar.slider("Weight (kg)", 60, 110, int(specs["race_weight"]))

# --- MAIN AREA LAYOUT ---
col_course, col_status = st.columns(2)

with col_course:
    st.subheader(f"📐 Numeric Course Coordinate Logger - {active_race}")
    st.caption("Input the precise coordinates of your markers below to avoid map lag entirely.")
    
    if active_race not in st.session_state.manual_course:
        st.session_state.manual_course[active_race] = {
            "Start_A_Lat": 0.0, "Start_A_Lon": 0.0, "Start_B_Lat": 0.0, "Start_B_Lon": 0.0,
            "Finish_A_Lat": 0.0, "Finish_A_Lon": 0.0, "Finish_B_Lat": 0.0, "Finish_B_Lon": 0.0,
            "Num_Cones": 2
        }
    
    course = st.session_state.manual_course[active_race]
    
    st.markdown("**🏁 Start Gate Coordinates**")
    g1, g2 = st.columns(2)
    course["Start_A_Lat"] = g1.number_input("Start Marker A Latitude", value=course["Start_A_Lat"], format="%.6f")
    course["Start_A_Lon"] = g2.number_input("Start Marker A Longitude", value=course["Start_A_Lon"], format="%.6f")
    g3, g4 = st.columns(2)
    course["Start_B_Lat"] = g3.number_input("Start Marker B Latitude", value=course["Start_B_Lat"], format="%.6f")
    course["Start_B_Lon"] = g4.number_input("Start Marker B Longitude", value=course["Start_B_Lon"], format="%.6f")

    st.markdown("**🛑 Finish Gate Coordinates**")
    f1, f2 = st.columns(2)
    course["Finish_A_Lat"] = f1.number_input("Finish Marker A Latitude", value=course["Finish_A_Lat"], format="%.6f")
    course["Finish_A_Lon"] = f2.number_input("Finish Marker A Longitude", value=course["Finish_A_Lon"], format="%.6f")
    f3, f4 = st.columns(2)
    course["Finish_B_Lat"] = f3.number_input("Finish Marker B Latitude", value=course["Finish_B_Lat"], format="%.6f")
    course["Finish_B_Lon"] = f4.number_input("Finish Marker B Longitude", value=course["Finish_B_Lon"], format="%.6f")

    st.markdown("**🟠 Course Mark Cones Selection**")
    course["Num_Cones"] = st.number_input("Total Cones on Beach (2 to 6)", min_value=2, max_value=6, value=course["Num_Cones"])

with col_status:
    st.subheader("📊 File Ingestion Logs")
    if not df_raw.empty:
        st.success(f"File parsed completely! Found {len(df_raw)} unique telemetry lines.")
        st.markdown("**Raw Data Head Sample:**")
        st.dataframe(df_raw.head(10), hide_index=True)
    else:
        st.info("Awaiting binary .fit data file structure via the upload panel.")

st.divider()

# --- PERFORMANCE LEADERBOARD MATRIX ---
st.subheader(f"📊 Performance Leaderboard Matrix — {active_race}")
st.caption(f"Allocated Clock Threshold: {allocated_duration} Minutes.")

fleet_rows = []
if active_race in st.session_state.race_specs:
    for name, tuning in st.session_state.race_specs[active_race].items():
        status_msg = "✅ Data Processing Complete" if not df_raw.empty else "⏳ Awaiting Data File"
        fleet_rows.append({
            "Yacht Identifier": name,
            "Sail Size": tuning["sail_size"],
            "Weight (kg)": tuning["race_weight"],
            "Boom Gap (cm)": tuning["boom_height"],
            "Tires (Bar)": tuning["tire_pressure"],
            "Analysis Status": status_msg,
            "Distance (km)": "0.00",
            "Avg Speed": "0.0 kph",
            "VMC": "0.0 kph"
        })

if fleet_rows:
    st.table(pd.DataFrame(fleet_rows))
