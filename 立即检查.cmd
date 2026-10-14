@echo off
start "" "%~dp0.venv\Scripts\pythonw.exe" "%~dp0scripts\runner.py" --config "%~dp0config.yaml" run-once
