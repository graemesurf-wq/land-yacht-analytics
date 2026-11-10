import streamlit as st
import pandas as pd
import plotly.express as px
from engine import extract_track_points

st.set_page_config(page_title="VMC Analyzer", layout="wide", initial_sidebar_state="expanded")
st.title("⛵ Land Yacht VMC Performance Analyzer")

if 'course_log' not in st.session_state: st.session_state.course_log = list()
if 'sailor_registry' not in st.session_state: st.session_state.sailor_registry = {}
if 'race_specs' not in st.session_state: st.session_state.race_specs = {}

st.sidebar.header("🕹️ Race Control Panel")
total_races = st.sidebar.number_input("Total Races", min_value=1, max_value=20, value=3)
race_options = [f"Race {i}" for i in range(1, total_races + 1)]
active_race = st.sidebar.selectbox("Active Race to Configure", options=race_options)

duration_choices = (10, 15, 20, 25, 30)
allocated_duration = st.sidebar.selectbox("Allocated Race Duration", options=duration_choices, index=2, format_func=lambda x: f"{x} Minutes")

st.sidebar.divider()
st.sidebar.header("📥 Sailor Log & Setup Profile")
uploaded_file = st.sidebar.file_uploader("Upload your XOSS .fit file", type=["fit"])
sailor_name = st.sidebar.text_input("Sailor Name / Yacht Number", placeholder="e.g., Yacht 42")

df_track = pd.DataFrame()
if uploaded_file:
    df_track = extract_track_points(uploaded_file)

if sailor_name:
    if sailor_name not in st.session_state.sailor_registry: st.session_state.sailor_registry[sailor_name] = True
    if active_race not in st.session_state.race_specs: st.session_state.race_specs[active_race] = {}
    if sailor_name not in st.session_state.race_specs[active_race]:
        st.session_state.race_specs[active_race][sailor_name] = {"tire_pressure": 1.4, "boom_height": 25, "sail_size": "5.5", "race_weight": 85}

    specs = st.session_state.race_specs[active_race][sailor_name]
    specs["tire_pressure"] = st.sidebar.selectbox("Tire Pressure (Bar)", options=(1.0, 1.2, 1.4, 1.6, 1.8, 2.0), index=(1.0, 1.2, 1.4, 1.6, 1.8, 2.0).index(specs["tire_pressure"]))
    specs["boom_height"] = st.sidebar.selectbox("Boom Height (cm gap)", options=(15, 17, 19, 22, 25, 28, 32, 36, 40, 44, 48), index=(15, 17, 19, 22, 25, 28, 32, 36, 40, 44, 48).index(specs["boom_height"]))
    specs["sail_size"] = st.sidebar.selectbox("Sail Size", options=("3", "3.5", "4.5", "5.5", "6.2"), index=("3", "3.5", "4.5", "5.5", "6.2").index(specs["sail_size"]))
    specs["race_weight"] = st.sidebar.slider("Total Race Weight (kg)", 60, 110, int(specs["race_weight"]))

col_map, col_data = st.columns([2.5, 1.5])

with col_map:
    st.subheader(f"🗺️ Performance Track Plot - {active_race}")
    
    if not df_track.empty:
        # Using standard scatter charts to bypass mapbox bugs entirely
        fig = px.line(df_track, x="Longitude", y="Latitude", title="Yacht Path Trace")
        fig.update_traces(line=dict(color="blue", width=3))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Awaiting a .fit file upload to map the track data coordinates.")

with col_data:
    st.subheader("📋 Course Definition Log")
    st.text("No course anchors set yet.")

st.divider()
st.subheader(f"📊 Performance Leaderboard Matrix — {active_race}")
fleet_rows = list()
if active_race in st.session_state.race_specs:
    for name, tuning in st.session_state.race_specs[active_race].items():
        fleet_rows.append({
            "Yacht Identifier": name, "Sail Size": tuning["sail_size"], "Weight (kg)": tuning["race_weight"],
            "Boom Gap (cm)": tuning["boom_height"], "Tires (Bar)": tuning["tire_pressure"]
        })
st.table(pd.DataFrame(fleet_rows))
