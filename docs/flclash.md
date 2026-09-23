# FlClash 使用指南

入口：[`dist/flclash.js`](https://raw.githubusercontent.com/Natsubrei/mihomo-configs/main/dist/flclash.js)。这是 **JavaScript 脚本覆写**，不是订阅或完整 YAML 配置；请先自备可用订阅。下载使用不需要 Python 或 Node.js。

## 首次导入

1. 在 FlClash 中添加自己的订阅，确认至少有一个节点能正常访问网络。
2. 打开该配置的菜单 → **覆写**，模式选 **脚本**。
3. 点击 **前往配置脚本** → **添加**，进入脚本编辑器。
4. 编辑器右上角菜单 → **外部获取 → 通过URL导入**，填入下面的地址：

   ```text
   https://raw.githubusercontent.com/Natsubrei/mihomo-configs/main/dist/flclash.js
   ```

5. 将脚本命名为 `mihomo-configs`，保存。返回该配置的覆写页，**选中这个脚本**；只添加脚本但未关联不会生效。
6. 返回并应用配置，切换到 **规则模式** 并启动连接。若系统弹出 VPN 授权（常见于 Android），需要允许。
7. 在代理页确认出现「节点选择」「自动选择」「规则更新」及地区组，且组内有自己的节点。

也可先下载 `.js`，通过编辑器的 **外部获取 → 通过文件导入** 导入。若你的版本没有外部获取菜单，将 `.js` 全文复制到编辑器，**替换全部默认内容**，不要只粘贴 URL 或追加第二个 `main` 函数。

菜单路径根据 FlClash 源码提交 `62addf7` 核对；不同版本可能调整名称。如果看不到「脚本」覆写模式，请检查客户端版本，不要把脚本当成配置订阅导入。

## 为什么不用 Party 的 YAML？

Party 入口的 `rule-providers!` 是该客户端的映射替换语法，mihomo 内核本身不处理它。这里生成的脚本实现 FlClash 的 `function main(config)` 接口，并返回修改后的配置：

- 整体替换 `proxy-groups`、`rule-providers`、`rules`，不保留订阅的旧策略和规则集。
- 保留原始 `proxies`、`proxy-providers`，不包含或索取私人订阅地址。
- 不修改 DNS、TUN、IPv6、监听端口、局域网共享、控制接口、`profile` 等其他设置。
- 不设置 `profile.store-selected`，策略选择由 FlClash 自己管理。

FlClash 后续仍会按客户端设置覆盖网络参数，并重写 HTTP provider 的缓存路径。脚本不接管流量；未经过 FlClash（系统代理 / TUN / VPN）的应用仍走直连。

## 更新

- **更新订阅**：更新订阅并应用配置后，已关联的脚本会重新执行；节点变化不会清除这份分流策略。
- **更新公共策略**：编辑已有脚本，再通过同一个 URL 获取新内容，保存并重新应用配置。这样保留原脚本关联，不必删除重建。
- **URL 导入不是远程自动更新**：当前实现把下载内容保存成本地脚本，没有定时同步该 URL 的机制。
- 不要填写 GitHub 的 `blob` 浏览页面 URL；使用自己的 Fork 时，替换用户名与仓库名，并确认已推送生成物。

在源码仓库自行生成时：

```bash
# 先按开发文档安装 Python 依赖，再运行
python -m tools.render flclash
python -m tools.render flclash --check
```

统一的 `python -m tools.render build` 也会生成此脚本。不要手改 `dist/flclash.js`；修改 [共用策略源](../templates/policy.yaml) 后重新构建。

## 确认生效与常见问题

在覆写页的 **预览** 中检查：

- 存在「节点选择」「自动选择」「规则更新」等策略组。
- 顶层是普通 `rule-providers`，不是 `rule-providers!`。
- 原有节点或 providers 仍在，规则最后一条为 `MATCH,漏网之鱼`。

实际启动后，再检查日志中规则集是否加载成功。首次下载需要 GitHub 原站直连可用，或「规则更新」组有可用代理；失败时不要反复清空有效缓存。

**策略组为空或变成直连？**

本策略依赖内核的 `include-all`、`exclude-filter`、`empty-fallback` 支持。空动态组应使用 `REJECT`，不应默默变成 `COMPATIBLE`。底层策略及脚本输出已通过 mihomo v1.19.30 离线测试；这不代表所有 FlClash 内置内核版本均兼容，也不代表完成了各平台端到端验证。

**原有自定义规则不见了？**

脚本会替换订阅的规则及策略组。从标准模式切到脚本模式后，标准模式的追加规则不参与应用。需要保留特殊规则时应明确整合，避免其他脚本再次覆盖整体策略。

**节点报旧组不存在？**

若节点的 `dialer-proxy` 或 proxy-provider 的 `proxy` 依赖被替换的旧组，需自行保留或改写依赖。节点不能与新策略组或内置代理重名。脚本不修改未知 provider 的健康检查设置。

**没有合并所有订阅？**

`include-all` 仅包含当前生效配置里的节点和 providers，不会合并 FlClash 中未启用的其他配置。

更多行为与限制见 [分流策略与常见问题](policy.md)；构建、测试及发布流程见 [开发与维护](development.md)。不要把私人订阅、节点密码或完整运行配置提交到公开仓库。
