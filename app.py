import streamlit as st
import pandas as pd
from engine import extract_fit_data

st.set_page_config(page_title="VMC Analyzer", layout="wide")
st.title("⛵ Land Yacht Course Definer")
st.markdown("👉 Check the boxes in the list below to assign your Start/Finish gates and course cones.")

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
    specs["tire_pressure"] = st.sidebar.selectbox("Tire Pressure (Bar)", (1.0, 1.2, 1.4, 1.6, 1.8, 2.0), index=(1.0, 1.2, 1.4, 1.6, 1.8, 2.0).index(specs["tire_pressure"]))
    specs["boom_height"] = st.sidebar.selectbox("Boom Height (cm)", (15, 17, 19, 22, 25, 28, 32, 36, 40, 44, 48), index=(15, 17, 19, 22, 25, 28, 32, 36, 40, 44, 48).index(specs["boom_height"]))
    specs["sail_size"] = st.sidebar.selectbox("Sail Size", ("3", "3.5", "4.5", "5.5", "6.2"), index=("3", "3.5", "4.5", "5.5", "6.2").index(specs["sail_size"]))
    specs["race_weight"] = st.sidebar.slider("Weight (kg)", 60, 110, int(specs["race_weight"]))

# --- SCREEN MAIN LAYOUT AREA ---
col_list, col_log = st.columns([2.2, 1.8])
current_markers = st.session_state.course_log[active_race]

with col_list:
    st.subheader("📋 Interactive Track Telemetry Selector")
    
    if not df_track.empty:
        st.caption("💡 Scroll and check the box next to any point to assign it as the next sequential mark.")
        
        # Add a selectable column to the track matrix
        df_track["Assign Mark"] = False
        
        # Render Streamlit's native data editor component
        edited_df = st.data_editor(
            df_track[["Assign Mark", "Time", "Kph", "Lat", "Lon"]],
            use_container_width=True,
            hide_index=True,
            disabled=["Time", "Kph", "Lat", "Lon"]
        )
        
        # Check if a row checkbox was toggled
        selected_rows = edited_df[edited_df["Assign Mark"] == True]
        if len(selected_rows) > 0:
            num_markers = len(current_markers)
            if num_markers < 10:
                c_num = num_markers + 1
                if c_num == 1: lbl, clr = "Start Line A", "green"
                elif c_num == 2: lbl, clr = "Start Line B", "green"
                elif c_num == 3: lbl, clr = "Finish Line A", "red"
                elif c_num == 4: lbl, clr = "Finish Line B", "red"
                else: lbl, clr = f"Cone {c_num - 4}", "orange"
                
                desc = "Gate" if c_num <= 4 else f"Mark Cone {c_num - 4}"
                target_row = selected_rows.iloc[0]
                
                st.session_state.course_log[active_race].append({
                    "Seq ID": c_num, "Description": desc, "Label": lbl,
                    "Latitude": float(target_row["Lat"]), "Longitude": float(target_row["Lon"]), "Color": clr
                })
                st.rerun()
    else:
        st.info("Awaiting a .fit file upload to load the interactive data list.")

with col_log:
    st.subheader("📋 Locked Course Parameters")
    num_markers = len(current_markers)
    if num_markers == 0: st.info("👉 Check a row to lock **Start Line Marker A**.")
    elif num_markers == 1: st.info("👉 Check a row to lock **Start Line Marker B**.")
    elif num_markers == 2: st.info("👉 Check a row to lock **Finish Line Marker A**.")
    elif num_markers == 3: st.info("👉 Check a row to lock **Finish Line Marker B**.")
    elif 4 <= num_markers < 10: st.success(f"Gates set. Cones remaining: {10 - num_markers}")
    else: st.warning("Layout locked.")

    if st.button("↩️ Undo Last Assignment", use_container_width=True):
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
