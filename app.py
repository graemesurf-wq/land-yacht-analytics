import streamlit as st
import pandas as pd
import folium
from folium.plugins import Draw
from streamlit_folium import st_folium
from fitparse import FitFile

st.set_page_config(layout="wide")
st.title("🏁 Shared Race Course & Multi-Track Viewer")

# --- STEP 1: INITIALIZE PERSISTENT STORAGE ---
if "designer_points" not in st.session_state:
    st.session_state["designer_points"] = []
if "racer_points" not in st.session_state:
    st.session_state["racer_points"] = []
if "saved_raw_drawings" not in st.session_state:
    st.session_state["saved_raw_drawings"] = None

# --- STEP 2: DEFINE YOUR FIXED HARDCODED COURSE HERE ---
# Paste your generated block here once you copy it from the sidebar!
SAVED_COURSE = {
    "start_line": [],  
    "finish_line": [], 
    "marks": []   
}

# --- SIDEBAR ROLE SELECTION ---
st.sidebar.header("Mode Selection")
app_mode = st.sidebar.radio("Choose App Role:", ["Racer Mode (Upload & Compare Tracks)", "Designer Mode (Create/Edit Course Layout)"])

if app_mode == "Designer Mode (Create/Edit Course Layout)":
    st.subheader("🛠️ Course Designer Mode")
    st.markdown("""
    ℹ️ **Drawing Instructions:**
    1. Draw your **Start Line** first using the Polyline tool.
    2. Draw your **Finish Line** second using the Polyline tool.
    3. Drop your **2 to 6 turn marks** using the Marker pin tool.
    4. **Crucial:** Once you are completely done drawing, click **'🔒 Lock Course Setup'** in the sidebar to process your lines and generate the code!
    """)
    
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
        center = [53.46, 9.98]
    
    # Checkbox to freeze drawing tool and calculate configurations
    lock_course = st.sidebar.checkbox("🔒 Lock Course Setup & Generate Code", value=False)
    
    m = folium.Map(location=center, zoom_start=15, tiles="https://arcgisonline.com{z}/{y}/{x}", attr="Esri World Imagery")
    
    if active_points:
        folium.PolyLine(locations=active_points, color="white", weight=3, opacity=0.4, tooltip="Reference Track").add_to(m)
        
    if not lock_course:
        # ONLY inject drawing controls when editing mode is completely unlocked
        # This completely avoids Leaflet component rendering loops and duplication glitches
        draw_tool = Draw(
            position='topleft', 
            draw_options={
                'polyline': {'shapeOptions': {'color': '#00ffcc', 'weight': 5}}, 
                'marker': True, 'circle': False, 'rectangle': False, 'polygon': False, 'circlemarker': False
            }
        )
        draw_tool.add_to(m)
        
        map_output = st_folium(m, width=1100, height=600, key="designer_draw_map", returned_objects=["all_drawings"])
        
        if map_output and map_output.get("all_drawings"):
            st.session_state["saved_raw_drawings"] = map_output["all_drawings"]
            st.sidebar.info("✨ Drawings captured! Check the 'Lock Course' box above to view configuration outputs.")
            
    else:
        # VISUAL VIEW MODE: The user has checked "Lock Course Setup"
        # We process the captured geometry coordinates safely without drawing features active
        user_drawings = st.session_state["saved_raw_drawings"]
        
        lines = []
        markers = []
        if user_drawings:
            for item in user_drawings:
                g_type = item['geometry']['type']
                coords = item['geometry']['coordinates']
                if g_type == "LineString":
                    lines.append([[pt[1], pt[0]] for pt in coords]) # Flip map lon/lat to leaflet lat/lon
                elif g_type == "Point":
                    markers.append([coords[1], coords[0]])
        
        # Render the lines as processed finalized static layers
        if len(lines) >= 1:
            folium.PolyLine(locations=lines[0], color="green", weight=6, opacity=0.9).add_to(m)
            folium.Marker(location=lines[0][0], popup="🟢 START", icon=folium.Icon(color="green", icon="play", prefix="fa")).add_to(m)
        if len(lines) >= 2:
            folium.PolyLine(locations=lines[1], color="red", weight=6, opacity=0.9).add_to(m)
            folium.Marker(location=lines[1][0], popup="🏁 FINISH", icon=folium.Icon(color="red", icon="flag-checkered", prefix="fa")).add_to(m)
        for idx, mk in enumerate(markers):
            folium.Marker(location=mk, popup=f"Mark {idx+1}", icon=folium.Icon(color="orange", icon="info-sign")).add_to(m)
            
        # Keep map container rendered on screen
        st_folium(m, width=1100, height=600, key="designer_view_map", returned_objects=[])
        
        # Generate the Code block print out safely in the sidebar layout
        st.sidebar.markdown("### 📋 Copy-Paste Configuration Block")
        st.sidebar.markdown("Copy this block and replace lines 20-24 in your code:")
        
        config_text = "```python\n"
        config_text += "SAVED_COURSE = {\n"
        config_text += f'    "start_line": {lines[0] if len(lines) >= 1 else []},\n'
        config_text += f'    "finish_line": {lines[1] if len(lines) >= 2 else []},\n'
        config_text += f'    "marks": {markers}\n'
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
    
    # Read the active layout configurations safely
    lines_source = SAVED_COURSE["start_line"] if SAVED_COURSE["start_line"] else (st.session_state["saved_raw_drawings"] if st.session_state["saved_raw_drawings"] else None)
    
    # Process geometry configurations for racers
    racer_lines = []
    racer_marks = []
    if SAVED_COURSE["start_line"]:
        racer_lines.append(SAVED_COURSE["start_line"])
        racer_lines.append(SAVED_COURSE["finish_line"])
        racer_marks = SAVED_COURSE["marks"]
    elif st.session_state["saved_raw_drawings"]:
        for item in st.session_state["saved_raw_drawings"]:
            g_type = item['geometry']['type']
            coords = item['geometry']['coordinates']
            if g_type == "LineString":
                racer_lines.append([[pt[1], pt[0]] for pt in coords])
            elif g_type == "Point":
                racer_marks.append([coords[1], coords[0]])

    if len(active_racer_points) > 0:
        df_racer = pd.DataFrame(active_racer_points, columns=["lat", "lon"])
        map_center = [df_racer["lat"].mean(), df_racer["lon"].mean()]
    elif len(racer_lines) >= 1:
        map_center = racer_lines[0][0]
    else:
        map_center = [53.46, 9.98]
        
    m = folium.Map(location=map_center, zoom_start=15, tiles="https://arcgisonline.com{z}/{y}/{x}", attr="Esri World Imagery")
    folium.TileLayer('OpenStreetMap').add_to(m)
    folium.LayerControl().add_to(m)
    
    # Render final course layout marks securely
    if len(racer_lines) >= 1:
        folium.PolyLine(locations=racer_lines[0], color="green", weight=7, opacity=0.9, tooltip="Official Start Line").add_to(m)
        folium.Marker(location=racer_lines[0][0], popup="🟢 START LINE", icon=folium.Icon(color="green", icon="play", prefix="fa")).add_to(m)
    if len(racer_lines) >= 2:
        folium.PolyLine(locations=racer_lines[1], color="red", weight=7, opacity=0.9, tooltip="Official Finish Line").add_to(m)
        folium.Marker(location=racer_lines[1][0], popup="🏁 FINISH LINE", icon=folium.Icon(color="red", icon="flag-checkered", prefix="fa")).add_to(m)
    
    colors = ["orange", "purple", "blue", "cadetblue", "darkpurple", "pink"]
    for idx, mark in enumerate(racer_marks):
        folium.Marker(location=mark, popup=f"📍 Course Mark {idx+1}", tooltip=f"Mark {idx+1}", icon=folium.Icon(color=colors[idx % len(colors)], icon="info-sign")).add_to(m)
        
    if len(active_racer_points) > 0:
        folium.PolyLine(locations=active_racer_points, color="cyan", weight=5, opacity=0.85, tooltip="Your Uploaded Track").add_to(m)
        st.success("🎉 Your track was loaded successfully over the course map layout below!")
            
    st_folium(m, width=1100, height=650, key="racer_map_widget", returned_objects=[])
