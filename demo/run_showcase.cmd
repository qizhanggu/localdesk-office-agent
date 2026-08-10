@echo off
setlocal

set "REPO_ROOT=%~dp0.."
set "PYTHON=%REPO_ROOT%\.venv\Scripts\python.exe"
set "SNAPSHOT=%REPO_ROOT%\demo\recorded_showcase.json"
set "METRICS=%REPO_ROOT%\evaluation\results\product_eval_v2.json"
set "OUTPUT=%REPO_ROOT%\.localdesk\demo-ui\index.html"

if not exist "%PYTHON%" (
  echo Cannot find project Python: %PYTHON%
  exit /b 1
)

"%PYTHON%" -m localdesk.desktop.demo_ui render --snapshot "%SNAPSHOT%" --metrics "%METRICS%" --output "%OUTPUT%"
if errorlevel 1 exit /b %errorlevel%

echo Demo UI generated: %OUTPUT%
echo Open this HTML file in a browser.
