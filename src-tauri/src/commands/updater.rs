use std::env;
use std::fs;
use super::utils;

/// 下载更新文件并启动平台安装脚本
#[tauri::command]
pub async fn download_and_update(url: String, file_name: String) -> serde_json::Value {
    let pid = std::process::id();

    // 获取当前 exe 路径
    let current_exe = match env::current_exe() {
        Ok(p) => p,
        Err(e) => {
            utils::dlog!("[Updater] ERROR: current_exe failed: {}", e);
            return serde_json::json!({
                "success": false,
                "message": format!("获取当前程序路径失败: {}", e)
            });
        }
    };

    utils::dlog!("[Updater] === download_and_update called === url={}, file={}, pid={}", url, file_name, pid);
    utils::dlog!("[Updater] current_exe={:?}", current_exe);

    // 使用系统临时目录存放下载文件和脚本，不污染 exe 所在目录
    let temp_dir = env::temp_dir();
    // macOS 下载 DMG，Windows 下载 EXE
    #[cfg(target_os = "macos")]
    let temp_file = temp_dir.join(format!("cursor-renewal-update-{}.dmg", pid));
    #[cfg(not(target_os = "macos"))]
    let temp_file = temp_dir.join(format!("cursor-renewal-update-{}.tmp", pid));
    let script_path = temp_dir.join(format!("cursor-renewal-updater-{}", pid));

    // 下载文件 (超时5分钟，与 Go 版一致)
    utils::dlog!("[Updater] 下载文件到: {:?}", temp_file);
    let client = match reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(300))
        .build()
    {
        Ok(c) => c,
        Err(e) => {
            return serde_json::json!({
                "success": false,
                "message": format!("创建HTTP客户端失败: {}", e)
            });
        }
    };

    let response = match client
        .get(&url)
        .header("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
        .send()
        .await
    {
        Ok(r) => r,
        Err(e) => {
            utils::dlog!("[Updater] 下载请求失败: {}", e);
            return serde_json::json!({
                "success": false,
                "message": format!("下载请求失败: {}", e)
            });
        }
    };

    if !response.status().is_success() {
        return serde_json::json!({
            "success": false,
            "message": format!("服务器返回错误: HTTP {}", response.status())
        });
    }

    let bytes = match response.bytes().await {
        Ok(b) => b,
        Err(e) => {
            utils::dlog!("[Updater] 读取下载内容失败: {}", e);
            return serde_json::json!({
                "success": false,
                "message": format!("读取下载内容失败: {}", e)
            });
        }
    };

    utils::dlog!("[Updater] 下载完成, 大小: {} bytes", bytes.len());

    // 基本校验：下载文件不应太小（至少 100KB，防止下载到错误页面）
    if bytes.len() < 100_000 {
        utils::dlog!("[Updater] ERROR: 文件太小 {} bytes", bytes.len());
        return serde_json::json!({
            "success": false,
            "message": format!("下载文件异常，大小仅 {} bytes，请检查下载链接是否正确", bytes.len())
        });
    }

    // 写入临时文件
    if let Err(e) = fs::write(&temp_file, &bytes) {
        utils::dlog!("[Updater] ERROR: 写入临时文件失败: {}", e);
        return serde_json::json!({
            "success": false,
            "message": format!("写入临时文件失败: {}", e)
        });
    }
    utils::dlog!("[Updater] 临时文件已写入: {:?}", temp_file);

    // ========== Windows: PowerShell 安装脚本 (DETACHED_PROCESS) ==========
    #[cfg(target_os = "windows")]
    {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x08000000;

        let script_path = script_path.with_extension("ps1");
        let task_name = format!("CursorUpdate_{}", pid);

        // 所有参数直接硬编码进脚本，避免 schtasks /TR 的 261 字符限制
        let ps_content = format!(
            r#"$PidToWait = {pid}
$ArchivePath = '{archive}'
$TargetExecutable = '{target}'
$TaskName = '{task}'

try {{
  if (-not (Test-Path -LiteralPath $ArchivePath)) {{
    exit 1
  }}

  while (Get-Process -Id $PidToWait -ErrorAction SilentlyContinue) {{
    Start-Sleep -Seconds 1
  }}
  Start-Sleep -Seconds 2

  Copy-Item -LiteralPath $ArchivePath -Destination $TargetExecutable -Force
  Start-Process -FilePath $TargetExecutable
}} catch {{
}} finally {{
  Remove-Item -LiteralPath $ArchivePath -Force -ErrorAction SilentlyContinue
  schtasks /Delete /TN $TaskName /F 2>$null
  Remove-Item -LiteralPath $MyInvocation.MyCommand.Path -Force -ErrorAction SilentlyContinue
}}
"#,
            pid = pid,
            archive = temp_file.to_string_lossy().replace('\'', "''"),
            target = current_exe.to_string_lossy().replace('\'', "''"),
            task = task_name,
        );

        // 写入 PS1 脚本（加 UTF-8 BOM 头，确保 PowerShell 正确读取中文路径）
        let bom: &[u8] = b"\xEF\xBB\xBF";
        let mut content_with_bom = Vec::with_capacity(bom.len() + ps_content.len());
        content_with_bom.extend_from_slice(bom);
        content_with_bom.extend_from_slice(ps_content.as_bytes());
        if let Err(e) = fs::write(&script_path, &content_with_bom) {
            utils::dlog!("[Updater] ERROR: 写入PS1脚本失败: {}", e);
            return serde_json::json!({
                "success": false,
                "message": format!("写入更新脚本失败: {}", e)
            });
        }
        utils::dlog!("[Updater] PS1脚本已写入: {:?}", script_path);

        // schtasks /TR 只需要短命令: powershell -File "path.ps1"
        let task_cmd = format!(
            r#"powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "{}""#,
            script_path.to_string_lossy()
        );

        utils::dlog!("[Updater] task_name={}, task_cmd len={}", task_name, task_cmd.len());
        utils::dlog!("[Updater] task_cmd={}", task_cmd);

        // 创建一次性计划任务
        let create_result = std::process::Command::new("schtasks")
            .args(&[
                "/Create",
                "/TN", &task_name,
                "/TR", &task_cmd,
                "/SC", "ONCE",
                "/ST", "00:00",
                "/F",
                "/RL", "HIGHEST",
            ])
            .creation_flags(CREATE_NO_WINDOW)
            .output();

        match create_result {
            Ok(output) => {
                let stdout = String::from_utf8_lossy(&output.stdout);
                let stderr = String::from_utf8_lossy(&output.stderr);
                utils::dlog!("[Updater] schtasks /Create status={}, stdout={}, stderr={}", output.status, stdout.trim(), stderr.trim());
                if !output.status.success() {
                    let _ = fs::remove_file(&temp_file);
                    let _ = fs::remove_file(&script_path);
                    return serde_json::json!({
                        "success": false,
                        "message": format!("创建计划任务失败: {}", stderr)
                    });
                }
            }
            Err(e) => {
                utils::dlog!("[Updater] ERROR: schtasks命令执行失败: {}", e);
                let _ = fs::remove_file(&temp_file);
                let _ = fs::remove_file(&script_path);
                return serde_json::json!({
                    "success": false,
                    "message": format!("执行 schtasks 失败: {}", e)
                });
            }
        }

        // 立即运行计划任务
        utils::dlog!("[Updater] 执行 schtasks /Run ...");
        let run_result = std::process::Command::new("schtasks")
            .args(&["/Run", "/TN", &task_name])
            .creation_flags(CREATE_NO_WINDOW)
            .output();

        match run_result {
            Ok(output) => {
                let stdout = String::from_utf8_lossy(&output.stdout);
                let stderr = String::from_utf8_lossy(&output.stderr);
                utils::dlog!("[Updater] schtasks /Run status={}, stdout={}, stderr={}", output.status, stdout.trim(), stderr.trim());
                utils::dlog!("[Updater] 计划任务已启动，3秒后强制退出主程序");
                std::thread::spawn(|| {
                    std::thread::sleep(std::time::Duration::from_secs(3));
                    std::process::exit(0);
                });
            }
            Err(e) => {
                utils::dlog!("[Updater] ERROR: schtasks /Run 失败: {}", e);
                let _ = std::process::Command::new("schtasks")
                    .args(&["/Delete", "/TN", &task_name, "/F"])
                    .creation_flags(CREATE_NO_WINDOW)
                    .output();
                let _ = fs::remove_file(&temp_file);
                let _ = fs::remove_file(&script_path);
                return serde_json::json!({
                    "success": false,
                    "message": format!("运行计划任务失败: {}", e)
                });
            }
        }
    }

    // ========== macOS: DMG 安装脚本 ==========
    #[cfg(target_os = "macos")]
    {
        let script_path = script_path.with_extension("sh");
        // macOS: 下载的是 DMG 文件，需要挂载、复制 .app、卸载
        // current_exe 类似 /Applications/续杯助手.app/Contents/MacOS/续杯助手
        // 需要找到 .app 包的路径
        let sh_content = format!(
            r#"#!/bin/bash
set -e
export LANG=en_US.UTF-8

PID_TO_WAIT="{pid}"
DMG_PATH="{archive}"
CURRENT_EXE="{target}"

# 从可执行文件路径推断 .app 包路径
# 例如: /Applications/续杯助手.app/Contents/MacOS/续杯助手 -> /Applications/续杯助手.app
APP_PATH="$(echo "$CURRENT_EXE" | sed 's|/Contents/MacOS/.*||')"
APP_NAME="$(basename "$APP_PATH")"
APP_DIR="$(dirname "$APP_PATH")"
MOUNT_POINT="/Volumes/CursorRenewalUpdate_$$"

cleanup() {{
  hdiutil detach "$MOUNT_POINT" 2>/dev/null || true
  rm -f "$DMG_PATH"
  rm -f "$0"
}}
trap cleanup EXIT

echo "[Updater] 等待主程序退出 (PID: $PID_TO_WAIT)..."
while kill -0 "$PID_TO_WAIT" 2>/dev/null; do
  sleep 1
done
sleep 2

echo "[Updater] 挂载 DMG: $DMG_PATH"
hdiutil attach "$DMG_PATH" -mountpoint "$MOUNT_POINT" -nobrowse -quiet

# 在挂载点中查找 .app
NEW_APP=$(find "$MOUNT_POINT" -maxdepth 1 -name "*.app" | head -1)
if [ -z "$NEW_APP" ]; then
  echo "[Updater] ERROR: DMG 中未找到 .app 文件"
  exit 1
fi
echo "[Updater] 找到新版本: $NEW_APP"

echo "[Updater] 删除旧版本: $APP_PATH"
rm -rf "$APP_PATH"

echo "[Updater] 复制新版本到: $APP_DIR/"
cp -R "$NEW_APP" "$APP_DIR/"

echo "[Updater] 卸载 DMG"
hdiutil detach "$MOUNT_POINT" -quiet

echo "[Updater] 启动新版本..."
open "$APP_PATH"

echo "[Updater] 完成！"
"#,
            pid = pid,
            archive = temp_file.to_string_lossy(),
            target = current_exe.to_string_lossy(),
        );

        if let Err(e) = fs::write(&script_path, &sh_content) {
            utils::dlog!("[Updater] 写入 shell 脚本失败: {}", e);
            return serde_json::json!({
                "success": false,
                "message": format!("写入更新脚本失败: {}", e)
            });
        }

        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            let _ = fs::set_permissions(&script_path, fs::Permissions::from_mode(0o755));
        }

        utils::dlog!("[Updater] 启动 shell 安装脚本: {:?}", script_path);
        match std::process::Command::new("sh")
            .arg(&script_path)
            .spawn()
        {
            Ok(_) => {
                utils::dlog!("[Updater] shell 安装脚本已启动，等待主程序退出后执行替换");
            }
            Err(e) => {
                utils::dlog!("[Updater] 启动 shell 脚本失败: {}", e);
                let _ = fs::remove_file(&temp_file);
                let _ = fs::remove_file(&script_path);
                return serde_json::json!({
                    "success": false,
                    "message": format!("启动更新脚本失败: {}", e)
                });
            }
        }
    }

    // ========== Linux: Shell 安装脚本 ==========
    #[cfg(target_os = "linux")]
    {
        let script_path = script_path.with_extension("sh");
        let sh_content = format!(
            r#"#!/bin/sh
set -eu

PID_TO_WAIT="{pid}"
ARCHIVE_PATH="{archive}"
TARGET_EXECUTABLE="{target}"
TARGET_DIR="$(dirname "$TARGET_EXECUTABLE")"
REPLACEMENT_PATH="${{TARGET_EXECUTABLE}}.new"

cleanup() {{
  rm -f "$ARCHIVE_PATH"
  rm -f "$REPLACEMENT_PATH"
  rm -f "$0"
}}
trap cleanup EXIT

# 等待主程序退出
while kill -0 "$PID_TO_WAIT" 2>/dev/null; do
  sleep 1
done
sleep 1

# 复制新版本并设置权限
cp "$ARCHIVE_PATH" "$REPLACEMENT_PATH"
chmod +x "$REPLACEMENT_PATH"
mv -f "$REPLACEMENT_PATH" "$TARGET_EXECUTABLE"
chmod +x "$TARGET_EXECUTABLE"

# 后台启动新版本
cd "$TARGET_DIR"
nohup "$TARGET_EXECUTABLE" >/dev/null 2>&1 &
"#,
            pid = pid,
            archive = temp_file.to_string_lossy(),
            target = current_exe.to_string_lossy(),
        );

        if let Err(e) = fs::write(&script_path, &sh_content) {
            utils::dlog!("[Updater] 写入 shell 脚本失败: {}", e);
            return serde_json::json!({
                "success": false,
                "message": format!("写入更新脚本失败: {}", e)
            });
        }

        use std::os::unix::fs::PermissionsExt;
        let _ = fs::set_permissions(&script_path, fs::Permissions::from_mode(0o755));

        utils::dlog!("[Updater] 启动 shell 安装脚本: {:?}", script_path);
        match std::process::Command::new("sh")
            .arg(&script_path)
            .spawn()
        {
            Ok(_) => {
                utils::dlog!("[Updater] shell 安装脚本已启动，等待主程序退出后执行替换");
            }
            Err(e) => {
                utils::dlog!("[Updater] 启动 shell 脚本失败: {}", e);
                let _ = fs::remove_file(&temp_file);
                let _ = fs::remove_file(&script_path);
                return serde_json::json!({
                    "success": false,
                    "message": format!("启动更新脚本失败: {}", e)
                });
            }
        }
    }

    serde_json::json!({
        "success": true,
        "message": "更新文件下载完成，安装脚本已启动，程序退出后自动替换并重启"
    })
}
