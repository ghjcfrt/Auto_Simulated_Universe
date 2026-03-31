@echo off
setlocal

cd /d "%~dp0.."

set "PYTHON_BIN=.venv\Scripts\python.exe"
if exist "%PYTHON_BIN%" (
    set "PY_CMD=%PYTHON_BIN%"
) else (
    set "PY_CMD=python"
)

if not exist "tests" (
    echo [ERROR] tests directory not found.
    exit /b 1
)

echo [INFO] Python: %PY_CMD%
if "%~1"=="" (
    echo [INFO] Running: -m unittest discover -s tests -p test_*.py -v
    "%PY_CMD%" -m unittest discover -s tests -p "test_*.py" -v
) else (
    echo [INFO] Running: -m unittest %*
    "%PY_CMD%" -m unittest %*
)

set "EXIT_CODE=%ERRORLEVEL%"
if not "%EXIT_CODE%"=="0" (
    echo [FAIL] Regression tests failed. Exit code: %EXIT_CODE%
) else (
    echo [OK] Regression tests passed.
)

exit /b %EXIT_CODE%
