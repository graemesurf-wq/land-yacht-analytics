import streamlit as st
import pandas as pd
import folium
from folium.plugins import Draw
from streamlit_folium import st_folium
from fitparse import FitFile

st.set_page_config(layout="wide")
st.title("🏁 Shared Race Course & Multi-Track Viewer")

# --- STEP 1: DEFINE YOUR FIXED SAVED COURSE HERE ---
# After you draw your course once in "Designer Mode", copy the printed coordinates from the app 
# and paste them into these variables below so they are locked for all future visitors.
SAVED_COURSE = {
    "start_line": [[53.4612, 9.9815], [53.4615, 9.9825]],  # Example Line Coordinates
    "finish_line": [[53.4650, 9.9880], [53.4652, 9.9890]], # Example Line Coordinates
    "marks": [
        [53.4625, 9.9840],  # Mark 1
        [53.4635, 9.9860],  # Mark 2
        [53.4645, 9.9850]   # Mark 3
    ]
}

# --- SIDEBAR ROLE SELECTION ---
st.sidebar.header("Mode Selection")
app_mode = st.sidebar.radio("Choose App Role:", ["Racer Mode (Upload & Compare Tracks)", "Designer Mode (Create/Edit Course Layout)"])

if app_mode == "Designer Mode (Create/Edit Course Layout)":
    st.subheader("🛠️ Course Designer Mode")
    st.markdown("1. Upload a reference `.fit` file to view the geography.\n2. Use the map drawing tools to draw your **Start Line** (1st line), **Finish Line** (2nd line), and **2-6 Turn Marks** (Pins).\n3. Copy the generated code from the sidebar and paste it into your `app.py` script on GitHub to save it permanently!")
    
    uploaded_file = st.file_uploader("Upload reference .fit file", type=["fit"], key="designer_uploader")
    points = []
    if uploaded_file:
        fitfile = FitFile(uploaded_file.read())
        for record in fitfile.get_messages("record"):
            lat = record.get_value("position_lat")
            lon = record.get_value("position_long")
            if lat and lon:
                points.append((lat * (180.0 / 2**31), lon * (180.0 / 2**31)))
                
    # Center map dynamically on reference track data if available
    if points:
        df_designer = pd.DataFrame(points, columns=["lat", "lon"])
        center = [df_designer["lat"].mean(), df_designer["lon"].mean()]
    else:
        center = SAVED_COURSE["start_line"][0] if SAVED_COURSE["start_line"] else [53.46, 9.98]
    
    m = folium.Map(location=center, zoom_start=15, tiles="https://arcgisonline.com{z}/{y}/{x}", attr="Esri World Imagery")
    if points:
        folium.PolyLine(locations=points, color="white", weight=3, opacity=0.5, tooltip="Reference Track").add_to(m)
        
    # Inject Drawing controls
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
                lines.append([[pt[1], pt[0]] for pt in coords]) # Swap to [lat, lon]
            elif g_type == "Point":
                markers.append([coords[1], coords[0]])
                
        # Generate configuration block text safely
        st.sidebar.markdown("### 📋 Copy-Paste Configuration Block")
        st.sidebar.markdown("Copy this block and replace lines 14-24 in your `app.py` file code:")
        
        start_val = lines[0] if len(lines) >= 1 else []
        finish_val = lines[1] if len(lines) >= 2 else []
        
        config_text = "```python\n"
        config_text += "SAVED_COURSE = {\n"
        config_text += f'    "start_line": {start_val},\n'
        config_text += f'    "finish_line": {finish_val},\n'
        config_text += f'    "marks": {markers}\n'
        config_text += "}\n"
        config_text += "```"
        st.sidebar.markdown(config_text)
        
        if len(lines) < 2: 
            st.warning(f"Please draw both a Start Line and Finish Line. Currently have: {len(lines)} lines.")
        if not (2 <= len(markers) <= 6): 
            st.warning(f"Please place between 2 and 6 turn marks. Currently have: {len(markers)} marks.")

else:
    # --- RACER MODE ---
    st.subheader("🏃‍♂️ Racer Track Uploader")
    st.markdown("The course layout is locked below. Upload your activity `.fit` file from today's session to see how well you matched the official race boundaries!")
    
    uploaded_file = st.file_uploader("Upload your .fit track file", type=["fit"], key="racer_uploader")
    
    racer_points = []
    if uploaded_file is not None:
        fitfile = FitFile(uploaded_file.read())
        for record in fitfile.get_messages("record"):
            lat = record.get_value("position_lat")
            lon = record.get_value("position_long")
            if lat and lon:
                racer_points.append((lat * (180.0 / 2**31), lon * (180.0 / 2**31)))
    
    # Dynamic Snap calculations
    if len(racer_points) > 0:
        df_racer = pd.DataFrame(racer_points, columns=["lat", "lon"])
        map_center = [df_racer["lat"].mean(), df_racer["lon"].mean()]
    elif SAVED_COURSE["start_line"] and len(SAVED_COURSE["start_line"]) > 0:
        map_center = SAVED_COURSE["start_line"][0]
    else:
        map_center = [53.46, 9.98]
        
    m = folium.Map(location=map_center, zoom_start=15, tiles="https://arcgisonline.com{z}/{y}/{x}", attr="Esri World Imagery")
    folium.TileLayer('OpenStreetMap').add_to(m)
    folium.LayerControl().add_to(m)
    
    # Render Locked Course Objects (Safely extracting pin point locations)
    if SAVED_COURSE["start_line"] and len(SAVED_COURSE["start_line"]) > 0:
        folium.PolyLine(locations=SAVED_COURSE["start_line"], color="green", weight=7, opacity=0.9, tooltip="Official Start Line").add_to(m)
        folium.Marker(location=SAVED_COURSE["start_line"][0], popup="🟢 START LINE", icon=folium.Icon(color="green", icon="play", prefix="fa")).add_to(m)
        
    if SAVED_COURSE["finish_line"] and len(SAVED_COURSE["finish_line"]) > 0:
        folium.PolyLine(locations=SAVED_COURSE["finish_line"], color="red", weight=7, opacity=0.9, tooltip="Official Finish Line").add_to(m)
        folium.Marker(location=SAVED_COURSE["finish_line"][0], popup="🏁 FINISH LINE", icon=folium.Icon(color="red", icon="flag-checkered", prefix="fa")).add_to(m)
        
    colors = ["orange", "purple", "blue", "cadetblue", "darkpurple", "pink"]
    for idx, mark in enumerate(SAVED_COURSE["marks"]):
        folium.Marker(location=mark, popup=f"📍 Course Mark {idx+1}", tooltip=f"Mark {idx+1}", icon=folium.Icon(color=colors[idx % len(colors)], icon="info-sign")).add_to(m)
        
    if uploaded_file is not None:
        if len(racer_points) > 0:
            folium.PolyLine(locations=racer_points, color="cyan", weight=5, opacity=0.85, tooltip="Your Uploaded Track").add_to(m)
            st.success("🎉 Your track was loaded successfully over the course map layout below!")
        else:
            st.error("No valid GPS data points found in your uploaded file.")
            
    st_folium(m, width=1100, height=650, key="racer_map_widget", returned_objects=[])
