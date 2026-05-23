use std::process::Command;
use super::utils;

#[tauri::command]
pub async fn get_current_permissions() -> serde_json::Value {
    let is_admin;

    #[cfg(target_os = "windows")]
    {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x08000000;
        is_admin = match Command::new("net")
            .args(["session"])
            .creation_flags(CREATE_NO_WINDOW)
            .output()
        {
            Ok(output) => output.status.success(),
            Err(_) => false,
        };
    }

    #[cfg(target_os = "macos")]
    {
        // macOS 上 root 不是必需的：只要 /Applications/Cursor.app 可写就视为有权限
        let euid_root = unsafe { libc::geteuid() } == 0;
        if euid_root {
            is_admin = true;
        } else {
            // 用 libc::access 检测 Cursor 安装目录是否可写
            let target = std::ffi::CString::new("/Applications/Cursor.app").unwrap_or_default();
            let writable = unsafe { libc::access(target.as_ptr(), libc::W_OK) } == 0;
            is_admin = writable;
        }
    }

    #[cfg(target_os = "linux")]
    {
        is_admin = unsafe { libc::geteuid() } == 0;
    }

    let (level, description) = if is_admin {
        #[cfg(target_os = "windows")]
        let r = ("administrator", "管理员权限");
        #[cfg(target_os = "macos")]
        let r = if unsafe { libc::geteuid() } == 0 {
            ("root", "Root权限")
        } else {
            ("user_writable", "普通用户（具备Cursor目录写权限）")
        };
        #[cfg(target_os = "linux")]
        let r = ("root", "Root权限");
        r
    } else {
        ("user", "普通用户权限")
    };

    let username = whoami::username();

    serde_json::json!({
        "success": true,
        "isAdmin": is_admin,
        "level": level,
        "description": description,
        "platform": std::env::consts::OS,
        "userId": username,
        "groupId": ""
    })
}

#[tauri::command]
pub async fn disable_cursor_auto_update() -> serde_json::Value {
    let settings_path = {
        #[cfg(target_os = "windows")]
        {
            dirs::home_dir().map(|h| h.join("AppData").join("Roaming").join("Cursor").join("User").join("settings.json"))
        }
        #[cfg(target_os = "macos")]
        {
            dirs::home_dir().map(|h| h.join("Library").join("Application Support").join("Cursor").join("User").join("settings.json"))
        }
        #[cfg(target_os = "linux")]
        {
            dirs::home_dir().map(|h| h.join(".config").join("Cursor").join("User").join("settings.json"))
        }
    };

    let path = match settings_path {
        Some(p) => p,
        None => {
            return serde_json::json!({
                "success": false,
                "error": "无法确定Cursor设置路径"
            });
        }
    };

    // Ensure directory exists
    if let Some(parent) = path.parent() {
        let _ = std::fs::create_dir_all(parent);
    }

    // Read existing settings or create new
    let mut settings: serde_json::Value = if path.exists() {
        match std::fs::read_to_string(&path) {
            Ok(content) => serde_json::from_str(&content).unwrap_or(serde_json::json!({})),
            Err(_) => serde_json::json!({}),
        }
    } else {
        serde_json::json!({})
    };

    // Set update settings
    if let Some(obj) = settings.as_object_mut() {
        obj.insert("update.mode".to_string(), serde_json::json!("none"));
        obj.insert("update.enableWindowsBackgroundUpdates".to_string(), serde_json::json!(false));
    }

    let serialized = serde_json::to_string_pretty(&settings).unwrap_or_default();
    let write_result = utils::safe_modify_file(&path, || {
        std::fs::write(&path, &serialized).map_err(|e| format!("写入设置失败: {}", e))
    });
    match write_result {
        Ok(_) => serde_json::json!({
            "success": true,
            "message": "已禁用Cursor自动更新"
        }),
        Err(e) => serde_json::json!({
            "success": false,
            "error": e
        }),
    }
}
