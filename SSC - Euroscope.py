import socket
import time
import requests

EUROSCOPE_IP = '127.0.0.1'
EUROSCOPE_PORT = 6809
SSC_URL = 'http://192.168.0.198:55055/json'
UPDATE_INTERVAL = 1

def fetch_ssc_items():
    try:
        r = requests.get(SSC_URL, timeout=2)
        data = r.json()
        return data.get("ITEMS", [])
    except:
        return []

def convert_to_fsd(item):
    altitude_ft = item.get("AGL", 0) * 3.28084
    groundspeed = item.get("GS", 0)
    heading = item.get("TH", 0)

    transponder = "N"
    if item.get("TSK_ONGROUND", 0) == 1:
        transponder = "S"

    return "@{t}:{cs}:0000:1:{lat}:{lon}:{alt}:{gs}:{hdg}:0\n".format(
        t=transponder,
        cs=item.get("ID", "UNK"),
        lat=item.get("LAT", 0),
        lon=item.get("LON", 0),
        alt=int(altitude_ft),
        gs=int(groundspeed),
        hdg=int(heading)
    )

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.bind((EUROSCOPE_IP, EUROSCOPE_PORT))
sock.listen(1)

print("Waiting for Euroscope connection...")
conn, addr = sock.accept()
print("Connected to Euroscope:", addr)

try:
    while True:
        items = fetch_ssc_items()

        for item in items:
            fsd = convert_to_fsd(item)
            conn.sendall(fsd.encode())

        time.sleep(UPDATE_INTERVAL)

except KeyboardInterrupt:
    print("Stopping SSC-Tracker → Euroscope feeder")
finally:
    conn.close()
    sock.close()
