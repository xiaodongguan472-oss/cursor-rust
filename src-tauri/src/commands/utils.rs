use std::path::PathBuf;
use std::env;

/// Get the Cursor data directory based on the operating system
pub fn get_cursor_data_dir() -> Option<PathBuf> {
    #[cfg(target_os = "windows")]
    {
        env::var("APPDATA").ok().map(|appdata| PathBuf::from(appdata).join("Cursor"))
    }
    #[cfg(target_os = "macos")]
    {
        dirs::home_dir().map(|h| h.join("Library").join("Application Support").join("Cursor"))
    }
    #[cfg(target_os = "linux")]
    {
        dirs::home_dir().map(|h| h.join(".config").join("Cursor"))
    }
}

/// Get the Cursor state.vscdb path
#[allow(dead_code)]
pub fn get_cursor_db_path() -> Option<PathBuf> {
    get_cursor_data_dir().map(|d| d.join("User").join("globalStorage").join("state.vscdb"))
}

/// Get the Cursor storage.json path
pub fn get_cursor_storage_json_path() -> Option<PathBuf> {
    get_cursor_data_dir().map(|d| d.join("User").join("globalStorage").join("storage.json"))
}

/// Get the app's user data directory for storing settings, card info, etc.
pub fn get_app_data_dir() -> PathBuf {
    #[cfg(target_os = "windows")]
    {
        let appdata = env::var("APPDATA").unwrap_or_else(|_| {
            dirs::home_dir()
                .unwrap_or_default()
                .join("AppData")
                .join("Roaming")
                .to_string_lossy()
                .to_string()
        });
        PathBuf::from(appdata).join("cursor-renewal")
    }
    #[cfg(not(target_os = "windows"))]
    {
        dirs::home_dir()
            .unwrap_or_default()
            .join(".cursor-renewal")
    }
}

/// Make an HTTP GET request and return JSON
pub async fn http_get_json(url: &str) -> Result<serde_json::Value, String> {
    let client = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(15))
        .build()
        .map_err(|e| format!("创建HTTP客户端失败: {}", e))?;

    let response = client
        .get(url)
        .header("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
        .header("Accept", "application/json, text/plain, */*")
        .send()
        .await
        .map_err(|e| format!("HTTP GET请求失败 [{}]: {}", url, e))?;

    let status = response.status();
    if !status.is_success() {
        return Err(format!("HTTP {} - 服务器返回错误", status));
    }
    let text = response.text().await.map_err(|e| format!("读取响应体失败: {}", e))?;

    serde_json::from_str(&text)
        .map_err(|e| format!("解析JSON失败 (HTTP {}): {}, 原始响应: {}", status, e, &text[..text.len().min(200)]))
}

/// Make an HTTP POST request with JSON body and return JSON
pub async fn http_post_json(url: &str, body: &serde_json::Value) -> Result<serde_json::Value, String> {
    let client = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(15))
        .build()
        .map_err(|e| format!("创建HTTP客户端失败: {}", e))?;

    let response = client
        .post(url)
        .header("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
        .header("Accept", "application/json, text/plain, */*")
        .header("Content-Type", "application/json")
        .json(body)
        .send()
        .await
        .map_err(|e| format!("HTTP POST请求失败 [{}]: {}", url, e))?;

    let status = response.status();
    if !status.is_success() {
        return Err(format!("HTTP {} - 服务器返回错误", status));
    }
    let text = response.text().await.map_err(|e| format!("读取响应体失败: {}", e))?;

    serde_json::from_str(&text)
        .map_err(|e| format!("解析JSON失败 (HTTP {}): {}, 原始响应: {}", status, e, &text[..text.len().min(200)]))
}

/// Generate a stable machine ID from system info
pub fn generate_stable_machine_id() -> String {
    use sha2::{Sha256, Digest};

    // Try to get real machine ID first
    if let Ok(id) = machine_uid::get() {
        return id;
    }

    // Fallback: generate from system info
    let mut hasher = Sha256::new();
    if let Some(home) = dirs::home_dir() {
        hasher.update(home.to_string_lossy().as_bytes());
    }
    if let Ok(name) = hostname::get() {
        hasher.update(name.to_string_lossy().as_bytes());
    }
    hasher.update(std::env::consts::OS.as_bytes());
    hasher.update(std::env::consts::ARCH.as_bytes());

    let result = hasher.finalize();
    hex::encode(&result[..16])
}

/// Check if a file is read-only
pub fn is_file_read_only(path: &std::path::Path) -> bool {
    if let Ok(metadata) = std::fs::metadata(path) {
        metadata.permissions().readonly()
    } else {
        false
    }
}

/// macOS: 清除文件的 BSD 不可变标志 (uchg / schg)
///
/// Cursor 续杯/破解工具常用 `chflags uchg` 给 storage.json 加锁，
/// 该标志比 chmod 优先级更高，POSIX 写权限不足以覆盖。
/// 必须先 `chflags nouchg` 才能修改文件。
/// Linux / Windows 平台为 no-op。
#[allow(unused_variables)]
pub fn clear_macos_immutable_flag(path: &std::path::Path) {
    #[cfg(target_os = "macos")]
    {
        if !path.exists() {
            return;
        }
        // nouchg: 用户不可变标志; noschg: 系统不可变标志（需 root，失败也无所谓）
        let path_str = path.to_string_lossy().to_string();
        let _ = std::process::Command::new("chflags")
            .args(["nouchg", &path_str])
            .output();
        let _ = std::process::Command::new("chflags")
            .args(["noschg", &path_str])
            .output();
    }
}

/// Temporarily remove read-only attribute, execute a closure, then restore
pub fn safe_modify_file<F>(path: &std::path::Path, modify_fn: F) -> Result<(), String>
where
    F: FnOnce() -> Result<(), String>,
{
    // macOS 必须先清除 chflags uchg，否则 chmod 完全无效
    clear_macos_immutable_flag(path);

    let was_readonly = is_file_read_only(path);

    if was_readonly {
        let mut perms = std::fs::metadata(path)
            .map_err(|e| format!("获取文件权限失败: {}", e))?
            .permissions();
        perms.set_readonly(false);
        std::fs::set_permissions(path, perms)
            .map_err(|e| format!("移除只读属性失败: {}", e))?;
    }

    let result = modify_fn();

    if was_readonly {
        if let Ok(metadata) = std::fs::metadata(path) {
            let mut perms = metadata.permissions();
            perms.set_readonly(true);
            let _ = std::fs::set_permissions(path, perms);
        }
    }

    result
}
