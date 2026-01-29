import subprocess
import sys
import socket
import time
import json
import os

packages = ["requests", "SimConnect"]
for pkg in packages:
    subprocess.run([sys.executable, "-m", "pip", "install", pkg], check=True)

import requests
import zipfile

url = "https://github.com/VATSIM-UK/uk-controller-pack/releases/download/2026_01/uk_controller_pack_2026_01.zip"

base = os.path.expandvars(r"%APPDATA%\EuroScope")
zip_path = os.path.join(base, "uk_controller_pack_2026_01.zip")

os.makedirs(base, exist_ok=True)

r = requests.get(url, stream=True)
r.raise_for_status()

with open(zip_path, "wb") as f:
    for chunk in r.iter_content(8192):
        f.write(chunk)

with zipfile.ZipFile(zip_path) as z:
    z.extractall(base)

from SimConnect import SimConnect, AircraftRequests

EUROSCOPE_IP = "127.0.0.1"
EUROSCOPE_PORT = 6809
SSC_URL = "http://127.0.0.1:55055/json"
UPDATE_INTERVAL = 1
ASSUME_DELAY = 5
FSHUB_FILE = r"\\192.168.0.4\FSHub API\fshub_webhooks.txt"
VATSIM_CACHE_TIME = 30

SPECIAL_CALLSIGNS = {
    "TARTAN21"
}

try:
    sm = SimConnect()
    aq = AircraftRequests(sm, _time=200)
except Exception:
    sm = None
    aq = None

vatsim_cache = {"data": None, "last": 0}
fshub_cache = {}
fshub_size = 0

def m_to_ft(m):
    return int(m)

def fetch_ssc_items():
    try:
        return requests.get(SSC_URL, timeout=2).json().get("ITEMS", [])
    except:
        return []

def parse_fshub():
    flights = {}
    buf = ""
    depth = 0
    try:
        with open(FSHUB_FILE, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                if "{" in line:
                    depth += line.count("{")
                if depth > 0:
                    buf += line
                if "}" in line:
                    depth -= line.count("}")
                if depth == 0 and buf.strip():
                    try:
                        data = json.loads(buf)
                    except:
                        buf = ""
                        continue
                    buf = ""

                    _data = data.get("_data") or {}
                    plan = _data.get("plan") or {}

                    cs = plan.get("flight_no") or plan.get("callsign")

                    dep_plan = (_data.get("departure") or {}).get("plan") or {}
                    arr_plan = (_data.get("arrival") or {}).get("plan") or {}

                    if not cs:
                        cs = dep_plan.get("flight_no") or dep_plan.get("callsign")
                    if not cs:
                        cs = arr_plan.get("flight_no") or arr_plan.get("callsign")

                    if not cs:
                        continue

                    flights[cs.upper()] = {
                        "dep": plan.get("departure") or dep_plan.get("departure"),
                        "arr": plan.get("arrival") or arr_plan.get("arrival"),
                        "route": plan.get("route") or dep_plan.get("route") or arr_plan.get("route") or "",
                        "icao": (_data.get("aircraft") or {}).get("icao"),
                        "crz": plan.get("cruise_lvl") or dep_plan.get("cruise_lvl") or arr_plan.get("cruise_lvl")
                    }

    except Exception as e:
        print("FSHub parse error:", e)

    return flights


def refresh_fshub_cache():
    global fshub_cache, fshub_size
    try:
        size = os.path.getsize(FSHUB_FILE)
        if size != fshub_size:
            fshub_cache = parse_fshub()
            fshub_size = size
    except:
        pass

def get_vatsim_data():
    now = time.time()
    if vatsim_cache["data"] is None or now - vatsim_cache["last"] > VATSIM_CACHE_TIME:
        try:
            vatsim_cache["data"] = requests.get(
                "https://data.vatsim.net/v3/vatsim-data.json",
                timeout=5
            ).json()
            vatsim_cache["last"] = now
        except:
            pass
    return vatsim_cache["data"]

def get_vatsim_fpl(callsign):
    data = get_vatsim_data()
    if not data:
        return None
    pilot = next((p for p in data["pilots"] if p["callsign"] == callsign), None)
    if not pilot or not pilot.get("flight_plan"):
        return None
    fp = pilot["flight_plan"]
    return {
        "dep": fp.get("departure"),
        "arr": fp.get("arrival"),
        "route": fp.get("route", ""),
        "icao": fp.get("aircraft_short"),
        "rfl": fp.get("altitude")
    }

def decode_squawk(raw):
    return (
        ((raw >> 12) & 0xF) * 1000 +
        ((raw >> 8) & 0xF) * 100 +
        ((raw >> 4) & 0xF) * 10 +
        (raw & 0xF)
    )

def get_ssr():
    try:
        raw = aq.get("TRANSPONDER_CODE:1")
        return decode_squawk(int(raw)) if raw else 7000
    except:
        return 7000

def build_normal_fpl(ac):
    callsign = ac["ID"].upper()
    gs = int(ac.get("GS", 250))
    dep = "ZZZZ"
    arr = "ZZZZ"
    route = ""
    acft = ac.get("MODEL", "ZZZZ")
    rfl = None

    if acft == "Typhoon":
        acft = "EUFI"

    if callsign in fshub_cache:
        d = fshub_cache[callsign]
        dep = d["dep"]
        arr = d["arr"]
        route = d["route"]
        acft = d["icao"] or acft
        rfl = d["crz"]
    else:
        v = get_vatsim_fpl(callsign)
        if v:
            dep = v["dep"] or dep
            arr = v["arr"] or arr
            route = v["route"]
            acft = v["icao"] or acft
            rfl = v["rfl"]

    alt = f"FL{int(rfl):03}" if rfl else f"FL{int(m_to_ft(ac.get('MSL', 0)) / 100):03.0f}"

    return (
        f"$FP{callsign}:*A:I:H/{acft}/L:{gs}:"
        f"{dep}:0000:0000:{alt}:{arr}:"
        f"0:30:2:00:{arr}:/V/:{route}"
    )

def build_special_fpl(ac):
    callsign = ac["ID"].upper()
    gs = int(ac.get("GS", 100))
    alt = f"FL{int(m_to_ft(ac.get('MSL', 0)) / 100):03.0f}"
    ARR = "EGVN"
    DEP = "EGVN"
    Type = "A332"
    RTE = "DCT HON DCT HON DCT CGY DCT 5318N00056E 5312N00208E DCT BKY DCT"
    return (
        f"$FP{callsign}:*A:I:H/{Type}/L:{gs}:"
        f"{DEP}:0000:0000:{alt}:{ARR}:"
        f"0:30:2:00:{ARR}:/V/:{RTE}"
    )

def build_pos(ac):
    sq = get_ssr()
    return (
        f"@N:{ac['ID']}:{sq:04d}:1:"
        f"{ac['LAT']:.5f}:{ac['LON']:.5f}:"
        f"{m_to_ft(ac['MSL'])}:{int(ac['GS'])}:{int(ac['TH'])}:0"
    )

def build_assume(controller, callsign):
    return f"$CQ{controller}:@94835:IT:{callsign}"

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.bind((EUROSCOPE_IP, EUROSCOPE_PORT))
sock.listen(1)

conn, _ = sock.accept()
conn.sendall(b"#AA\r\n")
conn.setblocking(False)

fpl_sent = set()
assumed = set()
first_seen = {}
controller_callsign = None

try:
    while True:
        try:
            data = conn.recv(4096).decode(errors="ignore")
            for line in data.splitlines():
                if "SERVER:ATC:" in line:
                    controller_callsign = line.split("SERVER:ATC:", 1)[1].strip()
        except:
            pass

        refresh_fshub_cache()
        items = fetch_ssc_items()
        now = time.time()

        for ac in items:
            cs = ac["ID"].upper()

            if cs not in first_seen:
                first_seen[cs] = now

            if cs not in fpl_sent:
                fpl = build_special_fpl(ac) if cs in SPECIAL_CALLSIGNS else build_normal_fpl(ac)
                conn.sendall((fpl + "\r\n").encode())
                fpl_sent.add(cs)

            if controller_callsign and cs not in assumed and now - first_seen[cs] >= ASSUME_DELAY:
                conn.sendall((build_assume(controller_callsign, cs) + "\r\n").encode())
                assumed.add(cs)

            conn.sendall((build_pos(ac) + "\r\n").encode())

        time.sleep(UPDATE_INTERVAL)

except KeyboardInterrupt:
    pass
finally:
    conn.close()
    sock.close()
