import requests
import time
import json
import os
import sys

# Configuration
CONFIG = {
    "api_key": "your_global_api_key",  # Cloudflare Global API Key
    "zone_id": "your_zone_id",  # Cloudflare Zone ID
    "domain": "your.domain.com",  # Domain to update
    "update_interval": 300,  # Update interval in seconds
    "ip_check_url": "https://api.ipify.org"  # Public IP check service
}


def display_startscreen():
    """Display a start screen with user information."""
    os.system('cls' if os.name == 'nt' else 'clear')  # Clear console
    print("=====================================")
    print("     Cloudflare DDNS Updater")
    print("     Created by: Sören - AMD_Ryzen753")
    print("=====================================")
    print(f"Domain: {CONFIG['domain']}")
    print(f"Update Interval: {CONFIG['update_interval']} seconds")
    print("=====================================")
    print("Press Ctrl+C to stop the script")
    print("=====================================")
    time.sleep(2)  # Pause to show the start screen


def get_current_ip():
    """Fetch current public IP address."""
    try:
        response = requests.get(CONFIG["ip_check_url"])
        response.raise_for_status()
        return response.text.strip()
    except requests.RequestException as e:
        print(f"Error fetching IP: {e}")
        return None


def get_dns_record():
    """Get DNS record details from Cloudflare."""
    url = f"https://api.cloudflare.com/client/v4/zones/{CONFIG['zone_id']}/dns_records"
    headers = {
        "Authorization": f"Bearer {CONFIG['api_key']}",
        "Content-Type": "application/json"
    }
    params = {"name": CONFIG["domain"]}

    try:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        records = response.json()["result"]
        if records:
            return records[0]  # Return first matching record
        return None
    except requests.RequestException as e:
        print(f"Error fetching DNS record: {e}")
        return None


def update_dns_record(record_id, ip):
    """Update DNS record with new IP."""
    url = f"https://api.cloudflare.com/client/v4/zones/{CONFIG['zone_id']}/dns_records/{record_id}"
    headers = {
        "Authorization": f"Bearer {CONFIG['api_key']}",
        "Content-Type": "application/json"
    }
    data = {
        "type": "A",
        "name": CONFIG["domain"],
        "content": ip,
        "ttl": 120,
        "proxied": False
    }

    try:
        response = requests.put(url, headers=headers, json=data)
        response.raise_for_status()
        print(f"Updated DNS record to IP: {ip}")
        return True
    except requests.RequestException as e:
        print(f"Error updating DNS record: {e}")
        return False


def main():
    """Main DDNS update loop."""
    display_startscreen()  # Show start screen
    while True:
        current_ip = get_current_ip()
        if not current_ip:
            time.sleep(60)
            continue

        dns_record = get_dns_record()
        if not dns_record:
            time.sleep(60)
            continue

        # Check if update is needed
        if dns_record["content"] != current_ip:
            update_dns_record(dns_record["id"], current_ip)
        else:
            print(f"No update needed. Current IP: {current_ip}")

        time.sleep(CONFIG["update_interval"])


if __name__ == "__main__":
    # Validate configuration
    required_configs = ["api_key", "zone_id", "domain"]
    for config in required_configs:
        if not CONFIG[config] or CONFIG[config].startswith("your_"):
            print(f"Error: Please configure {config} in CONFIG")
            exit(1)

    print(f"Starting DDNS for {CONFIG['domain']}")
    try:
        main()
    except KeyboardInterrupt:
        print("DDNS script stopped by user")