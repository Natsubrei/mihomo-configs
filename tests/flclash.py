"""用独立 JS 上下文执行真实生成物；不模拟覆写逻辑、不提供网络 API。"""
import json
import shutil
import subprocess

from tools.render import FLCLASH_ENTRY

NODE = shutil.which("node")


def apply_flclash_script(configs, script=None):
    if not NODE:
        raise RuntimeError("执行 FlClash 脚本测试需要 Node.js")
    runner = """
const fs = require('node:fs');
const vm = require('node:vm');
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const sandbox = {};
vm.createContext(sandbox);
vm.runInContext(input.script, sandbox, {timeout: 1000});
const results = input.configs.map(config => {
  sandbox.config = config;
  const result = vm.runInContext('main(config)', sandbox, {timeout: 1000});
  return JSON.parse(JSON.stringify(result));
});
process.stdout.write(JSON.stringify(results));
"""
    result = subprocess.run(
        [NODE, "-e", runner],
        input=json.dumps({
            "script": FLCLASH_ENTRY.read_text(encoding="utf-8") if script is None else script,
            "configs": configs,
        }, ensure_ascii=False),
        capture_output=True, text=True, encoding="utf-8", timeout=10,
    )
    if result.returncode:
        raise AssertionError(result.stderr)
    return json.loads(result.stdout)
