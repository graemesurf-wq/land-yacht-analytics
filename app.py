import streamlit as st
import pandas as pd
import plotly.express as px
from engine import extract_fit_data

st.set_page_config(page_title="VMC Analyzer", layout="wide")
st.title("⛵ Land Yacht Course Definer")
st.markdown("Isolate your racing arena layout and log fleet configuration parameters.")

# Initialize Core Session Memory Layers
if 'course_log' not in st.session_state: st.session_state.course_log = {}
if 'sailor_registry' not in st.session_state: st.session_state.sailor_registry = {}
if 'race_specs' not in st.session_state: st.session_state.race_specs = {}

# --- SIDEBAR CONTROL PANEL ---
st.sidebar.header("🕹️ Race Control Panel")
total_races = st.sidebar.number_input("Total Races", min_value=1, max_value=20, value=3)
race_options = [f"Race {i}" for i in range(1, total_races + 1)]
active_race = st.sidebar.selectbox("Active Race", options=race_options)
allocated_duration = st.sidebar.selectbox("Duration (Mins)", options=(10, 15, 20, 25, 30), index=2)

if active_race not in st.session_state.course_log:
    st.session_state.course_log[active_race] = []

if st.sidebar.button("📋 Copy Course from Previous Race"):
    current_idx = race_options.index(active_race)
    if current_idx > 0:
        prev_race = race_options[current_idx - 1]
        if prev_race in st.session_state.course_log and st.session_state.course_log[prev_race]:
            st.session_state.course_log[active_race] = list(st.session_state.course_log[prev_race])
            st.sidebar.success(f"Copied course from {prev_race}!")

st.sidebar.divider()
st.sidebar.header("📥 Sailor Setup Profile")
uploaded_file = st.sidebar.file_uploader("Upload XOSS .fit file", type=["fit"])
sailor_name = st.sidebar.text_input("Sailor Name / Yacht Number", placeholder="e.g., Yacht 42")

df_track = pd.DataFrame()
if uploaded_file:
    df_track = extract_fit_data(uploaded_file)

if sailor_name:
    if sailor_name not in st.session_state.sailor_registry: st.session_state.sailor_registry[sailor_name] = True
    if active_race not in st.session_state.race_specs: st.session_state.race_specs[active_race] = {}
    if sailor_name not in st.session_state.race_specs[active_race]:
        st.session_state.race_specs[active_race][sailor_name] = {"tire_pressure": 1.4, "boom_height": 25, "sail_size": "5.5", "race_weight": 85}

    specs = st.session_state.race_specs[active_race][sailor_name]
    specs["tire_pressure"] = st.sidebar.selectbox("Tires (Bar)", (1.0, 1.2, 1.4, 1.6, 1.8, 2.0), index=(1.0, 1.2, 1.4, 1.6, 1.8, 2.0).index(specs["tire_pressure"]))
    specs["boom_height"] = st.sidebar.selectbox("Boom (cm)", (15, 17, 19, 22, 25, 28, 32, 36, 40, 44, 48), index=(15, 17, 19, 22, 25, 28, 32, 36, 40, 44, 48).index(specs["boom_height"]))
    specs["sail_size"] = st.sidebar.selectbox("Sail Size", ("3", "3.5", "4.5", "5.5", "6.2"), index=("3", "3.5", "4.5", "5.5", "6.2").index(specs["sail_size"]))
    specs["race_weight"] = st.sidebar.slider("Weight (kg)", 60, 110, int(specs["race_weight"]))

# --- SCREEN MAIN LAYOUT AREA ---
col_map, col_data = st.columns([2.5, 1.5])
current_markers = st.session_state.course_log[active_race]

with col_map:
    st.subheader(f"📈 Telemetry Path Plot - {active_race}")
    if not df_track.empty:
        # Standard fast line graph to bypass all map errors completely
        fig = px.line(df_track, x="Lon", y="Lat", title="Yacht Sailing Footprint")
        fig.update_traces(line=dict(color="blue", width=3))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Awaiting a .fit file upload to plot the track coordinates.")

with col_data:
    st.subheader("📋 Course Definition Parameters")
    num_markers = len(current_markers)
    
    # 4 to 10 numerical layout definitions input boxes
    if num_markers < 4:
        st.markdown("**🏁 Define Gates**")
        in_lat = st.number_input("Marker Latitude", value=0.0, format="%.6f")
        in_lon = st.number_input("Marker Longitude", value=0.0, format="%.6f")
        
        lbl = "Start Line A" if num_markers == 0 else ("Start Line B" if num_markers == 1 else ("Finish Line A" if num_markers == 2 else "Finish Line B"))
        clr = "green" if num_markers < 2 else "red"
        desc = "Gate"
    else:
        st.markdown(f"**🟠 Define Cones (Max 6)**")
        in_lat = st.number_input(f"Cone {num_markers - 3} Latitude", value=0.0, format="%.6f")
        in_lon = st.number_input(f"Cone {num_markers - 3} Longitude", value=0.0, format="%.6f")
        lbl = f"Cone {num_markers - 3}"
        clr = "orange"
        desc = "Cone Mark"

    if num_markers < 10:
        if st.button("➕ Log Marker Coordinate"):
            st.session_state.course_log[active_race].append({"Seq ID": num_markers + 1, "Description": desc, "Label": lbl, "Latitude": in_lat, "Longitude": in_lon, "Color": clr})
            st.rerun()
    else:
        st.warning("Maximum capacity of 6 Cones reached. Layout locked.")

    if st.button("↩️ Undo Last"):
        if st.session_state.course_log[active_race]:
            st.session_state.course_log[active_race].pop()
            st.rerun()

    if current_markers:
        st.dataframe(pd.DataFrame(current_markers)[["Seq ID", "Description", "Latitude", "Longitude"]], use_container_width=True, hide_index=True)

st.divider()
st.subheader(f"📊 Performance Leaderboard Matrix — {active_race}")
fleet_rows = []
if active_race in st.session_state.race_specs:
    for name, tuning in st.session_state.race_specs[active_race].items():
        fleet_rows.append({
            "Yacht Identifier": name, "Sail Size": tuning["sail_size"], "Weight (kg)": tuning["race_weight"],
            "Boom Gap (cm)": tuning["boom_height"], "Tires (Bar)": tuning["tire_pressure"],
            "Distance (km)": "0.00", "Avg Speed": "0.0 kph", "VMC": "0.0 kph"
        })
st.table(pd.DataFrame(fleet_rows))
