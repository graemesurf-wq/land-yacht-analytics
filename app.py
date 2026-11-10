import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from engine import extract_fit_data

st.set_page_config(page_title="VMC Analyzer", layout="wide")
st.title("⛵ Land Yacht Course Definer")
st.markdown("Use the selection crosshair cursor to click on the grid relative to your tracks to place marks.")

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
    specs["tire_pressure"] = st.sidebar.selectbox("Tire Pressure (Bar)", (1.0, 1.2, 1.4, 1.6, 1.8, 2.0), index=(1.0, 1.2, 1.4, 1.6, 1.8, 2.0).index(specs["tire_pressure"]))
    specs["boom_height"] = st.sidebar.selectbox("Boom Height (cm)", (15, 17, 19, 22, 25, 28, 32, 36, 40, 44, 48), index=(15, 17, 19, 22, 25, 28, 32, 36, 40, 44, 48).index(specs["boom_height"]))
    specs["sail_size"] = st.sidebar.selectbox("Sail Size", ("3", "3.5", "4.5", "5.5", "6.2"), index=("3", "3.5", "4.5", "5.5", "6.2").index(specs["sail_size"]))
    specs["race_weight"] = st.sidebar.slider("Weight (kg)", 60, 110, int(specs["race_weight"]))

# --- SCREEN MAIN LAYOUT AREA ---
col_map, col_data = st.columns([2.5, 1.5])
current_markers = st.session_state.course_log[active_race]

with col_map:
    st.subheader(f"📈 Clickable Canvas Grid - {active_race}")
    
    fig = go.Figure()
    
    if not df_track.empty:
        fig.add_trace(go.Scatter(
            x=df_track["Lon"], y=df_track["Lat"], mode="lines",
            line=dict(color="blue", width=3), name="Yacht Track"
        ))
    
    if current_markers:
        df_markers = pd.DataFrame(current_markers)
        fig.add_trace(go.Scatter(
            x=df_markers["Longitude"], y=df_markers["Latitude"], mode="markers+text",
            marker=dict(size=14, color=df_markers["Color"]),
            text=df_markers["Label"], textposition="top center", name="Course Marks"
        ))

    # FIXED: Turned off standard dragging zoom and activated box select crosshairs by default
    fig.update_layout(
        xaxis=dict(title="Longitude", showgrid=True, zeroline=False),
        yaxis=dict(title="Latitude", showgrid=True, zeroline=False),
        margin=dict(r=10, t=10, l=10, b=10), height=500,
        dragmode="select",
        clickmode="event+select"
    )
    
    # Process choice outputs from selection canvas interaction
    map_click = st.plotly_chart(fig, use_container_width=True, on_select="rerun")

    if map_click and map_click.get("selection") and map_click["selection"].get("box"):
        box_data = map_click["selection"]["box"]
        # Extract the center point array from your click crosshair rectangle box boundary selection window
        if box_data and len(box_data) > 0:
            c_lon = float(sum(box_data["x"]) / 2)
            c_lat = float(sum(box_data["y"]) / 2)
            
            num_markers = len(current_markers)
            if num_markers < 10:
                c_num = num_markers + 1
                if c_num == 1: lbl, clr = "Start Line A", "green"
                elif c_num == 2: lbl, clr = "Start Line B", "green"
                elif c_num == 3: lbl, clr = "Finish Line A", "red"
                elif c_num == 4: lbl, clr = "Finish Line B", "red"
                else: lbl, clr = f"Cone {c_num - 4}", "orange"
                
                desc = "Gate" if c_num <= 4 else f"Mark Cone {c_num - 4}"
                
                st.session_state.course_log[active_race].append({
                    "Seq ID": c_num, "Description": desc, "Label": lbl,
                    "Latitude": c_lat, "Longitude": c_lon, "Color": clr
                })
                st.rerun()

    c1, c2 = st.columns(2)
    with c1:
        if st.button("↩️ Undo Last", use_container_width=True):
            if st.session_state.course_log[active_race]:
                st.session_state.course_log[active_race].pop()
                st.rerun()
    with c2:
        if st.button("🗑️ Clear Layout", use_container_width=True):
            st.session_state.course_log[active_race] = []
            st.rerun()

with col_data:
    st.subheader("📋 Course Definition Log")
    num_markers = len(current_markers)
    if num_markers == 0: st.info("👉 Click and draw a tiny selection square anywhere on the grid relative to the turn to drop **Start Line Marker A**.")
    elif num_markers == 1: st.info("👉 Click/select to drop **Start Line Marker B**.")
    elif num_markers == 2: st.info("👉 Click/select to drop **Finish Line Marker A**.")
    elif num_markers == 3: st.info("👉 Click/select to drop **Finish Line Marker B**.")
    elif 4 <= num_markers < 10: st.success(f"Gates set. Cones left to drop: {10 - num_markers} (Min 2 cones).")
    else: st.warning("Maximum capacity of 6 Cones reached. Layout locked.")

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
