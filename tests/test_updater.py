"""Unit tests for cloudflare-ddns-updater.py (no network access required)."""

import importlib.util
import os
import pathlib
import sys
import unittest
from unittest import mock

SCRIPT = pathlib.Path(__file__).resolve().parent.parent / "cloudflare-ddns-updater.py"
spec = importlib.util.spec_from_file_location("cf_ddns", SCRIPT)
cf_ddns = importlib.util.module_from_spec(spec)
sys.modules["cf_ddns"] = cf_ddns
spec.loader.exec_module(cf_ddns)


def response(json_data=None, text="", status=200):
    resp = mock.Mock()
    resp.status_code = status
    resp.text = text
    resp.json.return_value = json_data
    resp.raise_for_status.return_value = None
    return resp


def ok(result):
    return response({"success": True, "errors": [], "result": result})


def make_config(**overrides):
    values = dict(api_token="token", zone_id="zone", records=["home.example.com"])
    values.update(overrides)
    return cf_ddns.Config(**values)


class PublicIpTests(unittest.TestCase):
    def test_falls_back_to_next_service(self):
        session = mock.Mock()
        session.get.side_effect = [
            cf_ddns.requests.ConnectionError("down"),
            response(text="<html>oops</html>"),
            response(text="93.184.216.34\n"),
        ]
        ip = cf_ddns.get_public_ip(session, ["a", "b", "c"], 4, 5)
        self.assertEqual(ip, "93.184.216.34")
        self.assertEqual(session.get.call_count, 3)

    def test_rejects_wrong_version_and_private(self):
        session = mock.Mock()
        session.get.side_effect = [response(text="2001:db8::1"), response(text="192.168.1.2")]
        self.assertIsNone(cf_ddns.get_public_ip(session, ["a", "b"], 4, 5))


class UpdaterTests(unittest.TestCase):
    def setUp(self):
        self.session = mock.Mock()
        self.session.headers = {}

    def updater(self, **overrides):
        return cf_ddns.Updater(make_config(**overrides), self.session)

    def test_updates_changed_record_with_patch(self):
        record = {"id": "rec1", "content": "198.51.100.1", "proxied": True}
        self.session.request.side_effect = [ok([record]), ok(record)]
        self.updater().sync_record("home.example.com", "A", "203.0.113.7")

        method, url = self.session.request.call_args_list[1][0]
        self.assertEqual(method, "PATCH")
        self.assertTrue(url.endswith("/zones/zone/dns_records/rec1"))
        self.assertEqual(self.session.request.call_args_list[1][1]["json"],
                         {"content": "203.0.113.7"})

    def test_skips_api_when_ip_unchanged(self):
        record = {"id": "rec1", "content": "203.0.113.7"}
        self.session.request.side_effect = [ok([record])]
        updater = self.updater()
        updater.sync_record("home.example.com", "A", "203.0.113.7")
        updater.sync_record("home.example.com", "A", "203.0.113.7")
        self.assertEqual(self.session.request.call_count, 1)

    def test_missing_record_is_error_unless_create_missing(self):
        self.session.request.side_effect = [ok([])]
        with self.assertRaises(cf_ddns.CloudflareError):
            self.updater().sync_record("home.example.com", "A", "203.0.113.7")

        self.session.request.side_effect = [ok([]), ok({"id": "new"})]
        self.updater(create_missing=True).sync_record("home.example.com", "AAAA", "2001:db8::1")
        method, _ = self.session.request.call_args[0]
        self.assertEqual(method, "POST")
        self.assertEqual(self.session.request.call_args[1]["json"]["type"], "AAAA")

    def test_api_error_is_reported(self):
        self.session.request.return_value = response(
            {"success": False, "errors": [{"code": 9109, "message": "Invalid access token"}]},
            status=403)
        with self.assertRaisesRegex(cf_ddns.CloudflareError, "9109"):
            self.updater().sync_record("home.example.com", "A", "203.0.113.7")

    def test_zone_auto_detection(self):
        self.session.request.side_effect = [ok([]), ok([{"id": "zone-x"}])]
        cloudflare = self.updater(zone_id="").cloudflare
        self.assertEqual(cloudflare.zone_id_for("home.example.com"), "zone-x")
        params = [c[1]["params"]["name"] for c in self.session.request.call_args_list]
        self.assertEqual(params, ["home.example.com", "example.com"])

    def test_auth_headers(self):
        self.updater()
        self.assertEqual(self.session.headers["Authorization"], "Bearer token")
        self.session.headers = {}
        self.updater(api_token="", api_key="key", email="me@example.com")
        self.assertEqual(self.session.headers["X-Auth-Key"], "key")
        self.assertNotIn("Authorization", self.session.headers)


class ConfigTests(unittest.TestCase):
    def args(self, *argv):
        return cf_ddns.parse_args(list(argv))

    def test_placeholders_are_rejected(self):
        errors = make_config(records=["your.domain.com"], zone_id="your_zone_id").validate()
        self.assertEqual(len(errors), 2)

    def test_env_and_cli_priority(self):
        env = {"CF_API_TOKEN": "t", "CF_RECORDS": "a.example.com, b.example.com",
               "CF_INTERVAL": "600", "CF_IPV6": "true"}
        with mock.patch.dict(os.environ, env, clear=True):
            config = cf_ddns.load_config(self.args("--interval", "120"))
        self.assertEqual(config.records, ["a.example.com", "b.example.com"])
        self.assertEqual(config.interval, 120)
        self.assertTrue(config.ipv6)
        self.assertEqual(config.validate(), [])

    def test_legacy_config_file(self):
        import json
        import tempfile
        legacy = {"api_key": "tok", "zone_id": "z", "domain": "home.example.com",
                  "update_interval": 300, "ip_check_url": "https://api.ipify.org"}
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
            json.dump(legacy, fh)
        try:
            with mock.patch.dict(os.environ, {}, clear=True):
                config = cf_ddns.load_config(self.args("--config", fh.name))
        finally:
            os.unlink(fh.name)
        self.assertEqual(config.api_token, "tok")
        self.assertEqual(config.records, ["home.example.com"])
        self.assertEqual(config.ipv4_services, ["https://api.ipify.org"])
        self.assertEqual(config.validate(), [])


if __name__ == "__main__":
    unittest.main()
