#!/usr/bin/env python3
"""从同一策略源构建 Party / Linux 入口；本地私有合成不访问网络、不加载服务。"""
from __future__ import annotations

import argparse
import os
import re
import tempfile
from copy import deepcopy
from pathlib import Path
from urllib.parse import urlsplit

import yaml

from tools.validate import BUILTINS, CONFIG, ROOT, load_config, validate

POLICY = ROOT / "templates/policy.yaml"
LINUX_BASE = ROOT / "templates/linux-base.yaml"
PARTY_ENTRY = CONFIG
LINUX_ENTRY = ROOT / "dist/mihomo-linux.yaml"
PRIVATE_KEYS = {
    "proxies", "proxy-providers", "mixed-port", "allow-lan", "bind-address",
    "external-controller", "secret", "authentication", "dns", "tun", "ipv6",
    "log-level", "find-process-mode", "tcp-concurrent", "unified-delay",
    "keep-alive-interval", "hosts", "profile",
}


class ConfigError(ValueError):
    """面向用户的错误；不得包含私有 YAML 内容或节点凭据。"""


class PlainDumper(yaml.SafeDumper):
    def ignore_aliases(self, data):
        return True


def dump_yaml(data: dict, header: str = "") -> str:
    return header + yaml.dump(data, Dumper=PlainDumper, allow_unicode=True, sort_keys=False, width=120)


def merge_mapping(base: dict, patch: dict) -> dict:
    """本地映射递归合并，列表整体替换；不执行客户端特有操作符。"""
    result = deepcopy(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = merge_mapping(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


def render_party(policy: dict | None = None) -> dict:
    data = deepcopy(load_config(POLICY) if policy is None else policy)
    if set(data) != {"profile", "proxy-groups", "rule-providers", "rules"}:
        raise ConfigError("共用策略源的顶层结构不正确")
    party = {("rule-providers!" if key == "rule-providers" else key): value for key, value in data.items()}
    validate(party)
    return party


def render_linux(private: dict | None = None) -> dict:
    policy = load_config(POLICY)
    render_party(policy)  # 先校验共用策略，不依赖已生成的 Party 入口。
    config = merge_mapping(load_config(LINUX_BASE), policy)
    if private is None:
        return config
    if not isinstance(private, dict) or not set(private) <= PRIVATE_KEYS:
        raise ConfigError("私有文件只接受节点、proxy-providers 和支持的本地运行参数；不能覆盖策略/规则")
    for key in ("dns", "tun", "hosts", "profile"):
        if key in private and not isinstance(private[key], dict):
            raise ConfigError("本地 DNS/TUN/hosts/profile 设置必须是映射")
    config = merge_mapping(config, private)
    nodes = config.get("proxies")
    providers = config.get("proxy-providers")
    if not isinstance(nodes, list) or not isinstance(providers, dict):
        raise ConfigError("proxies 必须是列表，proxy-providers 必须是映射")
    if not nodes and not providers:
        raise ConfigError("私有文件未提供任何节点或 proxy-providers")
    reserved = BUILTINS | {"GLOBAL"} | {g["name"] for g in config["proxy-groups"]}
    seen = set()

    def check_nodes(items):
        if not isinstance(items, list):
            raise ConfigError("节点或 inline provider 的 payload 必须是列表")
        for node in items:
            if not isinstance(node, dict) or not isinstance(node.get("name"), str) or not node["name"].strip():
                raise ConfigError("节点缺少有效名称")
            if not isinstance(node.get("type"), str) or not node["type"]:
                raise ConfigError("节点缺少协议类型")
            name = node["name"]
            if name in reserved or name in seen:
                raise ConfigError("节点名称重复，或与策略组/内置名称冲突；请在私有文件中改名")
            seen.add(name)

    check_nodes(nodes)
    defaults = {
        "enable": True, "url": "https://www.gstatic.com/generate_204", "interval": 300,
        "timeout": 5000, "expected-status": 204, "lazy": True,
    }
    cache_paths = {p["path"] for p in config["rule-providers"].values()}
    for name, provider in providers.items():
        if not isinstance(name, str) or not name.strip() or name in reserved:
            raise ConfigError("provider 名称无效或与策略组/内置名称冲突")
        if not isinstance(provider, dict) or provider.get("type") not in {"http", "file", "inline"}:
            raise ConfigError("provider 必须为 http、file 或 inline 类型")
        if provider["type"] == "http":
            url = provider.get("url")
            if not isinstance(url, str):
                raise ConfigError("HTTP provider 缺少订阅地址")
            try:
                parsed = urlsplit(url)
                host = parsed.hostname
            except ValueError:
                raise ConfigError("HTTP provider 订阅地址格式错误") from None
            if parsed.scheme not in {"https", "http"} or not host:
                raise ConfigError("HTTP provider 需要有效的 HTTP/HTTPS 订阅地址")
            if host == "invalid" or host.endswith(".invalid"):
                raise ConfigError("请先在仓库外的私有文件中替换示例订阅地址")
            provider.setdefault("interval", 3600)
            # 首次订阅下载不能默认走尚未加载的自身节点；显式设置仍由用户决定。
            provider.setdefault("proxy", "DIRECT")
        if provider["type"] == "file" and not provider.get("path"):
            raise ConfigError("文件型 provider 缺少 path（相对于 mihomo -d 工作目录）")
        if provider["type"] == "inline":
            check_nodes(provider.get("payload"))
        if "path" in provider:
            path = provider["path"]
            if not isinstance(path, str) or not path:
                raise ConfigError("provider 缓存路径必须是非空字符串")
            normalized = os.path.normpath(path)
            if normalized in {os.path.normpath(p) for p in cache_paths}:
                raise ConfigError("provider 缓存路径重复或与规则缓存冲突")
            cache_paths.add(path)
        health = provider.get("health-check", {})
        if not isinstance(health, dict):
            raise ConfigError("provider health-check 必须是映射")
        provider["health-check"] = merge_mapping(defaults, health)

    controller = config.get("external-controller")
    if not isinstance(controller, str):
        raise ConfigError("external-controller 必须是字符串")
    if controller:
        if not re.fullmatch(r"(?:127\.0\.0\.1|\[::1\]):[0-9]+", controller):
            raise ConfigError("生成器仅允许控制 API 监听回环地址")
        secret = config.get("secret")
        if not isinstance(secret, str) or len(secret.strip()) < 16:
            raise ConfigError("启用控制 API 时请在私有文件设置至少 16 字符的随机 secret")
    return config


def public_entries() -> dict[Path, str]:
    common = "# 自动生成；修改 templates/ 中的源文件后运行 python -m tools.render build。\n"
    return {
        PARTY_ENTRY: dump_yaml(render_party(), common + "# mihomo-party YAML 覆写入口；不是完整内核配置。\n\n"),
        LINUX_ENTRY: dump_yaml(render_linux(), common + "# Linux mihomo 原生配置入口；无节点，使用前需接入本地私有订阅。\n\n"),
    }


def build(check=False) -> None:
    entries = public_entries()
    if check:
        stale = [path.name for path, text in entries.items()
                 if not path.is_file() or path.read_text(encoding="utf-8") != text]
        if stale:
            raise ConfigError("生成入口与策略源不一致；运行 python -m tools.render build")
        return
    for path, text in entries.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")


def outside_repo(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    if resolved.is_relative_to(ROOT.resolve()):
        raise ConfigError("私有输入和生成配置必须位于仓库外，避免误提交凭据")
    return resolved


def write_private(output: Path, text: str, force=False) -> None:
    if output.expanduser().is_symlink():
        raise ConfigError("拒绝写入符号链接，请指定实际输出文件")
    target = outside_repo(output)
    if target.exists() and not force:
        raise ConfigError("输出文件已存在；先备份，确认后使用 --force")
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".mihomo-", suffix=".yaml", dir=target.parent)
    try:
        # mkstemp 在 POSIX 上以 0600 创建，不会先写出可公开读取的凭据。
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        if force:
            os.replace(temporary, target)
        else:
            # 原子发布且不覆盖已存在文件，包括检查后被其他进程创建的文件。
            os.link(temporary, target)
    finally:
        Path(temporary).unlink(missing_ok=True)


def generate_private(private_path: Path, output: Path, force=False) -> None:
    source = outside_repo(private_path)
    target = outside_repo(output)
    if source == target:
        raise ConfigError("输出文件不能覆盖私有输入文件")
    try:
        private = load_config(source)
    except (ValueError, TypeError, yaml.YAMLError):
        # YAML 解析异常可能带原始行（含 URL/token），不要输出异常正文。
        raise ConfigError("私有 YAML 解析失败；请本地检查格式、重复键和顶层映射") from None
    config = render_linux(private)
    write_private(output, dump_yaml(config, "# 本地生成，可能含订阅及凭据；禁止提交到公开仓库。\n"), force=force)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    public = commands.add_parser("build", help="构建两个不含凭据的公共入口")
    public.add_argument("--check", action="store_true", help="仅检查生成物是否与源文件一致")
    linux = commands.add_parser("linux", help="从仓库外的私有文件生成完整 Linux 配置")
    linux.add_argument("--private", type=Path, required=True)
    linux.add_argument("--output", type=Path, required=True)
    linux.add_argument("--force", action="store_true", help="允许原子替换已存在的输出；不会自动加载服务")
    args = parser.parse_args()
    try:
        if args.command == "build":
            build(check=args.check)
            print("两个公共入口校验一致" if args.check else "已构建 Party 和 Linux 公共入口")
        else:
            generate_private(args.private, args.output, force=args.force)
            print("已生成本地 Linux 配置；未联网、未修改服务。请先运行 mihomo -t 校验再加载。")
    except ConfigError as error:
        parser.exit(1, f"失败：{error}\n")
    except (OSError, ValueError, KeyError, TypeError, yaml.YAMLError):
        parser.exit(1, "失败：无法读取、生成或写入配置；请检查文件权限及格式。私有内容未输出。\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
