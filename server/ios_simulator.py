import os
import json
import asyncio
import hashlib
import sqlite3
import ssl
import subprocess

def list_ios_simulators():
    """Returns available iOS simulators via xcrun simctl."""
    result = subprocess.run(
        ["xcrun", "simctl", "list", "devices", "--json"],
        capture_output=True, text=True, timeout=10
    )
    data = json.loads(result.stdout)
    simulators = []
    for runtime, devices in data.get("devices", {}).items():
        if "iOS" not in runtime:
            continue
        runtime_label = (runtime
            .replace("com.apple.CoreSimulator.SimRuntime.", "")
            .replace("-", " "))
        for device in devices:
            if not device.get("isAvailable", True):
                continue
            simulators.append({
                "udid":    device["udid"],
                "name":    device["name"],
                "state":   device.get("state", "Shutdown"),
                "runtime": runtime_label,
            })
    simulators.sort(key=lambda d: 0 if d["state"] == "Booted" else 1)
    return simulators


# ============================================================================
# NOTE: everything below was module-level dead code in the original main.py
# (a "# 3. ios setup" section) — not imported or called from anywhere in the
# live ProxyUIBridge flow, which installs the cert via `xcrun simctl keychain
# add-root-cert` instead (see server/bridge/ios_setup.py). Carried over as-is
# during the file-split refactor rather than deleted, since removing it is a
# separate decision from reorganizing working code. Candidate for cleanup.
# ============================================================================

SIMULATOR_DIR = os.path.expanduser("~/Library/Developer/CoreSimulator/Devices/")
TRUSTSTORE_PATHS = [
    "/data/private/var/protected/trustd/private/TrustStore.sqlite3",
    "/data/Library/Keychains/TrustStore.sqlite3",
]

def get_cert_der(pem_path):
    with open(pem_path) as f:
        return ssl.PEM_cert_to_DER_cert(f.read())

def get_cert_sha256(der: bytes) -> bytes:
    return hashlib.sha256(der).digest()

def get_cert_subject_asn1(der: bytes) -> bytes:
    """
    Walks the DER-encoded cert to extract the raw Subject field bytes.
    Structure: SEQUENCE { SEQUENCE { [0] version, serial, algo, issuer, validity, SUBJECT, ... } }
    """
    def read_tlv(data, pos):
        tag = data[pos]; pos += 1
        b = data[pos]; pos += 1
        if b & 0x80:
            n = b & 0x7f
            length = int.from_bytes(data[pos:pos+n], 'big'); pos += n
        else:
            length = b
        return tag, data[pos:pos+length], pos+length

    # Unwrap outer SEQUENCE
    _, cert_seq, _ = read_tlv(der, 0)
    # Unwrap tbsCertificate SEQUENCE
    _, tbs, _ = read_tlv(cert_seq, 0)

    pos = 0
    # Skip: [0] version (optional context tag 0xa0), serialNumber, signature, issuer, validity
    for _ in range(5):
        tag, val, pos = read_tlv(tbs, pos)
        if tag == 0xa0:  # version is optional explicit context [0]
            tag, val, pos = read_tlv(tbs, pos)  # serialNumber
            tag, val, pos = read_tlv(tbs, pos)  # signature
            tag, val, pos = read_tlv(tbs, pos)  # issuer
            tag, val, pos = read_tlv(tbs, pos)  # validity
            break

    # Next TLV is subject — we want the raw bytes INCLUDING the tag+length
    subj_start = pos
    tag, val, pos = read_tlv(tbs, pos)
    return tbs[subj_start:pos]

TSET_PLIST = (
    b'<?xml version="1.0" encoding="UTF-8"?>\n'
    b'<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
    b'"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
    b'<plist version="1.0">\n<array/>\n</plist>\n'
)

def inject_cert_into_truststore(db_path: str, der: bytes):
    sha   = get_cert_sha256(der)
    subj  = get_cert_subject_asn1(der)

    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    # Detect whether this TrustStore uses sha1 or sha256 column
    row = c.execute("SELECT sql FROM sqlite_master WHERE name='tsettings'").fetchone()
    if not row:
        conn.close()
        raise RuntimeError(f"No tsettings table in {db_path}")
    hash_col = "sha256" if "sha256" in row[0] else "sha1"

    existing = c.execute("SELECT COUNT(*) FROM tsettings WHERE subj=?",
                         [sqlite3.Binary(subj)]).fetchone()[0]
    if existing:
        c.execute(f"UPDATE tsettings SET {hash_col}=?, tset=?, data=? WHERE subj=?",
                  [sqlite3.Binary(sha), sqlite3.Binary(TSET_PLIST),
                   sqlite3.Binary(der), sqlite3.Binary(subj)])
    else:
        c.execute(f"INSERT INTO tsettings ({hash_col}, subj, tset, data) VALUES (?,?,?,?)",
                  [sqlite3.Binary(sha), sqlite3.Binary(subj),
                   sqlite3.Binary(TSET_PLIST), sqlite3.Binary(der)])
    conn.commit()
    conn.close()

def _find_truststore_path(udid: str):
    """Returns the TrustStore.sqlite3 path for the given simulator UDID, or None if not found."""
    device_dir = os.path.join(SIMULATOR_DIR, udid)
    for rel_path in TRUSTSTORE_PATHS:
        ts = os.path.join(device_dir, rel_path.lstrip("/"))
        if os.path.isfile(ts):
            return ts
    return None

async def handle_list_ios_simulators(self, ws):
    try:
        sims = list_ios_simulators()
        await ws.send(json.dumps({"type": "IOS_SIMULATORS", "simulators": sims}))
    except Exception as e:
        await ws.send(json.dumps({"type": "IOS_SIMULATORS", "simulators": [], "error": str(e)}))

async def setup_ios_simulator(self, ws, udid: str):
    async def update(step_id, status, msg=""):
        await ws.send(json.dumps({
            "type": "IOS_SIM_PROGRESS", "step": step_id,
            "status": status, "message": msg, "udid": udid
        }))

    try:
        await update("find_cert", "start")
        cert_path = os.path.expanduser("~/.mitmproxy/mitmproxy-ca-cert.pem")
        if not os.path.exists(cert_path):
            await update("find_cert", "error", "Certificate not found. Start proxy first.")
            return
        der = get_cert_der(cert_path)
        await update("find_cert", "success")

        await update("inject_cert", "start")
        truststore_path = _find_truststore_path(udid)
        if not truststore_path:
            await update("inject_cert", "error",
                "TrustStore not found. Ensure the simulator is booted and has been used at least once.")
            return
        await asyncio.get_running_loop().run_in_executor(
            None, inject_cert_into_truststore, truststore_path, der
        )
        await update("inject_cert", "success")
        await update("done", "success")

    except Exception as e:
        await update("inject_cert", "error", str(e))
