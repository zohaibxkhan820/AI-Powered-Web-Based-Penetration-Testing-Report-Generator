#!/usr/bin/env python3

import sys
import os
import requests
import re
import subprocess
import threading
import ssl
import socket
from time import sleep
from bs4 import BeautifulSoup
from urllib.parse import urlparse

results = {}

# ================== Utility ==================
def run(cmd):
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        return result.stdout if result.returncode == 0 else ""
    except:
        return ""

def normalize_url(target):
    parsed = urlparse(target if target.startswith("http") else f"https://{target}")
    domain = parsed.netloc or parsed.path.split("/")[0]
    return parsed.geturl().split("/")[0] + "//" + domain.strip('/'), domain

# ================== Detection ==================
def detect_technologies(response, url):
    detected = set()
    soup = BeautifulSoup(response.text, 'html.parser')
    content = response.text.lower()
    headers = {k.lower(): v for k, v in response.headers.items()}

    TECHS = [
        {'name': 'Apache', 'headers': ['server'], 'pattern': r'apache'},
        {'name': 'Nginx', 'headers': ['server'], 'pattern': r'nginx'},
        {'name': 'PHP', 'headers': ['x-powered-by'], 'pattern': r'php'},
        {'name': 'React', 'pattern': r'__next_data__|react-root', 'scripts': ['react.js']},
        {'name': 'Vue.js', 'pattern': r'v-|vue', 'scripts': ['vue.js']},
        {'name': 'WordPress', 'pattern': r'wp-|wordpress', 'files': ['/wp-login.php']}
    ]

    for tech in TECHS:
        for header in tech.get('headers', []):
            if header in headers and re.search(tech['pattern'], headers[header], re.I):
                detected.add(tech['name'])

        if 'pattern' in tech and re.search(tech['pattern'], content, re.I):
            detected.add(tech['name'])

        for script in soup.find_all('script', src=True):
            if any(x in script['src'].lower() for x in tech.get('scripts', [])):
                detected.add(tech['name'])

        for file in tech.get('files', []):
            try:
                if requests.get(f"{url}{file}", timeout=5).status_code == 200:
                    detected.add(tech['name'])
            except:
                continue

    return sorted(detected)

# ================== Recon ==================
def get_server_ip(domain):
    out = run(f"host {domain}")
    for line in out.splitlines():
        if "has address" in line:
            return line.split()[-1]
    return None

def get_subnet_info(ip):
    out = run(f"whois {ip}")
    cidr = re.search(r'CIDR:\s*(.+)', out)
    rng = re.search(r'NetRange:\s*(.+)', out)
    return cidr.group(1).strip() if cidr else None, rng.group(1).strip() if rng else None

def nmap_os_scan(ip):
    results['osn'] = run(f"nmap -Pn -O --osscan-guess {ip}")

def nmap_service_scan(ip):
    results['svc'] = run(f"nmap -Pn -sV --top-ports 100 {ip}")

def get_ssl_info(domain, ip):
    try:
        context = ssl.create_default_context()
        with socket.create_connection((ip, 443), timeout=5) as sock:
            with context.wrap_socket(sock, server_hostname=domain) as ssock:
                cipher = ssock.cipher()
                protocol = ssock.version()
                results['ssl_proto'] = protocol
                results['ssl_cipher'] = cipher[0]
    except Exception as e:
        results['ssl_proto'] = results['ssl_cipher'] = None

def parse_os_info(txt):
    m = re.search(r'OS guesses:\s*(.+)', txt)
    return m.group(1).split(',')[0].strip() if m else None

def parse_server_type(txt):
    for line in txt.splitlines():
        if m := re.match(r'^\d+/tcp\s+open\s+\S+\s+(.+)$', line):
            return m.group(1).strip()
    return None

def parse_ports_services(txt):
    return [f"{m.group(1)} {m.group(2)}" for line in txt.splitlines() if (m := re.match(r'^(\d+/tcp)\s+open\s+(\S+)', line))]

def get_domain_dates(domain):
    out = run(f"whois {domain}")
    created = re.search(r'(Creation Date|Registered on|Domain Registration Date):\s*(\S+)', out, re.I)
    expires = re.search(r'(Expiry Date|Expiration Date|Registrar Registration Expiration Date):\s*(\S+)', out, re.I)
    return created.group(2).split('T')[0] if created else None, expires.group(2).split('T')[0] if expires else None

# ================== Main ==================
def full_scan(target):
    url, domain = normalize_url(target)
    ip = get_server_ip(domain)
    if not ip:
        print(f"[!] Could not resolve {domain}")
        return

    threads = [
        threading.Thread(target=nmap_os_scan, args=(ip,)),
        threading.Thread(target=nmap_service_scan, args=(ip,)),
        threading.Thread(target=get_ssl_info, args=(domain, ip))
    ]
    for t in threads: t.start()

    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        r = requests.get(url, headers=headers, timeout=15)
        tech = detect_technologies(r, url)
        code = r.status_code
    except:
        tech, code = [], None

    for t in threads: t.join()
    cidr, rng = get_subnet_info(ip)
    reg, exp = get_domain_dates(domain)

    output_dir = os.path.join(os.getcwd(), "outputs")
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "recon.txt")

    if os.path.exists(output_path):
        os.remove(output_path)

    with open(output_path, 'w') as f:
        f.write(f"[+] Target Domain: {domain}\n")
        f.write(f"[+] Resolved IP: {ip}\n")
        if code: f.write(f"[+] HTTP Status Code: {code}\n")
        if tech: f.write(f"[+] Technologies Detected: {', '.join(tech)}\n")
        if cidr: f.write(f"[+] Network CIDR: {cidr}\n")
        if rng: f.write(f"[+] IP Range: {rng}\n")
        if reg: f.write(f"[+] Domain Created On: {reg}\n")
        if exp: f.write(f"[+] Domain Expires On: {exp}\n")
        os_info = parse_os_info(results.get('osn', ''))
        if os_info: f.write(f"[+] OS Detected: {os_info}\n")
        srv = parse_server_type(results.get('svc', ''))
        if srv: f.write(f"[+] Server Type: {srv}\n")
        ports = parse_ports_services(results.get('svc', ''))
        if ports: f.write("[+] Open Ports and Services:\n" + "\n".join([f"   - {p}" for p in ports]) + "\n")
        if results.get('ssl_proto'): f.write(f"[+] SSL Protocol: {results['ssl_proto']}\n")
        if results.get('ssl_cipher'): f.write(f"[+] SSL Cipher: {results['ssl_cipher']}\n")

    print(f"[✓] Recon complete. Output saved to {output_path}")

if __name__ == '__main__':
    if len(sys.argv) != 2:
        print("Usage: python3 full_scan.py <domain or URL>")
        sys.exit(1)
    print(f"\n[+] Starting Scan for {sys.argv[1]}\n{'='*50}")
    full_scan(sys.argv[1])
