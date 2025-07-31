import scapy.all as scapy
import ipaddress
import socket
import sys
import json

# Small OUI database for MAC address lookup
oui_dict = {
    "00:50:56": "VMware",
    "00:0C:29": "VMware",
    "00:16:17": "Intel",
    "00:18:F3": "ASUSTek",
    "00:1C:BF": "Dell",
    "00:24:D7": "Apple",
    "00:25:00": "Apple",
    "B8:27:EB": "Raspberry Pi",
    "FC:FC:48": "Amazon (Echo)",
}

def get_manufacturer(mac):
    """Get manufacturer from MAC address."""
    if mac:
        prefix = mac.upper()[:8]
        return oui_dict.get(prefix, "Unknown")
    return "Unknown"

def ping(ip):
    """Ping the IP to check status and get TTL."""
    packet = scapy.IP(dst=ip)/scapy.ICMP()
    response = scapy.sr1(packet, timeout=1, verbose=0)
    if response:
        return "up", response.ttl
    return "down", None

def scan_ports(ip, ports=[22, 80, 443]):
    """Scan common ports."""
    open_ports = []
    for port in ports:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex((ip, port))
            if result == 0:
                open_ports.append(port)
            sock.close()
        except Exception as e:
            print(f"Error scanning port {port} on {ip}: {e}")
    return open_ports

def infer_device_type(manufacturer, open_ports):
    """Infer device type."""
    if manufacturer in ["Apple", "Samsung"]:
        return "Mobile"
    elif manufacturer in ["Dell", "HP", "Lenovo"]:
        return "Laptop/PC"
    elif manufacturer in ["Amazon", "Google"] or 443 in open_ports:
        return "IoT"
    elif 80 in open_ports or 443 in open_ports or manufacturer in ["Cisco", "TP-Link", "Netgear"]:
        return "Router"
    return "Unknown"

def estimate_os(ttl):
    """Estimate OS based on TTL."""
    if ttl is None:
        return "Unknown"
    if ttl <= 64:
        return "Linux/Unix"
    elif ttl <= 128:
        return "Windows"
    elif ttl <= 255:
        return "Network Device"
    return "Unknown"

def scan_network(network):
    """Scan the network."""
    ip_net = ipaddress.IPv4Network(network)
    arp_request = scapy.ARP(pdst=str(ip_net))
    broadcast = scapy.Ether(dst="ff:ff:ff:ff:ff:ff")
    packet = broadcast / arp_request
    answered = scapy.srp(packet, timeout=2, verbose=False)[0]
    active_ips = {answer[1].psrc: answer[1].hwsrc for answer in answered}
    
    hosts = []
    for ip in ip_net.hosts():
        ip_str = str(ip)
        host_data = {
            "ip": ip_str,
            "mac": active_ips.get(ip_str, None),
            "manufacturer": get_manufacturer(active_ips.get(ip_str, None)),
            "status": "down",
            "open_ports": [],
            "device_type": "Unknown",
            "os_estimate": "Unknown"
        }
        if ip_str in active_ips:
            status, ttl = ping(ip_str)
            if status == "up":
                host_data["status"] = "up"
                host_data["open_ports"] = scan_ports(ip_str)
                host_data["device_type"] = infer_device_type(host_data["manufacturer"], host_data["open_ports"])
                host_data["os_estimate"] = estimate_os(ttl)
        hosts.append(host_data)
    return hosts

def save_results(hosts, output_file="network_scan.json"):
    """Save results to JSON."""
    with open(output_file, 'w') as f:
        json.dump(hosts, f, indent=4)
    print(f"Results saved to {output_file}")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: sudo python network_scanner.py <network_range>")
        print("Example: sudo python network_scanner.py 192.168.1.0/24")
        sys.exit(1)
    
    network = sys.argv[1]
    try:
        hosts = scan_network(network)
        for host in hosts:
            print(f"IP: {host['ip']}")
            print(f"MAC: {host['mac']}")
            print(f"Manufacturer: {host['manufacturer']}")
            print(f"Status: {host['status']}")
            print(f"Open Ports: {host['open_ports']}")
            print(f"Device Type: {host['device_type']}")
            print(f"OS Estimate: {host['os_estimate']}")
            print("-" * 20)
        save_results(hosts)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)