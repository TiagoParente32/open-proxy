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
