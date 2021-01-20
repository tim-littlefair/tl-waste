@rem setup_venv.cmd
@echo off

set OS_PYTHON=py -3
set VENV_DIR=.venv3

if  "%1" equ "--clean" (
    rmdir /s/q %VENV_DIR%
)

if not exist %VENV_DIR% (
    %OS_PYTHON% -m venv %VENV_DIR%
)

call %VENV_DIR%\Scripts\activate.bat

rem The next line uses 'python' not '$OS_PYTHON' so that it picks
rem up the activated venv python not the base OS version
python -m pip install --upgrade pip rope wheel coverage pytest
python -m pip install boto3 ifaddr requests
