# Windows 使用教程

## 1. 下载并准备

需要 Windows 10/11、Python 3.11+ 和 Microsoft Edge。首次打开 PowerShell 时用 `python --version` 确认版本。

从 GitHub 下载仓库 ZIP 后解压，或使用 Git：

```powershell
git clone https://github.com/XX123122/USTC-Report-Watcher.git
cd USTC-Report-Watcher
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\install.ps1
```

在解压后的项目目录执行同一安装脚本即可；目录可以包含中文和空格。安装脚本创建 `.venv`、安装依赖并生成 `config.yaml`，不会覆盖已有配置。默认不注册自启动，需要第 5 步显式安装。

如镜像网络不可用，改用官方 PyPI 安装：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --index-url https://pypi.org/simple -e ".[test]"
.\watcher.cmd init
```

不需要单独下载 Playwright 浏览器，程序直接使用本机 Edge。可以将整个配置流程交给 Codex，复制 [部署 prompt](codex-setup-prompt.md)。

## 2. 首次登录

```powershell
.\watcher.cmd login
```

程序打开一个独立的 Edge 窗口和“保存登录”窗口：

1. 在新 Edge 中进入学校统一认证，本人输入账号密码，完成验证码/多因素认证。
2. 进入“学术报告”列表，翻到下一页，再打开一条报告详情。
3. 点击“保存登录态和接口调查，完成”。

程序根据实际捕获的列表和详情请求生成 `.auth/source.json`，会话与调查数据由当前 Windows 用户 DPAPI 加密。无需在聊天里提供 Cookie 或密码。使用日常 Edge 已登录的页面，不能替代这一步独立登录。

仅完成登录但没有打开报告列表/详情时，会话可能已保存，数据源仍未确认；再次执行 `login` 补齐操作。如需检查结构：

```powershell
.\watcher.cmd discover
```

只导出脱敏字段结构；学校接口变化时，先确认新结构，不盲目替换地址。

## 3. 检查与查看

```powershell
.\watcher.cmd run-once
.\watcher.cmd show
```

完整检查通常约 2–3 分钟；等待结束后查看 `success` 与报告数量。首次仅建立历史基线，默认最多一条汇总，旧报告不会逐条弹窗。

日常双击：

| 文件 | 操作 |
|---|---|
| 查看报告.cmd | 打开本地列表 |
| 立即检查.cmd | 后台静默检查一次 |
| 登录.cmd | 更新学校登录态 |

列表分为两页：

* **当前可选**：学校标记可选、未超过选课截止时间及已知开始时间的报告，包括线下。最终选课资格和名额以学校界面为准；程序不代选课。
* **线上会议**：待参加的确定线上/混合报告；勾选“线上列表包含历史报告”回看历史。疑似或信息不足的报告不会被当成已确定线上。

选中报告可查看完整地点、报告内容、判别理由、开始时间和选课截止时间。学校 `JZSJ` 是选课截止时间，不是报告结束时间。没有确认永久详情链接时，原始报告按钮打开官方入口。

“立即刷新”启动真实检查，显示用时；“上次成功同步”在整批成功后更新为完成时间，内容不变也更新。后台已有检查时会提示等待，其完成后当前窗口自动读取结果。“查看本地最新结果”只读本地数据库，不重新抓取，因此不会改变同步时间。

## 4. 测试 Windows 通知

```powershell
.\watcher.cmd test-notification
```

确认通知出现，并在命令退出后点击通知，检查本地窗口能否打开。通知使用 Windows 原生 Toast，点击由系统协议处理器启动本地窗口。

`submitted` 只表示提交成功。未看到时检查 Windows 设置→系统→通知中的“中科大学术报告监控”，以及勿扰/专注助手。通知提交失败不影响保存的报告数据。

## 5. 安装登录自启动

```powershell
.\watcher.cmd install-task
.\watcher.cmd status
```

任务名 **USTCReportWatcher**：当前用户登录后检查一次，电脑开着且用户已登录期间每 6 小时检查；使用 `pythonw.exe`，无需保持终端。任务设置错过计划后补运行，使用跨进程锁避免重复抓取。

`status` 的任务信息应显示 `installed: true`、`logon_type: Interactive` 和两个触发器。新任务未运行过时 `last_result` 不一定为 0；完成任务后检查实际结果。

“开机自启动”指**开机后登录 Windows**，不在尚未登录的系统会话里显示通知。关机期间不运行，不保证恢复已经被学校删除或隐藏的报告。

项目目录和 `.venv` 必须保留。移动目录或修改检查间隔后，在新位置重新 `install-task`，更新任务与通知点击路径。

## 6. 修改订阅

编辑项目根目录 `config.yaml`：

```yaml
schedule:
  interval_hours: 6
subscriptions:
  include_modalities: [online, hybrid]
  title_keywords_any: [机器学习, 科学计算]
  title_keywords_all: []
  department_keywords: []
  speaker_keywords: []
  exclude_keywords: []
  watch_report_ids: []
  notify_on_update: true
  remind_before_hours: null
```

标题任意关键词为空列表表示不限制方向。手工关注 ID 可跳过普通兴趣条件，仍遵守排除词和全局通知开关。通知兴趣过滤不隐藏两个列表中的报告。

检查间隔允许 1–24 小时。修改间隔后重新安装任务；修改其他订阅后下一次检查生效。`notification.enabled: false` 关闭全部通知；`notify_possible_online: true` 可选关注疑似线上。

## 7. 常见问题

| 状态 | 处理 |
|---|---|
| 没有确认报告接口 | 再次 login，进入报告列表、翻页并打开详情后保存 |
| 登录失效/权限不足 | 再次 login，保留原数据库 |
| 刷新时间暂时没变 | 等待完整检查结束；查看刷新中用时、失败提示或是否已有检查运行 |
| 线上列表为空 | 可能确实没有待参加的确定线上报告；可查看当前可选或历史线上列表 |
| 分页不全/结构变化 | 查看 status 与 logs；旧数据保留，确认接口后再修复 |
| 没有弹窗 | 首次基线/无新增/内容不变通常不通知；运行 test-notification 检查系统设置 |
| 更新代码后界面未变化 | 关闭旧窗口，再双击“查看报告.cmd” |

日志位于 `logs/watcher.log`；隐藏启动器异常类型位于 `logs/launcher.log`。不要公开 `.auth/`、SQLite、日志、配置文件或含会议号/密码的截图。

## 8. 关闭自启动与验证

```powershell
.\watcher.cmd uninstall-task
```

只删除定时任务，保留登录态、历史与通知点击入口。再启用时重新 `install-task`。

开发测试：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

离线测试使用合成 fixture，不访问学校、不需要账号。实际 Windows 注销/登录、睡眠恢复、锁屏/勿扰模式和 Windows 10 的通知行为仍应在对应机器验收；详细记录见 [validation.md](validation.md)。
