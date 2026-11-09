import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from fitparse import FitFile

st.set_page_config(page_title="VMC Analyzer", layout="wide")
st.title("⛵ Land Yacht VMC Performance Analyzer")

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
total_races = st.sidebar.number_input("Total Races", min_value=1, max_value=20, value=3)
race_options = [f"Race {i}" for i in range(1, total_races + 1)]
active_race = st.sidebar.selectbox("Active Race", options=race_options)

duration_choices = [10, 15, 20, 25, 30]
allocated_duration = st.sidebar.selectbox("Duration", options=duration_choices, index=2)

st.sidebar.divider()
st.sidebar.header("📥 Sailor Log & Setup Profile")
uploaded_file = st.sidebar.file_uploader("Upload .fit file", type=["fit"])
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
        st.session_state.race_specs[active_race][sailor_name] = {
            "tire_pressure": 1.4, "boom_height": 25, "sail_size": "5.5", "race_weight": 85
        }

    specs = st.session_state.race_specs[active_race][sailor_name]
    tp_options = [1.0, 1.2, 1.4, 1.6, 1.8, 2.0]
    specs["tire_pressure"] = st.sidebar.selectbox("Tire Pressure (Bar)", options=tp_options, index=tp_options.index(specs["tire_pressure"]))
    bh_options = [15, 17, 19, 22, 25, 28, 32, 36, 40, 44, 48]
    specs["boom_height"] = st.sidebar.selectbox("Boom Height (cm)", options=bh_options, index=bh_options.index(specs["boom_height"]))
    ss_options = ["3", "3.5", "4.5", "5.5", "6.2"]
    specs["sail_size"] = st.sidebar.selectbox("Sail Size", options=ss_options, index=ss_options.index(specs["sail_size"]))
    specs["race_weight"] = st.sidebar.slider("Weight (kg)", 60, 110, int(specs["race_weight"]))
    col_map, col_data = st.columns([2.5, 1.5])
with col_map:
    st.subheader("🗺️ Performance Vector Map")
    st.caption("💡 Upload a .fit file first, then click directly on the yellow track line to place your markers!")
    
    center_lat, center_lon = 51.5074, -0.1278
    if not df_track.empty:
        center_lat = df_track["Latitude"].iloc[0]
        center_lon = df_track["Longitude"].iloc[0]

    fig = go.Figure()
    if not df_track.empty:
        fig.add_trace(go.Scattermap(
            lat=df_track["Latitude"], lon=df_track["Longitude"],
            mode="lines", line=dict(width=4, color="yellow"), name="Track",
            hoverinfo="text", text="Click here to add mark"
        ))

    markers = [m for m in st.session_state.course_log if m.get("race") == active_race]
    if markers:
        df_markers = pd.DataFrame(markers)
        fig.add_trace(go.Scattermap(
            lat=df_markers["Latitude"], lon=df_markers["Longitude"],
            mode="markers+text", marker=dict(size=14, color=df_markers["Color"]),
            text=df_markers["Label"], textposition="top center", name="Marks"
        ))

        if len(markers) >= 2:
            fig.add_trace(go.Scattermap(lat=[markers[0]["Latitude"], markers[1]["Latitude"]], lon=[markers[0]["Longitude"], markers[1]["Longitude"]], mode="lines", line=dict(width=2, color="green", dash="dash"), showlegend=False))
        if len(markers) >= 4:
            fig.add_trace(go.Scattermap(lat=[markers[2]["Latitude"], markers[3]["Latitude"]], lon=[markers[2]["Longitude"], markers[3]["Longitude"]], mode="lines", line=dict(width=2, color="red", dash="dash"), showlegend=False))

    fig.update_layout(
        map=dict(style="open-street-map", center=dict(lat=center_lat, lon=center_lon), zoom=14),
        margin=dict(r=0, t=0, l=0, b=0), height=500, clickmode="event"
    )
    
    map_click = st.plotly_chart(fig, use_container_width=True, on_click=True)

    if map_click and map_click.get("points") and map_click["points"].get("point_index"):
        pt_idx = map_click["points"]["point_index"][0]
        if not df_track.empty and pt_idx < len(df_track):
            c_lat = df_track["Latitude"].iloc[pt_idx]
            c_lon = df_track["Longitude"].iloc[pt_idx]
            active_markers_count = len(markers)
            if active_markers_count < 10:
                c_num = active_markers_count + 1
                if c_num == 1: lbl, clr = "Start Line A", "green"
                elif c_num == 2: lbl, clr = "Start Line B", "green"
                elif c_num == 3: lbl, clr = "Finish Line A", "red"
                elif c_num == 4: lbl, clr = "Finish Line B", "red"
                else: lbl, clr = f"Cone {c_num - 4}", "orange"
                
                st.session_state.course_log.append({
                    "race": active_race, "Seq ID": c_num, "Label": lbl, 
                    "Description": "Gate" if c_num<=4 else f"Mark Cone {c_num-4}",
                    "Latitude": c_lat, "Longitude": c_lon, "Color": clr
                })
                st.rerun()

    c1, c2 = st.columns(2)
    with c1:
        if st.button("↩️ Undo Last", use_container_width=True):
            for i in range(len(st.session_state.course_log) - 1, -1, -1):
                if st.session_state.course_log[i]["race"] == active_race:
                    st.session_state.course_log.pop(i)
                    st.rerun()
    with c2:
        if st.button("🗑️ Clear Layout", use_container_width=True):
            st.session_state.course_log = [m for m in st.session_state.course_log if m.get("race") != active_race]
            st.rerun()

with col_data:
    st.subheader("📋 Course Definition Log")
    if markers:
        st.dataframe(pd.DataFrame(markers)[["Seq ID", "Description", "Latitude", "Longitude"]], use_container_width=True, hide_index=True)
    else:
        st.info("No course markers set yet.")

st.divider()
st.subheader("📊 Performance Leaderboard Matrix")
fleet_rows = []
if active_race in st.session_state.race_specs:
    for name, tuning in st.session_state.race_specs[active_race].items():
        fleet_rows.append({
            "Yacht Identifier": name, "Sail Size": tuning["sail_size"],
            "Weight (kg)": tuning["race_weight"], "Boom Gap (cm)": tuning["boom_height"],
            "Tires (Bar)": tuning["tire_pressure"], "Distance (km)": "0.00", "Avg Speed": "0.0 kph", "VMC": "0.0 kph"
        })
if fleet_rows:
    st.table(pd.DataFrame(fleet_rows))
    
