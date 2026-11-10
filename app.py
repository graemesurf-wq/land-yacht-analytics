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
    """Pins in order: 1-2 = start line ends, 3 = finish, 4+ = marks (lap order).
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
def detect(df, course, r_start, r_mark, r_fin, give_up_min):
    """Per boat: every valid start (leaving the start area towards the first mark and
    reaching it), the time it crossed the start line, and the lap completions after it."""
    lat, lon = df["lat"].to_numpy(), df["lon"].to_numpy()
    t = (df["t"] - df["t"].iloc[0]).dt.total_seconds().to_numpy()
    base = df["t"].iloc[0]
    n = len(t)

    d_start = hav(lat, lon, *course["start"])
    d_fin = hav(lat, lon, *course["finish"])
    d_marks = [hav(lat, lon, *m) for m in course["marks"]]
    n_marks = len(d_marks)
    d_first = d_marks[0] if n_marks else d_fin
    first_pt = course["marks"][0] if n_marks else course["finish"]
    line_to_first = hav(np.array([course["start"][0]]), np.array([course["start"][1]]), *first_pt)[0]

    # forward crossings of the start line (back side -> first-mark side)
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

    def stamp(sec):
        return base + pd.to_timedelta(sec, unit="s")

    cands, last_in_start = [], None
    for i in range(n):
        if d_start[i] <= r_start:
            last_in_start = i  # sailing around the start area
            continue
        if last_in_start is None or t[i] - t[last_in_start] > 30:
            continue
        s_i, last_in_start = last_in_start, None
        if d_first[i] > line_to_first + 0.25 * r_start:
            continue  # left from behind the line: not a start
        j, reached = i, False
        while j < n and t[j] - t[i] <= 600 and d_start[j] > r_start:
            if d_first[j] <= r_mark:
                reached = True
                break
            j += 1
        if not reached:
            continue  # went back to the line (early start / still manoeuvring)

        # laps completed after this start: all marks in order, then the finish
        laps, nm, cool = [], 0, False
        for k in range(i, n):
            if t[k] - t[s_i] > give_up_min * 60:
                break
            if cool:
                if d_fin[k] > r_fin:
                    cool = False
                continue
            if nm < n_marks and d_marks[nm][k] <= r_mark:
                nm += 1
            if nm == n_marks and d_fin[k] <= r_fin:
                laps.append(stamp(t[k]))
                nm, cool = 0, True
        cand = cross_t[(cross_t >= t[s_i] - 300) & (cross_t <= t[s_i] + 60)]
        cands.append({"start_time": stamp(t[s_i]),
                      "cross_time": stamp(cand[-1]) if len(cand) else None,
                      "laps": laps})
    return cands


@st.cache_data(show_spinner="Analysing track…")
def analyse(data, course_json, r_start, r_mark, r_fin, give_up_min):
    df = load_fit(data)
    if len(df) < 10:
        return None
    course = json.loads(course_json)
    cands = detect(df, course, r_start, r_mark, r_fin, give_up_min)
    la, lo = df["lat"].to_numpy(), df["lon"].to_numpy()
    diag = {"Closest to start (m)": round(float(hav(la, lo, *course["start"]).min())),
            "Closest to finish (m)": round(float(hav(la, lo, *course["finish"]).min()))}
    for i, mk in enumerate(course["marks"]):
        diag[f"Closest to mark {i + 1} (m)"] = round(float(hav(la, lo, *mk).min()))
    diag["Start attempts found"] = len(cands)
    diag["Most laps after a start"] = max([len(c["laps"]) for c in cands], default=0)
    sub = df.iloc[::2]
    base = df["t"].iloc[0]
    return {"cands": cands, "base": base, "diag": diag,
            "t": (sub["t"] - base).dt.total_seconds().to_numpy(),
            "lat": sub["lat"].to_numpy(), "lon": sub["lon"].to_numpy()}


def build_races(per_boat, limits, window_min, n_races=0):
    """Fleet races in time order. A race starts when the first boat crosses the line;
    after the race time limit each boat finishes at its next lap completion.
    n_races > 0: keep the N starts with the most boats (no two overlapping).
    n_races = 0: take every start in time order."""
    window = pd.Timedelta(minutes=window_min)
    items = sorted(((c["cross_time"] if c["cross_time"] is not None else c["start_time"], b, c)
                    for b, info in per_boat.items() for c in info["cands"]), key=lambda x: x[0])
    clusters = []
    for ts, b, c in items:
        if clusters and ts - clusters[-1]["t0"] <= window:
            clusters[-1]["boats"].setdefault(b, (ts, c))
        else:
            clusters.append({"t0": ts, "boats": {b: (ts, c)}})

    chosen = []
    if n_races > 0:
        min_limit = pd.Timedelta(minutes=min(limits))
        for cl in sorted(clusters, key=lambda c: (-len(c["boats"]), c["t0"])):
            if len(chosen) >= n_races:
                break
            if all(cl["t0"] > o["t0"] + min_limit or o["t0"] > cl["t0"] + min_limit for o in chosen):
                chosen.append(cl)
        chosen.sort(key=lambda c: c["t0"])
    else:
        lower = None
        for cl in clusters:
            if lower is None or cl["t0"] >= lower:
                chosen.append(cl)
                lower = cl["t0"] + pd.Timedelta(minutes=limits[min(len(chosen) - 1, len(limits) - 1)])

    races = []
    for k, cl in enumerate(chosen):
        limit = limits[min(k, len(limits) - 1)]
        F = cl["t0"]
        limit_t = F + pd.Timedelta(minutes=limit)
        boats = {}
        for b, (ts, c) in cl["boats"].items():
            idx = next((i for i, lap in enumerate(c["laps"]) if lap >= limit_t), None)
            end = c["laps"][idx] if idx is not None else None
            boats[b] = {"own_start": ts, "end": end, "finished": end is not None,
                        "laps": idx + 1 if idx is not None else len(c["laps"])}
        races.append({"n": k + 1, "start": F, "limit": limit, "limit_t": limit_t, "boats": boats})
    return races


def track_slice(info, s, e):
    base = info["base"]
    s_sec, e_sec = (s - base).total_seconds(), (e - base).total_seconds()
    i0, i1 = np.searchsorted(info["t"], s_sec), np.searchsorted(info["t"], e_sec, side="right")
    return np.column_stack([info["lat"][i0:i1], info["lon"][i0:i1]]).tolist()


# ----------------------------------------------------------------- sidebar
mode = st.sidebar.radio("Mode", ["Racer (analyse tracks)", "Designer (set up course)"])

# ---------------------------------------------------------------- designer
if mode.startswith("Designer"):
    st.subheader("🛠️ Course Designer")
    st.markdown("Drop pins in this order: **1–2 = ends of the start line, 3 = finish, 4+ = marks** "
                "(in the order they are rounded each lap). Then save or download the course.")

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
    limits_raw = st.sidebar.text_input("Race time limits in minutes, one per race (comma separated)",
                                       "15, 20, 15, 15, 10",
                                       help="When the limit runs out, each boat finishes the lap it is on. "
                                            "The last value is reused if there are more races.")
    try:
        limits = [float(x) for x in limits_raw.split(",") if x.strip()] or [20.0]
    except ValueError:
        limits = [20.0]
    n_races = st.sidebar.number_input("Number of races to find (0 = detect automatically)", 0, 12, 0,
                                      help="If you know how many races were sailed, set it here. The app keeps "
                                           "the starts with the most boats.")
    window_min = st.sidebar.number_input("Boats starting within N minutes of the first = same race", 1, 30, 4)
    r_start = st.sidebar.slider("Start area radius (m)", 20, 300, 100)
    r_mark = st.sidebar.slider("Mark rounding radius (m)", 10, 150, 60)
    r_fin = st.sidebar.slider("Finish zone radius (m)", 10, 150, 50)
    give_up = st.sidebar.number_input("Look for laps up to (minutes after start)", 20, 180, 60,
                                      help="Must be longer than your longest race plus one lap.")

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
    per_boat = {}
    for f in files:
        try:
            info = analyse(f.getvalue(), course_json, r_start, r_mark, r_fin, give_up)
            if info is None:
                st.warning(f"{f.name}: no usable GPS data")
            else:
                per_boat[f.name] = info
        except Exception as e:
            st.error(f"{f.name}: {e}")

    races = build_races(per_boat, limits, window_min, int(n_races))
    if not races:
        st.warning("No races found. Try bigger radii, check the pin order in Designer mode, "
                   "or check that the marks are listed in the order they are rounded.")
        st.stop()
    race_cols = [f"Race {r['n']}" for r in races]
    if n_races and len(races) < n_races:
        st.warning(f"Asked for {n_races} races but only found {len(races)}. Check the diagnostics below.")

    # The usual lap count for each race is whatever most finishing boats did that day.
    usual = {}
    for r in races:
        done = [v["laps"] for v in r["boats"].values() if v["finished"]]
        usual[r["n"]] = max(set(done), key=done.count) if done else None

    rows, totals, lap_totals, delays = {}, {}, {}, {}
    for r in races:
        for b, v in r["boats"].items():
            col = f"Race {r['n']}"
            if v["finished"]:
                secs = (v["end"] - r["start"]).total_seconds()
                flag = " ⚠️" if usual[r["n"]] is not None and v["laps"] != usual[r["n"]] else ""
                rows.setdefault(b, {})[col] = f"{fmt(secs)} ({v['laps']} laps){flag}"
                totals[b] = totals.get(b, 0) + secs
                lap_totals[b] = lap_totals.get(b, 0) + v["laps"]
            else:
                rows.setdefault(b, {})[col] = f"DNF ({v['laps']} laps)"
            delays.setdefault(b, {})[col] = fmt(max(0.0, (v["own_start"] - r["start"]).total_seconds()))
    table = pd.DataFrame(rows).T.reindex(columns=race_cols).fillna("–")
    table["Total time (finished)"] = [fmt(totals[b]) if b in totals else "–" for b in table.index]
    table["Total laps"] = [lap_totals.get(b, 0) for b in table.index]

    st.subheader("⏱️ Time on course (from the first boat across the start line)")
    st.dataframe(table, use_container_width=True)
    st.caption("Race start (first boat across the line), time limit and usual laps: " + " · ".join(
        f"Race {r['n']}: {r['start']:%H:%M:%S}, {r['limit']:g} min, {usual[r['n']] or '?'} laps"
        for r in races))
    st.caption("⚠️ = this boat's lap count differs from most of the fleet in that race "
               "(a missed mark, a GPS gap, or a boat that was genuinely a lap up or down).")

    with st.expander("How far behind the first starter each boat started"):
        st.dataframe(pd.DataFrame(delays).T.reindex(columns=race_cols).fillna("–"), use_container_width=True)

    with st.expander("🔍 Diagnostics (why a race or boat is missing)"):
        st.dataframe(pd.DataFrame({b: i["diag"] for b, i in per_boat.items()}).T, use_container_width=True)
        st.caption("If 'closest to mark' is bigger than the mark radius, raise the radius or move the pin. "
                   "If there are 0 start attempts, the boat never left the start area towards the first mark "
                   "(check pin order and start area radius).")

    # --- map
    choice = st.sidebar.selectbox("Show on map", ["All races"] + race_cols)
    boats = list(per_boat.keys())
    visible = {b: st.sidebar.checkbox(b, value=True) for b in boats}

    allpts = np.concatenate([np.column_stack([i["lat"], i["lon"]]) for i in per_boat.values()])
    m = folium.Map(location=allpts.mean(axis=0).tolist(), zoom_start=14)
    if course.get("start_a") and course.get("start_b"):
        folium.PolyLine([course["start_a"], course["start_b"]], color="green", weight=5, tooltip="Start line").add_to(m)
    folium.Circle(course["start"], radius=r_start, color="green", fill=True, opacity=0.1).add_to(m)
    folium.Marker(course["finish"], popup="Finish", icon=folium.Icon(color="red", icon="flag")).add_to(m)
    folium.Circle(course["finish"], radius=r_fin, color="red", fill=True, opacity=0.1).add_to(m)
    for i, mk in enumerate(course["marks"]):
        folium.Marker(mk, popup=f"Mark {i + 1}", icon=folium.Icon(color="orange", icon="star")).add_to(m)
    for r in races:
        if choice not in ("All races", f"Race {r['n']}"):
            continue
        for b, v in r["boats"].items():
            if not visible[b]:
                continue
            end = v["end"] if v["finished"] else r["limit_t"] + pd.Timedelta(minutes=3)
            label = (fmt((v["end"] - r["start"]).total_seconds()) if v["finished"] else "DNF") + f", {v['laps']} laps"
            folium.PolyLine(track_slice(per_boat[b], v["own_start"], end),
                            color=COLORS[boats.index(b) % len(COLORS)], weight=4, opacity=0.85,
                            tooltip=f"{b} – Race {r['n']} – {label}").add_to(m)
    st_folium(m, width=1000, height=550, key="racer_map", returned_objects=[])
