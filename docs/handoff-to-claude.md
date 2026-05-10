# netwatch-cli Claude Code 交接文档

## 1. 项目概览

- 项目名：`netwatch-cli`
- 定位：轻量级命令行网络状态与测速诊断工具
- 当前核心能力：
  - 实时网卡流量
  - 本机网络信息
  - 局域网设备发现
  - 路由器管理后台打开
  - 小米/Redmi 路由器设备名同步
  - 多后端带宽测速
  - 代理/当前出口测速
  - 高级测速服务器诊断

## 2. 当前版本状态

已完成版本：

- V0.1 基础 CLI 菜单和实时流量
- V0.2 网卡过滤和基础 Speedtest
- V0.3 Mbps / MB/s 单位修正、服务器选择雏形
- V0.5 ARP/MAC 解析修复
- V0.6 路由器集成和小米设备名同步
- V0.7 菜单重构、设备发现子菜单、路由器后台候选入口
- V0.8 多测速后端架构
- V0.8.2 官方 Ookla CLI、物理网卡 interface、代理出口测速
- V0.8.3 测速质量诊断、常用 server id 配置、speedtest.cn 网页对照入口

当前版本号请以 `pyproject.toml` / `netwatch/__init__.py` 为准。版本历史中存在命名跳跃和小版本补丁，后续维护时不要仅凭文档标题判断代码状态。

## 3. 当前已知核心问题

- 官方 Ookla CLI 已经可以调用，但在当前用户网络环境下经常选到 Tokyo / Hong Kong 节点。
- 用户本地测速网 `speedtest.cn` 能选到“广东移动_Vixtel_1”，Ping 约 7ms，接近千兆。
- Ookla server pool 与 `speedtest.cn` server pool 不同，不能保证复现网页测速。
- `--interface en0` 可以避开 `utun` / TUN，但不能保证 Ookla 选到广州移动节点。
- Python speedtest-cli fallback 结果通常明显偏低。
- 代理/TUN 环境会影响 CLI 出口，可能出现 JP/Tokyo 或 CN/China Mobile 出口来回变化。
- `Cannot read from socket` 代表官方 Ookla CLI 已安装但本次测速失败，不应误判为未安装。

## 4. 项目目录说明

- `netwatch/cli.py`：主菜单和交互展示
- `netwatch/network_info.py`：网卡/IP/物理接口识别
- `netwatch/scanner.py`：局域网扫描、ARP/MAC/hostname
- `netwatch/router.py`：默认网关、打开路由器后台、小米 LuCI API、设备合并
- `netwatch/proxy_probe.py`：当前公网出口 IP 检测
- `netwatch/config.py`：非敏感用户配置，例如常用 speedtest server id
- `netwatch/speedtest_runner.py`：测速后端调度、fallback、服务器筛选、质量诊断
- `netwatch/speedtest_backends/ookla_cli.py`：官方 Ookla CLI 后端
- `netwatch/speedtest_backends/python_speedtest.py`：Python speedtest-cli fallback
- `netwatch/speedtest_backends/librespeed_cli.py`：LibreSpeed CLI 后端
- `netwatch/speedtest_backends/models.py`：`SpeedtestResult` 数据结构
- `tests/`：pytest 测试
- `docs/`：版本计划和交接文档

## 5. 关键设计原则

- CLI 层只负责交互和展示。
- runner 层负责策略和 fallback。
- backend 层不直接 print，只返回结构化结果。
- 不保存任何敏感信息。
- 小米路由器 `stok` 默认只在当前运行内存中使用，不落盘。
- `~/.netwatch/config.json` 只允许保存非敏感配置，例如常用 server id、server name、interface。
- 不逆向 `speedtest.cn` 私有网页 API。
- `speedtest.cn` 只作为浏览器对照入口，除非未来有正式 SDK/API 授权。

## 6. 当前推荐开发路线

- P0：修复任何 traceback / 错误提示误导问题。
- P0：完善测速结果质量诊断。
- P1：保存和复用常用 Ookla server id。
- P1：增强高级功能里的“指定 server id 测速并保存”。
- P1：完善 `speedtest.cn` 网页对照入口。
- P2：加入 LibreSpeed 自定义 server list。
- P2：设备发现结果导出 JSON/CSV。
- P3：更多路由器品牌适配。
- P3：做 GitHub README 截图和 Release。

## 7. 常用命令

运行：

```bash
cd /Users/y4n9/Workspace/Projects/My-github-projects/netwatch-cli
source .venv/bin/activate
python -m netwatch.cli
```

测试：

```bash
python -m compileall netwatch
pytest -q
python -m pytest -q
```

Git：

```bash
git status
git add .
git commit -m "..."
git push
```

## 8. 当前机器环境线索

- macOS
- 项目路径：`/Users/y4n9/Workspace/Projects/My-github-projects/netwatch-cli`
- venv：`.venv/`
- 官方 Ookla CLI 路径：`/opt/homebrew/bin/speedtest`
- Python speedtest-cli 可能 shadow：`.venv/bin/speedtest`
- 真实物理网卡常见：`en0 / 192.168.31.x`
- TUN/代理网卡特征：`utun*`、`198.18.0.x`
- 默认网关：`192.168.31.1`
- 小米路由器后台：`http://192.168.31.1/`
- `speedtest.cn` 网页对照曾选到：`广东移动_Vixtel_1`

## 9. Claude Code 接手注意事项

- 接手后先读 `README.md`、`docs/v0.8.2-plan.md`、`docs/v0.8.3-plan.md`、`docs/handoff-to-claude.md`。
- 不要一上来大重构。
- 每次只做一个小版本。
- 每次修改后运行 compileall 和 pytest。
- 网络真实测速不要写入单元测试，测试必须 mock。
- 涉及公网 IP、stok、路由器 token 的内容不要落盘。
- 对 `speedtest.cn` 不做私有接口逆向，只做网页打开或未来正式 SDK/API 后端。
- 如果用户要求“跑满千兆”，要解释测速服务器选择和后端差异，而不是承诺 CLI 一定复现网页测速。

## 10. 最近一次重要终端现象

- 普通带宽测速使用 `en0` 后，仍可能选到 Hong Kong 的 CMHK Mobile Service，下载只有数 Mbps。
- 代理/当前出口测速有时显示 JP Tokyo 出口，有时显示 CN China Mobile 出口。
- `/opt/homebrew/bin/speedtest --servers --format=json` 返回 Tokyo/Japan 服务器列表。
- 这说明 Ookla 当前 server discovery 与用户广州移动线路不匹配。
- 后续重点应是保存可用 server id、质量诊断和对照测速，而不是继续盲信自动选服。
