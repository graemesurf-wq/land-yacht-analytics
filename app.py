import streamlit as st
import pandas as pd
import folium
from folium.plugins import Draw
from streamlit_folium import st_folium
from fitparse import FitFile
import numpy as np
from datetime import datetime, timedelta

st.set_page_config(layout="wide", page_title="Land Yacht Sync Engine")
st.title("🏁 Fleet-Synchronized Land Yacht Analyst")

# Initialize background memory states safely
if "saved_raw_drawings" not in st.session_state:
    st.session_state["saved_raw_drawings"] = None

# Empty template block - live tab memory handles everything dynamically
SAVED_COURSE = {
    "start_pin": [],  
    "finish_pin": [], 
    "marks": []   
}

def clean_coordinates(coord_input, default_coords=None):
    fallback = default_coords if default_coords else [53.407453, 5.274961]
    if not coord_input:
        return fallback
    try:
        while isinstance(coord_input, list) and len(coord_input) == 1:
            coord_input = coord_input[0]
        if isinstance(coord_input, list) and len(coord_input) >= 2:
            return [float(coord_input[0]), float(coord_input[1])]
        return fallback
    except Exception:
        return fallback

def haversine_dist(p1, p2):
    pt1 = clean_coordinates(p1)
    pt2 = clean_coordinates(p2)
    R = 6371000
    phi1, phi2 = np.radians(pt1[0]), np.radians(pt2[0])
    dphi = np.radians(pt2[0] - pt1[0])
    dlon = np.radians(pt2[1] - pt1[1])
    a = np.sin(dphi/2)**2 + np.cos(phi1)*np.cos(phi2) * np.sin(dlon/2)**2
    return R * 2 * np.arctan2(np.sqrt(a), np.sqrt(1-a))
def advanced_first_boat_sync(all_competitors_raw, start_pin, finish_pin, course_marks, duration_list, max_races, fallback_anchor=None):
    """
    Synchronizes fleet race runs based on speed ignition triggers, allowing for late starters
    and arming finish gates dynamically once the last course mark has been verified as rounded.
    """
    st_pin = clean_coordinates(start_pin, default_coords=fallback_anchor)
    fn_pin = clean_coordinates(finish_pin, default_coords=fallback_anchor) if finish_pin else st_pin
    c_marks = [clean_coordinates(m, default_coords=fallback_anchor) for m in course_marks] if course_marks else []

    last_mark_pt = c_marks[-1] if len(c_marks) > 0 else None

    # Step 1: Detect all fleet ignition triggers where speed climbs past 0.5 km/h
    movement_triggers = []
    for records in all_competitors_raw.values():
        for idx in range(1, len(records)):
            p1 = records[idx-1]
            p2 = records[idx]
            
            dist_moved = haversine_dist(p1["coords"], p2["coords"])
            time_diff = (p2["timestamp"] - p1["timestamp"]).total_seconds()
            speed_kmh = (dist_moved / time_diff) * 3.6 if time_diff > 0 else 0
            
            if speed_kmh > 0.5:
                movement_triggers.append(p2["timestamp"])

    if not movement_triggers:
        return {c_name: [{"name": f"Race {idx+1}", "points": [r["coords"] for r in recs[:800]], "duration": 20.0, "time_secs": len(recs)//5} for idx in range(min(max_races, 3))] for c_name, recs in all_competitors_raw.items()}

    movement_triggers.sort()
    race_start_anchors = []
    
    if movement_triggers:
        current_cluster = [movement_triggers[0]]
        for t in movement_triggers[1:]:
            if (t - current_cluster[-1]).total_seconds() < 600:
                current_cluster.append(t)
            else:
                race_start_anchors.append(current_cluster[0])
                current_cluster = [t]
        if current_cluster and len(race_start_anchors) < max_races:
            race_start_anchors.append(current_cluster[0])

    # Step 2: Symmetrically slice tracking lines across fleet
    fleet_final_data = {}
    validated_race_count = 0
    for c_name in all_competitors_raw.keys():
        fleet_final_data[c_name] = []
        
    for master_start_t in race_start_anchors:
        if validated_race_count >= max_races: break
        race_duration_mins = duration_list[validated_race_count] if validated_race_count < len(duration_list) else 20.0
        timer_expiry_t = master_start_t + timedelta(minutes=race_duration_mins)
        
        for c_name, records in all_competitors_raw.items():
            race_points = []
            found_finish = False
            has_rounded_last_mark = False
            actual_finish_time = None
            
            for r in records:
                # Capture everything inside the baseline chronological sequence window
                if master_start_t <= r["timestamp"] <= timer_expiry_t:
                    race_points.append(r["coords"])
                    # Check if they pass near the final mark early/before expiry time
                    if last_mark_pt and haversine_dist(r["coords"], last_mark_pt) <= 60.0:
                        has_rounded_last_mark = True
                        
                # After timer runs out, hold open until they cross the finish pin
                elif r["timestamp"] > timer_expiry_t and not found_finish:
                    race_points.append(r["coords"])
                    
                    if last_mark_pt and haversine_dist(r["coords"], last_mark_pt) <= 60.0:
                        has_rounded_last_mark = True
                        
                    # Trigger condition: Time limit is expired AND final mark rounding is satisfied
                    if has_rounded_last_mark or not last_mark_pt:
                        if haversine_dist(r["coords"], fn_pin) <= 50.0:
                            actual_finish_time = r["timestamp"]
                            found_finish = True
                            break
            
            if actual_finish_time is None: actual_finish_time = timer_expiry_t
            elapsed_seconds = int((actual_finish_time - master_start_t).total_seconds())
            
            if len(race_points) > 10:
                fleet_final_data[c_name].append({
                    "name": f"Race {validated_race_count + 1}",
                    "points": race_points[::3],
                    "duration": race_duration_mins,
                    "time_secs": elapsed_seconds
                })
        validated_race_count += 1

    return fleet_final_data
# --- DESIGNER MODE CONTROLS ---
st.sidebar.header("Mode Selection")
app_mode = st.sidebar.radio("Choose App Role:", ["Racer Mode (Upload & Compare Tracks)", "Designer Mode (Create/Edit Course Layout)"])

if app_mode == "Designer Mode (Create/Edit Course Layout)":
    st.subheader("🛠️ Course Designer Mode")
    st.markdown("ℹ️ **Drawing Instructions:** Drop **Pins** (Markers) onto the map layout: \n1. First Pin = **Start Gate center (100m radius check)** \n2. Second Pin = **Finish Gate center (50m radius check)** \n3. Subsequent Pins = **Marks 1, 2, 3, etc. (Chronological Order)**")
    
    uploaded_file = st.file_uploader("Upload reference .fit file", type=["fit"], key="designer_uploader")
    if uploaded_file:
        pts = []
        fitfile = FitFile(uploaded_file.read())
        for r in fitfile.get_messages("record"):
            lat = r.get_value("position_lat")
            lon = r.get_value("position_long")
            if lat and lon: pts.append((lat * (180.0 / 2**31), lon * (180.0 / 2**31)))
        st.session_state["designer_points"] = pts[::4]
                
    active_points = st.session_state["designer_points"]
    center = [pd.DataFrame(active_points, columns=["lat", "lon"])["lat"].mean(), pd.DataFrame(active_points, columns=["lat", "lon"])["lon"].mean()] if active_points else [53.407453, 5.274961]
    
    lock_course = st.sidebar.checkbox("🔒 Lock Course Setup & View Layout", value=False)
    m = folium.Map(location=center, zoom_start=14, tiles="OpenStreetMap")
    
    if active_points:
        folium.PolyLine(locations=active_points, color="white", weight=2, opacity=0.4).add_to(m)
        
    if not lock_course:
        draw_tool = Draw(position='topleft', draw_options={'polyline': False, 'marker': True, 'circle': False, 'rectangle': False, 'polygon': False, 'circlemarker': False})
        draw_tool.add_to(m)
        map_output = st_folium(m, width=900, height=500, key="designer_draw_map", returned_objects=["all_drawings"])
        if map_output and map_output.get("all_drawings"):
            st.session_state["saved_raw_drawings"] = map_output["all_drawings"]
    else:
        user_drawings = st.session_state["saved_raw_drawings"]
        markers = []
        if user_drawings:
            for item in user_drawings:
                if item['geometry']['type'] == "Point":
                    markers.append(item['geometry']['coordinates'])
        
        if len(markers) >= 1:
            folium.Marker(location=clean_coordinates(markers[0]), popup="🟢 START ANCHOR", icon=folium.Icon(color="green", icon="play")).add_to(m)
            folium.Circle(location=clean_coordinates(markers[0]), radius=100, color="green", fill=True, opacity=0.12).add_to(m)
        if len(markers) >= 2:
            folium.Marker(location=clean_coordinates(markers[1]), popup="🏁 FINISH ANCHOR", icon=folium.Icon(color="red", icon="flag-checkered")).add_to(m)
            folium.Circle(location=clean_coordinates(markers[1]), radius=50, color="red", fill=True, opacity=0.12).add_to(m)
        for idx, mk in enumerate(markers[2:]):
            folium.Marker(location=clean_coordinates(mk), popup=f"📍 Mark {idx+1}", icon=folium.Icon(color="orange", icon="star")).add_to(m)
            
        st_folium(m, width=900, height=500, key="designer_view_map", returned_objects=[])
else:
    # --- RACER MODE ---
    st.sidebar.header("🏁 Analytics Configuration")
    max_races_input = st.sidebar.slider("Maximum number of races to scan for:", min_value=1, max_value=8, value=5)
    
    durations_raw = st.sidebar.text_input("Race Durations in Minutes (comma separated):", value="15, 20, 15, 15, 10")
    try:
        parsed_durations = [float(d.strip()) for d in durations_raw.split(",")]
    except:
        parsed_durations = [20.0] * max_races_input

    st.subheader("Multi-Race Fleet-Synchronized Dashboard")
    uploaded_files = st.file_uploader("Upload competitor .fit track files", type=["fit"], accept_multiple_files=True, key="racer_uploader")
    
    course_start, course_finish, course_marks = [], [], []
    if st.session_state["saved_raw_drawings"]:
        raw_markers = []
        for item in st.session_state["saved_raw_drawings"]:
            if item['geometry']['type'] == "Point":
                raw_markers.append(item['geometry']['coordinates'])
        
        if len(raw_markers) >= 1: course_start = clean_coordinates(raw_markers[0])
        if len(raw_markers) >= 2: course_finish = clean_coordinates(raw_markers[1])
        if len(raw_markers) > 2: course_marks = [clean_coordinates(m) for m in raw_markers[2:]]

    all_raw_competitors_dict = {}
    all_lats, all_lons = [], []
    first_file_anchor = None
    
    if uploaded_files:
        for up_file in uploaded_files:
            raw_records = []
            try:
                fitfile = FitFile(up_file.read())
                for idx, record in enumerate(fitfile.get_messages("record")):
                    if idx % 3 != 0: continue 
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
                st.error(f"Error parsing file: {e}")

    # Process all files concurrently through the advanced adaptive movement engine
    all_parsed_competitor_data = advanced_first_boat_sync(all_raw_competitors_dict, course_start, course_finish, course_marks, parsed_durations, max_races_input, fallback_anchor=first_file_anchor)

    map_center = [sum(all_lats)/len(all_lats), sum(all_lons)/len(all_lons)] if all_lats else [53.407453, 5.274961]
    m = folium.Map(location=map_center, zoom_start=14, tiles="OpenStreetMap")
    
    if course_start:
        folium.Marker(location=course_start, popup="🟢 START ANCHOR", icon=folium.Icon(color="green", icon="play")).add_to(m)
        folium.Circle(location=course_start, radius=100, color="green", fill=True, opacity=0.12).add_to(m)
    if course_finish:
        folium.Marker(location=course_finish, popup="🏁 FINISH ANCHOR", icon=folium.Icon(color="red", icon="flag-checkered")).add_to(m)
        folium.Circle(location=course_finish, radius=50, color="red", fill=True, opacity=0.12).add_to(m)
    for idx, mark in enumerate(course_marks):
        folium.Marker(location=mark, popup=f"📍 Mark {idx+1}", icon=folium.Icon(color="orange", icon="star")).add_to(m)

    selected_heat_view = "Show All Context"
    competitor_visibility = {}
    
    if all_parsed_competitor_data:
        max_len = max([len(h) for h in all_parsed_competitor_data.values()]) if all_parsed_competitor_data else 1
        selected_heat_view = st.sidebar.selectbox("Select a race event:", ["Show All Context"] + [f"Race {i+1}" for i in range(max_len)])
        for c_name in all_parsed_competitor_data.keys():
            competitor_visibility[c_name] = st.sidebar.checkbox(f"Display {c_name}", value=True)

    competitor_colors = ["cyan", "yellow", "magenta", "lime", "orange", "pink", "white", "gold"]
    for c_idx, (c_name, heats) in enumerate(all_parsed_competitor_data.items()):
        if not competitor_visibility.get(c_name, True): continue
        c_color = competitor_colors[c_idx % len(competitor_colors)]
        for heat in heats:
            if selected_heat_view == "Show All Context" or selected_heat_view == heat["name"]:
                folium.PolyLine(locations=heat["points"], color=c_color, weight=4, opacity=0.85).add_to(m)

    st_folium(m, width=900, height=500, key="racer_map_widget", returned_objects=[])
    
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
                    col_target.metric(label=heat["name"], value=f"{mins_disp:02d}:{secs_disp:02d} Total", delta=f"+{extra_secs // 60:02d}:{extra_secs % 60:02d} past cap", delta_color="inverse")
