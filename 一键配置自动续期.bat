@echo off
title 配置自动续期 - 只需运行一次
cd /d "%~dp0"
echo ============================================
echo   一次配置，以后自动续期，不用再手动登录
echo ============================================
echo.
set "PY="
where python >nul 2>nul && set "PY=python"
if not defined PY (where py >nul 2>nul && set "PY=py")
if not defined PY goto nopython
echo 请输入站点账号 [手机号或用户名]
set /p KOOK_USER=
if "%KOOK_USER%"=="" goto empty
echo.
echo 请输入站点密码 [屏幕上会显示，仅本机使用]
set /p KOOK_PASS=
if "%KOOK_PASS%"=="" goto empty
echo.
%PY% tools\setup_autologin.py
echo.
echo ============================================
pause
exit /b 0

:nopython
echo [错误] 这台电脑没找到 python 命令
echo 请先安装 Python 并勾选 Add Python to PATH
pause
exit /b 1

:empty
echo [错误] 账号或密码是空的，请重新运行
pause
exit /b 1
