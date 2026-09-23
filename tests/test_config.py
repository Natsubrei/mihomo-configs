import re
import unittest
from copy import deepcopy

import yaml

from tests.fixtures import INFO_NAMES, NAMES, REGIONS, apply_party_patch, dummy_nodes
from tools.validate import UniqueKeyLoader, load_config, validate


class OverrideTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = load_config()
        cls.groups = {group["name"]: group for group in cls.config["proxy-groups"]}

    def test_structure(self):
        validate(deepcopy(self.config))

    def test_duplicate_yaml_keys_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "重复 YAML 键"):
            yaml.load("name: first\nname: second\n", Loader=UniqueKeyLoader)

    def test_yaml_anchor_overrides_are_legal(self):
        data = yaml.load("base: &base {a: 1}\nchild: {<<: *base, a: 2}\n", Loader=UniqueKeyLoader)
        self.assertEqual(data["child"]["a"], 2)

    def test_region_aliases(self):
        samples = {
            "香港节点": ["香港 01", "🇭🇰 01", "HK01", "HongKong2 SS", "Hong Kong 01", "Hong-Kong 01"],
            "台湾节点": ["台湾 01", "台灣 01", "🇹🇼 01", "TW-01", "Taiwan 01", "Taipei 01"],
            "日本节点": ["日本 01", "東京 01", "🇯🇵 01", "JP01", "Tokyo2 SS", "Osaka 01"],
            "狮城节点": ["新加坡 01", "獅城 01", "🇸🇬 01", "SG01", "sg-01", "Singapore2 SS"],
            "美国节点": ["美国 01", "美國 01", "🇺🇸 01", "US-01", "USA01", "California V2", "United States 01"],
            "韩国节点": ["韩国 01", "韓國 01", "🇰🇷 01", "KR01", "KOR-01", "Incheon V2", "Seoul 01"],
            "德国节点": ["德国 01", "德國 01", "🇩🇪 01", "DE01", "GER-01", "Frankfurt SS", "Germany 01"],
        }
        for group, names in samples.items():
            for name in names:
                with self.subTest(group=group, node=name):
                    self.assertRegex(name, self.groups[group]["filter"])

    def test_short_country_codes_do_not_match_inside_words(self):
        for group, name in [
            ("美国节点", "Australia 01"), ("美国节点", "RUSH 01"),
            ("美国节点", "USABLE 01"), ("德国节点", "Sweden 01"),
            ("香港节点", "Earthkeeper 01"), ("台湾节点", "Network 01"),
        ]:
            with self.subTest(group=group, node=name):
                self.assertNotRegex(name, self.groups[group]["filter"])

    def test_info_entries_are_excluded_consistently(self):
        for group in self.groups.values():
            if group.get("include-all"):
                for name in INFO_NAMES:
                    with self.subTest(group=group["name"], node=name):
                        self.assertRegex(name, group["exclude-filter"])

    def test_normal_nodes_are_not_excluded_by_broad_words(self):
        pattern = self.groups["节点选择"]["exclude-filter"]
        for name in NAMES:
            with self.subTest(node=name):
                self.assertIsNone(re.search(pattern, name))

    def test_regions_do_not_capture_info_entries(self):
        for name in INFO_NAMES:
            for region in REGIONS:
                self.assertNotRegex(name, self.groups[region]["filter"])

    def test_all_dynamic_groups_fail_closed(self):
        for group in self.groups.values():
            if group.get("include-all"):
                self.assertEqual(group["empty-fallback"], "REJECT")

    def test_failover_probes_often_enough_to_skip_dead_nodes(self):
        failover = self.groups["故障转移"]
        self.assertEqual(failover["type"], "fallback")
        self.assertEqual(failover["interval"], 60)
        self.assertEqual(failover["timeout"], 3000)
        self.assertEqual(failover["max-failed-times"], 1)
        self.assertFalse(failover["lazy"])

    def test_default_selector_uses_sticky_urltest(self):
        self.assertEqual(self.groups["节点选择"]["proxies"][0], "自动选择")
        auto = self.groups["自动选择"]
        self.assertEqual(auto["type"], "url-test")
        self.assertEqual(auto["tolerance"], 200)
        self.assertEqual(auto["timeout"], 3000)
        self.assertEqual(auto["max-failed-times"], 1)

    def test_url_test_lazy_only_for_active_path(self):
        self.assertFalse(self.groups["自动选择"]["lazy"])
        for name in REGIONS:
            with self.subTest(group=name):
                self.assertTrue(self.groups[name]["lazy"])

    def test_cycle_is_rejected(self):
        broken = deepcopy(self.config)
        broken["proxy-groups"][1]["proxies"] = ["节点选择"]
        with self.assertRaisesRegex(ValueError, "循环引用"):
            validate(broken)

    def test_unknown_group_is_rejected(self):
        broken = deepcopy(self.config)
        broken["proxy-groups"][0]["proxies"].append("不存在的分组")
        with self.assertRaisesRegex(ValueError, "引用不存在"):
            validate(broken)

    def test_mistyped_classical_ruleset_is_rejected(self):
        broken = deepcopy(self.config)
        broken["rule-providers!"]["ChinaDomain"]["behavior"] = "domain"
        with self.assertRaisesRegex(ValueError, "classical/text"):
            validate(broken)

    def test_provider_cache_paths_are_unique(self):
        paths = [p["path"] for p in self.config["rule-providers!"].values()]
        self.assertEqual(len(paths), len(set(paths)))

    def test_patch_preserves_nodes_providers_and_client_network_settings(self):
        base = {
            "proxies": dummy_nodes(NAMES),
            "proxy-providers": {"arbitrary-provider-name": {"type": "file", "path": "./nodes.yaml"}},
            "dns": {"enable": True, "nameserver": ["system"]},
            "tun": {"enable": True}, "mixed-port": 23456, "ipv6": True,
            "allow-lan": False, "find-process-mode": "strict",
            "profile": {"store-fake-ip": False},
            "proxy-groups": [{"name": "旧分组", "type": "select", "proxies": ["DIRECT"]}],
            "rules": ["MATCH,旧分组"],
            "rule-providers": {"old": {"proxy": "旧分组"}},
        }
        snapshot = deepcopy(base)
        result = apply_party_patch(base, self.config)
        self.assertEqual(base, snapshot)  # 测试工具也不能修改输入
        for key in ("proxies", "proxy-providers", "dns", "tun", "mixed-port", "ipv6", "allow-lan", "find-process-mode"):
            self.assertEqual(result[key], base[key])
        self.assertEqual(result["profile"], {"store-fake-ip": False, "store-selected": True})
        self.assertNotIn("old", result["rule-providers"])
        self.assertNotIn("rule-providers!", result)
        self.assertEqual(result["rules"], self.config["rules"])
        self.assertEqual(result["proxy-groups"], self.config["proxy-groups"])

    def test_subscription_refresh_changes_nodes_not_overrides(self):
        for names in [["US01"], ["Singapore 02", "日本 03"], ["未知地区线路 01"]]:
            result = apply_party_patch({"proxies": dummy_nodes(names)}, self.config)
            self.assertEqual([p["name"] for p in result["proxies"]], names)
            self.assertEqual(result["proxy-groups"], self.config["proxy-groups"])


if __name__ == "__main__":
    unittest.main()
