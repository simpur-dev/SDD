# 复现说明（修改前/后快照 + 测试）

本目录包含该 MiniMax 开发记录的可复现材料：

- `before/`：修改前的 `src/` 与 `tests/` 快照（= 仓库 `demo/railway` 基线）
- `after/`：修改后的 `src/` 与 `tests/` 快照（= 提交 `b3f5884` 后的文件）
- `agent.diff`：`git diff` 形式的代码差异
- `target-tests.py`：目标行为测试（behavior-level；修改前失败、修改后通过）
- `baseline-pytest.txt` / `post-pytest.txt`：工程测试修改前后结果
- `hidden-acceptance.txt`：隐藏验收（diff 捕获后注入）
- `transcript.jsonl` / `prompt.txt` / `minimax-usage.json`：MiniMax 开发记录

## 复现命令（在仓库的 minimax/source 根内，Linux/macOS）

```bash
# 1) 准备基线工作副本
cp -r demo/railway /tmp/railway && cd /tmp/railway
git init -q && git config user.name demo && git config user.email demo@local
git add -A && git commit -qm baseline

# 2) 修改前：工程测试 + 目标测试
python -m pytest -q                 # 期望 10 passed
python <本目录>/target-tests.py /tmp/railway    # 期望 FAIL（目标行为未实现）

# 3) 应用 MiniMax 产生的补丁
git apply <本目录>/agent.diff

# 4) 修改后：工程测试 + 目标测试 + 隐藏验收
python -m pytest -q                 # 期望 16 passed
python <本目录>/target-tests.py /tmp/railway    # 期望 PASS
cp taskpacks/suites/railway-acceptance.py tests/
python -m pytest -q tests/test_railway_acceptance.py   # 期望 3 passed
```

Windows PowerShell 下把 `cp -r` 换成 `Copy-Item -Recurse`、`python` 指向项目 venv 即可；
`before/` 与 `after/` 也可直接用于人工核对差异。

> 说明：正式题面只要求核对 MiniMax 开发记录，不要求评审重新调用 MiniMax 生成相同补丁；
> 上述步骤用已记录的 diff 即可复现修改前后测试。