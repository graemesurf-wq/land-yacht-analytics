import streamlit as st
import pandas as pd
import folium
from folium.plugins import Draw
from streamlit_folium import st_folium
from fitparse import FitFile
import numpy as np

st.set_page_config(layout="wide")
st.title("⛵ Land Yacht Multi-Race Performance Analyst")

if "designer_points" not in st.session_state:
    st.session_state["designer_points"] = []
if "saved_raw_drawings" not in st.session_state:
    st.session_state["saved_raw_drawings"] = None

# --- STEP 1: LOCKED COURSE CONFIGURATION ---
SAVED_COURSE = {
    "start_line": [],  
    "finish_line": [], 
    "marks": []   
}

# --- GEOSPATIAL & ANCHOR TIMELINE MATH ---
def haversine_dist(p1, p2):
    """Distance in meters between two [lat, lon] points"""
    R = 6371000
    phi1, phi2 = np.radians(p1[0]), np.radians(p2[0])
    dphi = np.radians(p2[0] - p1[0])
    dlon = np.radians(p2[1] - p1[1])
    a = np.sin(dphi/2)**2 + np.cos(phi1)*np.cos(phi2) * np.sin(dlon/2)**2
    return R * 2 * np.arctan2(np.sqrt(a), np.sqrt(1-a))

def parse_multi_races(records, course_start, course_finish, mark1, race_duration_mins, max_races):
    """
    Parses up to 8 races by detecting when the file cuts back in (T_zero),
    validating via Mark 1 proximity within 5 minutes, running a delayed 
    countdown (+3 min), and cutting cleanly at the finish gate after the timer expires.
    """
    if len(records) < 20 or not course_start or not mark1:
        return [{"name": "Full Session Log", "points": records}]

    races = []
    i = 0
    total_pts = len(records)
    
    while i < total_pts - 1 and len(races) < max_races:
        # T_zero is established immediately when a data chunk begins or wakes up
        t0_p = records[i]
        
        # 1. Validate via Mark 1: Look ahead 5 minutes (approx 300 data points at 1Hz recording)
        validated = False
        validation_window = min(i + 300, total_pts)
        
        for v_idx in range(i, validation_window):
            if haversine_dist(records[v_idx], mark1) < 40: # 40 meter turn radius window
                validated = True
                break
                
        if not validated:
            i += 15 # Not a race sequence; skip forward and keep searching
            continue
            
        # 2. Countdown Delay sequence initiation (+3 minutes / 180 points from T_zero)
        countdown_start_idx = min(i + 180, total_pts - 1)
        
        # 3. Race Duration calculation (e.g., 20 mins = 1200 points after countdown trigger)
        duration_pts = int(race_duration_mins * 60)
        timer_expiry_idx = min(countdown_start_idx + duration_pts, total_pts - 1)
        
        # 4. Post-Timer Hard Stop Finish Gate Check
        finish_crossed_idx = timer_expiry_idx
        for f_idx in range(timer_expiry_idx, total_pts):
            # Tight finish gate check (within 25 meters of the finish mark center coordinate)
            if haversine_dist(records[f_idx], course_finish[0]) < 25:
                finish_crossed_idx = f_idx
                break
                
        # Isolate the clean competitive race window segment array
        race_segment = records[i : finish_crossed_idx + 1]
        if len(race_segment) > 60: # Filter out short testing fragments
            races.append({
                "name": f"Race {len(races) + 1}",
                "points": race_segment,
                "start_index": i,
                "end_index": finish_crossed_idx
            })
            
        # Jump past this completed race segment block to scan for the next sequence break
        i = finish_crossed_idx + 1
        
    if not races:
        return [{"name": "Full Data Track (No Races Validated)", "points": records}]
    return races

# --- SIDEBAR CONTROLS & DESIGNER VIEW ---
st.sidebar.header("Mode Selection")
app_mode = st.sidebar.radio("Choose App Role:", ["Racer Mode (Upload & Compare Tracks)", "Designer Mode (Create/Edit Course Layout)"])

if app_mode == "Designer Mode (Create/Edit Course Layout)":
    st.subheader("🛠️ Course Designer Mode")
    st.markdown("1. Upload file. 2. Draw **Start** line first, **Finish** line second, then drop **Mark 1** pin first. 3. Lock setup.")
    
    uploaded_file = st.file_uploader("Upload reference .fit file", type=["fit"], key="designer_uploader")
    if uploaded_file:
        pts = []
        fitfile = FitFile(uploaded_file.read())
        for r in fitfile.get_messages("record"):
            lat, lon = r.get_value("position_lat"), r.get_value("position_long")
            if lat and lon: pts.append((lat * (180.0 / 2**31), lon * (180.0 / 2**31)))
        st.session_state["designer_points"] = pts
                
    active_points = st.session_state["designer_points"]
    center = [pd.DataFrame(active_points, columns=["lat", "lon"])["lat"].mean(), pd.DataFrame(active_points, columns=["lat", "lon"])["lon"].mean()] if active_points else [53.46, 9.98]
    
    lock_course = st.sidebar.checkbox("🔒 Lock Course Setup & Generate Code", value=False)
    m = folium.Map(location=center, zoom_start=15, tiles="https://arcgisonline.com{z}/{y}/{x}", attr="Esri World Imagery")
    
    if active_points:
        folium.PolyLine(locations=active_points, color="white", weight=3, opacity=0.4).add_to(m)
        
    if not lock_course:
        draw_tool = Draw(position='topleft', draw_options={'polyline': {'shapeOptions': {'color': '#00ffcc', 'weight': 5}}, 'marker': True, 'circle': False, 'rectangle': False, 'polygon': False, 'circlemarker': False})
        draw_tool.add_to(m)
        map_output = st_folium(m, width=1100, height=600, key="designer_draw_map", returned_objects=["all_drawings"])
        if map_output and map_output.get("all_drawings"):
            st.session_state["saved_raw_drawings"] = map_output["all_drawings"]
    else:
        user_drawings = st.session_state["saved_raw_drawings"]
        lines, markers = [], []
        if user_drawings:
            for item in user_drawings:
                g_type, coords = item['geometry']['type'], item['geometry']['coordinates']
                if g_type == "LineString": lines.append([[pt, pt] for pt in coords])
                elif g_type == "Point": markers.append([coords, coords])
        
        if len(lines) >= 1: folium.PolyLine(locations=lines, color="green", weight=6).add_to(m)
        if len(lines) >= 2: folium.PolyLine(locations=lines, color="red", weight=6).add_to(m)
        for mk in markers: folium.Marker(location=mk, icon=folium.Icon(color="orange")).add_to(m)
            
        st_folium(m, width=1100, height=600, key="designer_view_map", returned_objects=[])
        
        config_text = "SAVED_COURSE = {\n"
        config_text += f'    "start_line": {lines if len(lines) >= 1 else []},\n'
        config_text += f'    "finish_line": {lines if len(lines) >= 2 else []},\n'
        config_text += f'    "marks": {markers}\n'
        config_text += "}"
        st.sidebar.text_area(label="Course Coordinates Box", value=config_text, height=200)
else:
    # --- RACER MODE ---
    st.sidebar.subheader("🏁 Analytics Configuration")
    race_time_selection = st.sidebar.selectbox("Select Scheduled Race Duration:", [10, 15, 20, 25, 30], index=2)
    max_races_input = st.sidebar.slider("Maximum number of races to scan for:", min_value=1, max_value=8, value=4)
    
    st.subheader("🏃‍♂️ Multi-Race Segmentation Dashboard")
    st.markdown("Upload your session `.fit` tracking logs below. The timeline processing engine will filter warmups, validate runs via Mark 1, and segment your individual heat iterations automatically.")
    
    uploaded_files = st.file_uploader("Upload competitor .fit track files", type=["fit"], accept_multiple_files=True, key="racer_uploader")
    
    # Reconstruct master course boundaries
    course_start = SAVED_COURSE["start_line"]
    course_finish = SAVED_COURSE["finish_line"]
    course_marks = SAVED_COURSE["marks"]
    
    if not course_start and st.session_state["saved_raw_drawings"]:
        lines, markers = [], []
        for item in st.session_state["saved_raw_drawings"]:
            g_type, coords = item['geometry']['type'], item['geometry']['coordinates']
            if g_type == "LineString": lines.append([[pt, pt] for pt in coords])
            elif g_type == "Point": markers.append([coords, coords])
        if len(lines) >= 1: course_start = lines
        if len(lines) >= 2: course_finish = lines
        course_marks = markers

    # Isolate Mark 1 coordinates specifically as the primary anchor point validation gate
    mark1_anchor = course_marks[0] if course_marks else None
    
    all_parsed_competitor_data = {}
    all_lats, all_lons = [], []
    
    if uploaded_files:
        for up_file in uploaded_files:
            raw_pts = []
            try:
                fitfile = FitFile(up_file.read())
                for record in fitfile.get_messages("record"):
                    lat, lon = record.get_value("position_lat"), record.get_value("position_long")
                    if lat and lon:
                        lat_d, lon_d = lat * (180.0 / 2**31), lon * (180.0 / 2**31)
                        raw_pts.append((lat_d, lon_d))
                        all_lats.append(lat_d)
                        all_lons.append(lon_d)
                        
                if len(raw_pts) > 0:
                    # Parse out individual races from this competitor's session log
                    segmented_heats = parse_multi_races(raw_pts, course_start, course_finish, mark1_anchor, race_time_selection, max_races_input)
                    all_parsed_competitor_data[up_file.name] = segmented_heats
            except Exception as e:
                st.error(f"Error parsing file {up_file.name}: {e}")

    map_center = [sum(all_lats)/len(all_lats), sum(all_lons)/len(all_lons)] if all_lats else (course_start[0] if course_start else [53.46, 9.98])
    m = folium.Map(location=map_center, zoom_start=15, tiles="https://arcgisonline.com{z}/{y}/{x}", attr="Esri World Imagery")
    folium.TileLayer('OpenStreetMap').add_to(m)
    folium.LayerControl().add_to(m)
    
    # Draw locked track landmarks
    if course_start:
        folium.PolyLine(locations=course_start, color="green", weight=6).add_to(m)
        folium.Marker(location=course_start[0], popup="🟢 START GATE", icon=folium.Icon(color="green", icon="play")).add_to(m)
    if course_finish:
        folium.PolyLine(locations=course_finish, color="red", weight=6).add_to(m)
        folium.Marker(location=course_finish[0], popup="🏁 FINISH GATE", icon=folium.Icon(color="red", icon="flag-checkered")).add_to(m)
    for idx, mark in enumerate(course_marks):
        folium.Marker(location=mark, popup=f"📍 Mark {idx+1}", icon=folium.Icon(color="orange", icon="star")).add_to(m)

    # Isolated Race Heat Selector filter
    selected_heat_view = "Show All Context"
    if all_parsed_competitor_data:
        st.sidebar.subheader("🔍 Active Heat Isolate")
        heat_options = ["Show All Context"] + [f"Race {i+1}" for i in range(max_races_input)]
        selected_heat_view = st.sidebar.selectbox("Select a race event to sync on screen:", heat_options)

    # Plot lines securely
    competitor_colors = ["cyan", "yellow", "magenta", "lime", "orange", "pink", "white", "gold"]
    
    for c_idx, (c_name, heats) in enumerate(all_parsed_competitor_data.items()):
        c_color = competitor_colors[c_idx % len(competitor_colors)]
        
        for heat in heats:
            # Check if this specific segment matches the filtered selection choice
            if selected_heat_view == "Show All Context":
                opacity_val, weight_val = 0.5, 3
            elif selected_heat_view == heat["name"]:
                opacity_val, weight_val = 0.95, 5 # Highlight synchronized race across the field
            else:
                opacity_val, weight_val = 0.0, 0 # Completely isolate view window by hiding irrelevant log points
                
            if weight_val > 0:
                folium.PolyLine(locations=heat["points"], color=c_color, weight=weight_val, opacity=opacity_val, tooltip=f"{c_name} - {heat['name']}").add_to(m)

    st_folium(m, width=1100, height=650, key="racer_map_widget", returned_objects=[])
    
    # Detailed telemetry report generation panels below the canvas view
    if all_parsed_competitor_data:
        st.markdown("### 🏆 Segmented Race Diagnostics Analytics Matrix")
        for c_name, heats in all_parsed_competitor_data.items():
            with st.expander(f"📋 Telemetry Profiles: {c_name}"):
                cols = st.columns(len(heats) if len(heats) > 0 else 1)
                for h_idx, heat in enumerate(heats):
                    col_target = cols[h_idx % len(cols)]
                    col_target.metric(label=heat["name"], value=f"{len(heat['points'])} GPS Secs", delta="Sync Targeted" if selected_heat_view == heat["name"] else None)
