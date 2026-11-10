import streamlit as st
import pandas as pd
import folium
from folium.plugins import Draw
from streamlit_folium import st_folium
from fitparse import FitFile

st.set_page_config(layout="wide")
st.title("🗺️ Interactive Course Designer")
st.markdown("Use the drawing toolbar on the left side of the map to physically click and place your Start Line, Finish Line, and course markers directly on top of your track!")

# 1. File Uploader
uploaded_file = st.file_uploader("Upload your track (.fit file)", type=["fit"])

if uploaded_file is not None:
    fitfile = FitFile(uploaded_file.read())
    
    # Extract GPS points from .fit file
    points = []
    for record in fitfile.get_messages("record"):
        lat = record.get_value("position_lat")
        lon = record.get_value("position_long")
        if lat and lon:
            lat_deg = lat * (180.0 / 2**31)
            lon_deg = lon * (180.0 / 2**31)
            points.append((lat_deg, lon_deg))
            
    if len(points) > 0:
        df = pd.DataFrame(points, columns=["lat", "lon"])
        center_lat = df["lat"].mean()
        center_lon = df["lon"].mean()
        
        # 2. Initialize Base Map
        m = folium.Map(
            location=[center_lat, center_lon], 
            zoom_start=15, 
            tiles="https://arcgisonline.com{z}/{y}/{x}",
            attr="Esri World Imagery"
        )
        folium.TileLayer('OpenStreetMap').add_to(m)
        folium.LayerControl().add_to(m)

        # 3. Draw the background raw track file
        folium.PolyLine(
            locations=points,
            color="cyan",
            weight=4,
            opacity=0.7,
            tooltip="Raw GPS Track"
        ).add_to(m)
        
        # 4. Add the Interactive Drawing Toolbar
        # We configure it to allow drawing Polylines (for lines) and Markers (for waypoints)
        draw_tool = Draw(
            export=False,
            position='topleft',
            draw_options={
                'polyline': {
                    'shapeOptions': {
                        'color': '#3388ff',
                        'weight': 5
                    }
                },
                'marker': True,
                'circle': False,
                'rectangle': False,
                'polygon': False,
                'circlemarker': False
            }
        )
        draw_tool.add_to(m)
        
        # 5. Render Map and Capture User Drawings
        # We tell st_folium to return "all_drawings" when the user interacts
        map_output = st_folium(m, width=1100, height=650, returned_objects=["all_drawings"])
        
        # 6. Parse and Categorize User-Dropped Elements
        user_drawings = map_output.get("all_drawings") if map_output else None
        
        if user_drawings:
            st.markdown("---")
            st.subheader("📋 Map Objects Placed")
            
            lines = []
            markers = []
            
            for item in user_drawings:
                geometry_type = item['geometry']['type']
                coordinates = item['geometry']['coordinates']
                
                if geometry_type == "LineString":
                    # Folium returns coordinates as [lon, lat], we swap them to [lat, lon]
                    swapped_coords = [[pt[1], pt[0]] for pt in coordinates]
                    lines.append(swapped_coords)
                elif geometry_type == "Point":
                    # Single point coordinate [lon, lat] -> [lat, lon]
                    markers.append([coordinates[1], coordinates[0]])
            
            # Display configuration summary dynamically based on what they draw
            col1, col2 = st.columns(2)
            
            with col1:
                st.write(f"**Lines Drawn ({len(lines)}):**")
                for idx, line in enumerate(lines):
                    if idx == 0:
                        st.success(f"🟢 **Start Line Defined** (Ends at: {round(line[0][0],4)}, {round(line[0][1],4)} to {round(line[-1][0],4)}, {round(line[-1][1],4)})")
                    elif idx == 1:
                        st.danger(f"🏁 **Finish Line Defined** (Ends at: {round(line[0][0],4)}, {round(line[0][1],4)} to {round(line[-1][0],4)}, {round(line[-1][1],4)})")
                    else:
                        st.warning(f"➖ Extra Line {idx+1}")
                        
            with col2:
                st.write(f"**Course Markers Dropped ({len(markers)}):**")
                if 2 <= len(markers) <= 6:
                    st.success(f"✅ Active Course Marks: **{len(markers)}** (Valid 2-6 range)")
                elif len(markers) < 2:
                    st.info(f"💡 Place at least **{2 - len(markers)} more marker(s)** to reach your minimum turn goal.")
                else:
                    st.error(f"⚠️ You have placed **{len(markers)}** markers. (Max limit is 6 for your setup)")
                    
                for idx, marker in enumerate(markers):
                    st.write(f"📍 Mark {idx+1}: `{round(marker[0], 5)}, {round(marker[1], 5)}`")
                    
        else:
            st.sidebar.info("💡 **How to design your course:**\n1. Click the Line tool (🛠️) on the map to click-and-draw your **Start Line**.\n2. Draw a second line for your **Finish Line**.\n3. Click the Marker icon to drop your **2 to 6 turn points**.")
            
    else:
        st.error("Could not parse coordinates from this FIT file.")
else:
    st.info("Upload a `.fit` file to view your background map track and activate the drawing toolkit.")
