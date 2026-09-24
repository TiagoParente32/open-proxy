import subprocess

def list_adb_devices(adb_cmd):
    result = subprocess.run(
        [adb_cmd, "devices", "-l"],
        capture_output=True, text=True
    )

    print(f"[DEBUG] adb devices output:\n{result.stdout}")

    devices = []
    for line in result.stdout.splitlines()[1:]:  # skip header
        line = line.strip()
        if not line:
            continue

        # adb devices -l format:
        # "emulator-5554          device product:sdk_gphone... model:Pixel_6 device:..."
        # serial and state are whitespace-separated, rest is key:value tokens
        parts = line.split()
        if len(parts) < 2:
            continue

        serial = parts[0]
        state = parts[1]

        if state != "device":
            continue

        info = {}
        for token in parts[2:]:
            if ":" in token:
                k, _, v = token.partition(":")
                info[k] = v

        model = info.get("model", info.get("device", serial))
        device_type = "emulator" if serial.startswith("emulator-") else "device"

        devices.append({
            "serial": serial,
            "model": model.replace("_", " "),
            "type": device_type,
            "state": state
        })

    return devices


def list_avds(emulator_cmd):
    """Returns the names of all configured AVDs (running or not) via `emulator -list-avds`."""
    result = subprocess.run(
        [emulator_cmd, "-list-avds"],
        capture_output=True, text=True, timeout=10
    )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def get_avd_name_for_serial(adb_cmd, serial):
    """Returns the AVD name backing a running emulator serial, or None if it can't be determined."""
    try:
        result = subprocess.run(
            [adb_cmd, "-s", serial, "emu", "avd", "name"],
            capture_output=True, text=True, timeout=5
        )
        # Output is the AVD name on the first line, "OK" on the second.
        lines = [l.strip() for l in result.stdout.splitlines() if l.strip()]
        return lines[0] if lines else None
    except Exception:
        return None
