import streamlit as st
import pandas as pd
import folium
from folium.plugins import Draw
from streamlit_folium import st_folium
from fitparse import FitFile

st.set_page_config(layout="wide")
st.title("🏁 Shared Race Course & Multi-Track Viewer")

# --- STEP 1: INITIALIZE SAVED SESSIONS ---
if "designer_points" not in st.session_state:
    st.session_state["designer_points"] = []
if "racer_points" not in st.session_state:
    st.session_state["racer_points"] = []
if "live_course" not in st.session_state:
    # This stores the drawn course dynamically during the session before you lock it into code
    st.session_state["live_course"] = {
        "start_line": [[53.4612, 9.9815], [53.4615, 9.9825]],  # Default example coordinates
        "finish_line": [[53.4650, 9.9880], [53.4652, 9.9890]],
        "marks": [[53.4625, 9.9840], [53.4635, 9.9860], [53.4645, 9.9850]]
    }

# --- STEP 2: DEFINE YOUR LOCKED SAVED COURSE HERE ---
# When you copy the configuration block from the sidebar, paste it directly into this dictionary.
# If this dictionary has data, the app prioritizes it!
SAVED_COURSE = {
    "start_line": [],  
    "finish_line": [], 
    "marks": []   
}

# If you haven't saved a course into the code yet, fallback to the session dynamic drawn course
ACTIVE_COURSE = SAVED_COURSE if SAVED_COURSE["start_line"] else st.session_state["live_course"]

# --- SIDEBAR ROLE SELECTION ---
st.sidebar.header("Mode Selection")
app_mode = st.sidebar.radio("Choose App Role:", ["Racer Mode (Upload & Compare Tracks)", "Designer Mode (Create/Edit Course Layout)"])

if app_mode == "Designer Mode (Create/Edit Course Layout)":
    st.subheader("🛠️ Course Designer Mode")
    st.markdown("1. Upload a reference `.fit` file to view the geography.\n2. Use the map drawing tools to draw your **Start Line** (1st line), **Finish Line** (2nd line), and **2-6 Turn Marks** (Pins).\n3. Copy the generated code from the sidebar and paste it into your `app.py` script on GitHub to save it permanently!")
    
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
        center = ACTIVE_COURSE["start_line"] if ACTIVE_COURSE["start_line"] else [53.46, 9.98]
    
    m = folium.Map(location=center, zoom_start=15, tiles="https://arcgisonline.com{z}/{y}/{x}", attr="Esri World Imagery")
    
    if active_points:
        folium.PolyLine(locations=active_points, color="white", weight=3, opacity=0.5, tooltip="Reference Track").add_to(m)
        
    # --- REDRAW SESSIONS MARKS IN DESIGNER VIEW TO KEEP THEM VISIBLE ---
    if ACTIVE_COURSE["start_line"]:
        folium.PolyLine(locations=ACTIVE_COURSE["start_line"], color="green", weight=5, opacity=0.8).add_to(m)
    if ACTIVE_COURSE["finish_line"]:
        folium.PolyLine(locations=ACTIVE_COURSE["finish_line"], color="red", weight=5, opacity=0.8).add_to(m)
    for mk in ACTIVE_COURSE["marks"]:
        folium.Marker(location=mk, icon=folium.Icon(color="orange", icon="info-sign")).add_to(m)

    draw_tool = Draw(position='topleft', draw_options={'polyline': {'shapeOptions': {'color': '#00ffcc', 'weight': 5}}, 'marker': True, 'circle': False, 'rectangle': False, 'polygon': False, 'circlemarker': False})
    draw_tool.add_to(m)
    
    map_output = st_folium(m, width=1100, height=600, key="designer_map_widget", returned_objects=["all_drawings"])
    user_drawings = map_output.get("all_drawings") if map_output else None
    
    if user_drawings:
        lines = []
        markers = []
        for item in user_drawings:
            g_type = item['geometry']['type']
            coords = item['geometry']['coordinates']
            if g_type == "LineString":
                lines.append([[pt[1], pt[0]] for pt in coords]) # Correct coordinate axis formatting
            elif g_type == "Point":
                markers.append([coords[1], coords[0]])
        
        # Save newly drawn layout instantly to session state so it doesn't clear when changing tabs
        if len(lines) >= 1: st.session_state["live_course"]["start_line"] = lines[0]
        if len(lines) >= 2: st.session_state["live_course"]["finish_line"] = lines[1]
        if len(markers) > 0: st.session_state["live_course"]["marks"] = markers

        # Re-verify working datasets
        start_val = lines[0] if len(lines) >= 1 else (st.session_state["live_course"]["start_line"] if st.session_state["live_course"]["start_line"] else [])
        finish_val = lines[1] if len(lines) >= 2 else (st.session_state["live_course"]["finish_line"] if st.session_state["live_course"]["finish_line"] else [])
        marks_val = markers if len(markers) > 0 else st.session_state["live_course"]["marks"]

        st.sidebar.markdown("### 📋 Copy-Paste Configuration Block")
        st.sidebar.markdown("Copy this block and replace lines 23-27 in your `app.py` file code:")
        
        config_text = "```python\n"
        config_text += "SAVED_COURSE = {\n"
        config_text += f'    "start_line": {start_val},\n'
        config_text += f'    "finish_line": {finish_val},\n'
        config_text += f'    "marks": {marks_val}\n'
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
    elif ACTIVE_COURSE["start_line"] and len(ACTIVE_COURSE["start_line"]) > 0:
        map_center = ACTIVE_COURSE["start_line"][0]
    else:
        map_center = [53.46, 9.98]
        
    m = folium.Map(location=map_center, zoom_start=15, tiles="https://arcgisonline.com{z}/{y}/{x}", attr="Esri World Imagery")
    folium.TileLayer('OpenStreetMap').add_to(m)
    folium.LayerControl().add_to(m)
    
    # Render Saved lines and marks explicitly onto the Racer View Map
    if ACTIVE_COURSE["start_line"]:
        folium.PolyLine(locations=ACTIVE_COURSE["start_line"], color="green", weight=7, opacity=0.9, tooltip="Official Start Line").add_to(m)
        folium.Marker(location=ACTIVE_COURSE["start_line"][0], popup="🟢 START LINE", icon=folium.Icon(color="green", icon="play", prefix="fa")).add_to(m)
        
    if ACTIVE_COURSE["finish_line"]:
        folium.PolyLine(locations=ACTIVE_COURSE["finish_line"], color="red", weight=7, opacity=0.9, tooltip="Official Finish Line").add_to(m)
        folium.Marker(location=ACTIVE_COURSE["finish_line"][0], popup="🏁 FINISH LINE", icon=folium.Icon(color="red", icon="flag-checkered", prefix="fa")).add_to(m)
        
    colors = ["orange", "purple", "blue", "cadetblue", "darkpurple", "pink"]
    for idx, mark in enumerate(ACTIVE_COURSE["marks"]):
        folium.Marker(location=mark, popup=f"📍 Course Mark {idx+1}", tooltip=f"Mark {idx+1}", icon=folium.Icon(color=colors[idx % len(colors)], icon="info-sign")).add_to(m)
        
    if len(active_racer_points) > 0:
        folium.PolyLine(locations=active_racer_points, color="cyan", weight=5, opacity=0.85, tooltip="Your Uploaded Track").add_to(m)
        st.success("🎉 Your track was loaded successfully over the course map layout below!")
            
    st_folium(m, width=1100, height=650, key="racer_map_widget", returned_objects=[])
