import os
import subprocess
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from tests.fixtures import dummy_nodes
from tests.flclash import NODE, apply_flclash_script
from tools.render import (
    ConfigError, FLCLASH_ENTRY, POLICY, ROOT, build, load_config, render_flclash,
)


class FlClashBuildTests(unittest.TestCase):
    def test_render_is_deterministic_and_does_not_mutate_source(self):
        source = load_config(POLICY)
        before = deepcopy(source)
        self.assertEqual(render_flclash(source), render_flclash())
        self.assertEqual(source, before)
        self.assertEqual(FLCLASH_ENTRY.read_text(encoding="utf-8"), render_flclash())

    def test_invalid_policy_is_rejected_before_rendering(self):
        source = load_config(POLICY)
        source["proxy-groups"][0]["proxies"].append("不存在的组")
        with self.assertRaisesRegex(ValueError, "引用不存在"):
            render_flclash(source)

    def test_dedicated_build_and_check_only_touch_script(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "dist/flclash.js"
            with patch("tools.render.FLCLASH_ENTRY", output):
                with patch("tools.render.public_entries", side_effect=AssertionError("不应构建其他入口")):
                    with self.assertRaises(ConfigError):
                        build(check=True, flclash_only=True)
                    self.assertFalse(output.exists())
                    build(flclash_only=True)
                    self.assertEqual(output.read_text(encoding="utf-8"), render_flclash())
                    build(check=True, flclash_only=True)
                    output.write_text("stale\n", encoding="utf-8")
                    with self.assertRaises(ConfigError):
                        build(check=True, flclash_only=True)
                    self.assertEqual(output.read_text(encoding="utf-8"), "stale\n")

    def test_flclash_cli_check(self):
        result = subprocess.run(
            [sys.executable, "-m", "tools.render", "flclash", "--check"],
            cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=20,
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("FlClash", result.stdout)


@unittest.skipUnless(NODE, "安装 Node.js 可执行真实 FlClash 脚本测试")
class FlClashScriptTests(unittest.TestCase):
    def test_script_replaces_only_policy_and_preserves_subscription(self):
        base = {
            "proxies": dummy_nodes(["HK01", "US01"]),
            "proxy-providers": {"arbitrary": {
                "type": "http", "url": "https://example.invalid/subscription",
                "path": "providers/arbitrary.yaml", "health-check": {"enable": False},
            }},
            "dns": {"enable": True, "nameserver": ["system"]},
            "tun": {"enable": True}, "ipv6": True, "mixed-port": 23456,
            "allow-lan": False, "external-controller": "127.0.0.1:9090",
            "profile": {"store-selected": False, "store-fake-ip": True},
            "hosts": {"example.invalid": "127.0.0.1"},
            "sniffer": {"enable": True},
            "proxy-groups": [{"name": "旧组", "type": "select", "proxies": ["DIRECT"]}],
            "rule-providers": {"old": {"type": "file", "path": "old.yaml"}},
            "rules": ["MATCH,旧组"],
        }
        result, = apply_flclash_script([base])
        policy = load_config(POLICY)
        self.assertEqual(set(result), set(base))
        for key in base:
            with self.subTest(key=key):
                expected = policy[key] if key in {"proxy-groups", "rule-providers", "rules"} else base[key]
                self.assertEqual(result[key], expected)
        self.assertNotIn("rule-providers!", result)
        self.assertNotIn("old", result["rule-providers"])

    def test_refresh_and_repeated_application_preserve_current_nodes(self):
        sources = [{"proxies": dummy_nodes(names)} for names in [
            ["US01"], ["SG01", "日本 03"], ["未知地区线路 01"], [],
        ]]
        sources += [{}, {"proxy-providers": {"file": {"type": "file", "path": "nodes.yaml"}}}]
        results = apply_flclash_script(sources)
        policy = load_config(POLICY)
        for source, result in zip(sources, results):
            self.assertEqual(result, {**source, **{key: policy[key] for key in (
                "proxy-groups", "rule-providers", "rules",
            )}})
        self.assertEqual(apply_flclash_script(results), results)

    def test_serialization_preserves_regex_and_special_characters(self):
        policy = load_config(POLICY)
        policy["proxy-groups"][0]["exclude-filter"] += '|"quote"|\\\\|\u2028|\u2029'
        result, = apply_flclash_script([{}], render_flclash(policy))
        self.assertEqual(result["proxy-groups"], policy["proxy-groups"])


if __name__ == "__main__":
    unittest.main()
