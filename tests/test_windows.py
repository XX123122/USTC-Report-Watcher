import os
import xml.etree.ElementTree as ET
from pathlib import Path
import pytest
from ustc_report_watcher.scheduler import task_xml
from ustc_report_watcher.security import save_secret, load_secret
from ustc_report_watcher.locking import run_lock, AlreadyRunning


def test_schedule_interactive_repetition_and_unicode(config):
    config.file = config.root / "中文 路径/config.yaml"
    tree = ET.fromstring(task_xml(config, "S-1-5-test"))
    namespace = {"t":"http://schemas.microsoft.com/windows/2004/02/mit/task"}
    assert len(tree.find("t:Triggers",namespace)) == 2
    assert tree.find(".//t:Interval",namespace).text == "PT360M"
    assert tree.find(".//t:LogonType",namespace).text == "InteractiveToken"
    assert tree.find(".//t:StartWhenAvailable",namespace).text == "true"
    assert tree.find(".//t:Command",namespace).text.endswith("pythonw.exe")
    assert '"' in tree.find(".//t:Arguments",namespace).text


@pytest.mark.skipif(os.name!='nt',reason='Windows DPAPI')
def test_dpapi_ciphertext(tmp_path):
    path = tmp_path / 'session.bin'
    save_secret(path, {'cookie':'offline-test-value'})
    assert b'offline-test-value' not in path.read_bytes()
    assert load_secret(path) == {'cookie':'offline-test-value'}


def test_process_lock(tmp_path):
    path = tmp_path / 'run.lock'
    with run_lock(path):
        with pytest.raises(AlreadyRunning):
            with run_lock(path):
                pass
    with run_lock(path):
        pass


def test_real_launcher_with_chinese_and_spaces(tmp_path):
    import sys
    import subprocess
    import json
    project = Path(__file__).resolve().parents[1]
    config_path = tmp_path / '中文 路径' / '测试配置.yaml'
    result = subprocess.run([sys.executable,str(project / 'scripts/runner.py'),'--config',str(config_path),
                             'run-once','--dry-run','--fixture',str(project / 'tests/fixtures/baseline.json')],
                            capture_output=True,text=True,encoding='utf-8')
    assert result.returncode == 0
    assert json.loads(result.stdout)['reports'] == 2
    assert not config_path.parent.exists()
