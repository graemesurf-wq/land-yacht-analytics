import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from fitparse import FitFile

st.set_page_config(
    page_title="Land Yacht VMC Analyzer",
    page_icon="⛵",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("⛵ Land Yacht VMC Performance Analyzer")
st.markdown("Foundational framework for course layout definitions and fleet configuration parameters.")

if 'course_log' not in st.session_state: 
    st.session_state.course_log = []
if 'sailor_registry' not in st.session_state: 
    st.session_state.sailor_registry = {}
if 'race_specs' not in st.session_state: 
    st.session_state.race_specs = {}

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
        st.sidebar.header("🕹️ Race Control Panel")
total_races = st.sidebar.number_input("Total Races for the Day", min_value=1, max_value=20, value=3)
race_options = [f"Race {i}" for i in range(1, total_races + 1)]
active_race = st.sidebar.selectbox("Active Race to Configure", options=race_options)

duration_choices =
allocated_duration = st.sidebar.selectbox("Allocated Race Duration", options=duration_choices, index=2, format_func=lambda x: f"{x} Minutes")

if st.sidebar.button("📋 Copy Course Layout from Previous Race"):
    current_idx = race_options.index(active_race)
    if current_idx > 0:
        prev_race = race_options[current_idx - 1]
        prev_markers = [dict(m) for m in st.session_state.course_log if m.get("race") == prev_race]
        if prev_markers:
            st.session_state.course_log = [m for m in st.session_state.course_log if m.get("race") != active_race]
            for m in prev_markers:
                m["race"] = active_race
                st.session_state.course_log.append(m)
            st.sidebar.success(f"Copied course markers from {prev_race}!")
        else:
            st.sidebar.error(f"No course layout found in {prev_race} to copy.")
    else:
        st.sidebar.error("This is the first race. No previous course exists.")

st.sidebar.divider()
st.sidebar.header("📥 Sailor Log & Setup Profile")
uploaded_file = st.sidebar.file_uploader("Upload your XOSS .fit file", type=["fit"])
sailor_name = st.sidebar.text_input("Sailor Name / Yacht Number", placeholder="e.g., Yacht 42")

df_track = pd.DataFrame()
if uploaded_file:
    df_track = extract_track_points(uploaded_file)

if sailor_name:
    if sailor_name not in st.session_state.sailor_registry:
        st.session_state.sailor_registry[sailor_name] = True
    if active_race not in st.session_state.race_specs:
        st.session_state.race_specs[active_race] = {}
    if sailor_name not in st.session_state.race_specs[active_race]:
        current_idx = race_options.index(active_race)
        prev_race = race_options[current_idx - 1] if current_idx > 0 else None
        if prev_race and prev_race in st.session_state.race_specs and sailor_name in st.session_state.race_specs[prev_race]:
            st.session_state.race_specs[active_race][sailor_name] = dict(st.session_state.race_specs[prev_race][sailor_name])
        else:
            st.session_state.race_specs[active_race][sailor_name] = {
                "tire_pressure": 1.4, "boom_height": 25, "sail_size": "5.5", "race_weight": 85
            }

    specs = st.session_state.race_specs[active_race][sailor_name]
    tp_options = [1.0, 1.2, 1.4, 1.6, 1.8, 2.0]
    specs["tire_pressure"] = st.sidebar.selectbox("Tire Pressure (Bar)", options=tp_options, index=tp_options.index(specs["tire_pressure"]))
    bh_options =
    specs["boom_height"] = st.sidebar.selectbox("Boom Height (cm gap)", options=bh_options, index=bh_options.index(specs["boom_height"]))
    ss_options = ["3", "3.5", "4.5", "5.5", "6.2"]
    specs["sail_size"] = st.sidebar.selectbox("Sail Size", options=ss_options, index=ss_options.index(specs["sail_size"]))
    specs["race_weight"] = st.sidebar.slider("Total Race Weight (kg)", min_value=60, max_value=110, value=int(specs["race_weight"]))
col_map, col_data = st.columns([2.5, 1.5])
active_markers = [m for m in st.session_state.course_log if m.get("race") == active_race]

with col_map:
    st.subheader(f"🗺️ Performance Satellite Map - {active_race}")
    st.caption("💡 Zoom cleanly with your scroll wheel. Click anywhere on the map image grid to position your racing cones.")
    
    center_lat, center_lon = 51.5074, -0.1278
    # FIXED: Added [0] indexers to force raw numeric extraction and prevent the validator crash
    if not df_track.empty:
        center_lat = float(df_track["Latitude"].iloc[0])
        center_lon = float(df_track["Longitude"].iloc[0])

    fig = go.Figure()
    if not df_track.empty:
        fig.add_trace(go.Scattermapbox(
            lat=df_track["Latitude"], lon=df_track["Longitude"],
            mode="lines", line=dict(width=3.5, color="yellow"), name="Sailing Path"
        ))

    if active_markers:
        df_markers = pd.DataFrame(active_markers)
        fig.add_trace(go.Scattermapbox(
            lat=df_markers["Latitude"], lon=df_markers["Longitude"],
            mode="markers+text", marker=dict(size=14, color=df_markers["Color"]),
            text=df_markers["Label"], textposition="top center", name="Course Markers"
        ))
        if len(active_markers) >= 2:
            fig.add_trace(go.Scattermapbox(lat=[active_markers[0]["Latitude"], active_markers[1]["Latitude"]], lon=[active_markers[0]["Longitude"], active_markers[1]["Longitude"]], mode="lines", line=dict(width=2, color="green", dash="dash"), showlegend=False))
        if len(active_markers) >= 4:
            fig.add_trace(go.Scattermapbox(lat=[active_markers[2]["Latitude"], active_markers[3]["Latitude"]], lon=[active_markers[2]["Longitude"], active_markers[3]["Longitude"]], mode="lines", line=dict(width=2, color="red", dash="dash"), showlegend=False))

    fig.update_layout(
        mapbox=dict(
            style="white-bg",
            layers=[{
                "below": "traces", "sourcetype": "raster",
                "source": ["https://arcgisonline.com{z}/{y}/{x}"]
            }],
            center=dict(lat=center_lat, lon=center_lon), zoom=14
        ),
        margin=dict(r=0, t=0, l=0, b=0), height=500
    )
    
    map_click = st.plotly_chart(fig, use_container_width=True, on_click=True)

    if map_click and map_click.get("points") and map_click["points"].get("mapbox_clicks"):
        click_data = map_click["points"]["mapbox_clicks"]
        c_lat = click_data.get("lat")
        c_lon = click_data.get("lon")
        if c_lat and c_lon:
            c_num = len(active_markers) + 1
            if c_num <= 10:
                if c_num == 1: lbl, clr = "Start Line A", "green"
                elif c_num == 2: lbl, clr = "Start Line B", "green"
                elif c_num == 3: lbl, clr = "Finish Line A", "red"
                elif c_num == 4: lbl, clr = "Finish Line B", "red"
                else: lbl, clr = f"Cone {c_num - 4}", "orange"
                st.session_state.course_log.append({
                    "race": active_race, "Seq ID": c_num, "Label": lbl, 
                    "Description": "Gate Components" if c_num<=4 else f"Course Cone {c_num-4}", 
                    "Latitude": c_lat, "Longitude": c_lon, "Color": clr
                })
                st.rerun()

    c1, c2 = st.columns(2)
    with c1:
        if st.button("↩️ Undo Last Marker", use_container_width=True):
            for i in range(len(st.session_state.course_log) - 1, -1, -1):
                if st.session_state.course_log[i]["race"] == active_race:
                    st.session_state.course_log.pop(i)
                    st.rerun()
    with c2:
        if st.button("🗑️ Clear Entire Course Layout", use_container_width=True):
            st.session_state.course_log = [m for m in st.session_state.course_log if m.get("race") != active_race]
            st.rerun()

with col_data:
    st.subheader("📋 Active Course Definition Log")
    if active_markers:
        st.dataframe(pd.DataFrame(active_markers)[["Seq ID", "Description", "Latitude", "Longitude"]], use_container_width=True, hide_index=True)
    else:
        st.text("No geometric layout anchors mapped yet.")

st.divider()
st.subheader(f"📊 Performance Leaderboard Matrix — {active_race}")
fleet_rows = []
if active_race in st.session_state.race_specs:
    for name, tuning in st.session_state.race_specs[active_race].items():
        file_status = "✅ File Loaded" if uploaded_file and not df_track.empty else ("❌ Empty File" if uploaded_file else "⏳ Awaiting File")
        fleet_rows.append({
            "Yacht Identifier": name, "Sail Size": tuning["sail_size"], "Weight (kg)": tuning["race_weight"],
            "Boom Gap (cm)": tuning["boom_height"], "Tires (Bar)": tuning["tire_pressure"],
            "Data Status": file_status, "Distance (km)": "0.00", "Avg Speed": "0.0 kph", "VMC": "0.0 kph"
        })
if fleet_rows:
    st.table(pd.DataFrame(fleet_rows))
