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

这个方向主要用于减少手动录入网页测速结果的操作成本，并尽量避免用户在
CLI 场景中直接面对网页广告和复杂页面。

## 2. 为什么是实验功能

`speedtest.cn` 官方提供 SDK / 产品集成入口，但这不等同于公开免费 REST API。
当前项目不能依赖私有网页接口，也不能通过抓包或逆向方式把隐藏接口包装成
稳定后端。

浏览器自动化本质上依赖页面结构和前端行为。页面改版、广告、弹窗、验证码、
反自动化策略、按钮文案变化或结果布局变化，都可能导致自动化失败。

因此该功能只能放在 experimental / lab 范围内，不进入默认带宽测速主流程，也
不替代当前稳定后端。

## 3. 技术方案

建议方案：

- 使用 Playwright Python。
- 默认 `headless=True` 后台运行。
- Debug 模式支持 `headless=False`，方便观察页面行为。
- 使用 `page.goto("https://www.speedtest.cn/")` 打开页面。
- 等待测速按钮出现。
- 点击测速按钮。
- 等待 20~60 秒，或等待结果文本稳定。
- 使用 `page.locator("body").inner_text()` 读取 DOM 文本。
- 用 parser 从文本提取测速结果。
- 可选保存 screenshot 到 `~/.netwatch/debug/` 作为调试证据。

该方案只模拟用户打开网页并点击测速，不调用网页内部私有接口，不读取网络请求
payload，不做抓包分析。

## 4. 第一版实现边界

第一版只做：

- 检测 Playwright 是否安装。
- 自动打开页面。
- 自动点击测速。
- DOM 文本解析。
- 失败时返回友好错误，不抛出 traceback 给用户。

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

未来可以在高级功能中加入实验室入口：

```text
实验室功能
1. 自动浏览器测速 speedtest.cn
2. 返回
```

运行前提示：

```text
这是实验功能，会启动后台浏览器访问 speedtest.cn。
本功能不会调用 speedtest.cn 私有 API。
页面结构变化、广告、验证码或反自动化策略可能导致失败。
是否继续？[y/N]
```

运行时提示：

- 正在启动浏览器...
- 正在打开 speedtest.cn...
- 正在等待测速按钮...
- 正在开始测速...
- 正在等待结果，大约需要 20~60 秒...
- 正在解析结果...

V0.10.0 只记录设计，不新增 CLI 菜单入口。

## 7. 失败处理

失败时应说明可能原因：

- 页面结构变化。
- 弹窗或广告遮挡。
- Headless 浏览器被限制。
- 测速未完成。
- DOM 文本无法解析。

建议用户：

- 使用 `headless=False` 调试。
- 使用 `speedtest.cn` 网页手动对照。
- 使用 Ookla / LibreSpeed 后端。

错误信息应面向用户解释原因和下一步选择，不暴露长 traceback。

## 8. 安全和合规边界

必须遵守：

- 不逆向 `speedtest.cn` 私有 API。
- 不绕过验证码或风控。
- 不保存 Cookie。
- 不保存公网 IP。
- 不高频循环测速。
- 不作为官方 `speedtest.cn` 后端。
- 不把浏览器自动化结果宣传为稳定、官方或可长期依赖。

如果未来有 `speedtest.cn` 正式 SDK/API 授权，应作为独立后端接入，并与本实验
功能分开设计、分开测试、分开文档说明。

## 9. 测试策略

默认 pytest 不访问真实 `speedtest.cn`。

自动测试只覆盖：

- Parser mock text。
- Playwright missing dependency error。
- CLI 确认提示。
- Failure path。

真实浏览器测试只作为手动实验，不放进默认 CI。所有公网测速、浏览器访问和
外部页面行为都不能成为默认测试依赖。

## 10. Roadmap

V0.10.0:

- 只新增设计文档。

V0.10.1:

- 实现 parser + mock tests。

V0.10.2:

- 实现 Playwright 实验模块，但不进默认主流程。

V0.10.3:

- 可选 `headless=False` 调试模式。

V0.10.4:

- 可选 screenshot debug。
- OCR fallback 只作为未来可能性，不默认实现。

