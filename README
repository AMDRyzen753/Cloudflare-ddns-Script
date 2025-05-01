# Cloudflare DDNS Python Script

This Python script automates the process of updating a DNS A record in Cloudflare with your current public IP address, effectively creating a Dynamic DNS (DDNS) solution. Created by Sören - AMD_Ryzen753.

## Prerequisites

Before using this script, ensure you have the following:

- **Python 3.6+** installed on your system.
- A **Cloudflare account** with a domain configured.
- A **Cloudflare Global API Key** (or API Token with appropriate permissions).
- The **Zone ID** of your domain in Cloudflare.
- The `requests` Python library installed. You can install it using:
  ```bash
  pip install requests
  ```

## Installation

1. **Clone or Download the Repository**
   - Clone this repository to your local machine:
     ```bash
     git clone https://github.com/AMDRyzen753/Cloudflare-ddns-Script.git
     ```
   - Alternatively, download the ZIP file from GitHub and extract it.

2. **Navigate to the Project Directory**
   ```bash
   cd Cloudflare-ddns-Script
   ```

3. **Install Dependencies**
   Run the following command to install the required Python library:
   ```bash
   pip install requests
   ```

## Configuration

1. **Edit the Script**
   Open the `cloudflare_ddns.py` file in a text editor.

2. **Update the Configuration Section**
   Modify the `CONFIG` dictionary in the script with your Cloudflare details:
   ```python
   CONFIG = {
       "api_key": "your_global_api_key",   # Cloudflare Global API Key
       "zone_id": "your_zone_id",          # Cloudflare Zone ID
       "domain": "your.domain.com",        # Domain to update (e.g., subdomain.example.com)
       "update_interval": 300,             # Update interval in seconds
       "ip_check_url": "https://api.ipify.org"  # Public IP check service
   }
   ```
   - **api_key**: Your Cloudflare Global API Key. Find it in your Cloudflare dashboard under "My Profile" > "API Tokens" > "Global API Key".
   - **zone_id**: The Zone ID of your domain. Find it in the Cloudflare dashboard under your domain's "Overview" tab.
   - **domain**: The DNS record you want to update (e.g., `home.example.com` or `example.com`).
   - **update_interval**: How often (in seconds) the script checks for IP changes. Default is 300 seconds (5 minutes).
   - **ip_check_url**: The service used to check your public IP. The default (`https://api.ipify.org`) works fine for most cases.

## Usage

1. **Run the Script**
   Execute the script using Python:
   ```bash
   python cloudflare_ddns.py
   ```

2. **Start Screen**
   Upon running, the script displays a start screen with your name ("Sören - AMD_Ryzen753"), the configured domain, and the update interval. It will pause briefly before starting the DDNS process.

3. **Operation**
   - The script checks your public IP address using the specified `ip_check_url`.
   - It compares the current IP with the IP in the Cloudflare DNS A record.
   - If they differ, the script updates the DNS record with the new IP.
   - If no update is needed, it logs the current IP and waits for the next check (based on `update_interval`).
   - The script runs continuously until stopped with `Ctrl+C`.

4. **Stopping the Script**
   Press `Ctrl+C` to stop the script. It will display a message confirming termination.

## Example Output

```
=====================================
     Cloudflare DDNS Updater
     Created by: Sören - AMD_Ryzen753
=====================================
Domain: your.domain.com
Update Interval: 300 seconds
=====================================
Press Ctrl+C to stop the script
=====================================
Starting DDNS for your.domain.com
No update needed. Current IP: 203.0.113.1
```

## Troubleshooting

- **Configuration Errors**: If any required configuration (`api_key`, `zone_id`, `domain`) is missing or still set to a placeholder (e.g., `your_global_api_key`), the script will exit with an error message.
- **API Errors**: Ensure your API key has permissions to edit DNS records and that the Zone ID and domain are correct.
- **Network Issues**: If the script cannot fetch your public IP or connect to Cloudflare, it will retry after 60 seconds.
- **Dependencies**: Ensure the `requests` library is installed.

## Contributing

Feel free to fork this repository, make improvements, and submit pull requests. For issues or suggestions, open an issue on GitHub.

## License

This project is licensed under the MIT License. See the `LICENSE` file for details.

## Acknowledgments

- Built with Python and the Cloudflare API.
- Thanks to the open-source community for tools like `requests` and services like `ipify`.
