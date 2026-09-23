"""可选内核集成测试：设置 MIHOMO_BIN 后运行，只连接 127.0.0.1。

不读取真实订阅、不修改系统服务。配置、日志和 provider 文件均放在临时目录。
规则使用内联合成数据；这些测试验证解析和组装，不验证外网节点连通性。
"""
import json
import os
import re
import secrets
import socket
import subprocess
import tempfile
import threading
import time
import unittest
from contextlib import ExitStack
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import URLError
from urllib.request import ProxyHandler, Request, build_opener

import yaml

from tests.fixtures import INFO_NAMES, NAMES, REGIONS, apply_party_patch, dummy_nodes
from tests.flclash import NODE, apply_flclash_script
from tools.validate import load_config
from tools.render import LINUX_ENTRY, merge_mapping, render_linux

CORE = os.environ.get("MIHOMO_BIN")


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@unittest.skipUnless(CORE, "设置 MIHOMO_BIN 可启用离线内核测试")
class CoreTests(unittest.TestCase):
    def run_case(self, names, from_provider=False, provider_names=None, target="party", http_provider=False):
        with tempfile.TemporaryDirectory(prefix="mihomo-configs-test-") as directory, ExitStack() as cleanup:
            root = Path(directory)
            patch = load_config()
            base = {"proxies": dummy_nodes(names)}
            all_names = list(names)
            if from_provider:
                base["proxies"] = []
                supplied = names if provider_names is None else provider_names
                if provider_names is not None:
                    base["proxies"] = dummy_nodes(names)
                    all_names += supplied
                (root / "fixture-provider.yaml").write_text(
                    yaml.safe_dump({"proxies": dummy_nodes(supplied)}, allow_unicode=True), encoding="utf-8")
                base["proxy-providers"] = {
                    "any-provider-name": {
                        "type": "file", "path": "./fixture-provider.yaml",
                        "health-check": {"enable": False},
                    }
                }
                if http_provider:
                    payload = (root / "fixture-provider.yaml").read_bytes()

                    class Handler(BaseHTTPRequestHandler):
                        def do_GET(self):
                            self.send_response(200)
                            self.send_header("Content-Type", "application/yaml")
                            self.send_header("Content-Length", str(len(payload)))
                            self.end_headers()
                            self.wfile.write(payload)

                        def log_message(self, *args):
                            pass

                    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
                    thread = threading.Thread(target=server.serve_forever, daemon=True)
                    thread.start()
                    cleanup.callback(thread.join, 5)
                    cleanup.callback(server.server_close)
                    cleanup.callback(server.shutdown)
                    base["proxy-providers"]["any-provider-name"] = {
                        "type": "http", "url": f"http://127.0.0.1:{server.server_port}/nodes.yaml",
                        "path": "./downloaded-provider.yaml", "interval": 3600,
                    }
            if target == "linux-entry":
                config = merge_mapping(load_config(LINUX_ENTRY), base)
            elif target == "linux-render":
                config = render_linux(base)
            elif target == "flclash":
                config, = apply_flclash_script([base])
            else:
                config = apply_party_patch(base, patch)
            for provider in config.get("proxy-providers", {}).values():
                provider["health-check"] = {"enable": False}
            for group in config["proxy-groups"]:
                if "url" in group:
                    group["url"] = "http://127.0.0.1:9/generate_204"
                    group["interval"] = 0
                    group["lazy"] = True
            # 无 GitHub 下载、无 geodata 下载；仍由内核实际解析 classical 数据。
            config["rule-providers"] = {
                name: {"type": "inline", "behavior": provider["behavior"], "payload": [
                    "DOMAIN,example.invalid", "IP-CIDR,192.0.2.0/24,no-resolve",
                ]}
                for name, provider in config["rule-providers"].items()
            }
            port = free_port()
            secret = secrets.token_hex(16)
            config.update({
                "mixed-port": 0, "allow-lan": False, "bind-address": "127.0.0.1",
                "external-controller": f"127.0.0.1:{port}", "secret": secret,
                "dns": {"enable": False}, "tun": {"enable": False},
                "log-level": "warning", "mode": "rule",
            })
            (root / "config.yaml").write_text(yaml.safe_dump(config, allow_unicode=True), encoding="utf-8")
            check = subprocess.run([CORE, "-t", "-d", str(root)], capture_output=True, text=True, timeout=20)
            self.assertEqual(check.returncode, 0, check.stdout + check.stderr)
            opener = build_opener(ProxyHandler({}))  # 不使用用户的代理环境变量

            def get(endpoint):
                request = Request(f"http://127.0.0.1:{port}/{endpoint}",
                                  headers={"Authorization": f"Bearer {secret}"})
                with opener.open(request, timeout=1) as response:
                    return json.load(response)

            with (root / "runtime.log").open("w", encoding="utf-8") as log:
                process = subprocess.Popen([CORE, "-d", str(root)], stdout=log, stderr=subprocess.STDOUT)
                try:
                    deadline = time.monotonic() + 12
                    while True:
                        try:
                            state = get("proxies")["proxies"]
                            if "自动选择" in state:
                                break
                        except (URLError, OSError, ValueError):
                            pass
                        if process.poll() is not None or time.monotonic() > deadline:
                            self.fail((root / "runtime.log").read_text(encoding="utf-8"))
                        time.sleep(0.1)

                    definitions = {g["name"]: g for g in patch["proxy-groups"]}
                    expected = {n for n in all_names if not re.search(definitions["自动选择"]["exclude-filter"], n)}
                    # file provider 初始化可能晚于 API 监听，等候其成员列表加载完毕。
                    while set(state["自动选择"]["all"]) != (expected or {"REJECT"}) and time.monotonic() < deadline:
                        time.sleep(0.1)
                        state = get("proxies")["proxies"]
                    self.assertEqual(set(state["自动选择"]["all"]), expected or {"REJECT"},
                                     (root / "runtime.log").read_text(encoding="utf-8"))
                    self.assertEqual(set(state["故障转移"]["all"]), expected or {"REJECT"})
                    for region in REGIONS:
                        group = definitions[region]
                        hits = {n for n in expected if re.search(group["filter"], n)}
                        self.assertEqual(set(state[region]["all"]), hits or {"REJECT"}, region)
                    for name in ("节点选择", "OpenAI", "电报消息", "油管视频", "奈飞视频"):
                        self.assertTrue(expected <= set(state[name]["all"]))
                        self.assertFalse(set(INFO_NAMES) & set(state[name]["all"]))
                    providers = get("providers/rules")["providers"]
                    self.assertEqual(set(providers), set(patch["rule-providers!"]))
                    self.assertTrue(all(p["ruleCount"] == 2 for p in providers.values()))
                finally:
                    if process.poll() is None:
                        process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=5)

    def test_inline_nodes_multiple_naming_styles(self):
        self.run_case(NAMES + INFO_NAMES)

    def test_arbitrary_file_provider_name(self):
        self.run_case(NAMES + INFO_NAMES, from_provider=True)

    def test_inline_and_provider_nodes_combined(self):
        self.run_case(["US01", "未知地区线路 01"], from_provider=True,
                      provider_names=["Taipei 01", "SG01"] + INFO_NAMES)

    def test_unknown_region_is_available_in_auto_and_manual(self):
        self.run_case(["未知地区线路 01", "Australia 01"])

    def test_all_nodes_filtered_is_reject_not_direct(self):
        self.run_case(INFO_NAMES)

    def test_empty_subscription_is_reject_not_direct(self):
        self.run_case([])

    @unittest.skipUnless(NODE, "FlClash 内核测试需要 Node.js")
    def test_flclash_script_with_inline_and_provider_nodes(self):
        self.run_case(["US01", "未知地区线路 01"], from_provider=True,
                      provider_names=NAMES + INFO_NAMES, target="flclash")

    @unittest.skipUnless(NODE, "FlClash 内核测试需要 Node.js")
    def test_flclash_script_empty_subscription_fails_closed(self):
        self.run_case([], target="flclash")

    @unittest.skipUnless(NODE, "FlClash 内核测试需要 Node.js")
    def test_flclash_script_all_nodes_filtered(self):
        self.run_case(INFO_NAMES, target="flclash")

    def test_linux_native_entry_accepts_inline_nodes(self):
        self.run_case(NAMES + INFO_NAMES, target="linux-entry")

    def test_linux_native_entry_without_nodes_fails_closed(self):
        self.run_case([], target="linux-entry")

    def test_linux_renderer_file_provider(self):
        self.run_case(NAMES + INFO_NAMES, from_provider=True, target="linux-render")

    def test_linux_renderer_http_provider_download(self):
        self.run_case(NAMES + INFO_NAMES, from_provider=True, target="linux-render", http_provider=True)

    def test_linux_renderer_mixed_sources(self):
        self.run_case(["US01", "未知地区线路 01"], from_provider=True,
                      provider_names=["Taipei 01", "SG01"] + INFO_NAMES, target="linux-render")

    def test_linux_renderer_unknown_region(self):
        self.run_case(["未知地区线路 01", "Australia 01"], target="linux-render")

    def test_linux_renderer_all_nodes_filtered(self):
        self.run_case(INFO_NAMES, target="linux-render")


if __name__ == "__main__":
    unittest.main()
