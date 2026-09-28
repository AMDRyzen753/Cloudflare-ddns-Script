# Cloudflare DDNS Python Script

This Python script keeps one or more Cloudflare DNS records in sync with your current public IP address, effectively creating a Dynamic DNS (DDNS) solution. Created by Sören - AMD_Ryzen753.

## Features

- Updates **A (IPv4)** and/or **AAAA (IPv6)** records
- Updates **multiple records** at once (e.g. `example.com` and `home.example.com`)
- Supports **API tokens** (recommended) and the legacy **Global API Key**
- **Zone ID auto-detection** – the zone ID is optional
- Only changes the IP address – **TTL, proxy status, comments and tags set in the dashboard are preserved**
- Several **fallback IP services**; responses are validated so a broken service never ends up in your DNS
- Only calls the Cloudflare API when your IP actually changed
- Configuration via **environment variables, a JSON file or command line** – no need to edit the script
- **Continuous mode** with exponential backoff on errors, or **`--once`** for cron / systemd timers
- Clean shutdown on `Ctrl+C` and `SIGTERM`, timestamped logging, optional log file

## Prerequisites

- **Python 3.7+**
- A **Cloudflare account** with a domain configured
- A **Cloudflare API token** with the permission `Zone → DNS → Edit`
  (add `Zone → Zone → Read` if you want the zone ID to be detected automatically)
- The `requests` library:
  ```bash
  pip install -r requirements.txt
  ```

### Creating an API token

1. Open the Cloudflare dashboard → **My Profile → API Tokens → Create Token**.
2. Use the template **"Edit zone DNS"** and select your zone.
3. Copy the token – it is only shown once.

> The Global API Key still works (`CF_API_KEY` + `CF_EMAIL`), but it grants full access to your account. An API token limited to DNS is much safer.

## Installation

```bash
git clone https://github.com/AMDRyzen753/Cloudflare-ddns-Script.git
cd Cloudflare-ddns-Script
pip install -r requirements.txt
```

## Configuration

Settings are read in this order – later sources override earlier ones:

1. Built-in defaults
2. JSON config file (`--config config.json` or `CF_DDNS_CONFIG`)
3. Environment variables
4. Command line arguments

| Config key       | Environment variable | CLI option               | Default | Description |
|------------------|----------------------|--------------------------|---------|-------------|
| `api_token`      | `CF_API_TOKEN`       | `--token`                | –       | Cloudflare API token (recommended) |
| `api_key`        | `CF_API_KEY`         | –                        | –       | Global API Key (requires `email`) |
| `email`          | `CF_EMAIL`           | –                        | –       | Account e-mail for the Global API Key |
| `zone_id`        | `CF_ZONE_ID`         | `--zone-id`              | auto    | Zone ID; detected automatically if empty |
| `records`        | `CF_RECORDS`         | `-r/--record` (repeat)   | –       | Records to update, comma separated in env |
| `ipv4`           | `CF_IPV4`            | –                        | `true`  | Update A records |
| `ipv6`           | `CF_IPV6`            | `-6/--ipv6`, `--ipv6-only` | `false` | Update AAAA records |
| `interval`       | `CF_INTERVAL`        | `-i/--interval`          | `300`   | Seconds between checks (min. 30) |
| `ttl`            | `CF_TTL`             | `--ttl`                  | `1`     | TTL for newly created records (`1` = auto) |
| `proxied`        | `CF_PROXIED`         | `--proxied/--no-proxied` | keep    | Force the proxy status; unset keeps the current one |
| `create_missing` | `CF_CREATE_MISSING`  | `--create-missing`       | `false` | Create records that do not exist yet |
| `timeout`        | `CF_TIMEOUT`         | –                        | `10`    | HTTP timeout in seconds |
| `ipv4_services`  | `CF_IPV4_SERVICES`   | –                        | ipify, icanhazip, ident.me | Services used to detect the IPv4 address |
| `ipv6_services`  | `CF_IPV6_SERVICES`   | –                        | ipify, icanhazip, ident.me | Services used to detect the IPv6 address |

### Example: environment variables

```bash
export CF_API_TOKEN="your_api_token"
export CF_RECORDS="home.example.com,vpn.example.com"
python3 cloudflare-ddns-updater.py
```

### Example: config file

```bash
cp config.example.json config.json   # config.json is git-ignored
nano config.json
python3 cloudflare-ddns-updater.py --config config.json
```

Config files from version 1 of the script (`api_key`, `domain`, `update_interval`, `ip_check_url`) are still understood.

> Keep your token secret: `chmod 600 config.json` and never commit it.

## Usage

```bash
# Run continuously (default)
python3 cloudflare-ddns-updater.py -r home.example.com

# Update IPv4 and IPv6, create the records if they are missing
python3 cloudflare-ddns-updater.py -r home.example.com --ipv6 --create-missing

# Run once and exit – for cron or a systemd timer
python3 cloudflare-ddns-updater.py --once

# All options
python3 cloudflare-ddns-updater.py --help
```

Exit codes: `0` = success, `1` = an update failed (`--once`), `2` = configuration or authentication error.

### Running with cron

```cron
*/5 * * * * CF_API_TOKEN=xxx CF_RECORDS=home.example.com /usr/bin/python3 /opt/cloudflare-ddns/cloudflare-ddns-updater.py --once --log-file /var/log/cloudflare-ddns.log
```

### Running as a systemd service

```bash
sudo mkdir -p /opt/cloudflare-ddns
sudo cp cloudflare-ddns-updater.py /opt/cloudflare-ddns/
printf 'CF_API_TOKEN=xxx\nCF_RECORDS=home.example.com\n' | sudo tee /etc/cloudflare-ddns.env
sudo chmod 600 /etc/cloudflare-ddns.env
sudo cp cloudflare-ddns.service /etc/systemd/system/
sudo systemctl enable --now cloudflare-ddns
journalctl -u cloudflare-ddns -f
```

## Example Output

```
=============================================
     Cloudflare DDNS Updater v2.0.0
     Created by: Sören - AMD_Ryzen753
=============================================
Records:         home.example.com
Protocols:       IPv4 (A)
Update interval: 300 seconds
Authentication:  API token
=============================================
Press Ctrl+C to stop the script
=============================================
2026-09-28 17:20:00 [INFO] Starting DDNS for home.example.com
2026-09-28 17:20:01 [INFO] Updated A record home.example.com: 198.51.100.4 -> 198.51.100.7
```

## Troubleshooting

- **Configuration errors**: Missing values or leftover placeholders (e.g. `your_api_token`) are reported at startup and the script exits with code `2`.
- **`Cloudflare credentials are invalid`**: Check the token and its permissions. A Global API Key must be used with `CF_API_KEY` + `CF_EMAIL`, not as a token.
- **`record ... does not exist`**: Create the record in the dashboard or run with `--create-missing`.
- **`no zone found`**: Set `CF_ZONE_ID` or give the token the `Zone → Zone → Read` permission.
- **Network issues**: Failed checks are retried after 30 s, doubling up to the update interval.
- **More details**: Run with `--verbose`.

## Development

```bash
python3 -m unittest discover -s tests
```

## Contributing

Feel free to fork this repository, make improvements, and submit pull requests. For issues or suggestions, open an issue on GitHub.

## License

This project is licensed under the MIT License.

## Acknowledgments

- Built with Python and the Cloudflare API.
- Thanks to the open-source community for tools like `requests` and services like `ipify`, `icanhazip` and `ident.me`.
