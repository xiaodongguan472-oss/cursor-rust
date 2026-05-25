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

// ============================================================================
// macOS App Management 提权写入策略
//
// 背景：macOS Sonoma/Sequoia 引入 App Management TCC 保护，
//   /Applications/Cursor.app 内的文件即便 root 也会 EPERM。
// 解决：整包副本 → 在副本里改 → 由内向外 ad-hoc 重签 → 原子替换 (rm + mv)。
// 与 Python 参考实现 core/cursor_injector.py 中的 _mac_replace_file_in_app 等价。
// ============================================================================

/// 检测路径是否需要提权才能写入（macOS 用，其他平台一律返回 false）
#[cfg(target_os = "macos")]
pub fn mac_needs_privilege(path: &std::path::Path) -> bool {
    let parent = match path.parent() {
        Some(p) => p,
        None => return true,
    };
    // 直接尝试写一个临时文件来判断
    let probe = parent.join(".mc_perm_probe");
    match std::fs::OpenOptions::new()
        .create(true)
        .write(true)
        .truncate(true)
        .open(&probe)
    {
        Ok(_) => {
            let _ = std::fs::remove_file(&probe);
            false
        }
        Err(_) => true,
    }
}

#[cfg(not(target_os = "macos"))]
#[allow(dead_code)]
pub fn mac_needs_privilege(_path: &std::path::Path) -> bool { false }

/// 向上找到包含 target 的 .app 根目录
#[cfg(target_os = "macos")]
pub fn mac_find_app_root(path: &std::path::Path) -> Option<std::path::PathBuf> {
    let mut p = path.to_path_buf();
    loop {
        if p.extension().and_then(|s| s.to_str()) == Some("app") {
            return Some(p);
        }
        match p.parent() {
            Some(parent) => p = parent.to_path_buf(),
            None => return None,
        }
    }
}

/// 通过 osascript 提权将 src_file 替换到 target_path（target_path 必须在 .app 内）。
/// 步骤：
/// 1. 复制 .app → .wxtmp 副本（APFS clonefile，秒级）
/// 2. 解锁副本：chflags / chmod / xattr
/// 3. 在副本里写入新文件
/// 4. 移除签名，由内向外重签 Helper Bundles + 外层 bundle
/// 5. 原子替换：rm -rf 旧 .app + mv 副本 → .app
#[cfg(target_os = "macos")]
pub fn mac_privileged_replace_in_app(
    src_file: &std::path::Path,
    target_path: &std::path::Path,
) -> Result<(), String> {
    let app_root = mac_find_app_root(target_path)
        .ok_or_else(|| format!("未定位到 .app 根目录: {}", target_path.display()))?;
    let rel = target_path
        .strip_prefix(&app_root)
        .map_err(|e| format!("路径计算失败: {}", e))?;

    let app_str = app_root.to_string_lossy().to_string();
    let tmp_str = format!("{}.wxtmp", app_str);

    fn esc(s: &str) -> String { s.replace('\'', "'\\''") }

    let e_app = esc(&app_str);
    let e_tmp = esc(&tmp_str);
    let e_src = esc(&src_file.to_string_lossy());
    let e_rel = esc(&rel.to_string_lossy());
    let e_fw = esc(&format!("{}/Contents/Frameworks", &tmp_str));

    // 注意：所有步骤用 && 串联，任何一步失败则整体失败，副本残留下次清理
    let shell_cmd = format!(
        "rm -rf '{e_tmp}' && \
         cp -a '{e_app}' '{e_tmp}' && \
         chflags -R nouchg '{e_tmp}' && \
         chmod -R u+w '{e_tmp}' && \
         xattr -cr '{e_tmp}' && \
         cp -f '{e_src}' '{e_tmp}/{e_rel}' && \
         (codesign --remove-signature '{e_tmp}' || true) && \
         (if [ -d '{e_fw}' ]; then find '{e_fw}' -name '*.app' -type d -print0 | xargs -0 -I HELPER codesign --force --timestamp=none --sign - 'HELPER'; fi) && \
         codesign --force --timestamp=none --sign - '{e_tmp}' && \
         rm -rf '{e_app}' && \
         mv '{e_tmp}' '{e_app}'",
        e_app = e_app, e_tmp = e_tmp, e_src = e_src, e_rel = e_rel, e_fw = e_fw,
    );

    // 转义双引号以嵌入 AppleScript 字符串
    let osa_script = format!(
        "do shell script \"{}\" with administrator privileges",
        shell_cmd.replace('\\', "\\\\").replace('"', "\\\""),
    );

    let output = std::process::Command::new("osascript")
        .args(["-e", &osa_script])
        .output()
        .map_err(|e| format!("osascript 调用失败: {}", e))?;

    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr).to_string();
        let lower = stderr.to_lowercase();
        if lower.contains("user canceled") || lower.contains("-128") {
            return Err("您取消了授权，请重新操作并输入密码".to_string());
        }
        return Err(format!("提权写入失败: {}", stderr.trim()));
    }
    Ok(())
}

/// 将新内容写入 .app 内的目标 JS 文件（自动判断是否需要 macOS 提权）。
/// - macOS 需要提权：写到临时文件 → osascript 替换
/// - macOS 不需要提权 或 其他平台：直接 fs::write
/// 适用于 workbench.desktop.main.js / extensionHostProcess.js 等所有 .app 内文件。
pub fn write_file_in_app(target_path: &std::path::Path, new_content: &str) -> Result<(), String> {
    #[cfg(target_os = "macos")]
    {
        if mac_needs_privilege(target_path) {
            // 写入临时文件
            let tmp_dir = std::env::temp_dir();
            let tmp_file = tmp_dir.join(format!("mc_inject_{}.js", std::process::id()));
            std::fs::write(&tmp_file, new_content)
                .map_err(|e| format!("写入临时文件失败: {}", e))?;
            let res = mac_privileged_replace_in_app(&tmp_file, target_path);
            let _ = std::fs::remove_file(&tmp_file);
            return res;
        }
    }
    // 直接写（其他平台 / macOS 但可直接写入）
    safe_modify_file(target_path, || {
        std::fs::write(target_path, new_content).map_err(|e| format!("写入文件失败: {}", e))
    })
}
