import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
from fitparse import FitFile

st.set_page_config(layout="wide")
st.title("🏃‍♂️ FIT File GPS Track Viewer")

# 1. File Uploader
uploaded_file = st.file_uploader("Upload a .fit file", type=["fit"])

if uploaded_file is not None:
    # Read the FIT file bytes
    fitfile = FitFile(uploaded_file.read())
    
    # Extract latitude and longitude tracking data
    points = []
    for record in fitfile.get_messages("record"):
        # FIT files store semi-degrees; we must convert them to standard degrees
        lat = record.get_value("position_lat")
        lon = record.get_value("position_long")
        
        if lat and lon:
            lat_deg = lat * (180.0 / 2**31)
            lon_deg = lon * (180.0 / 2**31)
            points.append((lat_deg, lon_deg))
            
    if len(points) > 0:
        # Create a DataFrame for convenience
        df = pd.DataFrame(points, columns=["lat", "lon"])
        
        # Calculate the starting/mid center point to orient the map
        start_point = points[0]
        end_point = points[-1]
        center_lat = df["lat"].mean()
        center_lon = df["lon"].mean()
        
        # 2. Build the Folium Map with Satellite View
        # Esri World Imagery offers a reliable, high-quality satellite base layer
        m = folium.Map(
            location=[center_lat, center_lon], 
            zoom_start=14, 
            tiles="https://arcgisonline.com{z}/{y}/{x}",
            attr="Esri World Imagery"
        )
        
        # Add a fallback standard map toggle so users can see labels if needed
        folium.TileLayer('OpenStreetMap').add_to(m)
        folium.LayerControl().add_to(m)

        # 3. Draw the Track (PolyLine)
        folium.PolyLine(
            locations=points,
            color="cyan",
            weight=5,
            opacity=0.8,
            tooltip="Activity Track"
        ).add_to(m)
        
        # 4. Insert Custom Markers
        # Start marker (Green)
        folium.Marker(
            location=start_point,
            popup="🚀 Start Point",
            icon=folium.Icon(color="green", icon="play")
        ).add_to(m)
        
        # End marker (Red)
        folium.Marker(
            location=end_point,
            popup="🏁 End Point",
            icon=folium.Icon(color="red", icon="stop")
        ).add_to(m)
        
        # 5. Render the Map into Streamlit
        st_folium(m, width=1100, height=600, returned_objects=[])
        
        # Optional: Metrics display below map
        st.subheader("Activity Summary")
        col1, col2 = st.columns(2)
        col1.metric("Data Points Found", len(df))
        col2.metric("Starting Coordinates", f"{round(start_point[0], 4)}, {round(start_point[1], 4)}")
        
    else:
        st.error("No valid GPS data points found in this FIT file. Make sure the activity recorded GPS tracking.")
else:
    st.info("Please upload a `.fit` file from your device to map your track.")
