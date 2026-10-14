# USTC Report Watcher

Windows 10/11 本地中科大学术报告监控。数据保存在本机 SQLite；使用 Edge 正常登录、Windows DPAPI 加密会话、原生 Toast 与任务计划程序。无需服务器或常驻终端。

快速入口：[完整使用教程](docs/usage.md) · [复制给 Codex 的配置 prompt](docs/codex-setup-prompt.md) · [接口调查](docs/network-discovery.md) · [验收记录](docs/validation.md)

## 功能与已验证接入

* 当前可选与线上会议两个独立列表，支持完整地点、报告内容和线上判别依据。
* 新增、转线上和重要变化通知，SQLite 历史与重复抑制。
* 当前用户登录时和每 6 小时自动检查，静默运行，无需常驻终端。
* 独立 Edge 正常登录；当前用户 DPAPI 加密会话，过期后重新登录。

2026-10-14 已使用本人正常登录会话验证学校真实 API：完整抓取 **23 页 / 2,260 条**，补查 **39 条待参加或时间不明报告的详情**。当前可选 **14 场**；当前待参加的线上/混合报告 **0 场**。历史线上/混合报告 **137 场**。这些是本次数据状态，后续会变化。

开发机已验证定时任务、原生通知及协议点击入口，任务实测退出码为 0，重复扫描不重复通知。新电脑仍需按下文安装、本人登录和注册任务；仓库不附带登录态。请勿打扰、锁屏/睡眠恢复、Windows 10 和实际重新登录 Windows 的弹窗表现尚需对应环境验证。

## 直接使用

双击项目里的 **查看报告.cmd**，有两个独立列表：

* **当前可选**：学校 `SFKXK` 标记可选，且尚未超过选课截止时间和已知报告开始时间；包括线下报告。是否能最终选课仍以学校界面为准，程序不会代选课。
* **线上会议**：全部待参加的 `online`/`hybrid` 报告；勾选“线上列表包含历史报告”可回看历史。该视图不受通知兴趣关键词过滤；通知仍按订阅规则筛选。

详情区域显示完整地点、报告内容、识别理由、报告时间和**独立的选课截止时间**。`JZSJ` 是选课截止时间，**不是报告结束时间**。

**立即检查.cmd** 静默检查；**登录.cmd** 更新登录态。窗口也有“立即刷新”“重新登录”“查看本地最新结果”按钮。已打开旧版窗口时，关闭后重新打开以加载更新后的程序。

“上次成功同步”显示**整批采集完成时间**，内容没有变化也会更新。点击“立即刷新”后显示“刷新中”和已用时，完整检查通常约 2 分钟；成功后更新时间，失败则保留旧成功时间并显示错误。若已有检查在运行，会提示等待，其他窗口/定时任务完成检查后，当前窗口约 3 秒内自动读取最新结果。“查看本地最新结果”只读取本地保存的数据，不会重新抓取学校数据或改变同步时间。

## 新电脑一键初始化

安装 Python 3.11+ 和 Microsoft Edge，解压/放置整个项目目录。在项目目录打开 PowerShell：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\install.ps1
.\watcher.cmd login
.\watcher.cmd run-once
.\watcher.cmd test-notification
.\watcher.cmd install-task
```

安装脚本使用阿里云 PyPI 镜像安装依赖；也可自行使用官方源：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --index-url https://pypi.org/simple -e ".[test]"
.\watcher.cmd init
```

使用已安装的 Edge，不需要另行下载 Playwright Chromium。安装路径可以含空格或中文。保留项目与 `.venv` 在原位置；移动目录后从新位置重新 `install-task` 以更新任务和通知点击入口。

## 首次登录和再次登录

`login` 打开独立 Edge 窗口与“保存登录”小窗口：

1. 用户自行完成学校统一认证、验证码/多因素认证。
2. 进入“学术报告”列表，翻一次页，打开一条报告详情。
3. 点击“保存登录态和接口调查，完成”。

程序只保存当前 Windows 用户 DPAPI 加密的会话，不保存账号密码，不读取日常 Edge 配置。登录时只捕获报告模块的 JSON；调查数据也用 DPAPI 加密。实际观察到列表和详情接口后，自动生成本机数据源配置 `.auth/source.json`。如果只登录而未打开列表/详情，会话仍保留，但需要重新 `login` 补齐调查。

```powershell
.\watcher.cmd discover   # 导出不含值、Cookie、查询字符串的响应字段结构
```

Cookie/CAS Ticket/Authorization 不需要也不应贴到聊天里。`.auth/session.bin`、`.auth/discovery.bin` 不能在其他 Windows 用户/机器直接解密。DPAPI 不保护已经登录的当前用户进程；SQLite 与日志未加密，包含报告信息的本地目录限制为当前用户和 SYSTEM 访问。

## 实际命令

```powershell
.\watcher.cmd init
.\watcher.cmd login
.\watcher.cmd discover
.\watcher.cmd run-once
.\watcher.cmd run-once --dry-run
.\watcher.cmd show
.\watcher.cmd test-notification
.\watcher.cmd install-task
.\watcher.cmd status
.\watcher.cmd uninstall-task
```

等价调用：`.\.venv\Scripts\python.exe scripts\runner.py --config "C:\路径\config.yaml" run-once`；或在安装环境中运行 `python -m ustc_report_watcher` / `ustc-report-watcher`。`--config` 放在子命令前。相对路径基于配置文件所在目录。

`--dry-run` 真实读取和分类，但不写 SQLite、日志或通知。首次正式成功扫描仅建立基线，默认最多一条汇总。之后新报告、线下转线上、时间/地点/会议链接等重要变化才提醒。多条事件合并成一条通知。开机补查只能对比当前仍可查询的报告，不能还原关机期间已消失的记录。

退出码：0=成功/干跑/已有检查安全跳过；2=登录、配置、采集或系统操作失败。通知提交失败不会让已成功抓取的数据失效，可在 `status` 查看通知状态。

## 通知与任务

通知使用 Windows 原生 WinRT，通过 PowerShell 隐藏窗口调用；开始菜单快捷方式注册真实 AppUserModelID。采用微软 [协议激活通知](https://learn.microsoft.com/windows/apps/design/shell/tiles-and-notifications/toast-schema) 机制，点击由 Windows 启动 `ustc-report-watcher://show`，不依赖短命进程的 Python 回调。有真实详情 URL 时优先打开它；当前学校详情为弹层，未确认独立深链，因此打开本地报告详情或官方入口，不拼造链接。

任务名 `USTCReportWatcher`，按当前用户幂等安装。包含登录和重复时间两个触发器、`InteractiveToken`、错过计划后补运行、15 分钟任务上限、`pythonw.exe` 静默启动。跨进程文件锁阻止重复抓取。不会唤醒关机的电脑，也不安装系统服务或开放网络端口。

```powershell
.\watcher.cmd install-task       # 修改检查间隔后再次执行
.\watcher.cmd uninstall-task     # 仅移除定时任务，保留历史、登录态与通知点击入口
```

配置 `notification.enabled: false` 关闭全部通知；Windows 设置→系统→通知中可检查“中科大学术报告监控”，同时检查勿扰模式。通知状态 `submitted` 只代表已提交 Windows，不能证明用户看见/阅读；`failed` 可在后续检查重试；提交过程中崩溃的事件标记 `uncertain`，保留记录、不自动重放。

## 配置与订阅

`config.example.yaml` 是完整默认示例，`init` 创建 `config.yaml` 且不覆盖现有内容。

* 默认关注所有确定线上/混合报告；疑似线上默认不提醒。
* `title_keywords_any` 为空=全部标题；`title_keywords_all` 要求全部命中。院系、报告人关键词各按任意命中。
* `exclude_keywords` 优先；`watch_report_ids` 可跳过兴趣关键词，仍遵守排除词、线上方式与全局通知开关。
* `notify_on_update: false` 关闭已相关报告普通更新；线下转线上仍提醒。
* `remind_before_hours: 24` 可启用开始前提醒，按每次检查判断，去重按报告 ID 与开始时间。不保证在准确 24 小时处弹出；时间未知则不提醒。
* 可加 `subscriptions.online_keywords` 列表扩充明确参会方式用语。

时区为 `Asia/Shanghai`，检查频率允许 1–24 小时；默认请求间隔 2 秒、单请求 20 秒、总抓取 600 秒、最多 30 页、最多两次退避重试。真实接口每页 100 条，首次扫描约 2 分钟。达到页数上限或详情失败则整批标记失败/不完整，不覆盖历史。

## 离线验收

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\watcher.cmd run-once --dry-run --fixture tests\fixtures\baseline.json
.\watcher.cmd run-once --fixture tests\fixtures\baseline.json
.\watcher.cmd run-once --fixture tests\fixtures\updated.json
.\watcher.cmd run-once --fixture tests\fixtures\updated.json
.\watcher.cmd status --demo
.\watcher.cmd show --demo
```

样例只写 `data/demo.db`，不使用真实数据库、不发桌面通知。样例数据不含真实身份或参会密码。自动测试覆盖分类、完整分页/重复页/数量变化、失效会话、失败保留历史、订阅优先级、重要变更、通知聚合和重复抑制、干跑隔离、DPAPI、互斥锁、任务 XML 和两个列表切换。

## 文件与故障排查

* `.auth/`：加密会话、加密调查、本机数据源配置；不提交。
* `data/reports.db`：历史、变化、通知事件、运行记录；报告不再出现时仅标记非当前，不删除历史。
* `logs/watcher.log`：滚动日志，只记录固定诊断、数量和异常类型，无凭据或会议参数。
* `logs/launcher.log`：隐藏启动器的异常类型。
* `docs/network-discovery.md`：真实字段与接口核实记录。

“尚未确认报告接口”：重新登录并进入报告列表、翻页、打开详情，保存后运行 `discover`。

“学校会话失效”：重新 `login`；保留旧报告。Cookie 过期后不会绕过 CAS 或持续重试。

“分页不完整/字段结构变化”：旧数据保留，查看 `status`。在确有更多报告时可合理增大 `max_pages`；结构变化需重新调查，不应盲目改路径。

“有数据但没通知”：默认首次仅建基线、历史/线下不提醒，相同结果也不提醒；用 `test-notification` 检查系统权限。两个列表与通知订阅分别展示/筛选。

尚未完成的环境验收：实际 Windows 注销/登录、睡眠恢复、勿扰/锁屏表现、Windows 10，以及学校后续会话自然过期时的重登录体验。当前 API 已接入；页面 DOM 回退适配器支持经过核实的选择器配置，但未在学校页面实测，默认使用已验证 API。
