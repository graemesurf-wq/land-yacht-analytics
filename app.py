import json
import os

import folium
import numpy as np
import pandas as pd
import streamlit as st
from fitparse import FitFile
from folium.plugins import Draw
from streamlit_folium import st_folium

COURSE_FILE = "course.json"
DEFAULT_CENTER = [53.407453, 5.274961]
COLORS = ["cyan", "yellow", "magenta", "lime", "orange", "pink", "white", "gold"]

st.set_page_config(layout="wide", page_title="Land Yacht Race Analyst")
st.title("🏁 Land Yacht Race Analyst")


# ---------------------------------------------------------------- helpers
def hav(lat, lon, plat, plon):
    """Vectorised haversine distance in metres from arrays to one point."""
    R = 6371000.0
    p1, p2 = np.radians(lat), np.radians(plat)
    dphi = p2 - p1
    dlon = np.radians(plon - lon)
    a = np.sin(dphi / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dlon / 2) ** 2
    return R * 2 * np.arctan2(np.sqrt(a), np.sqrt(1 - a))


@st.cache_data(show_spinner=False)
def load_fit(data: bytes) -> pd.DataFrame:
    rows = []
    for r in FitFile(data).get_messages("record"):
        lat, lon, t = r.get_value("position_lat"), r.get_value("position_long"), r.get_value("timestamp")
        if lat is not None and lon is not None and t is not None:
            rows.append((t, lat * 180.0 / 2**31, lon * 180.0 / 2**31))
    df = pd.DataFrame(rows, columns=["t", "lat", "lon"]).sort_values("t").reset_index(drop=True)
    return df


def load_course():
    if os.path.exists(COURSE_FILE):
        try:
            with open(COURSE_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {"start": None, "finish": None, "marks": []}


def drawings_to_course(drawings):
    # Leaflet/GeoJSON gives [lon, lat]; we store [lat, lon].
    pts = [[d["geometry"]["coordinates"][1], d["geometry"]["coordinates"][0]]
           for d in drawings if d["geometry"]["type"] == "Point"]
    return {
        "start": pts[0] if len(pts) >= 1 else None,
        "finish": pts[1] if len(pts) >= 2 else None,
        "marks": pts[2:],
    }


def fmt(secs):
    secs = int(round(secs))
    return f"{secs // 60:02d}:{secs % 60:02d}"


# ------------------------------------------------------- race detection
def detect_races(df, course, r_start, r_mark, r_fin, max_min):
    """Find each time a boat leaves the start zone, rounds every mark in order
    and reaches the finish. Returns a list of per-boat race attempts."""
    lat, lon = df["lat"].to_numpy(), df["lon"].to_numpy()
    t = (df["t"] - df["t"].iloc[0]).dt.total_seconds().to_numpy()

    d_start = hav(lat, lon, *course["start"])
    d_fin = hav(lat, lon, *course["finish"])
    d_marks = [hav(lat, lon, *m) for m in course["marks"]]
    n_marks = len(d_marks)

    # Direction of travel for a valid start: towards the first mark (or finish if no marks)
    d_first = d_marks[0] if n_marks else d_fin
    first_pt = course["marks"][0] if n_marks else course["finish"]
    line_to_first = hav(np.array([course["start"][0]]), np.array([course["start"][1]]), *first_pt)[0]

    attempts = []
    active, last_in_start, start_i, next_mark = False, None, 0, 0

    for i in range(len(t)):
        if not active:
            if d_start[i] <= r_start:
                last_in_start = i  # still sailing around the start area
            elif last_in_start is not None and t[i] - t[last_in_start] <= 30:
                # Left the start area. It only counts as a start if it left on the
                # first-mark side of the line (beside the line is fine, behind it is not).
                if d_first[i] <= line_to_first + 0.25 * r_start:
                    active, start_i, next_mark = True, last_in_start, 0
                last_in_start = None
            continue

        # on course
        if next_mark == 0 and d_start[i] <= r_start:
            active, last_in_start = False, i  # went back to the line: not racing yet
            continue
        if next_mark < n_marks and d_marks[next_mark][i] <= r_mark:
            next_mark += 1
        if next_mark == n_marks and d_fin[i] <= r_fin:
            attempts.append((start_i, i, True))
            active = False
        elif t[i] - t[start_i] > max_min * 60:
            if next_mark > 0:
                attempts.append((start_i, i, False))
            active = False

    out = []
    base = df["t"].iloc[0]
    for s, e, ok in attempts:
        out.append({
            "start_time": base + pd.to_timedelta(t[s], unit="s"),
            "end_time": base + pd.to_timedelta(t[e], unit="s"),
            "secs": t[e] - t[s],
            "finished": ok,
            "points": df.iloc[s:e + 1][["lat", "lon"]].to_numpy()[::2].tolist(),
        })
    return out


def number_races(per_boat, gap_min):
    """Group attempts from all boats into fleet races by start time."""
    flat = [(b, a) for b, atts in per_boat.items() for a in atts]
    flat.sort(key=lambda x: x[1]["start_time"])
    race_no, last_t = 0, None
    for b, a in flat:
        if last_t is None or (a["start_time"] - last_t).total_seconds() > gap_min * 60:
            race_no += 1
        a["race"] = race_no
        last_t = a["start_time"]
    return flat


# ----------------------------------------------------------------- sidebar
mode = st.sidebar.radio("Mode", ["Racer (analyse tracks)", "Designer (set up course)"])

# ---------------------------------------------------------------- designer
if mode.startswith("Designer"):
    st.subheader("🛠️ Course Designer")
    st.markdown("Drop pins in order: **1 = Start, 2 = Finish, 3+ = Marks** (in rounding order), then save.")

    ref = st.file_uploader("Optional: reference .fit track", type=["fit"])
    center, track = DEFAULT_CENTER, None
    if ref:
        track = load_fit(ref.getvalue())
        if len(track):
            center = [track["lat"].mean(), track["lon"].mean()]

    m = folium.Map(location=center, zoom_start=14)
    if track is not None and len(track):
        folium.PolyLine(track[["lat", "lon"]].to_numpy()[::4].tolist(), color="gray", weight=2, opacity=0.5).add_to(m)
    Draw(position="topleft", draw_options={k: False for k in
         ["polyline", "circle", "rectangle", "polygon", "circlemarker"]} | {"marker": True}).add_to(m)

    out = st_folium(m, width=900, height=500, key="designer", returned_objects=["all_drawings"])
    drawings = (out or {}).get("all_drawings") or []
    course = drawings_to_course(drawings)
    st.write(f"Pins placed: start {'✅' if course['start'] else '❌'}, "
             f"finish {'✅' if course['finish'] else '❌'}, marks: {len(course['marks'])}")

    if st.button("💾 Save course", disabled=not (course["start"] and course["finish"])):
        with open(COURSE_FILE, "w") as f:
            json.dump(course, f)
        st.success("Course saved. Switch to Racer mode.")

# ------------------------------------------------------------------- racer
else:
    st.sidebar.header("Detection settings")
    r_start = st.sidebar.slider("Start zone radius (m)", 20, 300, 100)
    r_mark = st.sidebar.slider("Mark rounding radius (m)", 10, 150, 60)
    r_fin = st.sidebar.slider("Finish zone radius (m)", 10, 150, 50)
    max_min = st.sidebar.number_input("Max minutes on course (time cap)", 5, 90, 30)
    gap_min = st.sidebar.number_input("Starts within N minutes = same race", 1, 30, 4)
    time_basis = st.sidebar.radio("Time on course measured from",
                                  ["Boat's own start", "First boat's start in that race"])

    course = load_course()
    if not (course["start"] and course["finish"]):
        st.info("No saved course yet. Use Designer mode to place start, finish and marks first.")
        st.stop()

    files = st.file_uploader("Upload competitor .fit files", type=["fit"], accept_multiple_files=True)
    if not files:
        st.stop()

    per_boat, all_pts = {}, []
    for f in files:
        try:
            df = load_fit(f.getvalue())
            if len(df) < 10:
                st.warning(f"{f.name}: no usable GPS data")
                continue
            per_boat[f.name] = detect_races(df, course, r_start, r_mark, r_fin, max_min)
            all_pts.append(df[["lat", "lon"]].mean().tolist())
        except Exception as e:
            st.error(f"{f.name}: {e}")

    flat = number_races(per_boat, gap_min)
    if not flat:
        st.warning("No races found. Try bigger zone radii, a longer time cap, or check pin placement in Designer mode.")
        st.stop()

    n_races = max(a["race"] for _, a in flat)

    # Boats that start beside the line start later than those on it, so offer both timings.
    first_start = {}
    for _, a in flat:
        first_start[a["race"]] = min(first_start.get(a["race"], a["start_time"]), a["start_time"])
    for _, a in flat:
        a["delay"] = (a["start_time"] - first_start[a["race"]]).total_seconds()
        if time_basis.startswith("First"):
            a["secs"] = (a["end_time"] - first_start[a["race"]]).total_seconds()

    # --- time-on-course table (boats x races)
    rows = {}
    for b, a in flat:
        label = fmt(a["secs"]) + ("" if a["finished"] else " (DNF)")
        rows.setdefault(b, {})[f"Race {a['race']}"] = label
    table = pd.DataFrame(rows).T.reindex(columns=[f"Race {i}" for i in range(1, n_races + 1)]).fillna("–")
    totals = {}
    for b, a in flat:
        if a["finished"]:
            totals[b] = totals.get(b, 0) + a["secs"]
    table["Total (finished)"] = [fmt(totals[b]) if b in totals else "–" for b in table.index]

    st.subheader("⏱️ Time on course")
    st.dataframe(table, use_container_width=True)

    starts = pd.DataFrame([{"Race": a["race"], "Start": a["start_time"]} for _, a in flat]
                          ).groupby("Race")["Start"].min()
    st.caption("Fleet race start times (earliest boat): " +
               ", ".join(f"Race {r}: {s:%H:%M:%S}" for r, s in starts.items()))

    with st.expander("Start delay behind the first boat in each race"):
        delay_rows = {}
        for b, a in flat:
            delay_rows.setdefault(b, {})[f"Race {a['race']}"] = fmt(a["delay"])
        st.dataframe(pd.DataFrame(delay_rows).T.reindex(
            columns=[f"Race {i}" for i in range(1, n_races + 1)]).fillna("–"), use_container_width=True)

    # --- map
    choice = st.sidebar.selectbox("Show on map", ["All races"] + [f"Race {i}" for i in range(1, n_races + 1)])
    boats = list(per_boat.keys())
    visible = {b: st.sidebar.checkbox(b, value=True) for b in boats}

    center = np.mean(all_pts, axis=0).tolist() if all_pts else DEFAULT_CENTER
    m = folium.Map(location=center, zoom_start=14)
    folium.Marker(course["start"], popup="Start", icon=folium.Icon(color="green", icon="play")).add_to(m)
    folium.Circle(course["start"], radius=r_start, color="green", fill=True, opacity=0.12).add_to(m)
    folium.Marker(course["finish"], popup="Finish", icon=folium.Icon(color="red", icon="flag")).add_to(m)
    folium.Circle(course["finish"], radius=r_fin, color="red", fill=True, opacity=0.12).add_to(m)
    for i, mk in enumerate(course["marks"]):
        folium.Marker(mk, popup=f"Mark {i + 1}", icon=folium.Icon(color="orange", icon="star")).add_to(m)

    for b, a in flat:
        if not visible[b] or choice not in ("All races", f"Race {a['race']}"):
            continue
        color = COLORS[boats.index(b) % len(COLORS)]
        folium.PolyLine(a["points"], color=color, weight=4, opacity=0.85,
                        tooltip=f"{b} – Race {a['race']} – {fmt(a['secs'])}").add_to(m)

    st_folium(m, width=1000, height=550, key="racer_map", returned_objects=[])
