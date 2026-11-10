import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
from fitparse import FitFile

st.set_page_config(layout="wide")
st.title("🏃‍♂️ FIT File GPS Track Viewer with Custom Start/Finish Lines")

# 1. File Uploader
uploaded_file = st.file_uploader("Upload a .fit file", type=["fit"])

if uploaded_file is not None:
    # Read the FIT file bytes
    fitfile = FitFile(uploaded_file.read())
    
    # Extract latitude and longitude tracking data
    points = []
    for record in fitfile.get_messages("record"):
        lat = record.get_value("position_lat")
        lon = record.get_value("position_long")
        
        if lat and lon:
            lat_deg = lat * (180.0 / 2**31)
            lon_deg = lon * (180.0 / 2**31)
            points.append((lat_deg, lon_deg))
            
    if len(points) > 2:
        df = pd.DataFrame(points, columns=["lat", "lon"])
        total_points = len(points)
        
        # --- SIDEBAR CONFIGURATION FOR CUSTOM START/FINISH ---
        st.sidebar.header("🏁 Race Course Configuration")
        
        # Sliders to override where the official Start and Finish lines are on the track
        start_percent = st.sidebar.slider("Set Start Line Location (%)", min_value=0, max_value=90, value=0)
        finish_percent = st.sidebar.slider("Set Finish Line Location (%)", min_value=10, max_value=100, value=100)
        
        # Ensure Start doesn't cross Finish
        if start_percent >= finish_percent:
            st.sidebar.error("Start Line must be placed before the Finish Line!")
            start_percent = max(0, finish_percent - 5)
            
        # Convert percentages to actual indices in the points list
        start_idx = int((start_percent / 100) * (total_points - 1))
        finish_idx = int((finish_percent / 100) * (total_points - 1))
        
        # Segment the track to only what is within the official start/finish boundaries
        course_points = points[start_idx:finish_idx + 1]
        total_course_points = len(course_points)
        
        # --- SIDEBAR CONFIGURATION FOR MID-COURSE MARKERS ---
        st.sidebar.markdown("---")
        st.sidebar.header("📍 Mid-Course Markers")
        num_markers = st.sidebar.slider("Number of custom markers", min_value=2, max_value=6, value=3)
        
        # Sliders for markers, relative to the NEW active course length
        marker_positions = []
        for i in range(num_markers):
            default_percent = int(((i + 1) / (num_markers + 1)) * 100)
            percent = st.sidebar.slider(
                f"Marker {i+1} Position (% of active course)", 
                min_value=1, 
                max_value=99, 
                value=default_percent,
                key=f"marker_{i}"
            )
            marker_positions.append(percent)
        
        # --- MAP BUILDING ---
        center_lat = df["lat"].mean()
        center_lon = df["lon"].mean()
        
        m = folium.Map(
            location=[center_lat, center_lon], 
            zoom_start=14, 
            tiles="https://arcgisonline.com{z}/{y}/{x}",
            attr="Esri World Imagery"
        )
        folium.TileLayer('OpenStreetMap').add_to(m)
        folium.LayerControl().add_to(m)

        # Draw the Full Track (Faint grey line to show warmup/cooldown context)
        folium.PolyLine(
            locations=points,
            color="white",
            weight=3,
            opacity=0.4,
            tooltip="Full Recorded Track"
        ).add_to(m)

        # Draw the Active Course Track (Bold cyan line between custom Start and Finish)
        folium.PolyLine(
            locations=course_points,
            color="cyan",
            weight=6,
            opacity=0.9,
            tooltip="Official Course"
        ).add_to(m)
        
        # 2. CUSTOM START LINE
        start_line_coords = points[start_idx]
        folium.Marker(
            location=start_line_coords,
            popup="🟢 CUSTOM START LINE",
            icon=folium.Icon(color="green", icon="play", prefix="fa")
        ).add_to(m)
        
        # 3. CUSTOM FINISH LINE
        finish_line_coords = points[finish_idx]
        folium.Marker(
            location=finish_line_coords,
            popup="🏁 CUSTOM FINISH LINE",
            icon=folium.Icon(color="red", icon="flag-checkered", prefix="fa")
        ).add_to(m)
        
        # 4. CUSTOM MID-COURSE MARKERS (Mapped relative to the course section)
        colors = ["orange", "purple", "blue", "cadetblue", "darkpurple", "pink"]
        
        for idx, percent in enumerate(marker_positions):
            point_index = int((percent / 100) * (total_course_points - 1))
            marker_coords = course_points[point_index]
            
            folium.Marker(
                location=marker_coords,
                popup=f"📍 Custom Marker {idx+1} ({percent}% through course)",
                tooltip=f"Marker {idx+1}",
                icon=folium.Icon(color=colors[idx % len(colors)], icon="info-sign")
            ).add_to(m)
            
        # Render Map into Streamlit
        st_folium(m, width=1100, height=600, returned_objects=[])
        
    else:
        st.error("Not enough valid GPS data points found to calculate custom lines.")
else:
    st.info("Please upload a `.fit` file from your device to configure your custom course lines and markers.")
