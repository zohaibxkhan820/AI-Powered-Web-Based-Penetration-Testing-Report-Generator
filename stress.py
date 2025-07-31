import subprocess
import logging
import time
import os
import re
import random
import sys
import shutil

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0.3 Safari/605.1.15",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:89.0) Gecko/20100101 Firefox/89.0",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Mobile/15E148 Safari/604.1"
]

def validate_url(url):
    url = url.strip()
    if not re.match(r'^(https?://)?[\w.-]+\.[a-zA-Z]{2,}(/.*)?$', url):
        raise ValueError(f"Invalid URL format: {url}")
    if not url.startswith(('http://', 'https://')):
        url = f"https://{url}"
    return url

def check_siege_installed():
    if not shutil.which("siege"):
        raise RuntimeError("Siege is not installed. Install it with 'sudo apt install siege'.")

def run_siege_test(url):
    users = 250
    duration = 120
    delay = 1
    user_agent = random.choice(USER_AGENTS)

    url = validate_url(url)
    check_siege_installed()

    output_dir = os.path.join(os.getcwd(), "outputs")
    os.makedirs(output_dir, exist_ok=True)
    output_file = os.path.join(output_dir, "stresstest.txt")

    if os.path.exists(output_file):
        os.remove(output_file)

    logger.info(f"Running Siege on {url} with {users} users for {duration} seconds")

    siege_cmd = [
        "siege",
        "-c", str(users),
        "-t", f"{duration}s",
        "-d", str(delay),
        "--header", f"User-Agent: {user_agent}",
        url
    ]

    try:
        result = subprocess.run(
            siege_cmd,
            capture_output=True,
            text=True,
            timeout=duration + 10
        )
        output = result.stdout + result.stderr

        metrics = {
            "Transactions:": "Total number of requests sent.",
            "Availability:": "Percentage of successful responses.",
            "Elapsed time:": "Total duration of the test.",
            "Data transferred:": "Total data received from the server.",
            "Response time:": "Average time per response.",
            "Transaction rate:": "Requests per second.",
            "Throughput:": "Kilobytes transferred per second.",
            "Concurrency:": "Average number of simultaneous users.",
            "Successful transactions:": "Total successful responses.",
            "Failed transactions:": "Total failed requests.",
            "Longest transaction:": "Slowest request duration.",
            "Shortest transaction:": "Fastest request duration."
        }

        summary = []
        for line in output.splitlines():
            for key, desc in metrics.items():
                if key in line:
                    summary.append(f"{line}  <-- {desc}")

        with open(output_file, 'w') as f:
            f.write(f"Stress test summary with {users} users for {duration} seconds on {url}\n\n")
            f.write("\n".join(summary))

        logger.info(f"Siege test completed. Results saved to {output_file}")

    except subprocess.TimeoutExpired:
        logger.error("Siege test timed out")
        raise
    except Exception as e:
        logger.error(f"Siege test failed: {str(e)}")
        raise

def main():
    if len(sys.argv) != 2:
        print("Usage: python3 stress.py <url>")
        sys.exit(1)

    url = sys.argv[1]
    try:
        run_siege_test(url)
    except Exception as e:
        print(f"Error: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
