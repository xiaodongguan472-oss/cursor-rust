use std::path::PathBuf;
#[cfg_attr(not(target_os = "windows"), allow(unused_imports))]
use std::env;

// Release 模式下所有调试日志完全移除（防止 strings 提取模块信息）
#[cfg(debug_assertions)]
macro_rules! dlog {
    ($($arg:tt)*) => { println!($($arg)*) }
}
#[cfg(not(debug_assertions))]
macro_rules! dlog {
    ($($arg:tt)*) => {}
}
pub(crate) use dlog;

// ============================================================================
// 反逆向：API URL 多层加密
// 密钥分散 + 非线性变换，macOS 无壳场景也无法被自动化提取
// ============================================================================

// 密钥材料分散在不同常量中（编译后散布在 .rodata 不同位置）
#[doc(hidden)] pub const _M0: u32 = 0x7A3F_1D9E;
#[doc(hidden)] pub const _M1: u32 = 0x4B8C_E2A5;

// 密文（非 XOR 模式，无法用 XOR 扫描器自动提取）
const _CT: [u8; 22] = [
    0x5A, 0x2F, 0xEE, 0x23, 0x34, 0x9A, 0xC4, 0x92,
    0x89, 0xD0, 0xB2, 0x9F, 0xAB, 0x26, 0x82, 0x6E,
    0x5D, 0xF9, 0xAD, 0xEF, 0xEC, 0xEF,
];

/// 多步派生解密（rotate + sub + XOR with derived sub-keys）
#[inline(never)]
fn _dk() -> [u8; 4] {
    [
        ((_M0 >> 24) as u8) ^ (_M1 as u8),
        ((_M0 >> 16) as u8) ^ ((_M1 >> 8) as u8),
        ((_M0 >> 8) as u8) ^ ((_M1 >> 16) as u8),
        (_M0 as u8) ^ ((_M1 >> 24) as u8),
    ]
}

#[inline(always)]
pub fn api_base() -> String {
    let k = _dk();
    let mut out = Vec::with_capacity(_CT.len());
    for (i, &b) in _CT.iter().enumerate() {
        let s1 = b.wrapping_sub(k[i % 4]);
        let rot = (i % 5) + 1;
        let s2 = (s1 >> rot) | (s1 << (8 - rot)); // u8 rotate_right
        let s3 = s2 ^ k[(i + 3) % 4].wrapping_add(i as u8);
        out.push(s3);
    }
    String::from_utf8(out).unwrap_or_default()
}

#[inline(always)]
pub fn api_url(path: &str) -> String {
    let mut url = api_base();
    if !path.starts_with('/') {
        url.push('/');
    }
    url.push_str(path);
    url
}

// ============================================================================
// 反逆向：SQLite/Storage 字段名混淆助手
// 所有 cursorAuth/* / telemetry.* / cursorai/* 等敏感 key 都通过函数调用拼接
// 反编译看 .rdata 节区只能看到加密字节序列，看不到任何明文
// ============================================================================
pub mod keys {
    use obfstr::obfstr;
    // === cursorAuth/* ===
    #[inline(always)] pub fn auth_email() -> String { format!("{}{}", obfstr!("cursorAuth/"), obfstr!("cachedEmail")) }
    #[inline(always)] pub fn auth_access() -> String { format!("{}{}", obfstr!("cursorAuth/"), obfstr!("accessToken")) }
    #[inline(always)] pub fn auth_refresh() -> String { format!("{}{}", obfstr!("cursorAuth/"), obfstr!("refreshToken")) }
    #[inline(always)] pub fn auth_signup() -> String { format!("{}{}", obfstr!("cursorAuth/"), obfstr!("cachedSignUpType")) }
    #[inline(always)] pub fn auth_stripe() -> String { format!("{}{}", obfstr!("cursorAuth/"), obfstr!("stripeMembershipType")) }
    // === cursorai/* ===
    #[inline(always)] pub fn ai_server_config() -> String { format!("{}{}", obfstr!("cursorai/"), obfstr!("serverConfig")) }
    #[inline(always)] pub fn ai_feature_status() -> String { format!("{}{}", obfstr!("cursorai/"), obfstr!("featureStatusCache")) }
    #[inline(always)] pub fn ai_feature_config() -> String { format!("{}{}", obfstr!("cursorai/"), obfstr!("featureConfigCache")) }
    // === telemetry.* ===
    #[inline(always)] pub fn telem_machine() -> String { format!("{}{}", obfstr!("telemetry."), obfstr!("machineId")) }
    #[inline(always)] pub fn telem_mac() -> String { format!("{}{}", obfstr!("telemetry."), obfstr!("macMachineId")) }
    #[inline(always)] pub fn telem_dev() -> String { format!("{}{}", obfstr!("telemetry."), obfstr!("devDeviceId")) }
    #[inline(always)] pub fn telem_sqm() -> String { format!("{}{}", obfstr!("telemetry."), obfstr!("sqmId")) }
    // === auth/ + 杂项 ===
    #[inline(always)] pub fn auth_user() -> String { format!("{}{}", obfstr!("auth/"), obfstr!("user")) }
    #[inline(always)] pub fn auth_session() -> String { format!("{}{}", obfstr!("auth/"), obfstr!("session")) }
    #[inline(always)] pub fn vscode_chat_token() -> String { format!("{}{}", obfstr!("vscode.chat."), obfstr!("access-token")) }
    #[inline(always)] pub fn auth0_value() -> String { obfstr!("Auth_0").to_string() }
}


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

/// Get the legacy (Electron) app data directory
pub fn get_legacy_app_data_dir() -> PathBuf {
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
        PathBuf::from(appdata).join("cursor-renewal-client")
    }
    #[cfg(not(target_os = "windows"))]
    {
        dirs::home_dir()
            .unwrap_or_default()
            .join(".cursor-renewal-client")
    }
}

/// Migrate data from legacy Electron app directory to new Tauri app directory
/// Files to migrate: device_id.txt, card_info.json, settings.json
pub fn migrate_legacy_data() {
    let new_dir = get_app_data_dir();
    let legacy_dir = get_legacy_app_data_dir();
    let migrated_marker = new_dir.join("migrated.txt");
    
    // Skip if already migrated
    if migrated_marker.exists() {
        return;
    }
    
    // Skip if legacy directory doesn't exist
    if !legacy_dir.exists() {
        // Create marker anyway to skip future checks
        let _ = std::fs::create_dir_all(&new_dir);
        let _ = std::fs::write(&migrated_marker, "migrated");
        return;
    }
    
    // Ensure new directory exists
    let _ = std::fs::create_dir_all(&new_dir);
    
    // Files to migrate
    let files_to_migrate = ["device_id.txt", "card_info.json", "settings.json"];
    
    for file_name in &files_to_migrate {
        let legacy_file = legacy_dir.join(file_name);
        let new_file = new_dir.join(file_name);
        
        // Only copy if legacy file exists and new file doesn't
        if legacy_file.exists() && !new_file.exists() {
            if let Ok(content) = std::fs::read(&legacy_file) {
                let _ = std::fs::write(&new_file, content);
                dlog!("[Migration] Copied {} from legacy directory", file_name);
            }
        }
    }
    
    // Create migration marker
    let _ = std::fs::write(&migrated_marker, format!("migrated at {}", chrono::Local::now()));
    dlog!("[Migration] Legacy data migration completed");
}

/// Get cached device ID, or generate and cache if not exists
/// This is the stable device ID sent to backend API
pub fn get_cached_device_id() -> String {
    let app_dir = get_app_data_dir();
    let device_id_file = app_dir.join("device_id.txt");
    
    // Try to read cached device ID
    if device_id_file.exists() {
        if let Ok(cached) = std::fs::read_to_string(&device_id_file) {
            let cached = cached.trim().to_string();
            if cached.len() > 10 {
                return cached;
            }
        }
    }
    
    // Generate new device ID
    let device_id = generate_stable_machine_id();
    
    // Cache it
    let _ = std::fs::create_dir_all(&app_dir);
    let _ = std::fs::write(&device_id_file, &device_id);
    dlog!("[DeviceID] Generated and cached new device ID");
    
    device_id
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
