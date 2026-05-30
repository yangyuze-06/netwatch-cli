# speedtest.cn Browser Automation Experiment

## 1. 目标

本实验功能的目标是用 Playwright 自动化普通浏览器页面，而不是把
`speedtest.cn` 当成 CLI 后端或私有 API 服务。

目标流程：

- 用 Playwright 自动打开 `https://www.speedtest.cn/`。
- 自动等待并点击测速按钮。
- 等待测速完成。
- 优先从 DOM 文本读取测速结果字段：
  - `download_mbps`
  - `upload_mbps`
  - `ping_ms`
  - `jitter_ms`
  - `server_name`
  - `location` / ISP
- 将结构化结果输出到 `netwatch-cli` 表格。
- 不调用、不抓包、不逆向 `speedtest.cn` 私有 API。

当前实现主要用于减少手动录入网页测速结果的操作成本，并尽量避免用户在
CLI 场景中直接面对网页广告和复杂页面。

## 2. 为什么是实验功能

`speedtest.cn` 官方提供 SDK / 产品集成入口，但这不等同于公开免费 REST API。
当前项目不能依赖私有网页接口，也不能通过抓包或逆向方式把隐藏接口包装成
稳定后端。

浏览器自动化本质上依赖页面结构和前端行为。页面改版、广告、弹窗、验证码、
反自动化策略、按钮文案变化或结果布局变化，都可能导致自动化失败。

V0.10.4 已将该功能提升为主菜单“宽带测速（speedtest.cn）”默认入口，为普通用户提供接近网页测速体验的简洁结果。但该功能仍然依赖页面结构，页面改版、广告、弹窗、验证码、反自动化策略、按钮文案变化或结果布局变化都可能导致自动化失败。因此该功能不是官方 API 后端，失败时不自动 fallback 到 Ookla。

## 3. 技术方案

当前实现：

- 使用 Playwright Python。
- 当前 CLI 入口固定 `headless=True` 后台运行，不打开可见浏览器窗口。
- 当前 CLI 入口固定 `debug_screenshot=False`，不保存截图。
- CLI 不暴露 debug / 可见浏览器 / screenshot 交互，也不显示 headless、screenshot、geolocation 等实现细节。
- CLI 使用 event-driven progress：状态提示由 Playwright 实际执行节点通过 `progress_callback` 发出，而不是 CLI 预先打印固定步骤。
- Browser context 使用桌面 Chrome UA、`1440x900` viewport、`zh-CN` locale、`Asia/Shanghai` timezone 和 `Accept-Language` 头，尽量贴近普通桌面浏览器。
- Browser context 授予 `geolocation` 权限，并使用默认模拟位置（广州：`113.2644, 23.1291`）避免浏览器地理位置权限弹窗阻塞测速。
- 不读取、不保存用户真实位置。
- 使用 `page.goto("https://www.speedtest.cn/")` 打开页面。
- 如果 headless 首次访问出现 `ERR_HTTP2_PROTOCOL_ERROR`，自动以 `headless=True` 和兼容 launch args 重试一次。
- 尝试处理 `speedtest.cn` 页面内测速提醒弹窗，只点击“不再提醒”或“继续测速”两个已知按钮。
- 等待测速按钮出现。
- 点击测速按钮。
- 点击测速按钮后再次尝试处理页面内测速提醒弹窗。
- 等待 20~90 秒，或等待结果文本稳定。
- 使用 `page.locator("body").inner_text()` 读取 DOM 文本。
- 用 parser 从文本提取测速结果。
- 底层 `BrowserAutomationOptions` 仍可保留 `headless` / `debug_screenshot` 字段，供未来开发者模式重新设计；当前 CLI 不使用这些选项。
- Playwright 是 optional dependency，不在默认安装依赖中强制安装。

该方案只模拟用户打开网页并点击测速，不调用网页内部私有接口，不读取网络请求
payload，不做抓包分析。

可选依赖安装：

```bash
pip install -e ".[browser]"
playwright install chromium
```

或：

```bash
pip install playwright
playwright install chromium
```

## 4. 第一版实现边界

第一版已做：

- 检测 Playwright 是否安装。
- 自动打开页面。
- 自动点击测速。
- DOM 文本解析。
- 失败时返回友好错误，不抛出 traceback 给用户。
- 高级功能实验入口。
- CLI 入口固定后台运行，不暴露 debug 模式或 screenshot 交互。

第一版不做：

- OCR。
- 绕过验证码。
- 读取浏览器 Cookie。
- 抓包。
- 私有 API 调用。
- 批量循环测速。
- 默认主菜单入口。

## 5. Parser 设计

Parser 应先独立出来，避免浏览器自动化、CLI 展示和文本解析耦合。例如：

```text
parse_speedtest_cn_text(text: str) -> SpeedtestCnResult
```

Parser 支持从页面文本里解析：

- 下载 / Download / Mbps
- 上传 / Upload / Mbps
- Ping / 时延 / ms
- 抖动 / Jitter / ms
- 测速点 / 服务器 / server
- 地区 / ISP

要求：

- Parser 测试只用 mock text，不访问真实网站。
- 如果字段缺失，返回结构化 error，不 traceback。
- 单位统一：
  - Mbps 保持为 Mbps。
  - MB/s 按 `Mbps / 8` 派生展示，不作为主存储单位。

## 6. CLI 设计

当前高级功能中包含实验入口：

```text
11. 打开 speedtest.cn 网页对照测速
12. 实验：自动浏览器测速 speedtest.cn
13. 返回主菜单
```

运行前提示：

```text
这是实验功能，会在后台浏览器中访问 speedtest.cn 并尝试读取测速结果。
本功能不调用 speedtest.cn 私有 API，页面结构变化可能导致失败。
是否继续？[y/N]
```

确认后 CLI 直接使用 `headless=True`、`debug_screenshot=False` 的后台实验测速，不打开可见浏览器，不保存截图，不显示地理位置权限或模拟位置等实现细节。

运行时提示：

- 正在执行 speedtest.cn 后台测速，请稍候...
- 正在后台启动浏览器...
- 已打开 speedtest.cn
- 已处理页面提示
- 已找到测速按钮
- 已点击测速按钮，正在测速...
- 已检测到 Ping 结果
- 已检测到下载结果
- 已检测到上传结果
- 测速完成，正在生成结果...

除第一句总提示外，其余状态来自浏览器自动化模块的真实事件回调。等待结果期间最多约每 2 秒读取一次 DOM 文本，但只在 Ping、下载、上传字段首次出现时输出状态，避免刷屏。由于网页结构可能变化，部分阶段状态可能缺失，最终以结果表格或错误提示为准。

V0.10.4 该功能已接入主菜单第 4 项“宽带测速（speedtest.cn）”作为默认入口，为普通用户输出简洁结果。高级功能入口“实验：自动浏览器测速 speedtest.cn”已移除（不再重复）。高级功能第 1 项的“通用测速诊断”保留原有 Ookla/LibreSpeed/Python fallback。

## 7. 失败处理

失败时应说明可能原因：

- 页面结构变化。
- 页面内提醒弹窗未能自动关闭。
- 弹窗或广告遮挡。
- 浏览器地理位置权限或定位逻辑被页面限制。
- Headless 浏览器被限制。
- `speedtest.cn` 页面/CDN/HTTP2 对 headless Chromium 不兼容，可能表现为 `ERR_HTTP2_PROTOCOL_ERROR`。
- 测速未完成。
- DOM 文本无法解析。

建议用户：

- 使用 `speedtest.cn` 网页手动对照。
- 使用 Ookla / LibreSpeed 后端。

错误信息应面向用户解释原因和下一步选择，不暴露长 traceback。
如果 headless 兼容重试仍失败，CLI 不会询问切换到可见浏览器，也不会静默打开窗口。未来如需 debug，应通过开发者模式重新设计。

## 8. 安全和合规边界

必须遵守：

- 不逆向 `speedtest.cn` 私有 API。
- 不绕过验证码或风控。
- 不保存 Cookie。
- 不保存公网 IP。
- 不读取、不保存用户真实地理位置；默认广州坐标只用于 Playwright context 模拟定位，避免权限弹窗阻塞。
- 不高频循环测速。
- 不作为官方 `speedtest.cn` 后端。
- 不把浏览器自动化结果宣传为稳定、官方或可长期依赖。
- 当前 CLI 入口不保存 debug screenshot。
- 当前 CLI 入口不会降级到可见浏览器，也不会静默打开窗口。

如果未来有 `speedtest.cn` 正式 SDK/API 授权，应作为独立后端接入，并与本实验
功能分开设计、分开测试、分开文档说明。

## 9. 测试策略

默认 pytest 不访问真实 `speedtest.cn`。

自动测试只覆盖：

- Parser mock text。
- Playwright missing dependency error。
- CLI 确认提示。
- Failure path。
- Mock browser DOM success path。
- Timeout / KeyboardInterrupt path。
- CLI 只询问是否继续。
- CLI 固定传入 `headless=True` 和 `debug_screenshot=False`。
- CLI 普通输出不泄露 debug、screenshot、geolocation 或 traceback。
- Progress callback mock tests。
- 等待循环字段首次出现时只输出一次状态。

真实浏览器测试只作为手动实验，不放进默认 CI。所有公网测速、浏览器访问和
外部页面行为都不能成为默认测试依赖。

## 10. Roadmap

V0.10.0:

- 新增设计文档。
- 实现 parser + mock tests。
- 实现 Playwright 实验模块，但不进默认主流程。
- 增加高级功能实验入口。
- CLI 入口固定后台运行。

V0.10.2:

- 移除用户可见 debug / 可见浏览器 / screenshot 交互。
- 失败时建议使用 `speedtest.cn` 网页对照测速或 Ookla / LibreSpeed 后端。

后续可能方向：

- OCR fallback 只作为未来可能性，不默认实现。
- 如果 `speedtest.cn` 提供正式 SDK/API 授权，可独立设计官方后端。
