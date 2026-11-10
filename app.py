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

# --- STEP 1: FIXED COURSE CONFIGURATION ---
# Leave this empty while testing! Your drawn marks will pass over automatically.
SAVED_COURSE = {
    "start_line": [],  
    "finish_line": [], 
    "marks": []   
}

def clean_coordinates(coord_input, expect_single_point=False, default_coords=None):
    fallback = default_coords if default_coords else [53.407, 5.274]
    if not coord_input:
        return [] if not expect_single_point else fallback
    try:
        while isinstance(coord_input, list) and len(coord_input) == 1 and isinstance(coord_input, list):
            coord_input = coord_input
        if expect_single_point:
            if isinstance(coord_input, list) and len(coord_input) >= 2:
                return [float(coord_input[0]), float(coord_input[1])]
            return fallback
        else:
            cleaned_list = []
            for pair in coord_input:
                if isinstance(pair, list) and len(pair) >= 2:
                    cleaned_list.append([float(pair[0]), float(pair[1])])
            return cleaned_list
    except Exception:
        return [] if not expect_single_point else fallback

def haversine_dist(p1, p2):
    pt1 = clean_coordinates(p1, expect_single_point=True)
    pt2 = clean_coordinates(p2, expect_single_point=True)
    R = 6371000
    phi1, phi2 = np.radians(pt1[0]), np.radians(pt2[0])
    dphi = np.radians(pt2[0] - pt1[0])
    dlon = np.radians(pt2[1] - pt1[1])
    a = np.sin(dphi/2)**2 + np.cos(phi1)*np.cos(phi2) * np.sin(dlon/2)**2
    return R * 2 * np.arctan2(np.sqrt(a), np.sqrt(1-a))

def generate_line_grid_points(line_endpoints, spacing_meters=5, default_coords=None):
    cleaned_line = clean_coordinates(line_endpoints, default_coords=default_coords)
    if len(cleaned_line) < 2:
        base = default_coords if default_coords else [53.407, 5.274]
        cleaned_line = [[base[0], base[1] - 0.0001], [base[0], base[1] + 0.0001]]
    p1, p2 = np.array(cleaned_line[0]), np.array(cleaned_line[-1])
    total_distance = haversine_dist(p1.tolist(), p2.tolist())
    num_points = max(2, int(total_distance / spacing_meters))
    return np.column_stack((np.linspace(p1[0], p2[0], num_points), np.linspace(p1[1], p2[1], num_points))).tolist()
def advanced_first_boat_sync(all_competitors_raw, course_start, course_finish, course_marks, duration_list, max_races, fallback_anchor=None):
    cleaned_start = clean_coordinates(course_start)
    cleaned_finish = clean_coordinates(course_finish)
    cleaned_marks = [clean_coordinates(m, expect_single_point=True, default_coords=fallback_anchor) for m in course_marks] if course_marks else []

    if not cleaned_start and fallback_anchor:
        cleaned_start = [[fallback_anchor[0], fallback_anchor[1] - 0.0001], [fallback_anchor[0], fallback_anchor[1] + 0.0001]]
    if not cleaned_marks and fallback_anchor:
        cleaned_marks = [[fallback_anchor[0] + 0.001, fallback_anchor[1] + 0.001]]

    start_grid_nodes = generate_line_grid_points(cleaned_start, spacing_meters=5, default_coords=fallback_anchor)
    finish_grid_nodes = generate_line_grid_points(cleaned_finish, spacing_meters=5, default_coords=fallback_anchor) if cleaned_finish else start_grid_nodes
    mark1_pt = cleaned_marks[0] if len(cleaned_marks) > 0 else None
    
    start_crossings = []
    for c_name, records in all_competitors_raw.items():
        for r in records:
            if any(haversine_dist(r["coords"], node) <= 40.0 for node in start_grid_nodes):
                start_crossings.append(r["timestamp"])

    if not start_crossings:
        return {c_name: [{"name": f"Race {idx+1}", "points": [r["coords"] for r in recs[:1200]], "duration": 20.0, "time_secs": min(1200, len(recs))} for idx in range(min(max_races, 5))][:max_races] for c_name, recs in all_competitors_raw.items()}

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

    fleet_final_segmented_data = {}
    validated_race_count = 0
    for c_name in all_competitors_raw.keys():
        fleet_final_segmented_data[c_name] = []
        
    for master_start_t in race_start_anchors:
        if validated_race_count >= max_races: break
        race_duration_mins = duration_list[validated_race_count] if validated_race_count < len(duration_list) else 20.0
        timer_expiry_t = master_start_t + timedelta(minutes=race_duration_mins)
        
        for c_name, records in all_competitors_raw.items():
            race_points = []
            found_finish = False
            actual_finish_time = None
            
            for r in records:
                if master_start_t <= r["timestamp"] <= timer_expiry_t:
                    race_points.append(r["coords"])
                elif r["timestamp"] > timer_expiry_t and not found_finish:
                    race_points.append(r["coords"])
                    if any(haversine_dist(r["coords"], node) <= 40.0 for node in finish_grid_nodes):
                        actual_finish_time = r["timestamp"]
                        found_finish = True
                        break
            
            if actual_finish_time is None: actual_finish_time = timer_expiry_t
            elapsed_seconds = int((actual_finish_time - master_start_t).total_seconds())
            
            if len(race_points) > 10:
                fleet_final_segmented_data[c_name].append({
                    "name": f"Race {validated_race_count + 1}",
                    "points": race_points,
                    "duration": race_duration_mins,
                    "time_secs": elapsed_seconds
                })
        validated_race_count += 1

    return fleet_final_segmented_data
# --- SIDEBAR INTERFACE VIEW CONTROLS ---
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
            lat = r.get_value("position_lat")
            lon = r.get_value("position_long")
            if lat and lon: pts.append((lat * (180.0 / 2**31), lon * (180.0 / 2**31)))
        st.session_state["designer_points"] = pts
                
    active_points = st.session_state["designer_points"]
    center = [pd.DataFrame(active_points, columns=["lat", "lon"])["lat"].mean(), pd.DataFrame(active_points, columns=["lat", "lon"])["lon"].mean()] if active_points else [53.407, 5.274]
    
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

    st.subheader("🏃‍♂️ Multi-Race Fleet-Synchronized Dashboard")
    uploaded_files = st.file_uploader("Upload competitor .fit track files", type=["fit"], accept_multiple_files=True, key="racer_uploader")
    
    # --- FIXED: GRACEFUL TAB MEMORY LINK FOR LIVE TESTING ---
    course_start = clean_coordinates(SAVED_COURSE["start_line"])
    course_finish = clean_coordinates(SAVED_COURSE["finish_line"])
    course_marks = [clean_coordinates(m, expect_single_point=True) for m in SAVED_COURSE["marks"]] if SAVED_COURSE["marks"] else []

    # If SAVED_COURSE in code is empty, look at what you just drew in the other tab!
    if not course_start and st.session_state["saved_raw_drawings"]:
        lines, markers = [], []
        for item in st.session_state["saved_raw_drawings"]:
            g_type = item['geometry']['type']
            coords = item['geometry']['coordinates']
            if g_type == "LineString": 
                lines.append([[pt[1], pt[0]] for pt in coords]) # Fixed alignment loop
            elif g_type == "Point": 
                markers.append([coords[1], coords[0]])
        
        raw_lines_clean = clean_coordinates(lines)
        if len(raw_lines_clean) > 1:
            course_start = raw_lines_clean
            course_finish = raw_lines_clean
        course_marks = [clean_coordinates(m, expect_single_point=True) for m in markers]

    all_raw_competitors_dict = {}
    all_lats, all_lons = [], []
    first_file_anchor = None
    
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
                        raw_records.append({"coords": [lat_d, lon_d], "timestamp": t_val})
                        all_lats.append(lat_d)
                        all_lons.append(lon_d)
                if len(raw_records) > 0: 
                    all_raw_competitors_dict[up_file.name] = raw_records
                    if first_file_anchor is None:
                        first_file_anchor = raw_records[0]["coords"]
            except Exception as e:
                st.error(f"Error parsing file {up_file.name}: {e}")

    all_parsed_competitor_data = {}
    if all_raw_competitors_dict:
        all_parsed_competitor_data = advanced_first_boat_sync(all_raw_competitors_dict, course_start, course_finish, course_marks, parsed_durations, max_races_input, fallback_anchor=first_file_anchor)

    map_center = [sum(all_lats)/len(all_lats), sum(all_lons)/len(all_lons)] if all_lats else [53.407, 5.274]
    m = folium.Map(location=map_center, zoom_start=14, tiles="https://arcgisonline.com{z}/{y}/{x}", attr="Esri World Imagery")
    folium.TileLayer('OpenStreetMap').add_to(m)
    folium.TileLayer('Stamen Terrain', attr='Stamen').add_to(m) if hasattr(folium.TileLayer, 'Stamen') else None
    folium.LayerControl().add_to(m)
    
    if course_start: folium.PolyLine(locations=course_start, color="green", weight=6).add_to(m)
    if course_finish: folium.PolyLine(locations=course_finish, color="red", weight=6).add_to(m)
    for idx, mark in enumerate(course_marks):
        folium.Marker(location=mark, popup=f"📍 Mark {idx+1}", icon=folium.Icon(color="orange", icon="star")).add_to(m)

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
        if not competitor_visibility.get(c_name, True): continue
        c_color = competitor_colors[c_idx % len(competitor_colors)]
        for heat in heats:
            if selected_heat_view == "Show All Context": opacity_val, weight_val = 0.5, 3
            elif selected_heat_view == heat["name"]: opacity_val, weight_val = 0.95, 5
            else: opacity_val, weight_val = 0.0, 0
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
                    mins_disp = heat["time_secs"] // 60
                    secs_disp = heat["time_secs"] % 60
                    extra_secs = max(0, heat["time_secs"] - int(heat["duration"] * 60))
                    extra_mins = extra_secs // 60
                    extra_secs_rem = extra_secs % 60
                    col_target.metric(label=heat["name"], value=f"{mins_disp:02d}:{secs_disp:02d} Total", delta=f"+{extra_mins:02d}:{extra_secs_rem:02d} past cap", delta_color="inverse")
