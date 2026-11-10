import streamlit as st
import pandas as pd
import folium
from folium.plugins import Draw
from streamlit_folium import st_folium
from fitparse import FitFile

st.set_page_config(layout="wide")
st.title("🏁 Shared Race Course & Multi-Track Viewer")

# --- PERSISTENT STORAGE INITIALIZATION ---
if "designer_points" not in st.session_state:
    st.session_state["designer_points"] = []
if "racer_points" not in st.session_state:
    st.session_state["racer_points"] = []

# Persistent variables for drawn items so they NEVER overwrite each other
if "start_line" not in st.session_state:
    st.session_state["start_line"] = [[53.4612, 9.9815], [53.4615, 9.9825]] # Initial default examples
if "finish_line" not in st.session_state:
    st.session_state["finish_line"] = [[53.4650, 9.9880], [53.4652, 9.9890]]
if "marks" not in st.session_state:
    st.session_state["marks"] = [[53.4625, 9.9840], [53.4635, 9.9860], [53.4645, 9.9850]]

# --- STEP 1: DEFINE YOUR FIXED SAVED COURSE HERE ---
# Once you copy the configuration block from the sidebar, paste it here to lock it for everyone.
SAVED_COURSE = {
    "start_line": [],  
    "finish_line": [], 
    "marks": []   
}

# Use the saved code layout if available, otherwise read what's actively in live session state
ACTIVE_START = SAVED_COURSE["start_line"] if SAVED_COURSE["start_line"] else st.session_state["start_line"]
ACTIVE_FINISH = SAVED_COURSE["finish_line"] if SAVED_COURSE["finish_line"] else st.session_state["finish_line"]
ACTIVE_MARKS = SAVED_COURSE["marks"] if SAVED_COURSE["marks"] else st.session_state["marks"]

# --- SIDEBAR ROLE SELECTION ---
st.sidebar.header("Mode Selection")
app_mode = st.sidebar.radio("Choose App Role:", ["Racer Mode (Upload & Compare Tracks)", "Designer Mode (Create/Edit Course Layout)"])

if app_mode == "Designer Mode (Create/Edit Course Layout)":
    st.subheader("🛠️ Course Designer Mode")
    st.markdown("ℹ️ **Drawing Instructions:** \n1. Draw **Start Line** first using the Polyline tool. \n2. Draw **Finish Line** second. \n3. Use the Marker pin tool to drop **2 to 6 course turning marks**.")
    
    uploaded_file = st.file_uploader("Upload reference .fit file", type=["fit"], key="designer_uploader")
    
    if uploaded_file:
        points = []
        fitfile = FitFile(uploaded_file.read())
        for record in fitfile.get_messages("record"):
            lat = record.get_value("position_lat")
            lon = record.get_value("position_long")
            if lat and lon:
                points.append((lat * (180.0 / 2**31), lon * (180.0 / 2**31)))
        st.session_state["designer_points"] = points
                
    active_points = st.session_state["designer_points"]
    
    if active_points:
        df_designer = pd.DataFrame(active_points, columns=["lat", "lon"])
        center = [df_designer["lat"].mean(), df_designer["lon"].mean()]
    else:
        center = ACTIVE_START[0] if ACTIVE_START else [53.46, 9.98]
    
    m = folium.Map(location=center, zoom_start=15, tiles="https://arcgisonline.com{z}/{y}/{x}", attr="Esri World Imagery")
    
    if active_points:
        folium.PolyLine(locations=active_points, color="white", weight=3, opacity=0.4, tooltip="Reference Track").add_to(m)
        
    # Render layers onto map canvas securely
    if ACTIVE_START:
        folium.PolyLine(locations=ACTIVE_START, color="green", weight=5, opacity=0.85, tooltip="Start").add_to(m)
    if ACTIVE_FINISH:
        folium.PolyLine(locations=ACTIVE_FINISH, color="red", weight=5, opacity=0.85, tooltip="Finish").add_to(m)
    for idx, mk in enumerate(ACTIVE_MARKS):
        folium.Marker(location=mk, icon=folium.Icon(color="orange", icon="info-sign")).add_to(m)

    draw_tool = Draw(position='topleft', draw_options={'polyline': {'shapeOptions': {'color': '#00ffcc', 'weight': 5}}, 'marker': True, 'circle': False, 'rectangle': False, 'polygon': False, 'circlemarker': False})
    draw_tool.add_to(m)
    
    map_output = st_folium(m, width=1100, height=600, key="designer_map_widget", returned_objects=["all_drawings"])
    user_drawings = map_output.get("all_drawings") if map_output else None
    
    if user_drawings:
        temp_lines = []
        temp_markers = []
        for item in user_drawings:
            g_type = item['geometry']['type']
            coords = item['geometry']['coordinates']
            if g_type == "LineString":
                temp_lines.append([[pt[1], pt[0]] for pt in coords]) # explicitly format to standard leaflet lat/lon
            elif g_type == "Point":
                temp_markers.append([coords[1], coords[0]])
        
        # Chronologically lock positions only as they are created to prevent shifting index bugs
        if len(temp_lines) >= 1:
            st.session_state["start_line"] = temp_lines[0]
        if len(temp_lines) >= 2:
            st.session_state["finish_line"] = temp_lines[1]
        if len(temp_markers) > 0:
            st.session_state["marks"] = temp_markers
            
        # Re-verify clean variables for code generation printout
        st.sidebar.markdown("### 📋 Copy-Paste Configuration Block")
        st.sidebar.markdown("Copy this block and replace lines 22-26 in your code:")
        
        config_text = "```python\n"
        config_text += "SAVED_COURSE = {\n"
        config_text += f'    "start_line": {st.session_state["start_line"]},\n'
        config_text += f'    "finish_line": {st.session_state["finish_line"]},\n'
        config_text += f'    "marks": {st.session_state["marks"]}\n'
        config_text += "}\n"
        config_text += "```"
        st.sidebar.markdown(config_text)

else:
    # --- RACER MODE ---
    st.subheader("🏃‍♂️ Racer Track Uploader")
    st.markdown("The course layout is locked below. Upload your activity `.fit` file from today's session to see how well you matched the official race boundaries!")
    
    uploaded_file = st.file_uploader("Upload your .fit track file", type=["fit"], key="racer_uploader")
    
    if uploaded_file is not None:
        racer_points = []
        fitfile = FitFile(uploaded_file.read())
        for record in fitfile.get_messages("record"):
            lat = record.get_value("position_lat")
            lon = record.get_value("position_long")
            if lat and lon:
                racer_points.append((lat * (180.0 / 2**31), lon * (180.0 / 2**31)))
        st.session_state["racer_points"] = racer_points
        
    active_racer_points = st.session_state["racer_points"]
    
    if len(active_racer_points) > 0:
        df_racer = pd.DataFrame(active_racer_points, columns=["lat", "lon"])
        map_center = [df_racer["lat"].mean(), df_racer["lon"].mean()]
    elif ACTIVE_START:
        map_center = ACTIVE_START[0]
    else:
        map_center = [53.46, 9.98]
        
    m = folium.Map(location=map_center, zoom_start=15, tiles="https://arcgisonline.com{z}/{y}/{x}", attr="Esri World Imagery")
    folium.TileLayer('OpenStreetMap').add_to(m)
    folium.LayerControl().add_to(m)
    
    # Render Locked Course layout lines explicitly
    if ACTIVE_START:
        folium.PolyLine(locations=ACTIVE_START, color="green", weight=7, opacity=0.9, tooltip="Official Start Line").add_to(m)
        folium.Marker(location=ACTIVE_START[0], popup="🟢 START LINE", icon=folium.Icon(color="green", icon="play", prefix="fa")).add_to(m)
        
    if ACTIVE_FINISH:
        folium.PolyLine(locations=ACTIVE_FINISH, color="red", weight=7, opacity=0.9, tooltip="Official Finish Line").add_to(m)
        folium.Marker(location=ACTIVE_FINISH[0], popup="🏁 FINISH LINE", icon=folium.Icon(color="red", icon="flag-checkered", prefix="fa")).add_to(m)
        
    colors = ["orange", "purple", "blue", "cadetblue", "darkpurple", "pink"]
    for idx, mark in enumerate(ACTIVE_MARKS):
        folium.Marker(location=mark, popup=f"📍 Course Mark {idx+1}", tooltip=f"Mark {idx+1}", icon=folium.Icon(color=colors[idx % len(colors)], icon="info-sign")).add_to(m)
        
    if len(active_racer_points) > 0:
        folium.PolyLine(locations=active_racer_points, color="cyan", weight=5, opacity=0.85, tooltip="Your Uploaded Track").add_to(m)
        st.success("🎉 Your track was loaded successfully over the course map layout below!")
            
    st_folium(m, width=1100, height=650, key="racer_map_widget", returned_objects=[])
