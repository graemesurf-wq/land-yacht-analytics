import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
from fitparse import FitFile

# Set up the look of the web page
st.set_page_config(
    page_title="Land Yacht VMC Analyzer",
    page_icon="⛵",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("⛵ Land Yacht VMC Performance Analyzer")
st.markdown("Foundational framework for course layout definitions and fleet configuration parameters.")

# Set up the memory banks to remember our data
if 'course_log' not in st.session_state:
    st.session_state.course_log = {}

if 'sailor_registry' not in st.session_state:
    st.session_state.sailor_registry = {}

if 'race_specs' not in st.session_state:
    st.session_state.race_specs = {}

# Helper function to extract GPS path out of an uploaded .fit file
def extract_track_points(uploaded_file):
    try:
        uploaded_file.seek(0)
        fitfile = FitFile(uploaded_file.read())
        points = []
        for record in fitfile.get_messages('record'):
            lat = record.get_value('position_lat')
            lon = record.get_value('position_long')
            if lat is not None and lon is not None:
                # Convert semicircles to standard GPS degrees safely
                points.append([lat * (180.0 / 2**31), lon * (180.0 / 2**31)])
        return points
    except:
        return []

# --- SIDEBAR PANEL (LEFT SIDE OF SCREEN) ---
st.sidebar.header("🕹️ Race Control Panel")

total_races = st.sidebar.number_input("Total Races for the Day", min_value=1, max_value=20, value=3)
race_options = [f"Race {i}" for i in range(1, total_races + 1)]
active_race = st.sidebar.selectbox("Active Race to Configure", options=race_options)

duration_choices = [10, 15, 20, 25, 30]
allocated_duration = st.sidebar.selectbox("Allocated Race Duration", options=duration_choices, index=2, format_func=lambda x: f"{x} Minutes")

if active_race not in st.session_state.course_log:
    st.session_state.course_log[active_race] = []

if st.sidebar.button("📋 Copy Course Layout from Previous Race"):
    current_idx = race_options.index(active_race)
    if current_idx > 0:
        prev_race = race_options[current_idx - 1]
        if prev_race in st.session_state.course_log and st.session_state.course_log[prev_race]:
            st.session_state.course_log[active_race] = list(st.session_state.course_log[prev_race])
            st.sidebar.success(f"Copied markers from {prev_race}!")
        else:
            st.sidebar.error(f"No course layout found in {prev_race} to copy.")
    else:
        st.sidebar.error("This is the first race. No previous course exists.")

st.sidebar.divider()
st.sidebar.header("📥 Sailor Log & Setup Profile")

uploaded_file = st.sidebar.file_uploader("Upload your XOSS .fit file", type=["fit"])
sailor_name = st.sidebar.text_input("Sailor Name / Yacht Number", placeholder="e.g., Yacht 42")

track_points = []
if uploaded_file:
    track_points = extract_track_points(uploaded_file)

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
                "tire_pressure": 1.4, "boom_height": 25, "sail_size": "5.5m", "race_weight": 85
            }

    specs = st.session_state.race_specs[active_race][sailor_name]
    
    tp_options = [1.0, 1.2, 1.4, 1.6, 1.8, 2.0]
    specs["tire_pressure"] = st.sidebar.selectbox("Tire Pressure (Bar)", options=tp_options, index=tp_options.index(specs["tire_pressure"]))
    
    bh_options = [15, 17, 19, 22, 25, 28, 32, 36, 40, 44, 48]
    specs["boom_height"] = st.sidebar.selectbox("Boom Height (cm gap)", options=bh_options, index=bh_options.index(specs["boom_height"]))
    
    ss_options = ["3", "3.5", "4.5", "5.5", "6.2"]
    specs["sail_size"] = st.sidebar.selectbox("Sail Size", options=ss_options, index=ss_options.index(specs["sail_size"]))
    
    specs["race_weight"] = st.sidebar.slider("Total Race Weight (kg)", min_value=60, max_value=110, value=int(specs["race_weight"]))

# --- MAIN AREA LAYOUT (MAP AND TABLES) ---
col_map, col_data = st.columns([2.5, 1.5])

with col_map:
    st.subheader(f"🗺️ Course Mapping Canvas - {active_race}")
    
    # Default map view center
    map_center = [51.5074, -0.1278]
    if len(track_points) > 0:
        map_center = track_points[0]
        
    # CHANGED HERE: Switched to Google Satellite Tiles for open web compatibility
    m = folium.Map(
        location=map_center, 
        zoom_start=15, 
        tiles="https://google.com{x}&y={y}&z={z}", 
        attr="Google Satellite"
    )
    
    # Render the bright yellow yacht track layer onto the satellite beach
    if len(track_points) > 0:
        folium.PolyLine(track_points, color="yellow", weight=3, opacity=0.9).add_to(m)
    
    current_markers = st.session_state.course_log[active_race]
    for idx, pt in enumerate(current_markers):
        click_num = idx + 1
        if click_num == 1: lbl, ico, clr = "Start Line A", "flag", "green"
        elif click_num == 2: lbl, ico, clr = "Start Line B", "flag", "green"
        elif click_num == 3: lbl, ico, clr = "Finish Line A", "flag", "red"
        elif click_num == 4: lbl, ico, clr = "Finish Line B", "flag", "red"
        else: lbl, ico, clr = f"Cone {click_num - 4}", "info-sign", "orange"
            
        folium.Marker(location=pt, popup=lbl, icon=folium.Icon(color=clr, icon=ico)).add_to(m)
        
    if len(current_markers) >= 2:
        folium.PolyLine(current_markers[0:2], color="green", weight=3, dash_array="5, 5").add_to(m)
    if len(current_markers) >= 4:
        folium.PolyLine(current_markers[2:4], color="red", weight=3, dash_array="5, 5").add_to(m)

    map_output = st_folium(m, width=700, height=500, key=f"folium_map_{active_race}")
    
    if map_output and map_output.get("last_clicked"):
        click_coord = [map_output["last_clicked"]["lat"], map_output["last_clicked"]["lng"]]
        
        if len(st.session_state.course_log[active_race]) < 10:
            if not st.session_state.course_log[active_race] or st.session_state.course_log[active_race][-1] != click_coord:
                st.session_state.course_log[active_race].append(click_coord)
                st.rerun()

    st.markdown("  ")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("↩️ Undo Last Marker", use_container_width=True):
            if st.session_state.course_log[active_race]:
                st.session_state.course_log[active_race].pop()
                st.rerun()
    with c2:
        if st.button("🗑️ Clear Entire Course Layout", use_container_width=True):
            st.session_state.course_log[active_race] = []
            st.rerun()

with col_data:
    st.subheader("📋 Active Course Definition Log")
    
    num_markers = len(current_markers)
    if num_markers == 0:
        st.info("👉 Click on the map to place **Start Line Marker A**.")
    elif num_markers == 1:
        st.info("👉 Click to place **Start Line Marker B**.")
    elif num_markers == 2:
        st.info("👉 Click to place **Finish Line Marker A**.")
    elif num_markers == 3:
        st.info("👉 Click to place **Finish Line Marker B**.")
    elif 4 <= num_markers < 10:
        st.success(f"Gates set. Cones left to drop: {10 - num_markers} (Min 2 cones).")
    else:
        st.warning("Max capacity of 6 Cones reached. Layout locked.")

    marker_records = []
    for idx, pt in enumerate(current_markers):
        c_id = idx + 1
        if c_id == 1 or c_id == 2: type_lbl = "Start Gate"
        elif c_id == 3 or c_id == 4: type_lbl = "Finish Gate"
        else: type_lbl = f"Course Mark Cone {c_id - 4}"
        marker_records.append({"Seq ID": c_id, "Description": type_lbl, "Latitude": round(pt[0], 5), "Longitude": round(pt[1], 5)})

    if marker_records:
        st.dataframe(pd.DataFrame(marker_records), use_container_width=True, hide_index=True)
    else:
        st.text("No layout markers set yet.")

st.divider()

# --- PREVIEW PERFORMANCE LEADERBOARD ---
st.subheader(f"📊 Performance Leaderboard Matrix — {active_race}")
st.caption(f"Allocated Clock Threshold: {allocated_duration} Minutes.")

fleet_rows = []
if active_race in st.session_state.race_specs:
    for name, tuning in st.session_state.race_specs[active_race].items():
        file_status = "✅ File Loaded" if uploaded_file and len(track_points) > 0 else ("❌ Empty File Track" if uploaded_file else "⏳ Awaiting File")
        fleet_rows.append({
            "Yacht Identifier": name,
            "Sail Size": tuning["sail_size"],
            "Weight (kg)": tuning["race_weight"],
            "Boom Gap (cm)": tuning["boom_height"],
            "Tires (Bar)": tuning["tire_pressure"],
            "Data Status": file_status,
            "Distance (km)": "0.00",
            "Avg Speed": "0.0 kph",
            "VMC": "0.0 kph"
        })

if fleet_rows:
    st.table(pd.DataFrame(fleet_rows))
else:
    st.info("No active sailors logged yet. Enter a name in the sidebar to test.")
