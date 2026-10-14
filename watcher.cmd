@echo off
"%~dp0.venv\Scripts\python.exe" "%~dp0scripts\runner.py" --config "%~dp0config.yaml" %*
