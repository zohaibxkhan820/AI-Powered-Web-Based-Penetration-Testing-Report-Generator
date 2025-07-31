import os
import sys
import subprocess
from datetime import datetime

# === Setup folders ===
output_dir = "outputs"
log_dir = "logs"
os.makedirs(output_dir, exist_ok=True)
os.makedirs(log_dir, exist_ok=True)

subdomain_output = os.path.join(output_dir, "subdomain.txt")
log_file = os.path.join(log_dir, "subdomains.log")

# === Logger ===
def log(msg):
    print(msg)
    with open(log_file, "a") as logf:
        logf.write(f"{datetime.now()} - {msg}\n")

# === Check input ===
if len(sys.argv) != 2:
    log("Usage: python3 subdomain.py <domain>")
    sys.exit(1)

domain = sys.argv[1]
log(f"[+] Starting Sublist3r subdomain enumeration for: {domain}")

# === Run Sublist3r ===
output_tmp = "/tmp/subs_temp.txt"
try:
    subprocess.run(["sublist3r", "-d", domain, "-o", output_tmp], check=True)
    log("[+] Sublist3r completed successfully.")
except Exception as e:
    log(f"[!] Sublist3r failed: {e}")
    sys.exit(1)

# === Check if output file exists ===
if not os.path.exists(output_tmp):
    log("[!] No subdomains found or output file missing.")
    sys.exit(0)

# === Read and number subdomains ===
with open(output_tmp, "r") as f:
    subdomains = f.read().splitlines()

# === Delete the old subdomain.txt if it exists, then create a new one ===
if os.path.exists(subdomain_output):
    os.remove(subdomain_output)

# === Write the new subdomains to subdomain.txt ===
with open(subdomain_output, "w") as out:
    for idx, sub in enumerate(subdomains, start=1):
        out.write(f"{idx}. {sub}\n")

os.remove(output_tmp)

log(f"[✓] Found {len(subdomains)} subdomains.")
log(f"[✓] Results saved to {subdomain_output}")
