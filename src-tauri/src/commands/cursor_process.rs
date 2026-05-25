use serde::{Deserialize, Serialize};
use std::process::Command;
use std::path::Path;
use super::cursor_paths;

#[cfg(target_os = "macos")]
use super::settings;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProcessResult {
    pub success: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub message: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub error: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub warning: Option<bool>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub workspace: Option<String>,
}

pub fn is_cursor_running() -> bool {
    #[cfg(target_os = "windows")]
    {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x08000000;
        if let Ok(output) = Command::new("tasklist")
            .args(["/FI", "IMAGENAME eq Cursor.exe"])
            .creation_flags(CREATE_NO_WINDOW)
            .output()
        {
            let stdout = String::from_utf8_lossy(&output.stdout);
            if stdout.contains("Cursor.exe") {
                return true;
            }
        }
        // Fallback: PowerShell
        if let Ok(output) = Command::new("powershell")
            .args(["-Command", "Get-Process -Name Cursor -ErrorAction SilentlyContinue | Select-Object -First 1"])
            .creation_flags(CREATE_NO_WINDOW)
            .output()
        {
            let stdout = String::from_utf8_lossy(&output.stdout);
            if !stdout.trim().is_empty() {
                return true;
            }
        }
        false
    }

    #[cfg(target_os = "macos")]
    {
        // 优先用 pgrep -f 匹配 Cursor.app 路径，避免 shell 转义问题
        let cursor_path = get_mac_cursor_app_path();
        if let Ok(output) = Command::new("pgrep")
            .args(["-f", &cursor_path])
            .output()
        {
            if !String::from_utf8_lossy(&output.stdout).trim().is_empty() {
                return true;
            }
        }
        // Fallback：按进程名 Cursor 检测
        if let Ok(output) = Command::new("pgrep")
            .args(["-x", "Cursor"])
            .output()
        {
            return !String::from_utf8_lossy(&output.stdout).trim().is_empty();
        }
        false
    }

    #[cfg(target_os = "linux")]
    {
        if let Ok(output) = Command::new("pgrep").args(["-f", "cursor"]).output() {
            let stdout = String::from_utf8_lossy(&output.stdout);
            return !stdout.trim().is_empty();
        }
        false
    }
}

pub fn kill_cursor() -> bool {
    #[cfg(target_os = "windows")]
    {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x08000000;
        Command::new("taskkill")
            .args(["/F", "/IM", "Cursor.exe"])
            .creation_flags(CREATE_NO_WINDOW)
            .output()
            .is_ok()
    }

    #[cfg(target_os = "macos")]
    {
        let cursor_path = get_mac_cursor_app_path();
        let cmd = format!(
            "osascript -e 'quit app \"Cursor\"' 2>/dev/null; sleep 1; pkill -9 -f '{}' 2>/dev/null; true",
            cursor_path
        );
        Command::new("sh").args(["-c", &cmd]).output().is_ok()
    }

    #[cfg(target_os = "linux")]
    {
        Command::new("pkill").args(["-9", "cursor"]).output().is_ok()
    }
}

#[cfg(target_os = "macos")]
fn get_mac_cursor_app_path() -> String {
    let s = settings::load_settings();
    if !s.custom_cursor_path.is_empty() {
        let custom = s.custom_cursor_path.trim().trim_matches(|c| c == '\'' || c == '"');
        if custom.ends_with(".app") || custom.ends_with(".app/") {
            return custom.trim_end_matches('/').to_string();
        }
    }
    "/Applications/Cursor.app".to_string()
}

#[tauri::command]
pub async fn check_cursor_running() -> bool {
    is_cursor_running()
}

#[tauri::command]
pub async fn force_close_cursor() -> ProcessResult {
    if !is_cursor_running() {
        return ProcessResult {
            success: true,
            message: Some("Cursor未运行或已关闭".to_string()),
            error: None, warning: None, workspace: None,
        };
    }

    kill_cursor();

    // Wait and verify
    for _attempt in 0..30 {
        std::thread::sleep(std::time::Duration::from_millis(500));
        if !is_cursor_running() {
            return ProcessResult {
                success: true,
                message: Some("所有Cursor进程已确认关闭".to_string()),
                error: None, warning: None, workspace: None,
            };
        }
    }

    // Retry
    kill_cursor();
    std::thread::sleep(std::time::Duration::from_secs(2));

    if is_cursor_running() {
        ProcessResult {
            success: false,
            message: None,
            error: Some("部分Cursor进程未能关闭，请手动关闭后重试".to_string()),
            warning: Some(true),
            workspace: None,
        }
    } else {
        ProcessResult {
            success: true,
            message: Some("所有Cursor进程已确认关闭（重试后成功）".to_string()),
            error: None, warning: None, workspace: None,
        }
    }
}

fn get_cursor_executable() -> Result<(String, String), String> {
    let paths = cursor_paths::get_cursor_paths();
    let base_path = paths.base_path.ok_or("无法获取Cursor路径")?;
    if paths.error.is_some() {
        return Err(paths.error.unwrap());
    }

    let install_path = cursor_paths::get_cursor_install_from_base_path(&base_path);

    #[cfg(target_os = "windows")]
    let exe = install_path.join("Cursor.exe");

    #[cfg(target_os = "macos")]
    let exe = install_path.clone(); // install_path 已经是 .app 路径

    #[cfg(target_os = "linux")]
    let exe = install_path.join("cursor");

    let exe_str = exe.to_string_lossy().to_string();
    let install_str = install_path.to_string_lossy().to_string();

    if !exe.exists() {
        return Err(format!("Cursor可执行文件不存在: {}", exe_str));
    }

    Ok((exe_str, install_str))
}

fn launch_cursor_with_args(args: &[&str]) -> Result<(), String> {
    let (exe_path, _) = get_cursor_executable()?;

    #[cfg(target_os = "windows")]
    {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x08000000;
        Command::new(&exe_path)
            .args(args)
            .creation_flags(CREATE_NO_WINDOW)
            .spawn()
            .map_err(|e| format!("启动Cursor失败: {}", e))?;
    }

    #[cfg(target_os = "macos")]
    {
        let mut cmd_args = vec!["-a", &exe_path];
        if !args.is_empty() {
            cmd_args.push("--args");
            cmd_args.extend(args.iter());
        }
        Command::new("open")
            .args(&cmd_args)
            .spawn()
            .map_err(|e| format!("启动Cursor失败: {}", e))?;
    }

    #[cfg(target_os = "linux")]
    {
        Command::new(&exe_path)
            .args(args)
            .spawn()
            .map_err(|e| format!("启动Cursor失败: {}", e))?;
    }

    Ok(())
}

#[tauri::command]
pub async fn restart_cursor(_cursor_path: String) -> bool {
    kill_cursor();
    std::thread::sleep(std::time::Duration::from_secs(1));
    launch_cursor_with_args(&[]).is_ok()
}

#[tauri::command]
pub async fn restart_cursor_complete() -> ProcessResult {
    if is_cursor_running() {
        kill_cursor();
        std::thread::sleep(std::time::Duration::from_secs(2));
    }

    match launch_cursor_with_args(&[]) {
        Ok(()) => ProcessResult {
            success: true,
            message: Some("Cursor重启成功".to_string()),
            error: None, warning: None, workspace: None,
        },
        Err(e) => ProcessResult {
            success: false,
            message: None,
            error: Some(format!("启动Cursor失败: {}", e)),
            warning: None, workspace: None,
        },
    }
}

#[tauri::command]
pub async fn launch_cursor(workspace_path: Option<String>) -> ProcessResult {
    let args: Vec<String> = match &workspace_path {
        Some(p) if !p.is_empty() && Path::new(p).exists() => vec![p.clone()],
        _ => vec![],
    };

    let args_refs: Vec<&str> = args.iter().map(|s| s.as_str()).collect();

    match launch_cursor_with_args(&args_refs) {
        Ok(()) => ProcessResult {
            success: true,
            message: Some("Cursor启动成功".to_string()),
            error: None, warning: None,
            workspace: workspace_path,
        },
        Err(e) => ProcessResult {
            success: false,
            message: None,
            error: Some(e),
            warning: None, workspace: None,
        },
    }
}
