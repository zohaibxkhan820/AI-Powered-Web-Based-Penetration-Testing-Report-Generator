import os
import subprocess
import sys
import requests
from datetime import datetime

# === Setup paths ===
output_dir = "outputs"
log_dir = "logs"
os.makedirs(output_dir, exist_ok=True)
os.makedirs(log_dir, exist_ok=True)

raw_output = os.path.join(output_dir, "raw.txt")
final_output = os.path.join(output_dir, "dir.txt")
log_file = os.path.join(log_dir, "dir.log")

# === Logger ===
def log(msg):
    print(msg)
    with open(log_file, "a") as logf:
        logf.write(f"{datetime.now()} - {msg}\n")

# === Get and normalize URL ===
if len(sys.argv) != 2:
    log("Usage: python3 dir.py <target_url>")
    sys.exit(1)

input_url = sys.argv[1]
if not input_url.startswith("http://") and not input_url.startswith("https://"):
    url = "http://" + input_url
else:
    url = input_url

# === Delete previous outputs ===
for f in [raw_output, final_output]:
    if os.path.exists(f):
        os.remove(f)
        log(f"[+] Deleted old {f}")

log(f"[+] Starting directory scan on: {url}")

# === Gobuster command ===
cmd = [
    "gobuster", "dir",
    "-u", url,
    "-w", "/usr/share/wordlists/dirb/common.txt",
    "-t", "50",
    "-b", "403,404,501",
    "-o", raw_output
]

# === Run Gobuster and resolve redirects ===
try:
    subprocess.run(cmd, check=True)
    log("[+] Gobuster scan completed.")

    with open(raw_output, "r") as raw, open(final_output, "w") as final:
        count = 1
        for line in raw:
            if "Status:" in line:
                path = line.split()[0]
                full_url = url.rstrip("/") + path

                try:
                    r = requests.get(full_url, allow_redirects=True)  # Removed timeout=5
                    final_url = r.url
                except requests.exceptions.RequestException:
                    final_url = "Could not resolve"

                result = f"{count}. {path}  -->  {final_url}"
                final.write(result + "\n")
                log(result)
                count += 1

    log(f"[✓] Scan finished. {count - 1} directories saved in {final_output}")

except KeyboardInterrupt:
    log("[!] Scan interrupted by user (Ctrl+C). Exiting cleanly.")
    sys.exit(0)

except subprocess.CalledProcessError:
    log("[!] Gobuster failed to run. Check if target is live or reachable.")
    sys.exit(1)
