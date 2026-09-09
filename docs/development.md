# 开发与维护

## 目录约定

| 目录 | 用途 |
|---|---|
| `templates/` | 唯一策略源和 Linux 默认参数，维护时编辑这里 |
| `dist/` | 自动生成的公开入口，需要提交到 Git，供用户直接下载 |
| `examples/` | 无凭据的输入示例，使用前复制到仓库外 |
| `docs/` | 客户端使用说明、策略说明和维护文档 |
| `tools/` | 构建、私有配置合成与校验 |
| `tests/` | 合成数据的单元测试和可选内核测试 |

不要手动修改 `dist/`；不要提交真实订阅、运行配置、缓存或备份。私有生成工具强制要求输入、输出位于仓库外。

## 构建与测试

需要 Python 3.11+：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m tools.render build
python -m tools.render build --check
python tools/validate.py
python -m unittest discover -v
```

Windows PowerShell 用 `python -m venv .venv` 创建环境，以 `.\.venv\Scripts\Activate.ps1` 激活，其余 Python 命令相同。

修改模板后，将源文件和两个生成入口一起提交。`--check` 只检查生成物是否过期，不写文件。

启用离线内核测试：

```bash
MIHOMO_BIN=/absolute/path/to/mihomo python -m unittest discover -v
```

未设置 `MIHOMO_BIN` 时会明确跳过内核测试。测试只使用临时目录、合成节点、内联规则及本机 HTTP server，不访问真实订阅、不修改系统服务。它不证明外网节点或规则源可用。

## GitHub Actions

CI 包括 workflow 语法/表达式检查、Ubuntu/Windows 单元测试，以及固定 mihomo v1.19.30 的 Linux 内核测试。内核下载必须通过 SHA-256 校验。

提交 workflow 前，建议使用 [actionlint v1.7.7](https://github.com/rhysd/actionlint/releases/tag/v1.7.7) 在本地检查：

```bash
actionlint .github/workflows/validate.yml
```

**仅能解析 YAML 不代表 workflow 有效。** GitHub 会限制不同位置可用的表达式上下文；例如 job 级 `env` 不能使用 `runner.temp`。本项目在执行步骤中读取 `$RUNNER_TEMP`，通过 `$GITHUB_ENV` 把 `MIHOMO_BIN` 传给后续步骤。

无效的 workflow 可能在任何 job 运行前就被 GitHub 拒绝，因此 CI 中的 actionlint 不能替代提交前的本地检查。GitHub CI 的依赖安装、镜像拉取和内核下载需要网络。

## 提交规范

采用 [Conventional Commits](https://www.conventionalcommits.org/zh-hans/v1.0.0/)：

```text
feat(config): add a new routing group
fix(ci): export the mihomo path from a runner step
docs: simplify the Linux setup guide
test: cover empty provider fallback
```

格式为 `type(scope): description`，scope 可省略。破坏性变更使用 `!` 或 `BREAKING CHANGE:`，并说明迁移方式。不维护 `CHANGELOG.md`。

## 首次发布

在 GitHub 创建空的 `mihomo-configs` 仓库，再在本地添加新地址并推送：

```bash
git remote add origin https://github.com/<用户名>/mihomo-configs.git
git push -u origin main
```

不要指向已废弃的旧仓库，也不要强制覆盖其他仓库历史。发布前检查暂存区中没有凭据；当前未预设许可证，如需授权他人使用和修改，请自行选择合适的许可证。
