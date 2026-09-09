import contextlib
import io
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

import yaml

from tests.fixtures import dummy_nodes
from tools.render import (
    ConfigError, LINUX_ENTRY, POLICY, ROOT, build, dump_yaml, generate_private,
    load_config, public_entries, render_linux, render_party, write_private,
)


class RenderTests(unittest.TestCase):
    def test_public_entries_are_current(self):
        build(check=True)

    def test_both_entries_share_one_policy(self):
        source = load_config(POLICY)
        party = render_party()
        linux = load_config(LINUX_ENTRY)
        for key in ("profile", "proxy-groups", "rules"):
            self.assertEqual(party[key], source[key])
            self.assertEqual(linux[key], source[key])
        self.assertEqual(party["rule-providers!"], source["rule-providers"])
        self.assertEqual(linux["rule-providers"], source["rule-providers"])
        self.assertNotIn("rule-providers!", linux)
        self.assertFalse(any(key.endswith("!") for key in linux))

    def test_public_native_template_is_safe_and_has_no_nodes(self):
        config = load_config(LINUX_ENTRY)
        self.assertEqual(config["bind-address"], "127.0.0.1")
        self.assertFalse(config["allow-lan"])
        self.assertFalse(config["tun"]["enable"])
        self.assertEqual(config["external-controller"], "")
        self.assertEqual(config["proxies"], [])
        self.assertEqual(config["proxy-providers"], {})
        self.assertNotIn("secret", config)

    def test_http_provider_and_runtime_options_preserved(self):
        private = {
            "mixed-port": 17890,
            "dns": {"enable": True, "nameserver": ["system"]},
            "proxy-providers": {"my-provider": {
                "type": "http", "url": "https://example.com/subscription",
                "path": "./providers/example.yaml", "proxy": "DIRECT",
                "health-check": {"lazy": False},
            }},
        }
        before = deepcopy(private)
        result = render_linux(private)
        self.assertEqual(private, before)
        self.assertEqual(result["mixed-port"], 17890)
        self.assertEqual(result["dns"], private["dns"])
        provider = result["proxy-providers"]["my-provider"]
        self.assertEqual(provider["url"], private["proxy-providers"]["my-provider"]["url"])
        self.assertEqual(provider["interval"], 3600)
        self.assertTrue(provider["health-check"]["enable"])
        self.assertFalse(provider["health-check"]["lazy"])
        self.assertEqual(provider["health-check"]["expected-status"], 204)

    def test_http_provider_bootstrap_defaults_to_direct(self):
        result = render_linux({"proxy-providers": {"subscription": {
            "type": "http", "url": "https://example.com/subscription",
        }}})
        self.assertEqual(result["proxy-providers"]["subscription"]["proxy"], "DIRECT")
        result = render_linux({"proxy-providers": {"subscription": {
            "type": "http", "url": "https://example.com/subscription", "proxy": "节点选择",
        }}})
        self.assertEqual(result["proxy-providers"]["subscription"]["proxy"], "节点选择")

    def test_inline_and_file_providers(self):
        private = {
            "proxies": dummy_nodes(["US01"]),
            "proxy-providers": {
                "from-file": {"type": "file", "path": "providers/nodes.yaml"},
                "embedded": {"type": "inline", "payload": dummy_nodes(["JP01"])},
            },
        }
        result = render_linux(private)
        self.assertEqual(result["proxies"], private["proxies"])
        self.assertEqual(result["proxy-providers"]["embedded"]["payload"], private["proxy-providers"]["embedded"]["payload"])
        self.assertTrue(result["proxy-providers"]["from-file"]["health-check"]["enable"])

    def test_explicitly_disabled_provider_healthcheck_is_preserved(self):
        result = render_linux({"proxy-providers": {"local-file": {
            "type": "file", "path": "providers/nodes.yaml", "health-check": {"enable": False},
        }}})
        self.assertFalse(result["proxy-providers"]["local-file"]["health-check"]["enable"])

    def test_private_input_cannot_replace_policy(self):
        for key in ("rules", "proxy-groups", "rule-providers", "rule-providers!"):
            with self.subTest(key=key), self.assertRaises(ConfigError):
                render_linux({"proxies": dummy_nodes(["US01"]), key: {}})

    def test_empty_private_input_is_rejected(self):
        with self.assertRaisesRegex(ConfigError, "未提供"):
            render_linux({})

    def test_example_subscription_cannot_be_used_unchanged(self):
        with self.assertRaisesRegex(ConfigError, "替换示例"):
            render_linux(load_config(ROOT / "examples/linux-private.yaml"))

    def test_duplicate_or_reserved_node_names_are_rejected(self):
        for names in (["US01", "US01"], ["DIRECT"], ["节点选择"]):
            with self.subTest(names=names), self.assertRaises(ConfigError):
                render_linux({"proxies": dummy_nodes(names)})

    def test_provider_names_cannot_collide_with_groups(self):
        with self.assertRaises(ConfigError):
            render_linux({"proxy-providers": {"节点选择": {"type": "file", "path": "nodes.yaml"}}})

    def test_normalized_cache_paths_cannot_collide(self):
        for second in ("providers/./nodes.yaml", "./ruleset/generic/ChinaDomain.list"):
            private = {"proxy-providers": {
                "first": {"type": "file", "path": "./providers/nodes.yaml"},
                "second": {"type": "file", "path": second},
            }}
            with self.subTest(path=second), self.assertRaisesRegex(ConfigError, "缓存路径"):
                render_linux(private)

    def test_controller_requires_loopback_and_secret(self):
        for opts in (
            {"external-controller": "0.0.0.0:9090", "secret": "synthetic-secret-for-test"},
            {"external-controller": "127.0.0.1:9090"},
            {"external-controller": "127.0.0.1:9090", "secret": "short"},
        ):
            with self.subTest(opts=opts), self.assertRaises(ConfigError):
                render_linux({"proxies": dummy_nodes(["JP01"]), **opts})
        result = render_linux({"proxies": dummy_nodes(["JP01"]),
                               "external-controller": "127.0.0.1:9090", "secret": "synthetic-secret-for-test"})
        self.assertEqual(result["external-controller"], "127.0.0.1:9090")

    def test_private_output_is_atomic_private_and_not_overwritten_by_default(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "generated/config.yaml"
            write_private(output, "first\n")
            self.assertEqual(output.read_text(), "first\n")
            if os.name == "posix":
                self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o600)
                self.assertEqual(stat.S_IMODE(output.parent.stat().st_mode), 0o700)
            with self.assertRaises(ConfigError):
                write_private(output, "second\n")
            self.assertEqual(output.read_text(), "first\n")
            write_private(output, "second\n", force=True)
            self.assertEqual(output.read_text(), "second\n")
            self.assertFalse(list(output.parent.glob(".mihomo-*")))

    def test_failed_atomic_publish_keeps_old_output_and_cleans_temp(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "config.yaml"
            with patch("tools.render.os.link", side_effect=FileExistsError):
                with self.assertRaises(FileExistsError):
                    write_private(output, "synthetic-private-data\n")
            self.assertFalse(output.exists())
            self.assertFalse(list(output.parent.glob(".mihomo-*")))

    def test_output_cannot_be_inside_repository(self):
        with self.assertRaisesRegex(ConfigError, "仓库外"):
            write_private(ROOT / "local/config.yaml", "must-not-be-written\n")

    def test_input_cannot_be_inside_repository(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ConfigError, "仓库外"):
                generate_private(ROOT / "examples/linux-private.yaml", Path(directory) / "config.yaml")

    def test_input_cannot_be_overwritten_even_with_force(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "private.yaml"
            source.write_text("proxies: []\n")
            with self.assertRaisesRegex(ConfigError, "覆盖私有输入"):
                generate_private(source, source, force=True)
            self.assertEqual(source.read_text(), "proxies: []\n")

    @unittest.skipUnless(os.name == "posix", "符号链接权限行为只在 POSIX 测试")
    def test_output_symlink_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "target.yaml"
            target.write_text("keep\n")
            link = Path(directory) / "config.yaml"
            link.symlink_to(target)
            with self.assertRaisesRegex(ConfigError, "符号链接"):
                write_private(link, "replacement\n", force=True)
            self.assertEqual(target.read_text(), "keep\n")

    def test_private_yaml_parse_errors_do_not_echo_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "private.yaml"
            source.write_text('proxies: ["synthetic-private-marker"\n', encoding="utf-8")
            with self.assertRaises(ConfigError) as result:
                generate_private(source, Path(directory) / "config.yaml")
            self.assertNotIn("synthetic-private-marker", str(result.exception))
            self.assertFalse((Path(directory) / "config.yaml").exists())

    def test_linux_cli_works_from_repo_with_private_input(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "private.yaml"
            output = Path(directory) / "runtime/config.yaml"
            source.write_text(dump_yaml({"proxies": dummy_nodes(["JP01", "US01"])}), encoding="utf-8")
            result = subprocess.run([
                sys.executable, "-m", "tools.render", "linux", "--private", str(source), "--output", str(output),
            ], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=20,
                env={**os.environ, "PYTHONIOENCODING": "utf-8"})
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            native = load_config(output)
            self.assertNotIn("rule-providers!", native)
            self.assertEqual(native["proxies"], dummy_nodes(["JP01", "US01"]))

    def test_build_check_does_not_rewrite_files(self):
        snapshots = {path: path.read_bytes() for path in public_entries()}
        with contextlib.redirect_stdout(io.StringIO()):
            build(check=True)
        self.assertEqual(snapshots, {path: path.read_bytes() for path in snapshots})


if __name__ == "__main__":
    unittest.main()
