import streamlit as st
import pandas as pd
import folium
from folium.plugins import Draw
from streamlit_folium import st_folium
from fitparse import FitFile
import numpy as np
from datetime import datetime, timedelta

st.set_page_config(layout="wide")
st.title("⛵ First-Crossing Synchronized Land Yacht Analyst")

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

def haversine_dist(p1, p2):
    if not p1 or not p2:
        return 999999
    # Ensure p1 and p2 are flat lists [lat, lon]
    pt1 = p1[0] if isinstance(p1, list) and len(p1) > 0 and isinstance(p1[0], list) else p1
    pt2 = p2[0] if isinstance(p2, list) and len(p2) > 0 and isinstance(p2[0], list) else p2
    
    # Final unpack fallback if deeply nested
    if isinstance(pt1, list) and len(pt1) > 0: pt1 = pt1[0] if isinstance(pt1[0], list) else pt1
    if isinstance(pt2, list) and len(pt2) > 0: pt2 = pt2[0] if isinstance(pt2[0], list) else pt2
    
    try:
        R = 6371000
        phi1, phi2 = np.radians(pt1[0]), np.radians(pt2[0])
        dphi = np.radians(pt2[0] - pt1[0])
        dlon = np.radians(pt2[1] - pt1[1])
        a = np.sin(dphi/2)**2 + np.cos(phi1)*np.cos(phi2) * np.sin(dlon/2)**2
        return R * 2 * np.arctan2(np.sqrt(a), np.sqrt(1-a))
    except:
        return 999999

def advanced_first_boat_sync(all_competitors_raw, course_start, course_finish, course_marks, duration_list, max_races):
    """
    First-Crossing Sync Engine: Scans fleet paths to find the exact moment the first boat
    comes within close proximity (25m) of the Start Line center.
    """
    if not all_competitors_raw or not course_start or not course_marks:
        return {}

    mark1_pt = course_marks[0] if len(course_marks) > 0 else None
    gate_start_pt = course_start[0] if len(course_start) > 0 else course_start
    gate_finish_pt = course_finish[0] if course_finish and len(course_finish) > 0 else gate_start_pt
    
    # Step 1: Find all timestamps where ANY boat is passing the start line gate
    start_crossings = []
    for c_name, records in all_competitors_raw.items():
        for r in records:
            if haversine_dist(r["coords"], gate_start_pt) < 25:
                start_crossings.append(r["timestamp"])

    if not start_crossings:
        return {c_name: [{"name": "Full Log (No Start Trigger Found)", "points": [r["coords"] for r in recs], "duration": 0.0}] for c_name, recs in all_competitors_raw.items()}

    # Sort crossings and cluster them chronologically
    start_crossings.sort()
    race_start_anchors = []
    
    if start_crossings:
        current_cluster = [start_crossings[0]]
        for t in start_crossings[1:]:
            if (t - current_cluster[-1]).total_seconds() < 600: # 10 min heat gap buffer
                current_cluster.append(t)
            else:
                race_start_anchors.append(current_cluster[0]) # The first arrival is our T_zero
                current_cluster = [t]
        if current_cluster:
            race_start_anchors.append(current_cluster[0])

    # Step 2: Segment using master time templates, validating via Mark 1
    fleet_final_segmented_data = {}
    validated_race_count = 0
    
    for c_name in all_competitors_raw.keys():
        fleet_final_segmented_data[c_name] = []
        
    for master_start_t in race_start_anchors:
        if validated_race_count >= max_races:
            break
            
        race_duration_mins = duration_list[validated_race_count] if validated_race_count < len(duration_list) else 20.0
        timer_expiry_t = master_start_t + timedelta(minutes=race_duration_mins)
        
        # Step 3: Check if fleet hits Mark 1 within 5 minutes after start triggering
        race_is_valid = False
        if mark1_pt:
            for c_name, records in all_competitors_raw.items():
                for r in records:
                    if master_start_t <= r["timestamp"] <= (master_start_t + timedelta(minutes=5)):
                        if haversine_dist(r["coords"], mark1_pt) < 60:
                            race_is_valid = True
                            break
                if race_is_valid: break
        else:
            race_is_valid = True
            
        if not race_is_valid:
            continue
            
        # Step 4: Isolate clean synchronization lanes
        for c_name, records in all_competitors_raw.items():
            race_points = []
            found_finish = False
            
            for r in records:
                if master_start_t <= r["timestamp"] <= timer_expiry_t:
                    race_points.append(r["coords"])
                elif r["timestamp"] > timer_expiry_t and not found_finish:
                    race_points.append(r["coords"])
                    if haversine_dist(r["coords"], gate_finish_pt) < 30:
                        found_finish = True
                        break
                        
            if len(race_points) > 20:
                fleet_final_segmented_data[c_name].append({
                    "name": f"Race {validated_race_count + 1}",
                    "points": race_points,
                    "duration": race_duration_mins
                })
                
        validated_race_count += 1

    for c_name in all_competitors_raw.keys():
        if not fleet_final_segmented_data[c_name]:
            fleet_final_segmented_data[c_name] = [{"name": "Full Log Run (No Sync Matches)", "points": [r["coords"] for r in all_competitors_raw[c_name]], "duration": 0.0}]

    return fleet_final_segmented_data

# --- DESIGNER CONTROLS ---
st.sidebar.header("Mode Selection")
app_mode = st.sidebar.radio("Choose App Role:", ["Racer Mode (Upload & Compare Tracks)", "Designer Mode (Create/Edit Course Layout)"])

if app_mode == "Designer Mode (Create/Edit Course Layout)":
    st.subheader("🛠️ Course Designer Mode")
    st.markdown("1. Upload reference log. 2. Draw Start Line, Finish Line, drop Mark 1. 3. Lock to export code.")
    
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
        
        if lines: folium.PolyLine(locations=lines, color="green", weight=6).add_to(m)
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
    st.sidebar.header("🏁 Analytics Configuration")
    max_races_input = st.sidebar.slider("Maximum number of races to scan for:", min_value=1, max_value=8, value=5)
    
    durations_raw = st.sidebar.text_input("Race Durations in Minutes (comma separated):", value="15, 20, 15, 15, 10")
    try:
        parsed_durations = [float(d.strip()) for d in durations_raw.split(",")]
    except:
        parsed_durations = [20.0] * max_races_input
        st.sidebar.error("Invalid duration format. Defaulted to 20 mins per heat.")

    st.subheader("Multi-Race Fleet-Synchronized Dashboard")
    st.markdown("Upload multiple competitor files simultaneously. The system detects the exact second the **first boat triggers the start line** to anchor the clock.")
    
    uploaded_files = st.file_uploader("Upload competitor .fit track files", type=["fit"], accept_multiple_files=True, key="racer_uploader")
    
    course_start = SAVED_COURSE["start_line"]
    course_finish = SAVED_COURSE["finish_line"]
    course_marks = SAVED_COURSE["marks"]
    
    if not course_start and st.session_state["saved_raw_drawings"]:
        lines, markers = [], []
        for item in st.session_state["saved_raw_drawings"]:
            g_type, coords = item['geometry']['type'], item['geometry']['coordinates']
            if g_type == "LineString": lines.append([[pt, pt] for pt in coords])
            elif g_type == "Point": markers.append([coords, coords])
        course_start = lines if len(lines) >= 1 else []
        course_finish = lines if len(lines) >= 2 else []
        course_marks = markers

    all_raw_competitors_dict = {}
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
                    
                    if lat and lon and t_val:
                        lat_d = lat * (180.0 / 2**31)
                        lon_d = lon * (180.0 / 2**31)
                        raw_records.append({
                            "coords": [lat_d, lon_d],
                            "timestamp": t_val
                        })
                        all_lats.append(lat_d)
                        all_lons.append(lon_d)
                        
                if len(raw_records) > 0:
                    all_raw_competitors_dict[up_file.name] = raw_records
            except Exception as e:
                st.error(f"Error parsing file {up_file.name}: {e}")

    # Process all files simultaneously through the updated Proximity Sync Engine
    all_parsed_competitor_data = {}
    if all_raw_competitors_dict and course_start:
        all_parsed_competitor_data = advanced_first_boat_sync(all_raw_competitors_dict, course_start, course_finish, course_marks, parsed_durations, max_races_input)

    # Clean camera target grouping
    if all_lats:
        map_center = [sum(all_lats)/len(all_lats), sum(all_lons)/len(all_lons)]
    elif course_start and len(course_start) > 0:
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
        folium.Marker(location=mark[0] if isinstance(mark, list) and isinstance(mark[0], list) else mark, popup=f"📍 Mark {idx+1}", icon=folium.Icon(color="orange", icon="star")).add_to(m)

    # --- SIDEBAR INTERACTIVE FILTERS ---
    selected_heat_view = "Show All Context"
    competitor_visibility = {}
    
    if all_parsed_competitor_data:
        st.sidebar.subheader("🔍 Active Heat Isolate")
        max_len = max([len(h) for h in all_parsed_competitor_data.values()]) if all_parsed_competitor_data else 1
        heat_options = ["Show All Context"] + [f"Race {i+1}" for i in range(max_len)]
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
