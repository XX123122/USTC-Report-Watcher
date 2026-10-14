import subprocess
from datetime import datetime, timedelta
from xml.sax.saxutils import escape
from .windows import powershell, ps_quote, launch_args

TASK_NAME = "USTCReportWatcher"


def task_xml(config, sid, start=None):
    args = launch_args(config, "run-once")
    interval = float(config["schedule"]["interval_hours"])
    start = start or (datetime.now() + timedelta(minutes=2)).isoformat(timespec="seconds")
    return f'''<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
 <RegistrationInfo><Description>中科大学术报告检查：登录时和周期执行</Description></RegistrationInfo>
 <Triggers>
  <LogonTrigger><Enabled>true</Enabled><UserId>{escape(sid)}</UserId><Delay>PT30S</Delay></LogonTrigger>
  <TimeTrigger><Repetition><Interval>PT{int(interval*60)}M</Interval><StopAtDurationEnd>false</StopAtDurationEnd></Repetition><StartBoundary>{start}</StartBoundary><Enabled>true</Enabled></TimeTrigger>
 </Triggers>
 <Principals><Principal id="User"><UserId>{escape(sid)}</UserId><LogonType>InteractiveToken</LogonType><RunLevel>LeastPrivilege</RunLevel></Principal></Principals>
 <Settings><MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy><DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries><StopIfGoingOnBatteries>false</StopIfGoingOnBatteries><StartWhenAvailable>true</StartWhenAvailable><RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable><ExecutionTimeLimit>PT15M</ExecutionTimeLimit><Enabled>true</Enabled></Settings>
 <Actions Context="User"><Exec><Command>{escape(args[0])}</Command><Arguments>{escape(subprocess.list2cmdline(args[1:]))}</Arguments><WorkingDirectory>{escape(str(config.root))}</WorkingDirectory></Exec></Actions>
</Task>'''


def install(config):
    from .notifier import register_identity
    register_identity(config)
    sid = powershell("[Security.Principal.WindowsIdentity]::GetCurrent().User.Value")
    xml = task_xml(config, sid)
    powershell(f"$ErrorActionPreference='Stop'; Register-ScheduledTask -TaskName '{TASK_NAME}' -Xml {ps_quote(xml)} -Force | Out-Null")
    return status()


def uninstall():
    powershell(f"$ErrorActionPreference='Stop'; if (Get-ScheduledTask -TaskName '{TASK_NAME}' -ErrorAction SilentlyContinue) {{ Unregister-ScheduledTask -TaskName '{TASK_NAME}' -Confirm:$false }}")


def status():
    return powershell(f"""
    [Console]::OutputEncoding=[Text.Encoding]::UTF8
    $task=Get-ScheduledTask -TaskName '{TASK_NAME}' -ErrorAction SilentlyContinue
    if ($task) {{ $info=$task | Get-ScheduledTaskInfo; @{{installed=$true;state=$task.State.ToString();next_run=$info.NextRunTime.ToString('s');last_result=$info.LastTaskResult;logon_type=$task.Principal.LogonType.ToString();triggers=$task.Triggers.Count}} | ConvertTo-Json -Compress }}
    else {{ '{{"installed":false}}' }}
    """)
