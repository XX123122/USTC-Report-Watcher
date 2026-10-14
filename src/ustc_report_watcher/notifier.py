import base64
import os
import re
import subprocess
from pathlib import Path
from urllib.parse import quote
from xml.sax.saxutils import escape, quoteattr
from .windows import powershell, ps_quote, launch_args

APP_ID = "USTC.ReportWatcher"
SCHEME = "ustc-report-watcher"


def viewer_uri(report_id=None):
    return f"{SCHEME}://show" + (f"?id={quote(report_id, safe='')}" if report_id else "")


def public_title(text):
    text = re.sub(r"https?://\S+", "[链接]", text)
    return re.sub(r"(?:会议号|会议ID|密码)\s*[:：]?\s*\S+", "[参会信息详见本地列表]", text)[:100]


def toast_xml(title, body, target):
    return (f'<toast activationType="protocol" launch={quoteattr(target)}>'
            f'<visual><binding template="ToastGeneric"><text>{escape(title)}</text>'
            f'<text>{escape(body)}</text></binding></visual>'
            f'<actions><action content="查看报告" activationType="protocol" arguments={quoteattr(target)}/></actions>'
            '<audio src="ms-winsoundevent:Notification.Default"/></toast>')


def register_identity(config):
    args = launch_args(config, "show", "--uri", "%1")
    command = subprocess.list2cmdline(args)
    identity_code = Path(__file__).resolve().parents[2] / 'scripts/ShellIdentity.cs'
    powershell(f"""
    $ErrorActionPreference='Stop'
    $base='HKCU:\\Software\\Classes\\{SCHEME}'
    New-Item -Path $base -Force | Out-Null
    Set-Item -Path $base -Value 'URL:USTC Report Watcher'
    New-ItemProperty -Path $base -Name 'URL Protocol' -Value '' -Force | Out-Null
    New-Item -Path "$base\\shell\\open\\command" -Force | Out-Null
    Set-Item -Path "$base\\shell\\open\\command" -Value {ps_quote(command)}
    $app='HKCU:\\Software\\Classes\\AppUserModelId\\{APP_ID}'
    New-Item -Path $app -Force | Out-Null
    New-ItemProperty -Path $app -Name DisplayName -Value '中科大学术报告监控' -Force | Out-Null
    New-ItemProperty -Path $app -Name ShowInSettings -PropertyType DWord -Value 1 -Force | Out-Null
    $shell=New-Object -ComObject WScript.Shell
    $shortcutPath=Join-Path ([Environment]::GetFolderPath('Programs')) 'USTC Report Watcher.lnk'
    $shortcut=$shell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath={ps_quote(args[0])}
    $shortcut.Arguments={ps_quote(subprocess.list2cmdline(launch_args(config, 'show')[1:]))}
    $shortcut.WorkingDirectory={ps_quote(config.root)}
    $shortcut.Description='中科大学术报告监控'
    $shortcut.Save()
    Add-Type -Path {ps_quote(identity_code)}
    [ShellIdentity]::SetAppId($shortcutPath, '{APP_ID}')
    """)


class Notifier:
    def __init__(self, config):
        self.config = config

    def send(self, title, body, target=None):
        if not self.config["notification"]["enabled"]:
            return "disabled"
        register_identity(self.config)
        xml = toast_xml(public_title(title), body, target or viewer_uri())
        payload = base64.b64encode(xml.encode("utf-8")).decode()
        return powershell(f"""
        $ErrorActionPreference='Stop'
        [Console]::OutputEncoding=[Text.Encoding]::UTF8
        [Windows.UI.Notifications.ToastNotificationManager,Windows.UI.Notifications,ContentType=WindowsRuntime] | Out-Null
        [Windows.UI.Notifications.ToastNotifier,Windows.UI.Notifications,ContentType=WindowsRuntime] | Out-Null
        [Windows.UI.Notifications.NotificationSetting,Windows.UI.Notifications,ContentType=WindowsRuntime] | Out-Null
        [Windows.UI.Notifications.ToastNotification,Windows.UI.Notifications,ContentType=WindowsRuntime] | Out-Null
        [Windows.Data.Xml.Dom.XmlDocument,Windows.Data.Xml.Dom.XmlDocument,ContentType=WindowsRuntime] | Out-Null
        $notifier=[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('{APP_ID}')
        # Before the first Show, Windows can return ELEMENT_NOT_FOUND for Setting.
        try {{ $setting=$notifier.get_Setting().ToString() }}
        catch {{ if ($_.Exception.ToString() -notmatch '80070490') {{ throw }}; $setting='Unregistered' }}
        if ($setting -notin @('Enabled','Unregistered')) {{ throw 'Notifications disabled' }}
        $xml=New-Object Windows.Data.Xml.Dom.XmlDocument
        $xml.LoadXml([Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{payload}')))
        $toast=[Windows.UI.Notifications.ToastNotification]::new($xml)
        $toast.Tag='reports'
        $toast.Group='ustc'
        $toast.ExpirationTime=[DateTimeOffset]::Now.AddDays(3)
        $notifier.Show($toast)
        Write-Output 'submitted'
        """)


def dispatch(store, config, now, notifier=None):
    rows = store.pending()
    if not rows:
        return "none"
    reports = {item["report"].report_id: item["report"] for item in store.reports()}
    from .filters import matches
    usable = []
    skipped = []
    for row in rows:
        if not config["notification"]["enabled"]:
            skipped.append(row)
        elif row["event_type"] == "auth_expired" and not config["notification"]["notify_on_auth_expiry"]:
            skipped.append(row)
        elif row["report_id"] and (row["report_id"] not in reports or not matches(reports[row["report_id"]], config, now)):
            skipped.append(row)
        else:
            usable.append(row)
    store.mark([row["event_key"] for row in skipped], "suppressed", now)
    if not usable:
        return "suppressed"
    kinds = {row["event_type"] for row in usable}
    targets = list(dict.fromkeys(row["report_id"] for row in usable if row["report_id"]))
    target = viewer_uri()
    if kinds & {"auth_expired", "failed", "partial"}:
        title = "报告监控需要重新登录" if "auth_expired" in kinds else "报告监控暂时无法同步"
        body = "旧报告已保留。点击查看状态及重新登录入口。"
    elif kinds == {"baseline"}:
        count = sum(matches(item, config, now) for item in reports.values())
        title = "首次扫描完成"
        body = f"发现 {count} 场符合订阅的待参加报告，已建立历史基线。"
    else:
        title = f"有 {len(targets)} 场学术报告新增或更新"
        body = "\n".join(public_title(reports[item].title_zh) for item in targets[:config["notification"]["max_titles_in_toast"]])
        if len(targets) == 1:
            target = reports[targets[0]].detail_url or viewer_uri(targets[0])
    keys = [row["event_key"] for row in usable]
    store.mark(keys, "sending", now)
    try:
        result = (notifier or Notifier(config)).send(title, body, target)
        store.mark(keys, "submitted" if result == "submitted" else "suppressed", now)
        return result
    except Exception:
        store.mark(keys, "failed", now, "原生通知未提交；请检查 Windows 通知权限并运行 test-notification。")
        return "failed"
