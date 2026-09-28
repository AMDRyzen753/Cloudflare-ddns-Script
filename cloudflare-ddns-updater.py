#!/usr/bin/env python3
"""Cloudflare DDNS Updater.

Keeps one or more Cloudflare DNS records (A and/or AAAA) in sync with the
current public IP address of this machine.

Configuration is read (in increasing order of priority) from:
  1. built-in defaults
  2. a JSON config file (--config / CF_DDNS_CONFIG)
  3. environment variables (CF_API_TOKEN, CF_ZONE_ID, CF_RECORDS, ...)
  4. command line arguments

Created by: Sören - AMD_Ryzen753
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import logging
import os
import signal
import sys
import threading
from dataclasses import dataclass, field
from typing import Dict, List, Optional

try:
    import requests
except ImportError:  # pragma: no cover - depends on the environment
    sys.exit("Error: the 'requests' library is required. Install it with: pip install requests")

__version__ = "2.0.0"

API_BASE = "https://api.cloudflare.com/client/v4"
USER_AGENT = f"cloudflare-ddns-updater/{__version__}"

DEFAULT_IPV4_SERVICES = [
    "https://api.ipify.org",
    "https://ipv4.icanhazip.com",
    "https://v4.ident.me",
]
DEFAULT_IPV6_SERVICES = [
    "https://api6.ipify.org",
    "https://ipv6.icanhazip.com",
    "https://v6.ident.me",
]

PLACEHOLDERS = {"your_api_token", "your_global_api_key", "your_zone_id", "your.domain.com"}

log = logging.getLogger("cf-ddns")


class CloudflareError(Exception):
    """Raised when the Cloudflare API reports an error."""


# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #
@dataclass
class Config:
    api_token: str = ""
    api_key: str = ""
    email: str = ""
    zone_id: str = ""
    records: List[str] = field(default_factory=list)
    ipv4: bool = True
    ipv6: bool = False
    interval: int = 300
    ttl: int = 1  # 1 = "automatic" in Cloudflare
    proxied: Optional[bool] = None  # None = keep the existing setting
    create_missing: bool = False
    timeout: int = 10
    ipv4_services: List[str] = field(default_factory=lambda: list(DEFAULT_IPV4_SERVICES))
    ipv6_services: List[str] = field(default_factory=lambda: list(DEFAULT_IPV6_SERVICES))

    def validate(self) -> List[str]:
        errors = []
        if not self.api_token and not (self.api_key and self.email):
            errors.append("an API token (CF_API_TOKEN) or a Global API key + e-mail "
                          "(CF_API_KEY + CF_EMAIL) is required")
        if not self.records:
            errors.append("at least one DNS record name is required (CF_RECORDS / --record)")
        if not (self.ipv4 or self.ipv6):
            errors.append("IPv4 and IPv6 are both disabled - nothing to do")
        if self.interval < 30:
            errors.append("the update interval must be at least 30 seconds")
        if self.ttl != 1 and not 60 <= self.ttl <= 86400:
            errors.append("ttl must be 1 (automatic) or between 60 and 86400")
        for name, value in (("api_token", self.api_token), ("api_key", self.api_key),
                            ("zone_id", self.zone_id)):
            if value in PLACEHOLDERS:
                errors.append(f"{name} still contains the placeholder value '{value}'")
        for record in self.records:
            if record in PLACEHOLDERS:
                errors.append(f"record '{record}' is still the placeholder value")
        return errors


def _to_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _to_list(value) -> List[str]:
    if isinstance(value, str):
        value = value.split(",")
    return [str(v).strip() for v in value if str(v).strip()]


# Maps config keys to (environment variable, converter).
_FIELDS = {
    "api_token": ("CF_API_TOKEN", str),
    "api_key": ("CF_API_KEY", str),
    "email": ("CF_EMAIL", str),
    "zone_id": ("CF_ZONE_ID", str),
    "records": ("CF_RECORDS", _to_list),
    "ipv4": ("CF_IPV4", _to_bool),
    "ipv6": ("CF_IPV6", _to_bool),
    "interval": ("CF_INTERVAL", int),
    "ttl": ("CF_TTL", int),
    "proxied": ("CF_PROXIED", _to_bool),
    "create_missing": ("CF_CREATE_MISSING", _to_bool),
    "timeout": ("CF_TIMEOUT", int),
    "ipv4_services": ("CF_IPV4_SERVICES", _to_list),
    "ipv6_services": ("CF_IPV6_SERVICES", _to_list),
}

# Keys from the original script's CONFIG dict, kept for backwards compatibility.
_LEGACY_KEYS = {"domain": "records", "update_interval": "interval"}


def load_config(args: argparse.Namespace) -> Config:
    values: Dict[str, object] = {}

    config_path = args.config or os.environ.get("CF_DDNS_CONFIG")
    if config_path:
        try:
            with open(config_path, encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError) as exc:
            raise SystemExit(f"Error: cannot read config file '{config_path}': {exc}")
        for key, value in data.items():
            key = _LEGACY_KEYS.get(key, key)
            if key == "ip_check_url":
                key, value = "ipv4_services", [value]
            if key not in _FIELDS:
                log.warning("Ignoring unknown config key '%s'", key)
                continue
            values[key] = _FIELDS[key][1](value)

    for key, (env, convert) in _FIELDS.items():
        if env in os.environ and os.environ[env] != "":
            try:
                values[key] = convert(os.environ[env])
            except ValueError:
                raise SystemExit(f"Error: invalid value for {env}: {os.environ[env]!r}")

    cli = {
        "api_token": args.token, "zone_id": args.zone_id, "records": args.record or None,
        "interval": args.interval, "ttl": args.ttl, "proxied": args.proxied,
        "create_missing": args.create_missing or None,
    }
    values.update({k: v for k, v in cli.items() if v is not None})
    if args.ipv6_only:
        values.update(ipv4=False, ipv6=True)
    elif args.ipv6:
        values["ipv6"] = True

    # The original script sent "api_key" as a Bearer token, so a key without
    # an e-mail address is really an API token.
    if values.get("api_key") and not values.get("email") and not values.get("api_token"):
        log.warning("'api_key' without 'email' is treated as an API token - "
                    "please rename it to 'api_token'")
        values["api_token"] = values.pop("api_key")

    return Config(**values)


# --------------------------------------------------------------------------- #
# Public IP detection
# --------------------------------------------------------------------------- #
def get_public_ip(session: requests.Session, services: List[str], version: int,
                  timeout: int) -> Optional[str]:
    """Return the public IP of the given version, trying each service in turn."""
    for url in services:
        try:
            response = session.get(url, timeout=timeout)
            response.raise_for_status()
            ip = ipaddress.ip_address(response.text.strip())
        except requests.RequestException as exc:
            log.debug("IP service %s failed: %s", url, exc)
            continue
        except ValueError:
            log.debug("IP service %s returned an invalid address", url)
            continue
        if ip.version != version:
            log.debug("IP service %s returned IPv%d, expected IPv%d", url, ip.version, version)
            continue
        if not ip.is_global:
            log.warning("IP service %s returned non-public address %s", url, ip)
            continue
        return str(ip)
    log.error("Could not determine public IPv%d address from any service", version)
    return None


# --------------------------------------------------------------------------- #
# Cloudflare API
# --------------------------------------------------------------------------- #
class Cloudflare:
    def __init__(self, config: Config, session: requests.Session):
        self.config = config
        self.session = session
        if config.api_token:
            session.headers["Authorization"] = f"Bearer {config.api_token}"
        else:
            session.headers["X-Auth-Email"] = config.email
            session.headers["X-Auth-Key"] = config.api_key
        self._zone_cache: Dict[str, str] = {}

    def _request(self, method: str, path: str, **kwargs):
        try:
            response = self.session.request(method, f"{API_BASE}{path}",
                                            timeout=self.config.timeout, **kwargs)
        except requests.RequestException as exc:
            raise CloudflareError(f"request failed: {exc}") from exc
        try:
            payload = response.json()
        except ValueError:
            raise CloudflareError(f"HTTP {response.status_code}: invalid JSON response")
        if not payload.get("success", False):
            errors = "; ".join(f"[{e.get('code')}] {e.get('message')}"
                               for e in payload.get("errors", [])) or "unknown error"
            raise CloudflareError(f"HTTP {response.status_code}: {errors}")
        return payload["result"]

    def verify_credentials(self) -> None:
        if self.config.api_token:
            self._request("GET", "/user/tokens/verify")
        else:
            self._request("GET", "/user")

    def zone_id_for(self, record_name: str) -> str:
        """Return the zone ID for a record, auto-detecting it if not configured."""
        if self.config.zone_id:
            return self.config.zone_id
        if record_name in self._zone_cache:
            return self._zone_cache[record_name]
        labels = record_name.split(".")
        for i in range(len(labels) - 1):
            candidate = ".".join(labels[i:])
            zones = self._request("GET", "/zones", params={"name": candidate})
            if zones:
                self._zone_cache[record_name] = zones[0]["id"]
                log.debug("Detected zone %s (%s) for %s", candidate, zones[0]["id"], record_name)
                return zones[0]["id"]
        raise CloudflareError(f"no zone found for '{record_name}' - set CF_ZONE_ID "
                              "or give the token Zone:Read permission")

    def get_record(self, zone_id: str, name: str, record_type: str) -> Optional[dict]:
        records = self._request("GET", f"/zones/{zone_id}/dns_records",
                                params={"name": name, "type": record_type})
        if len(records) > 1:
            log.warning("%d %s records found for %s, only the first one is updated",
                        len(records), record_type, name)
        return records[0] if records else None

    def update_record(self, zone_id: str, record: dict, ip: str) -> dict:
        # PATCH only the fields we want to change, so comments, tags and
        # other settings configured in the dashboard are preserved.
        data = {"content": ip}
        if self.config.proxied is not None:
            data["proxied"] = self.config.proxied
        return self._request("PATCH", f"/zones/{zone_id}/dns_records/{record['id']}", json=data)

    def create_record(self, zone_id: str, name: str, record_type: str, ip: str) -> dict:
        data = {
            "type": record_type,
            "name": name,
            "content": ip,
            "ttl": self.config.ttl,
            "proxied": bool(self.config.proxied),
        }
        return self._request("POST", f"/zones/{zone_id}/dns_records", json=data)


# --------------------------------------------------------------------------- #
# Updater
# --------------------------------------------------------------------------- #
class Updater:
    def __init__(self, config: Config, session: Optional[requests.Session] = None):
        self.config = config
        self.session = session or requests.Session()
        self.session.headers["User-Agent"] = USER_AGENT
        self.cloudflare = Cloudflare(config, self.session)
        # Last IP successfully synced per (record, type); avoids needless API calls.
        self._synced: Dict[tuple, str] = {}

    def current_ips(self) -> Dict[str, Optional[str]]:
        ips = {}
        if self.config.ipv4:
            ips["A"] = get_public_ip(self.session, self.config.ipv4_services, 4,
                                     self.config.timeout)
        if self.config.ipv6:
            ips["AAAA"] = get_public_ip(self.session, self.config.ipv6_services, 6,
                                        self.config.timeout)
        return ips

    def sync_record(self, name: str, record_type: str, ip: str) -> None:
        key = (name, record_type)
        if self._synced.get(key) == ip:
            log.debug("%s %s already points to %s", record_type, name, ip)
            return

        zone_id = self.cloudflare.zone_id_for(name)
        record = self.cloudflare.get_record(zone_id, name, record_type)
        if record is None:
            if not self.config.create_missing:
                raise CloudflareError(f"{record_type} record '{name}' does not exist "
                                      "(use --create-missing to create it)")
            self.cloudflare.create_record(zone_id, name, record_type, ip)
            log.info("Created %s record %s -> %s", record_type, name, ip)
        elif record["content"] != ip or (self.config.proxied is not None
                                         and record.get("proxied") != self.config.proxied):
            self.cloudflare.update_record(zone_id, record, ip)
            log.info("Updated %s record %s: %s -> %s", record_type, name, record["content"], ip)
        else:
            log.info("%s record %s is up to date (%s)", record_type, name, ip)
        self._synced[key] = ip

    def run_once(self) -> bool:
        """Run a single update cycle. Returns True if everything succeeded."""
        ok = True
        for record_type, ip in self.current_ips().items():
            if ip is None:
                ok = False
                continue
            for name in self.config.records:
                try:
                    self.sync_record(name, record_type, ip)
                except CloudflareError as exc:
                    log.error("Failed to sync %s record %s: %s", record_type, name, exc)
                    ok = False
        return ok

    def run_forever(self, stop: threading.Event) -> None:
        retry_delay = 30
        while not stop.is_set():
            if self.run_once():
                delay = self.config.interval
                retry_delay = 30
            else:
                # Retry sooner on errors, with exponential backoff capped at the interval.
                delay = min(retry_delay, self.config.interval)
                retry_delay = min(retry_delay * 2, self.config.interval)
                log.info("Retrying in %d seconds", delay)
            stop.wait(delay)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def display_startscreen(config: Config) -> None:
    line = "=" * 45
    print(line)
    print(f"     Cloudflare DDNS Updater v{__version__}")
    print("     Created by: Sören - AMD_Ryzen753")
    print(line)
    print(f"Records:         {', '.join(config.records)}")
    types = [t for t, enabled in (("IPv4 (A)", config.ipv4), ("IPv6 (AAAA)", config.ipv6)) if enabled]
    print(f"Protocols:       {', '.join(types)}")
    print(f"Update interval: {config.interval} seconds")
    print(f"Authentication:  {'API token' if config.api_token else 'Global API key'}")
    print(line)
    print("Press Ctrl+C to stop the script")
    print(line, flush=True)


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Keep Cloudflare DNS records in sync with your public IP address.",
        epilog="Settings can also be provided via environment variables or a JSON "
               "config file - see README.md.")
    parser.add_argument("-c", "--config", help="path to a JSON config file")
    parser.add_argument("-r", "--record", action="append",
                        help="DNS record to update (can be given multiple times)")
    parser.add_argument("--token", help="Cloudflare API token (prefer CF_API_TOKEN)")
    parser.add_argument("--zone-id", help="Cloudflare zone ID (auto-detected if omitted)")
    parser.add_argument("-i", "--interval", type=int, help="seconds between checks")
    parser.add_argument("--ttl", type=int, help="TTL for newly created records (1 = auto)")
    proxied = parser.add_mutually_exclusive_group()
    proxied.add_argument("--proxied", dest="proxied", action="store_true", default=None,
                         help="route records through Cloudflare's proxy")
    proxied.add_argument("--no-proxied", dest="proxied", action="store_false",
                         help="make records DNS only")
    parser.add_argument("--create-missing", action="store_true",
                        help="create records that do not exist yet")
    parser.add_argument("-6", "--ipv6", action="store_true", help="also update AAAA records")
    parser.add_argument("--ipv6-only", action="store_true", help="only update AAAA records")
    parser.add_argument("-1", "--once", action="store_true",
                        help="run a single update and exit (for cron / systemd timers)")
    parser.add_argument("-q", "--quiet", action="store_true", help="hide the start screen")
    parser.add_argument("-v", "--verbose", action="store_true", help="enable debug output")
    parser.add_argument("--log-file", help="also write log output to this file")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser.parse_args(argv)


def setup_logging(verbose: bool, log_file: Optional[str]) -> None:
    handlers: List[logging.Handler] = [logging.StreamHandler()]
    if log_file:
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s",
                        datefmt="%Y-%m-%d %H:%M:%S", handlers=handlers)
    # Keep urllib3 quiet unless explicitly debugging.
    logging.getLogger("urllib3").setLevel(logging.DEBUG if verbose else logging.WARNING)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    setup_logging(args.verbose, args.log_file)
    config = load_config(args)

    errors = config.validate()
    if errors:
        for error in errors:
            log.error("Configuration error: %s", error)
        return 2

    if not args.quiet and not args.once:
        display_startscreen(config)

    updater = Updater(config)
    try:
        updater.cloudflare.verify_credentials()
    except CloudflareError as exc:
        log.error("Cloudflare credentials are invalid: %s", exc)
        return 2

    if args.once:
        return 0 if updater.run_once() else 1

    stop = threading.Event()

    def handle_signal(signum, _frame):
        log.info("Received %s, shutting down", signal.Signals(signum).name)
        stop.set()

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    log.info("Starting DDNS for %s", ", ".join(config.records))
    updater.run_forever(stop)
    log.info("DDNS updater stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
