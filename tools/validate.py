#!/usr/bin/env python3
"""离线检查 Party 入口；双入口一致性由 tools.render build --check 校验。"""
from __future__ import annotations

import argparse
import re
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "dist/mihomo-party.yaml"
BUILTINS = {"DIRECT", "REJECT", "REJECT-DROP", "PASS", "COMPATIBLE"}


class UniqueKeyLoader(yaml.SafeLoader):
    """允许 YAML merge anchors 的显式覆盖，但拒绝重复书写的映射键。"""

    def construct_mapping(self, node, deep=False):
        seen = set()
        for key_node, _ in node.value:
            if key_node.tag == "tag:yaml.org,2002:merge":
                continue
            key = self.construct_object(key_node, deep=deep)
            if key in seen:
                raise ValueError(f"重复 YAML 键: {key}")
            seen.add(key)
        return super().construct_mapping(node, deep=deep)


def load_config(path: Path = CONFIG) -> dict:
    with path.open(encoding="utf-8") as source:
        data = yaml.load(source, Loader=UniqueKeyLoader)
    if not isinstance(data, dict):
        raise ValueError("顶层必须是 YAML 映射")
    return data


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def validate(data: dict) -> None:
    # 此函数只检查 Party 覆写；Linux 原生入口另由生成工具和内核测试校验。
    allowed = {"profile", "proxy-groups", "rule-providers!", "rules"}
    require(set(data) == allowed, "覆写顶层键不符合约定（可能混入完整订阅或运行配置）")
    require(data["profile"] == {"store-selected": True}, "profile 仅应保存策略选择")
    groups = data["proxy-groups"]
    require(isinstance(groups, list) and bool(groups), "缺少策略组")
    names = [g["name"] for g in groups]
    require(len(names) == len(set(names)), "策略组重名")
    require(not set(names) & BUILTINS, "策略组不得覆盖内置代理")
    require("GLOBAL" not in names, "使用内核默认 GLOBAL，不覆写内置组")
    available = set(names) | BUILTINS
    edges: dict[str, list[str]] = {}
    for group in groups:
        name = group["name"]
        require(group["type"] in {"select", "fallback", "url-test"}, f"不支持的组类型: {name}")
        members = group.get("proxies", [])
        require(group.get("include-all") or members, f"空的静态策略组: {name}")
        require(all(m in available for m in members), f"策略组引用不存在: {name}")
        edges[name] = [m for m in members if m in names]
        require(not group.get("use"), f"不得绑定特定 provider 名称: {name}")
        if group.get("include-all"):
            require(group.get("empty-fallback") == "REJECT", f"空组必须拒绝而非直连: {name}")
            require(bool(group.get("exclude-filter")), f"缺少信息条目排除: {name}")
        for field in ("filter", "exclude-filter"):
            if field in group:
                re.compile(group[field])
        if group["type"] in {"fallback", "url-test"}:
            require(group.get("url", "").startswith("https://"), f"测速必须使用 HTTPS: {name}")
            require(0 < group.get("interval", 0) <= 300, f"测速间隔应在 1~300 秒: {name}")
            require(group.get("expected-status") == 204, f"应校验 HTTP 204: {name}")
            require(0 < group.get("timeout", 0) <= 10000, f"应设置有限测速超时: {name}")

    visited: set[str] = set()
    active: set[str] = set()

    def visit(name: str) -> None:
        require(name not in active, f"策略组循环引用: {name}")
        if name in visited:
            return
        active.add(name)
        for member in edges[name]:
            visit(member)
        active.remove(name)
        visited.add(name)

    for name in names:
        visit(name)

    providers = data["rule-providers!"]
    require(isinstance(providers, dict) and bool(providers), "缺少规则集")
    paths = set()
    for name, provider in providers.items():
        require(provider["type"] == "http", f"公开模板只引用 HTTP 规则集: {name}")
        require(provider["behavior"] == "classical" and provider["format"] == "text",
                f"ACL4SSR .list 必须按 classical/text 解析: {name}")
        require(provider["proxy"] == "规则更新", f"规则集必须显式选择下载策略: {name}")
        url = urlsplit(provider["url"])
        require(url.scheme == "https" and url.netloc == "raw.githubusercontent.com",
                f"规则源必须为 GitHub HTTPS 原站: {name}")
        require(url.path.startswith("/ACL4SSR/ACL4SSR/master/Clash/") and url.path.endswith(".list"),
                f"未知规则路径: {name}")
        require(not url.query and not url.fragment, f"公开 URL 不应带 token/query: {name}")
        path = PurePosixPath(provider["path"])
        require(not path.is_absolute() and ".." not in path.parts and "\\" not in provider["path"],
                f"规则缓存应使用安全相对路径: {name}")
        require(path not in paths, f"规则缓存路径重复: {name}")
        paths.add(path)

    rules = data["rules"]
    require(isinstance(rules, list) and rules[-1] == "MATCH,漏网之鱼", "缺少最终规则")
    used = set()
    for rule in rules[:-1]:
        fields = rule.split(",")
        require(len(fields) == 3 and fields[0] == "RULE-SET", f"未知规则结构: {rule}")
        require(fields[1] in providers and fields[2] in available, f"规则引用不存在: {rule}")
        used.add(fields[1])
    require(used == set(providers), "存在未使用的规则集")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path, nargs="?", default=CONFIG)
    args = parser.parse_args()
    try:
        data = load_config(args.path)
        validate(data)
    except (ValueError, KeyError, TypeError, OSError, yaml.YAMLError) as error:
        parser.exit(1, f"校验失败: {error}\n")
    print(f"校验通过：{len(data['proxy-groups'])} 个策略组，"
          f"{len(data['rule-providers!'])} 个规则集，{len(data['rules'])} 条分流规则")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
