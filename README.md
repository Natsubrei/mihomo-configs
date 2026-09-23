# mihomo-configs

给 mihomo-party、Linux mihomo 和 FlClash 使用的通用分流配置：自动分组、故障转移、按应用选节点。**请自备可用订阅，本项目不提供节点。**

## 选择你的入口

| 使用方式 | 下载 | 使用说明 |
|---|---|---|
| mihomo-party | [YAML 覆写](https://raw.githubusercontent.com/Natsubrei/mihomo-configs/main/dist/mihomo-party.yaml) | [导入与更新](docs/mihomo-party.md) |
| Linux 原生 mihomo | [原生配置模板](https://raw.githubusercontent.com/Natsubrei/mihomo-configs/main/dist/mihomo-linux.yaml) | [填写订阅与运行](docs/linux.md) |
| FlClash | [JavaScript 覆写](https://raw.githubusercontent.com/Natsubrei/mihomo-configs/main/dist/flclash.js) | [脚本导入与更新](docs/flclash.md) |

链接直接打开原始文件；需要本地文件时，请保留 `.yaml` / `.js` 扩展名。

三个入口使用相同的分流策略，但格式不能混用：**Party YAML 覆写不是完整配置，FlClash 应使用 JS 脚本入口**。

## mihomo-party：导入即可使用

1. 在客户端导入自己的订阅，确认节点可用。
2. 下载上面的 **YAML 覆写**，在「覆写」中导入，并关联到订阅。
3. 应用配置，切换到**规则模式**。默认使用「自动选择」，也可改故障转移或手动选择节点。

需要远程更新？将下面的地址复制到客户端的远程 YAML 覆写中：

```text
https://raw.githubusercontent.com/Natsubrei/mihomo-configs/main/dist/mihomo-party.yaml
```

订阅更新后，只要关联仍在，覆写会继续应用。

## FlClash：给现有订阅关联脚本

1. 导入自己的订阅，确认节点可用。
2. 在该配置的「覆写」中选「脚本」→「前往配置脚本」，添加脚本。
3. 在编辑器菜单「外部获取 → 通过URL导入」填入下面的地址，命名并保存：

```text
https://raw.githubusercontent.com/Natsubrei/mihomo-configs/main/dist/flclash.js
```

4. 返回覆写页，选中脚本，应用配置并切到**规则模式**。

没有外部获取入口时，可下载 `.js` 全文粘贴到脚本编辑器。订阅更新会重新应用脚本；策略更新需要手动重新导入脚本内容。普通使用不需要 Python 或 Node.js，详见 [FlClash 使用指南](docs/flclash.md)。

## Linux：填写订阅后生成配置

推荐按 [Linux 使用指南](docs/linux.md) 操作：

1. 下载或克隆本仓库，安装生成工具的 Python 依赖。
2. 把 [私有配置示例](examples/linux-private.yaml) 复制到仓库外，填入自己的订阅。
3. 生成 `config.yaml`，用 `mihomo -t` 校验，再自行启动或部署。

默认代理地址为 **`127.0.0.1:7890`**，不开启 TUN、局域网共享和控制 API。工具不会修改或重启已有服务。

不想安装 Python？也可以下载原生模板，在仓库外直接填写 `proxies` / `proxy-providers`，校验后运行。

## 注意

- 已在 **mihomo v1.19.30** 上测试；旧版 Clash 或其他客户端不保证兼容。
- 没有候选节点的动态组会使用 `REJECT`，不会自动变成直连；配置无法修复失效节点。
- 私人订阅、密码和生成的运行配置请留在仓库外，不要上传 GitHub。

[分流策略与常见问题](docs/policy.md) · [开发与维护](docs/development.md)
