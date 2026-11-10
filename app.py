import streamlit as st
import pandas as pd
import folium
from folium.plugins import Draw
from streamlit_folium import st_folium
from fitparse import FitFile
import numpy as np
from datetime import datetime

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
    if not p1 or not p2:
        return 999999
    # Safely convert to flat lists if nested coordinates pass in
    pt1 = p1[0] if isinstance(p1[0], list) else p1
    pt2 = p2[0] if isinstance(p2[0], list) else p2
    
    R = 6371000
    phi1, phi2 = np.radians(pt1[0]), np.radians(pt2[0])
    dphi = np.radians(pt2[0] - pt1[0])
    dlon = np.radians(pt2[1] - pt1[1])
    a = np.sin(dphi/2)**2 + np.cos(phi1)*np.cos(phi2) * np.sin(dlon/2)**2
    return R * 2 * np.arctan2(np.sqrt(a), np.sqrt(1-a))

def parse_multi_races_by_gaps(records, course_start, course_finish, mark1, duration_list, max_races):
    if len(records) < 20 or not course_start or not mark1:
        return [{"name": "Full Session Log", "points": [r["coords"] for r in records], "duration": 0.0}]

    chunks = []
    current_chunk = [records]
    
    for idx in range(1, len(records)):
        t_prev = records[idx-1]["timestamp"]
        t_curr = records[idx]["timestamp"]
        time_delta = (t_curr - t_prev).total_seconds() if (t_prev and t_curr) else 1
        
        if time_delta > 30:
            chunks.append(current_chunk)
            current_chunk = [records[idx]]
        else:
            current_chunk.append(records[idx])
    chunks.append(current_chunk)

    races = []
    mark1_pt = mark1[0] if isinstance(mark1, list) and len(mark1) > 0 and isinstance(mark1[0], list) else mark1
    gate_finish_pt = course_finish[0] if course_finish and isinstance(course_finish, list) and len(course_finish) > 0 and isinstance(course_finish[0], list) else course_finish

    for chunk in chunks:
        if len(races) >= max_races:
            break
        if len(chunk) < 30:
            continue
            
        chunk_coords = [r["coords"] for r in chunk]
        
        validated = False
        validation_limit = min(300, len(chunk_coords))
        for v_idx in range(validation_limit):
            if haversine_dist(chunk_coords[v_idx], mark1_pt) < 50:
                validated = True
                break
                
        if not validated:
            continue 
            
        current_race_idx = len(races)
        race_duration_mins = duration_list[current_race_idx] if current_race_idx < len(duration_list) else 20.0
        
        countdown_start_idx = min(180, len(chunk_coords) - 1)
        duration_pts = int(race_duration_mins * 60)
        timer_expiry_idx = min(countdown_start_idx + duration_pts, len(chunk_coords) - 1)
        
        finish_crossed_idx = timer_expiry_idx
        found_finish = False
        for f_idx in range(timer_expiry_idx, len(chunk_coords)):
            if gate_finish_pt and haversine_dist(chunk_coords[f_idx], gate_finish_pt) < 30:
                finish_crossed_idx = f_idx
                found_finish = True
                break
                
        if not found_finish:
            finish_crossed_idx = len(chunk_coords) - 1
            
        races.append({
            "name": f"Race {current_race_idx + 1}",
            "points": chunk_coords[:finish_crossed_idx + 1],
            "duration": race_duration_mins
        })
        
    if not races:
        return [{"name": "Full Data Track (No Heats Validated)", "points": [r["coords"] for r in records], "duration": 0.0}]
    return races

# --- SIDEBAR CONTROLS & DESIGNER VIEW ---
st.sidebar.header("Mode Selection")
app_mode = st.sidebar.radio("Choose App Role:", ["Racer Mode (Upload & Compare Tracks)", "Designer Mode (Create/Edit Course Layout)"])

if app_mode == "Designer Mode (Create/Edit Course Layout)":
    st.subheader("🛠️ Course Designer Mode")
    st.markdown("1. Upload file. 2. Draw Start line first, Finish line second, drop Mark 1 pin. 3. Lock setup.")
    
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
                if g_type == "LineString": lines.append([[pt[1], pt[0]] for pt in coords])
                elif g_type == "Point": markers.append([coords[1], coords[0]])
        
        if lines: folium.PolyLine(locations=lines, color="green", weight=6).add_to(m)
        if len(lines) >= 2: folium.PolyLine(locations=lines[1], color="red", weight=6).add_to(m)
        for mk in markers: folium.Marker(location=mk, icon=folium.Icon(color="orange")).add_to(m)
            
        st_folium(m, width=1100, height=600, key="designer_view_map", returned_objects=[])
        
        config_text = "SAVED_COURSE = {\n"
        config_text += f'    "start_line": {lines[0] if len(lines) >= 1 else []},\n'
        config_text += f'    "finish_line": {lines[1] if len(lines) >= 2 else []},\n'
        config_text += f'    "marks": {markers}\n'
        config_text += "}"
        st.sidebar.text_area(label="Course Coordinates Box", value=config_text, height=200)
else:
    # --- RACER MODE ---
    st.sidebar.header("🏁 Analytics Configuration")
    max_races_input = st.sidebar.slider("Maximum number of races to scan for:", min_value=1, max_value=8, value=5)
    
    durations_raw = st.sidebar.text_input("Race Durations in Minutes (comma separated):", value="15, 20, 15, 15, 10")
    try:
        parsed_durations = [float(d.strip()) for d in durations_raw.split(",")]
    except:
        parsed_durations = [20.0] * max_races_input
        st.sidebar.error("Invalid duration format. Defaulted to 20 mins per heat.")

    st.subheader("🏃‍♂️ Multi-Race Segmentation Dashboard")
    st.markdown("Upload session tracking logs. The timeline state machine will completely discard warmups and filter staging movements to isolate clean races.")
    
    uploaded_files = st.file_uploader("Upload competitor .fit track files", type=["fit"], accept_multiple_files=True, key="racer_uploader")
    
    course_start = SAVED_COURSE["start_line"]
    course_finish = SAVED_COURSE["finish_line"]
    course_marks = SAVED_COURSE["marks"]
    
    if not course_start and st.session_state["saved_raw_drawings"]:
        lines, markers = [], []
        for item in st.session_state["saved_raw_drawings"]:
            g_type, coords = item['geometry']['type'], item['geometry']['coordinates']
            if g_type == "LineString": lines.append([[pt[1], pt[0]] for pt in coords])
            elif g_type == "Point": markers.append([coords[1], coords[0]])
        course_start = lines[0] if len(lines) >= 1 else []
        course_finish = lines[1] if len(lines) >= 2 else []
        course_marks = markers

    mark1_anchor = course_marks if course_marks else None
    all_parsed_competitor_data = {}
    all_lats, all_lons = [], []
    
    if uploaded_files:
        for up_file in uploaded_files:
            raw_records = []
            try:
                fitfile = FitFile(up_file.read())
                for record in fitfile.get_messages("record"):
                    lat = record.get_value("position_lat")
                    lon = record.get_value("position_long")
                    t_val = record.get_value("timestamp")
                    
                    if lat and lon:
                        lat_d = lat * (180.0 / 2**31)
                        lon_d = lon * (180.0 / 2**31)
                        raw_records.append({
                            "coords": (lat_d, lon_d),
                            "timestamp": t_val
                        })
                        all_lats.append(lat_d)
                        all_lons.append(lon_d)
                        
                if len(raw_records) > 0 and course_start:
                    segmented_heats = parse_multi_races_by_gaps(raw_records, course_start, course_finish, mark1_anchor, parsed_durations, max_races_input)
                    all_parsed_competitor_data[up_file.name] = segmented_heats
            except Exception as e:
                st.error(f"Error parsing file {up_file.name}: {e}")

    # CRUCIAL FIX: Extract single point pair [0] from multi-point gate arrays to anchor map center securely
    if all_lats:
        map_center = [sum(all_lats)/len(all_lats), sum(all_lons)/len(all_lons)]
    elif course_start and isinstance(course_start, list) and len(course_start) > 0:
        map_center = course_start[0] if isinstance(course_start[0], list) else course_start
    else:
        map_center = [53.46, 9.98]
        
    m = folium.Map(location=map_center, zoom_start=15, tiles="https://arcgisonline.com{z}/{y}/{x}", attr="Esri World Imagery")
    folium.TileLayer('OpenStreetMap').add_to(m)
    folium.LayerControl().add_to(m)
    
    if course_start:
        folium.PolyLine(locations=course_start, color="green", weight=6).add_to(m)
        folium.Marker(location=course_start[0] if isinstance(course_start[0], list) else course_start, popup="🟢 START", icon=folium.Icon(color="green", icon="play")).add_to(m)
    if course_finish:
        folium.PolyLine(locations=course_finish, color="red", weight=6).add_to(m)
        folium.Marker(location=course_finish[0] if isinstance(course_finish[0], list) else course_finish, popup="🏁 FINISH", icon=folium.Icon(color="red", icon="flag-checkered")).add_to(m)
    for idx, mark in enumerate(course_marks):
        folium.Marker(location=mark, popup=f"📍 Mark {idx+1}", icon=folium.Icon(color="orange", icon="star")).add_to(m)

    # --- SIDEBAR INTERACTIVE FILTERS ---
    selected_heat_view = "Show All Context"
    competitor_visibility = {}
    
    if all_parsed_competitor_data:
        st.sidebar.subheader("🔍 Active Heat Isolate")
        heat_options = ["Show All Context"] + [f"Race {i+1}" for i in range(max_races_input)]
        selected_heat_view = st.sidebar.selectbox("Select a race event to sync on screen:", heat_options)
        
        st.sidebar.subheader("👥 Competitors Filter")
        for c_name in all_parsed_competitor_data.keys():
            competitor_visibility[c_name] = st.sidebar.checkbox(f"Display {c_name}", value=True)

    competitor_colors = ["cyan", "yellow", "magenta", "lime", "orange", "pink", "white", "gold"]
    
    for c_idx, (c_name, heats) in enumerate(all_parsed_competitor_data.items()):
        if not competitor_visibility.get(c_name, True):
            continue
            
        c_color = competitor_colors[c_idx % len(competitor_colors)]
        for heat in heats:
            if selected_heat_view == "Show All Context":
                opacity_val, weight_val = 0.5, 3
            elif selected_heat_view == heat["name"]:
                opacity_val, weight_val = 0.95, 5
            else:
                opacity_val, weight_val = 0.0, 0
                
            if weight_val > 0:
                folium.PolyLine(locations=heat["points"], color=c_color, weight=weight_val, opacity=opacity_val, tooltip=f"{c_name} - {heat['name']}").add_to(m)

    st_folium(m, width=1100, height=650, key="racer_map_widget", returned_objects=[])
    
    if all_parsed_competitor_data:
        st.markdown("### 🏆 Segmented Race Diagnostics Analytics Matrix")
        for c_name, heats in all_parsed_competitor_data.items():
            if not competitor_visibility.get(c_name, True): continue
            with st.expander(f"📋 Telemetry Profiles: {c_name}"):
                cols = st.columns(len(heats) if len(heats) > 0 else 1)
                for h_idx, heat in enumerate(heats):
                    col_target = cols[h_idx % len(cols)]
                    col_target.metric(label=heat["name"], value=f"{len(heat['points'])} secs", delta=f"{heat['duration']} min cap")
