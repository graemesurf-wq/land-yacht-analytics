dimport json
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
    """Vectorised haversine distance (m) from arrays to one point."""
    R = 6371000.0
    p1, p2 = np.radians(lat), np.radians(plat)
    a = np.sin((p2 - p1) / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(np.radians(plon - lon) / 2) ** 2
    return R * 2 * np.arctan2(np.sqrt(a), np.sqrt(1 - a))


@st.cache_data(show_spinner=False)
def load_fit(data: bytes) -> pd.DataFrame:
    rows = []
    for r in FitFile(data).get_messages("record"):
        lat, lon, t = r.get_value("position_lat"), r.get_value("position_long"), r.get_value("timestamp")
        if lat is not None and lon is not None and t is not None:
            rows.append((t, lat * 180.0 / 2**31, lon * 180.0 / 2**31))
    return pd.DataFrame(rows, columns=["t", "lat", "lon"]).sort_values("t").reset_index(drop=True)


def load_course():
    if os.path.exists(COURSE_FILE):
        try:
            with open(COURSE_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def drawings_to_course(drawings):
    """Pins in order: 1-2 = start line ends, 3 = finish, 4+ = marks.
    Leaflet gives [lon, lat]; we store [lat, lon]."""
    pts = [[d["geometry"]["coordinates"][1], d["geometry"]["coordinates"][0]]
           for d in drawings if d["geometry"]["type"] == "Point"]
    c = {"start_a": pts[0] if len(pts) > 0 else None,
         "start_b": pts[1] if len(pts) > 1 else None,
         "finish": pts[2] if len(pts) > 2 else None,
         "marks": pts[3:], "start": None}
    if c["start_a"] and c["start_b"]:
        c["start"] = [(c["start_a"][0] + c["start_b"][0]) / 2, (c["start_a"][1] + c["start_b"][1]) / 2]
    return c


def course_ready(c):
    return bool(c.get("start") and c.get("finish"))


def fmt(secs):
    secs = int(round(secs))
    return f"{secs // 60:02d}:{secs % 60:02d}"


# ------------------------------------------------------- race detection
def detect_races(df, course, r_start, r_mark, r_fin, max_min):
    """Per boat: find each run  start area -> marks in order -> finish, plus the
    time the boat crossed the start line towards the first mark."""
    lat, lon = df["lat"].to_numpy(), df["lon"].to_numpy()
    t = (df["t"] - df["t"].iloc[0]).dt.total_seconds().to_numpy()

    d_start = hav(lat, lon, *course["start"])
    d_fin = hav(lat, lon, *course["finish"])
    d_marks = [hav(lat, lon, *m) for m in course["marks"]]
    n_marks = len(d_marks)
    d_first = d_marks[0] if n_marks else d_fin
    first_pt = course["marks"][0] if n_marks else course["finish"]
    line_to_first = hav(np.array([course["start"][0]]), np.array([course["start"][1]]), *first_pt)[0]

    # --- forward crossings of the start line (back side -> first-mark side)
    cross_t = np.array([])
    if course.get("start_a") and course.get("start_b"):
        lat0, lon0 = course["start"]
        kx, ky = 111320 * np.cos(np.radians(lat0)), 110540

        def xy(la, lo):
            return (np.asarray(lo) - lon0) * kx, (np.asarray(la) - lat0) * ky

        X, Y = xy(lat, lon)
        ax, ay = xy(*course["start_a"])
        bx, by = xy(*course["start_b"])
        mx, my = xy(*first_pt)
        dx, dy = bx - ax, by - ay
        L2 = dx * dx + dy * dy
        if L2 > 1:
            s = (dx * (Y - ay) - dy * (X - ax)) * np.sign(dx * (my - ay) - dy * (mx - ax))
            idx = np.where((s[:-1] <= 0) & (s[1:] > 0))[0]
            frac = -s[idx] / (s[idx + 1] - s[idx])
            px = X[idx] + frac * (X[idx + 1] - X[idx])
            py = Y[idx] + frac * (Y[idx + 1] - Y[idx])
            u = ((px - ax) * dx + (py - ay) * dy) / L2
            ok = (u >= 0) & (u <= 1)
            cross_t = t[idx][ok] + frac[ok] * (t[idx + 1][ok] - t[idx][ok])

    # --- state machine
    attempts = []
    active, last_in_start, start_i, next_mark = False, None, 0, 0
    for i in range(len(t)):
        if not active:
            if d_start[i] <= r_start:
                last_in_start = i  # sailing around the start area
            elif last_in_start is not None and t[i] - t[last_in_start] <= 30:
                # leaving the area: counts only on the first-mark side (beside the line is fine)
                if d_first[i] <= line_to_first + 0.25 * r_start:
                    active, start_i, next_mark = True, last_in_start, 0
                last_in_start = None
            continue
        if next_mark == 0 and d_start[i] <= r_start:
            active, last_in_start = False, i  # back at the line: restart
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

    base = df["t"].iloc[0]
    out = []
    for s_i, e_i, fin in attempts:
        cand = cross_t[(cross_t >= t[s_i] - 300) & (cross_t <= t[s_i] + 60)]
        out.append({
            "start_time": base + pd.to_timedelta(t[s_i], unit="s"),
            "cross_time": base + pd.to_timedelta(cand[-1], unit="s") if len(cand) else None,
            "end_time": base + pd.to_timedelta(t[e_i], unit="s"),
            "finished": fin,
            "points": df.iloc[s_i:e_i + 1][["lat", "lon"]].to_numpy()[::3].tolist(),
        })
    return out


@st.cache_data(show_spinner="Analysing track…")
def analyse(data, course_json, r_start, r_mark, r_fin, max_min):
    df = load_fit(data)
    if len(df) < 10:
        return None, None
    return (detect_races(df, json.loads(course_json), r_start, r_mark, r_fin, max_min),
            [float(df["lat"].mean()), float(df["lon"].mean())])


def number_races(per_boat, gap_min):
    flat = [(b, a) for b, atts in per_boat.items() for a in atts]
    flat.sort(key=lambda x: x[1]["start_time"])
    race_no, last_t = 0, None
    for _, a in flat:
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
    st.markdown("Drop pins in this order: **1–2 = ends of the start line, 3 = finish, 4+ = marks** "
                "(in rounding order). Then save or download the course.")

    ref = st.file_uploader("Optional: reference .fit track", type=["fit"])
    center, track = DEFAULT_CENTER, None
    if ref:
        track = load_fit(ref.getvalue())
        if len(track):
            center = [track["lat"].mean(), track["lon"].mean()]

    m = folium.Map(location=center, zoom_start=14)
    if track is not None and len(track):
        folium.PolyLine(track[["lat", "lon"]].to_numpy()[::6].tolist(), color="gray", weight=2, opacity=0.5).add_to(m)
    Draw(position="topleft", draw_options={"polyline": False, "circle": False, "rectangle": False,
                                           "polygon": False, "circlemarker": False, "marker": True}).add_to(m)

    out = st_folium(m, width=900, height=500, key="designer", returned_objects=["all_drawings"])
    course = drawings_to_course((out or {}).get("all_drawings") or [])
    st.write(f"Start line {'✅' if course['start'] else '❌ (needs 2 pins)'} · "
             f"finish {'✅' if course['finish'] else '❌'} · marks: {len(course['marks'])}")

    if course_ready(course):
        c1, c2 = st.columns(2)
        if c1.button("💾 Save course on server"):
            with open(COURSE_FILE, "w") as f:
                json.dump(course, f)
            st.success("Saved (note: on Streamlit Cloud this is lost on restart).")
        c2.download_button("⬇️ Download course.json (commit it to GitHub)", json.dumps(course),
                           file_name="course.json", mime="application/json")

# ------------------------------------------------------------------- racer
else:
    st.sidebar.header("Detection settings")
    r_start = st.sidebar.slider("Start area radius (m)", 20, 300, 100)
    r_mark = st.sidebar.slider("Mark rounding radius (m)", 10, 150, 60)
    r_fin = st.sidebar.slider("Finish zone radius (m)", 10, 150, 50)
    max_min = st.sidebar.number_input("Max minutes on course (time cap)", 5, 90, 30)
    gap_min = st.sidebar.number_input("Starts within N minutes = same race", 1, 30, 4)

    course = load_course()
    course_up = st.sidebar.file_uploader("Or load a course.json", type=["json"])
    if course_up:
        course = json.loads(course_up.getvalue())
    if not course_ready(course):
        st.info("No course yet. Create one in Designer mode, or load a course.json in the sidebar.")
        st.stop()

    files = st.file_uploader("Upload competitor .fit files", type=["fit"], accept_multiple_files=True)
    if not files:
        st.stop()

    course_json = json.dumps(course, sort_keys=True)
    per_boat, centers = {}, []
    for f in files:
        try:
            atts, c = analyse(f.getvalue(), course_json, r_start, r_mark, r_fin, max_min)
            if atts is None:
                st.warning(f"{f.name}: no usable GPS data")
                continue
            per_boat[f.name] = atts
            centers.append(c)
        except Exception as e:
            st.error(f"{f.name}: {e}")

    flat = number_races(per_boat, gap_min)
    if not flat:
        st.warning("No races found. Try bigger radii, a longer time cap, or check the pins in Designer mode.")
        st.stop()
    n_races = max(a["race"] for _, a in flat)
    race_cols = [f"Race {i}" for i in range(1, n_races + 1)]

    # The first boat across the line starts the clock for everyone.
    fleet_start = {}
    for r in range(1, n_races + 1):
        in_race = [a for _, a in flat if a["race"] == r]
        crossed = [a["cross_time"] for a in in_race if a["cross_time"] is not None]
        fleet_start[r] = min(crossed) if crossed else min(a["start_time"] for a in in_race)
    for _, a in flat:
        a["secs"] = max(0.0, (a["end_time"] - fleet_start[a["race"]]).total_seconds())
        own = a["cross_time"] if a["cross_time"] is not None else a["start_time"]
        a["delay"] = max(0.0, (own - fleet_start[a["race"]]).total_seconds())

    rows, totals = {}, {}
    for b, a in flat:
        rows.setdefault(b, {})[f"Race {a['race']}"] = fmt(a["secs"]) + ("" if a["finished"] else " (DNF)")
        if a["finished"]:
            totals[b] = totals.get(b, 0) + a["secs"]
    table = pd.DataFrame(rows).T.reindex(columns=race_cols).fillna("–")
    table["Total (finished)"] = [fmt(totals[b]) if b in totals else "–" for b in table.index]

    st.subheader("⏱️ Time on course (from the first boat across the start line)")
    st.dataframe(table, use_container_width=True)
    st.caption("Race starts: " + ", ".join(f"Race {r}: {s:%H:%M:%S}" for r, s in fleet_start.items()))

    with st.expander("How far behind the first starter each boat started"):
        d = {}
        for b, a in flat:
            d.setdefault(b, {})[f"Race {a['race']}"] = fmt(a["delay"])
        st.dataframe(pd.DataFrame(d).T.reindex(columns=race_cols).fillna("–"), use_container_width=True)

    # --- map
    choice = st.sidebar.selectbox("Show on map", ["All races"] + race_cols)
    boats = list(per_boat.keys())
    visible = {b: st.sidebar.checkbox(b, value=True) for b in boats}

    m = folium.Map(location=np.mean(centers, axis=0).tolist() if centers else DEFAULT_CENTER, zoom_start=14)
    if course.get("start_a") and course.get("start_b"):
        folium.PolyLine([course["start_a"], course["start_b"]], color="green", weight=5, tooltip="Start line").add_to(m)
    folium.Circle(course["start"], radius=r_start, color="green", fill=True, opacity=0.1).add_to(m)
    folium.Marker(course["finish"], popup="Finish", icon=folium.Icon(color="red", icon="flag")).add_to(m)
    folium.Circle(course["finish"], radius=r_fin, color="red", fill=True, opacity=0.1).add_to(m)
    for i, mk in enumerate(course["marks"]):
        folium.Marker(mk, popup=f"Mark {i + 1}", icon=folium.Icon(color="orange", icon="star")).add_to(m)
    for b, a in flat:
        if visible[b] and choice in ("All races", f"Race {a['race']}"):
            folium.PolyLine(a["points"], color=COLORS[boats.index(b) % len(COLORS)], weight=4, opacity=0.85,
                            tooltip=f"{b} – Race {a['race']} – {fmt(a['secs'])}").add_to(m)
    st_folium(m, width=1000, height=550, key="racer_map", returned_objects=[])
