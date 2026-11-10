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
# Once you copy the configuration block from the sidebar text box, paste it directly here!
SAVED_COURSE = {
    "start_line": [],  
    "finish_line": [], 
    "marks": []   
}

# --- BULLETPROOF BRACKET CLEANER FUNCTION ---
def clean_coordinates(coord_input, expect_single_point=False):
    if not coord_input:
        return [] if not expect_single_point else [53.46, 9.98]
    try:
        while isinstance(coord_input, list) and len(coord_input) == 1 and isinstance(coord_input[0], list):
            coord_input = coord_input[0]
            
        if expect_single_point:
            if isinstance(coord_input, list) and len(coord_input) >= 2 and not isinstance(coord_input[0], list):
                return [float(coord_input[0]), float(coord_input[1])]
            elif isinstance(coord_input, list) and len(coord_input) > 0 and isinstance(coord_input[0], list):
                return [float(coord_input[0][0]), float(coord_input[0][1])]
            return [53.46, 9.98]
        else:
            cleaned_list = []
            if isinstance(coord_input, list) and len(coord_input) > 0 and not isinstance(coord_input[0], list):
                return [[float(coord_input[0]), float(coord_input[1])]]
            for pair in coord_input:
                if isinstance(pair, list) and len(pair) >= 2:
                    cleaned_list.append([float(pair[0]), float(pair[1])])
            return cleaned_list
    except Exception:
        return [] if not expect_single_point else [53.46, 9.98]

def haversine_dist(p1, p2):
    pt1 = clean_coordinates(p1, expect_single_point=True)
    pt2 = clean_coordinates(p2, expect_single_point=True)
    R = 6371000
    phi1, phi2 = np.radians(pt1[0]), np.radians(pt2[0])
    dphi = np.radians(pt2[0] - pt1[0])
    dlon = np.radians(pt2[1] - pt1[1])
    a = np.sin(dphi/2)**2 + np.cos(phi1)*np.cos(phi2) * np.sin(dlon/2)**2
    return R * 2 * np.arctan2(np.sqrt(a), np.sqrt(1-a))

def generate_line_grid_points(line_endpoints, spacing_meters=5):
    """Breaks a drawn line vector into a series of points spaced 5m apart"""
    cleaned_line = clean_coordinates(line_endpoints)
    if len(cleaned_line) < 2:
        return cleaned_line
    
    p1, p2 = np.array(cleaned_line[0]), np.array(cleaned_line[1])
    total_distance = haversine_dist(p1.tolist(), p2.tolist())
    num_points = max(2, int(total_distance / spacing_meters))
    
    lats = np.linspace(p1[0], p2[0], num_points)
    lons = np.linspace(p1[1], p2[1], num_points)
    return np.column_stack((lats, lons)).tolist()
def advanced_first_boat_sync(all_competitors_raw, course_start, course_finish, course_marks, duration_list, max_races):
    """
    Slices individual race heats by checking when any boat enters a 2.5m proximity 
    bubble of any point along your newly generated dense gate grid.
    """
    cleaned_start = clean_coordinates(course_start)
    cleaned_finish = clean_coordinates(course_finish)
    cleaned_marks = [clean_coordinates(m, expect_single_point=True) for m in course_marks] if course_marks else []

    if not all_competitors_raw or not cleaned_start or not cleaned_marks:
        return {}

    # Turn the drawn lines into a high-density 5m sensor grid array
    start_grid_nodes = generate_line_grid_points(cleaned_start, spacing_meters=5)
    finish_grid_nodes = generate_line_grid_points(cleaned_finish, spacing_meters=5) if cleaned_finish else start_grid_nodes
    mark1_pt = cleaned_marks[0] if len(cleaned_marks) > 0 else None
    
    # Pass 1: Scan for the exact second ANY boat cuts through the 2.5m start point sensory array grid
    start_crossings = []
    for c_name, records in all_competitors_raw.items():
        for r in records:
            # Check proximity to EVERY point along the start grid array
            is_near_gate = any(haversine_dist(r["coords"], node) <= 2.51 for node in start_grid_nodes)
            if is_near_gate:
                start_crossings.append(r["timestamp"])

    if not start_crossings:
        return {c_name: [{"name": "Full Log (No Grid Start Triggered)", "points": [r["coords"] for r in recs], "duration": 0.0}] for c_name, recs in all_competitors_raw.items()}

    start_crossings.sort()
    race_start_anchors = []
    
    if start_crossings:
        current_cluster = [start_crossings[0]]
        for t in start_crossings[1:]:
            if (t - current_cluster[-1]).total_seconds() < 600:
                current_cluster.append(t)
            else:
                race_start_anchors.append(current_cluster[0])
                current_cluster = [t]
        if current_cluster:
            race_start_anchors.append(current_cluster[0])

    # Pass 2: Clip fleet tracks securely, validating data via the Mark 1 rule
    fleet_final_segmented_data = {}
    validated_race_count = 0
    
    for c_name in all_competitors_raw.keys():
        fleet_final_segmented_data[c_name] = []
        
    for master_start_t in race_start_anchors:
        if validated_race_count >= max_races:
            break
            
        race_duration_mins = duration_list[validated_race_count] if validated_race_count < len(duration_list) else 20.0
        timer_expiry_t = master_start_t + timedelta(minutes=race_duration_mins)
        
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
            
        for c_name, records in all_competitors_raw.items():
            race_points = []
            found_finish = False
            
            for r in records:
                if master_start_t <= r["timestamp"] <= timer_expiry_t:
                    race_points.append(r["coords"])
                elif r["timestamp"] > timer_expiry_t and not found_finish:
                    race_points.append(r["coords"])
                    # Use the 2.5m finish grid trigger array to execute clean post-race data clips
                    is_at_finish = any(haversine_dist(r["coords"], node) <= 2.51 for node in finish_grid_nodes)
                    if is_at_finish:
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
# --- SIDEBAR INTERFACE & MAP RENDER PANEL ---
st.sidebar.header("Mode Selection")
app_mode = st.sidebar.radio("Choose App Role:", ["Racer Mode (Upload & Compare Tracks)", "Designer Mode (Create/Edit Course Layout)"])

if app_mode == "Designer Mode (Create/Edit Course Layout)":
    st.subheader("🛠️ Course Designer Mode")
    st.markdown("1. Upload file. 2. Draw Start Line, Finish Line, drop Mark 1. 3. Lock setup to export code.")
    
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
        
        c_lines = clean_coordinates(lines)
        if c_lines: folium.PolyLine(locations=c_lines, color="green", weight=6).add_to(m)
        for mk in markers: 
            folium.Marker(location=clean_coordinates(mk, expect_single_point=True), icon=folium.Icon(color="orange")).add_to(m)
            
        st_folium(m, width=1100, height=600, key="designer_view_map", returned_objects=[])
        
        config_text = "SAVED_COURSE = {\n"
        config_text += f'    "start_line": {c_lines[:len(c_lines)//2] if len(c_lines) > 2 else c_lines},\n'
        config_text += f'    "finish_line": {c_lines[len(c_lines)//2:] if len(c_lines) > 2 else c_lines},\n'
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
    st.markdown("Upload competitor tracking logs below. The engine converts lines into high-density point grids to cleanly execute 2.5m precision triggers.")
    
    uploaded_files = st.file_uploader("Upload competitor .fit track files", type=["fit"], accept_multiple_files=True, key="racer_uploader")
    
    course_start = clean_coordinates(SAVED_COURSE["start_line"])
    course_finish = clean_coordinates(SAVED_COURSE["finish_line"])
    course_marks = [clean_coordinates(m, expect_single_point=True) for m in SAVED_COURSE["marks"]] if SAVED_COURSE["marks"] else []
    
    if not course_start and st.session_state["saved_raw_drawings"]:
        lines, markers = [], []
        for item in st.session_state["saved_raw_drawings"]:
            g_type, coords = item['geometry']['type'], item['geometry']['coordinates']
            if g_type == "LineString": lines.append([[pt[1], pt[0]] for pt in coords])
            elif g_type == "Point": markers.append([coords[1], coords[0]])
        
        raw_lines_clean = clean_coordinates(lines)
        if len(raw_lines_clean) > 2:
            course_start = raw_lines_clean[:len(raw_lines_clean)//2]
            course_finish = raw_lines_clean[len(raw_lines_clean)//2:]
        else:
            course_start = raw_lines_clean
            course_finish = raw_lines_clean
        course_marks = [clean_coordinates(m, expect_single_point=True) for m in markers]

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

    all_parsed_competitor_data = {}
    if all_raw_competitors_dict and course_start:
        all_parsed_competitor_data = advanced_first_boat_sync(all_raw_competitors_dict, course_start, course_finish, course_marks, parsed_durations, max_races_input)

    if all_lats:
        map_center = [sum(all_lats)/len(all_lats), sum(all_lons)/len(all_lons)]
    elif course_start and len(course_start) > 0:
        map_center = clean_coordinates(course_start, expect_single_point=True)
    else:
        map_center = [53.46, 9.98]
        
    m = folium.Map(location=map_center, zoom_start=15, tiles="https://arcgisonline.com{z}/{y}/{x}", attr="Esri World Imagery")
    folium.TileLayer('OpenStreetMap').add_to(m)
    folium.LayerControl().add_to(m)
    
    if course_start:
        folium.PolyLine(locations=course_start, color="green", weight=6).add_to(m)
        folium.Marker(location=clean_coordinates(course_start, expect_single_point=True), popup="🟢 START", icon=folium.Icon(color="green", icon="play")).add_to(m)
    if course_finish:
        folium.PolyLine(locations=course_finish, color="red", weight=6).add_to(m)
        folium.Marker(location=clean_coordinates(course_finish, expect_single_point=True), popup="🏁 FINISH", icon=folium.Icon(color="red", icon="flag-checkered")).add_to(m)
    for idx, mark in enumerate(course_marks):
        folium.Marker(location=clean_coordinates(mark, expect_single_point=True), popup=f"📍 Mark {idx+1}", icon=folium.Icon(color="orange", icon="star")).add_to(m)

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
