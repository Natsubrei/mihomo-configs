# Linux mihomo 原生入口

前提：已安装 mihomo，运行 `mihomo -v` 确认版本。未安装时，可从 [官方 Releases](https://github.com/MetaCubeX/mihomo/releases) 获取适合系统架构的内核并校验下载文件；本项目测试版本为 v1.19.30，不自动安装内核。

入口文件：[`dist/mihomo-linux.yaml`](https://raw.githubusercontent.com/Natsubrei/mihomo-configs/main/dist/mihomo-linux.yaml)。它是**标准 mihomo 配置**，不是客户端覆写，不包含 `rule-providers!` 等特殊语法。

与 mihomo-party 入口使用同一份 [`templates/policy.yaml`](../templates/policy.yaml)。公开模板没有私人节点；使用前需接入自己的 `proxies` / `proxy-providers`。没有候选时代理组会拒绝连接，显式直连规则仍可工作。

## 两种使用方式

### 方式 A：直接下载原生模板

适合不想安装 Python、愿意自己维护配置的用户：

1. 下载 `dist/mihomo-linux.yaml`，在**仓库外**保存为自己的 mihomo 工作目录下的 `config.yaml`。
2. 在本地副本里填写 `proxies` 或 `proxy-providers`，按需要调整 DNS 和监听设置。
3. 用 `mihomo -t -d <工作目录> -f <配置文件>` 校验后再运行。

不要把带订阅的文件传回 GitHub。再次下载公开模板会覆盖本地修改；长期维护推荐方式 B。

### 方式 B：私有文件 + 本地生成工具（推荐）

订阅地址只写入本地私有文件，公共策略可以随仓库更新。

```text
templates/ + 仓库外的 private.yaml
    → 生成工具 → 仓库外的 config.yaml
    → mihomo 运行时下载节点与规则 → 工作目录下的 providers/、ruleset/generic/
```

生成工具需要 Python 3.11+、PyYAML；**mihomo 运行时不需要 Python**。以下操作不会替你修改或重启已有系统服务。

#### 1. 准备依赖

先下载并解压本仓库（或使用 Git 克隆），进入 `mihomo-configs` 根目录，然后运行：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

#### 2. 创建仓库外的私有文件

```bash
install -d -m 700 "$HOME/.config/mihomo"
# 已有 private.yaml 时不要重复复制覆盖它。
cp -n examples/linux-private.yaml "$HOME/.config/mihomo/private.yaml"
chmod 600 "$HOME/.config/mihomo/private.yaml"
```

用本地编辑器打开 `~/.config/mihomo/private.yaml`，把示例地址换成自己的订阅。不要修改仓库里的 `examples/linux-private.yaml`，也不要把真实 URL 直接放进命令行或提交记录。

示例使用 HTTP provider，订阅更新间隔 3600 秒。缺少的 `health-check` 字段会由工具补齐；明确指定的值会保留，包括 `enable: false`。HTTP provider 未指定下载策略时默认 `proxy: DIRECT`，避免首次启动依赖尚未下载的自身节点。

如果订阅地址本身直连不可达，需要一个独立可用的下载路径（例如已有的其他节点），或先下载节点文件后使用文件型 provider。工具不会解决订阅下载的启动依赖环。

#### 3. 首次生成与校验

确认没有正在使用同名输出文件后：

```bash
python -m tools.render linux \
  --private "$HOME/.config/mihomo/private.yaml" \
  --output "$HOME/.config/mihomo/config.yaml"

mihomo -t -d "$HOME/.config/mihomo"
```

工具不会联网拉订阅、不读取 `/etc/mihomo/config.yaml`、不输出私有内容、不修改 systemd。输出文件在 POSIX 系统上以 **0600** 权限原子创建。

已有输出时默认拒绝覆盖。`--force` 允许替换，但**不会自动备份旧文件**，请先自行备份。私有输入不能作为输出，即使用 `--force` 也会拒绝；仓库内输出及输出符号链接也会拒绝。

#### 4. 运行

```bash
mihomo -d "$HOME/.config/mihomo"
```

默认只提供 `127.0.0.1:7890` 的 HTTP/SOCKS 代理。确认该端口没有被另一个 mihomo 占用；如有冲突，在私有文件中设置其他 `mixed-port` 后重新生成。

应用需要显式使用这个代理，例如：

```bash
curl -x http://127.0.0.1:7890 https://www.gstatic.com/generate_204
```

这不是全局透明代理：默认没有 TUN，不改路由、不改系统 DNS、不设置 shell 代理环境变量。

**已有系统服务若启动参数是 `mihomo -d /etc/mihomo`，不会读取上述用户目录。** 必须有意识地选择部署目录、备份、校验并重载对应服务；不要同时启动两个占用相同端口的进程。本工具不会替你迁移现有服务。

## 多个订阅、文件 provider 与内联节点

- 多个订阅：在自己的 `proxy-providers` 中添加不同名称的条目，每个缓存 `path` 必须不同。
- 文件型 provider：指定 `type: file` 和节点文件 `path`；生成器不会复制节点文件。
- 内联节点：把节点列表放在私有文件的顶层 `proxies` 下。
- 可以混用内联节点、HTTP/file/inline providers。
- 地区、测速、手动选择组使用 `include-all`，无需把 provider 名称再写进每个组。
- 节点不得与策略组/内置代理重名；远程订阅内部的重名及链式代理依赖仍需由你和内核检查。

**相对路径以 `mihomo -d` 的工作目录为基准，不是以私有文件或仓库目录为基准。** 建议最终 `config.yaml` 与运行工作目录放在一起。使用绝对路径时仍受内核的 HomeDir/SAFE_PATHS 限制。

## 本机网络设置与控制 API

默认：

| 项目 | 默认值 |
|---|---|
| 代理监听 | `127.0.0.1:7890`，不允许局域网共享 |
| 模式 | `rule` |
| TUN | 关闭 |
| 内置 DNS | 关闭，使用系统解析 |
| IPv6 | 顶层默认关闭，按自身环境调整 |
| 控制 API | 关闭 |

私有文件可设置 `mixed-port`、`bind-address`、`allow-lan`、`dns`、`tun`、`ipv6`、`external-controller`、`secret`、`authentication`、`profile` 等本地参数；完整允许列表见 `tools/render.py` 的 `PRIVATE_KEYS`。

映射递归合并，列表替换。例如启用自定义 DNS 时必须明确设置 `dns.enable: true`，只添加 `nameserver` 不会自动启用 DNS。不要把订阅下发的完整配置原封不动作为私有输入；它通常含会替换公共策略的 `rules` 和 `proxy-groups`，工具会拒绝。

要通过 API/面板手动选节点，可在私有文件中启用 `127.0.0.1:9090`，并设置自己的强随机 `secret`（生成器要求至少 16 字符）。生成器仅允许回环控制地址；面板和端口转发由你管理。不需要面板时保持默认关闭。

## 之后如何更新？

### 更新节点

HTTP providers 由**mihomo 内核**按 `interval` 更新，不改公共分流配置。只是更新节点时通常不需要再次运行生成器；文件型/内联节点按你自己的更新方式处理。

### 更新仓库策略或本机设置

在仓库目录更新代码后，生成候选配置，不直接覆盖正在使用的文件：

```bash
git pull --ff-only
python -m pip install -r requirements.txt
python -m tools.render linux \
  --private "$HOME/.config/mihomo/private.yaml" \
  --output "$HOME/.config/mihomo/config.next.yaml"

mihomo -t -d "$HOME/.config/mihomo" \
  -f "$HOME/.config/mihomo/config.next.yaml"
```

校验通过后，先备份旧 `config.yaml`，再替换并按自己的运行方式重启/重载。若之前留下了 `config.next.yaml`，先检查它，再决定删除还是用 `--force` 替换。

`mihomo -t` 主要检查配置，**不保证节点可用、规则下载成功或已有长连接不中断**。加载后还应检查日志和连通性。更新失败时保留有效缓存，不要无条件清空 `providers/`、`ruleset/`。

## 安全边界

- 工具仅生成文件，默认不覆盖现有输出，任何运行/部署都由用户明确执行。
- HTTP provider 的订阅 URL 及生成的完整配置可能包含凭据，必须留在仓库外。
- 生成器会拒绝示例域名 `.invalid`、已知节点重名、缓存路径冲突及策略覆盖；不是完整的 mihomo 配置验证器。
- 不接受把自定义策略/规则塞进私有文件来覆盖公共模板；需要改策略时修改 `templates/policy.yaml` 后构建。
- 生成工具与内核测试不使用真实节点；当前机器的系统代理配置不会因此自动切换。
