# mihomo-configs

给 mihomo-party 和 Linux mihomo 使用的通用分流配置：自动分组、故障转移、按应用选节点。**请自备可用订阅，本项目不提供节点。**

## 选择你的入口

| 使用方式 | 下载 | 使用说明 |
|---|---|---|
| mihomo-party | [YAML 覆写](dist/mihomo-party.yaml?raw=1) | [导入与更新](docs/mihomo-party.md) |
| Linux 原生 mihomo | [原生配置模板](dist/mihomo-linux.yaml?raw=1) | [填写订阅与运行](docs/linux.md) |

两个入口使用相同的分流策略，**不要把 Party 覆写当作 Linux 完整配置使用**。

## mihomo-party：导入即可使用

1. 在客户端导入自己的订阅，确认节点可用。
2. 下载上面的 **YAML 覆写**，在「覆写」中导入，并关联到订阅。
3. 应用配置，切换到**规则模式**。默认使用「故障转移」，也可手动选择节点。

需要远程更新？打开 [入口文件](dist/mihomo-party.yaml)，点击 **Raw**，将地址复制到客户端的远程 YAML 覆写中。订阅更新后，只要关联仍在，覆写会继续应用。

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
