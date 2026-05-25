use std::fs;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Mutex;
use sha2::{Sha256, Digest};
use rusqlite::Connection;
use tauri::{AppHandle, Manager};
use super::utils;
use super::cursor_paths;
use super::workbench_inject;

static AUTO_SWITCH_ENABLED: AtomicBool = AtomicBool::new(false);
static AUTO_SWITCH_BUSY: AtomicBool = AtomicBool::new(false);
static AUTO_SWITCH_CARD_CODE: Mutex<Option<String>> = Mutex::new(None);

const EH_PATCH_START: &str = "/* MOCURSO_EH_PATCH_START */";
const EH_PATCH_END: &str = "/* MOCURSO_EH_PATCH_END */";
const CURSOR_API: &str = "https://api2.cursor.sh";
const CURSOR_WEB: &str = "https://cursor.com";
const CURSOR_USER_AGENT: &str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Cursor/0.50.5 Chrome/128.0.6613.186 Electron/32.2.7 Safari/537.36";

fn get_data_dir() -> PathBuf {
    let home = dirs::home_dir().unwrap_or_default();
    home.join(".cursor-renewal")
}

fn get_active_token_file() -> PathBuf {
    get_data_dir().join("active_token")
}

fn get_ext_host_js_path(cursor_install_path: &Path) -> PathBuf {
    #[cfg(target_os = "macos")]
    {
        cursor_install_path
            .join("Contents")
            .join("Resources")
            .join("app")
            .join("out")
            .join("vs")
            .join("workbench")
            .join("api")
            .join("node")
            .join("extensionHostProcess.js")
    }
    #[cfg(not(target_os = "macos"))]
    {
        cursor_install_path
            .join("resources")
            .join("app")
            .join("out")
            .join("vs")
            .join("workbench")
            .join("api")
            .join("node")
            .join("extensionHostProcess.js")
    }
}

fn build_eh_inject_code() -> String {
    // 与 Electron 原版保持一致：路径中的反斜杠统一为正斜杠
    let token_file = get_active_token_file();
    let token_path = token_file.to_string_lossy().replace('\\', "/");

    format!(
        "{start}\n\
const _mcM=await import('node:module');\n\
const _mcR=_mcM.createRequire(import.meta.url);\n\
const _mcF=_mcR('fs');\n\
const _mcTF='{token}';\n\
let _mcTk=null,_mcLt=0;\n\
function _mcGT(){{const n=Date.now();if(n-_mcLt>500){{_mcLt=n;try{{_mcTk=_mcF.readFileSync(_mcTF,'utf8').trim()||null;}}catch(e){{_mcTk=null;}}}}return _mcTk;}}\n\
try{{const _h2=_mcR('http2');const _oC=_h2.connect;_h2.connect=function(a,...r){{const s=_oC.call(_h2,a,...r);if(typeof a==='string'&&(a.includes('cursor.sh')||a.includes('cursor.com'))){{const _oR=s.request.bind(s);s.request=function(h,...ra){{const t=_mcGT();if(t&&h)h['authorization']='Bearer '+t;return _oR(h,...ra);}};}}return s;}};}}catch(e){{}}\n\
try{{const _hs=_mcR('https');const _oR=_hs.request;_hs.request=function(o,...ra){{if(o&&typeof o==='object'&&o.hostname&&(o.hostname.includes('cursor.sh')||o.hostname.includes('cursor.com'))){{const t=_mcGT();if(t&&o.headers)o.headers['authorization']='Bearer '+t;}}return _oR.call(_hs,o,...ra);}};}}catch(e){{}}\n\
try{{if(typeof globalThis.fetch==='function'&&!globalThis._mcOF){{globalThis._mcOF=globalThis.fetch;globalThis.fetch=function(i,init){{const t=_mcGT();if(t){{let u=typeof i==='string'?i:(i instanceof URL?i.href:i?.url||'');if(u.includes('cursor.sh')||u.includes('cursor.com')){{init=init||{{}};init.headers=init.headers||{{}};if(typeof init.headers.set==='function')init.headers.set('authorization','Bearer '+t);else init.headers['authorization']='Bearer '+t;}}}}return globalThis._mcOF(i,init);}};}}}}catch(e){{}}\n\
{end}\n",
        start = EH_PATCH_START,
        end = EH_PATCH_END,
        token = token_path,
    )
}

fn do_patch_ext_host(cursor_install_path: &Path) -> serde_json::Value {
    let eh_path = get_ext_host_js_path(cursor_install_path);

    if !eh_path.exists() {
        return serde_json::json!({
            "success": false, "patched": false,
            "error": format!("extensionHostProcess.js not found: {}", eh_path.display())
        });
    }

    let content = match fs::read_to_string(&eh_path) {
        Ok(c) => c,
        Err(e) => {
            return serde_json::json!({
                "success": false, "patched": false,
                "error": format!("读取文件失败: {}", e)
            });
        }
    };

    // Already patched?
    if content.contains(EH_PATCH_START) {
        return serde_json::json!({"success": true, "patched": true, "message": "已经注入过补丁"});
    }

    // Create backup
    let backup = format!("{}.bak", eh_path.to_string_lossy());
    if !Path::new(&backup).exists() {
        let _ = fs::copy(&eh_path, &backup);
    }

    let inject_code = build_eh_inject_code();
    let new_content = format!("{}{}", inject_code, content);

    // macOS Sonoma+ App Management TCC: 走 osascript 提权 + 副本重签 + 原子替换
    let write_result = utils::write_file_in_app(&eh_path, &new_content);

    match write_result {
        Ok(()) => {
            // macOS 非提权场景兜底重签（提权路径下副本已重签）
            #[cfg(target_os = "macos")]
            {
                if !utils::mac_needs_privilege(&eh_path) {
                    let app_path = cursor_install_path.to_string_lossy();
                    let _ = std::process::Command::new("xattr")
                        .args(["-cr", &app_path])
                        .output();
                    let _ = std::process::Command::new("codesign")
                        .args(["--force", "--deep", "--sign", "-", &app_path])
                        .output();
                }
            }

            serde_json::json!({"success": true, "patched": true, "message": "补丁注入成功"})
        }
        Err(e) => serde_json::json!({"success": false, "patched": false, "error": e}),
    }
}

fn do_unpatch_ext_host(cursor_install_path: &Path) -> serde_json::Value {
    let eh_path = get_ext_host_js_path(cursor_install_path);

    if !eh_path.exists() {
        return serde_json::json!({"success": false, "patched": false, "error": "文件不存在"});
    }

    let content = match fs::read_to_string(&eh_path) {
        Ok(c) => c,
        Err(e) => {
            return serde_json::json!({"success": false, "patched": false, "error": e.to_string()});
        }
    };

    if !content.contains(EH_PATCH_START) {
        return serde_json::json!({"success": true, "patched": false, "message": "未检测到补丁"});
    }

    // Remove patch
    let new_content = if let (Some(start_idx), Some(end_idx)) = (
        content.find(EH_PATCH_START),
        content.find(EH_PATCH_END),
    ) {
        let end_with_marker = end_idx + EH_PATCH_END.len();
        let mut result = String::new();
        result.push_str(&content[..start_idx]);
        if end_with_marker < content.len() {
            result.push_str(&content[end_with_marker..]);
        }
        result.trim_start().to_string()
    } else {
        content
    };

    let write_result = utils::write_file_in_app(&eh_path, &new_content);

    match write_result {
        Ok(()) => {
            #[cfg(target_os = "macos")]
            {
                if !utils::mac_needs_privilege(&eh_path) {
                    let app_path = cursor_install_path.to_string_lossy();
                    let _ = std::process::Command::new("xattr")
                        .args(["-cr", &app_path])
                        .output();
                    let _ = std::process::Command::new("codesign")
                        .args(["--force", "--deep", "--sign", "-", &app_path])
                        .output();
                }
            }
            serde_json::json!({"success": true, "patched": false, "message": "补丁已移除"})
        }
        Err(e) => serde_json::json!({"success": false, "patched": true, "error": e}),
    }
}

fn do_check_ext_host_patched(cursor_install_path: &Path) -> bool {
    let eh_path = get_ext_host_js_path(cursor_install_path);
    if let Ok(content) = fs::read_to_string(&eh_path) {
        content.contains(EH_PATCH_START)
    } else {
        false
    }
}

// ========== Token file operations ==========

fn do_write_active_token(token: &str) -> bool {
    let file = get_active_token_file();
    let _ = fs::create_dir_all(file.parent().unwrap());
    fs::write(&file, token).is_ok()
}

fn do_read_active_token() -> Option<String> {
    let file = get_active_token_file();
    fs::read_to_string(&file).ok().map(|s| s.trim().to_string()).filter(|s| !s.is_empty())
}

fn do_clear_active_token() -> bool {
    let file = get_active_token_file();
    if file.exists() { fs::remove_file(&file).is_ok() } else { true }
}

// ========== Usage checking ==========

async fn https_get(url: &str, headers: &[(&str, &str)]) -> Result<serde_json::Value, String> {
    let client = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(15))
        .build()
        .map_err(|e| e.to_string())?;

    let mut req = client.get(url).header("User-Agent", CURSOR_USER_AGENT);
    for (k, v) in headers {
        req = req.header(*k, *v);
    }

    let resp = req.send().await.map_err(|e| e.to_string())?;
    let status = resp.status().as_u16();
    if status == 401 || status == 403 {
        return Err(format!("HTTP {}", status));
    }
    resp.json().await.map_err(|e| e.to_string())
}

fn decode_jwt_payload(token: &str) -> Option<serde_json::Value> {
    let parts: Vec<&str> = token.split('.').collect();
    if parts.len() < 2 { return None; }
    let payload = parts[1];
    // Add padding
    let _padded = match payload.len() % 4 {
        2 => format!("{}==", payload),
        3 => format!("{}=", payload),
        _ => payload.to_string(),
    };
    let decoded = base64::Engine::decode(
        &base64::engine::general_purpose::URL_SAFE_NO_PAD,
        payload,
    ).ok()?;
    serde_json::from_slice(&decoded).ok()
}

fn extract_user_id(token: &str) -> Option<String> {
    let payload = decode_jwt_payload(token)?;
    payload.get("sub").and_then(|v| v.as_str()).map(String::from)
}

fn is_token_expired(token: &str) -> bool {
    if let Some(payload) = decode_jwt_payload(token) {
        if let Some(exp) = payload.get("exp").and_then(|v| v.as_i64()) {
            let now = chrono::Utc::now().timestamp();
            return now >= exp;
        }
    }
    false
}

async fn fetch_usage_summary(token: &str) -> Result<serde_json::Value, String> {
    let user_id = extract_user_id(token).unwrap_or_default();
    let url = format!("{}/api/usage-summary?user={}", CURSOR_WEB, user_id);
    let cookie = format!("WorkosCursorSessionToken={}%3A%3A{}", user_id, token);
    https_get(&url, &[
        ("Cookie", &cookie),
        ("Referer", &format!("{}/settings", CURSOR_WEB)),
    ]).await
}

async fn fetch_stripe_profile(token: &str) -> Result<serde_json::Value, String> {
    let url = format!("{}/auth/full_stripe_profile", CURSOR_API);
    https_get(&url, &[("Authorization", &format!("Bearer {}", token))]).await
}

async fn do_check_account_status(token: &str) -> serde_json::Value {
    // ── 检查 1: token 是否过期 ──
    if token.is_empty() {
        return serde_json::json!({
            "needsSwitch": true, "reason": "no_token", "percentUsed": 0
        });
    }
    if is_token_expired(token) {
        return serde_json::json!({
            "needsSwitch": true, "reason": "token_expired", "percentUsed": 0
        });
    }

    // ── 检查 2: 调 /api/usage-summary（核心检测，与 Electron 一致） ──
    let mut percent_used: f64 = 0.0;
    let membership;
    let display_message;
    let mut total_quota: f64 = 0.0;
    let mut needs_switch = false;
    let mut reason = String::new();

    match fetch_usage_summary(token).await {
        Ok(usage) => {
            membership = usage
                .get("membershipType")
                .and_then(|v| v.as_str())
                .unwrap_or("")
                .to_string();
            display_message = usage
                .get("autoModelSelectedDisplayMessage")
                .and_then(|v| v.as_str())
                .unwrap_or("")
                .to_string();

            if let Some(plan) = usage.get("individualUsage").and_then(|v| v.get("plan")) {
                percent_used = plan
                    .get("totalPercentUsed")
                    .and_then(|v| v.as_f64())
                    .unwrap_or(0.0);
                total_quota = plan
                    .get("breakdown")
                    .and_then(|b| b.get("total"))
                    .and_then(|v| v.as_f64())
                    .unwrap_or(0.0);

                // ★ 唯一换号条件：总用量 >= 95%
                if percent_used >= 95.0 {
                    needs_switch = true;
                    reason = "quota_exhausted_percent".to_string();
                }
            }
        }
        Err(e) => {
            if e.contains("401") || e.contains("403") {
                // API 认证失败，标记原因让上层累计判断（不立即换号）
                return serde_json::json!({
                    "needsSwitch": false,
                    "reason": "api_auth_failed",
                    "percentUsed": 0,
                    "error": e
                });
            }
            return serde_json::json!({
                "needsSwitch": false,
                "reason": "network_error",
                "percentUsed": 0,
                "error": e,
                "displayMessage": e
            });
        }
    }

    // ── 检查 3: 付费账号额外检测 full_stripe_profile ──
    if !needs_switch && !membership.is_empty() && membership != "free" {
        if let Ok(profile) = fetch_stripe_profile(token).await {
            if let Some(usage_data) = profile.get("usageData").and_then(|v| v.as_array()) {
                for u in usage_data {
                    let exhausted = u
                        .get("usage")
                        .and_then(|x| x.get("exhausted"))
                        .and_then(|v| v.as_bool())
                        .unwrap_or(false);
                    if exhausted {
                        needs_switch = true;
                        reason = format!(
                            "model_exhausted:{}",
                            u.get("modelType").and_then(|v| v.as_str()).unwrap_or("")
                        );
                        break;
                    }
                    let num_requests = u.get("numRequests").and_then(|v| v.as_f64()).unwrap_or(0.0);
                    let max_request = u
                        .get("maxRequestUsage")
                        .and_then(|v| v.as_f64())
                        .unwrap_or(0.0);
                    if max_request > 0.0 && num_requests >= max_request {
                        needs_switch = true;
                        reason = format!(
                            "model_limit_reached:{}",
                            u.get("modelType").and_then(|v| v.as_str()).unwrap_or("")
                        );
                        break;
                    }
                }
            }
        }
    }

    serde_json::json!({
        "needsSwitch": needs_switch,
        "reason": reason,
        "percentUsed": percent_used,
        "membership": membership,
        "totalQuota": total_quota,
        "displayMessage": display_message,
    })
}

#[allow(dead_code)]
async fn do_seamless_switch(
    db_path: &str,
    email: &str,
    access_token: &str,
    refresh_token: &str,
) -> serde_json::Value {
    do_seamless_switch_with_id(db_path, email, access_token, refresh_token, None).await
}

async fn do_seamless_switch_with_id(
    db_path: &str,
    email: &str,
    access_token: &str,
    refresh_token: &str,
    machine_id_override: Option<&str>,
) -> serde_json::Value {
    // Write active token
    do_write_active_token(access_token);

    // Update database
    if !Path::new(db_path).exists() {
        return serde_json::json!({"success": false, "error": "数据库文件不存在"});
    }

    // macOS: 清除 chflags uchg
    utils::clear_macos_immutable_flag(Path::new(db_path));

    let conn = match Connection::open(db_path) {
        Ok(c) => c,
        Err(e) => {
            return serde_json::json!({"success": false, "error": format!("打开数据库失败: {}", e)});
        }
    };

    // 使用传入的 machineId 或自动生成（sha256 hex 格式，与 Cursor 原生一致）
    let new_machine_id = match machine_id_override {
        Some(id) => id.to_string(),
        None => {
            let mut hasher = Sha256::new();
            hasher.update(rand::random::<[u8; 32]>());
            hex::encode(hasher.finalize())
        }
    };

    // SQLite 字段名 obfstr 加密：反编译看 .rdata 看不到 cursorAuth/* / telemetry.* 明文
    let key_access = utils::keys::auth_access();
    let key_refresh = utils::keys::auth_refresh();
    let key_email = utils::keys::auth_email();
    let key_signup = utils::keys::auth_signup();
    let key_machine = utils::keys::telem_machine();
    let auth0_value = utils::keys::auth0_value();

    let updates: [(&str, &str); 5] = [
        (key_access.as_str(), access_token),
        (key_refresh.as_str(), refresh_token),
        (key_email.as_str(), email),
        (key_signup.as_str(), &auth0_value),
        (key_machine.as_str(), &new_machine_id),
    ];

    let mut updated_keys = Vec::new();
    for (key, value) in &updates {
        let count: i64 = conn
            .query_row("SELECT COUNT(*) FROM ItemTable WHERE key = ?1", [key], |row| row.get(0))
            .unwrap_or(0);
        let result = if count > 0 {
            conn.execute("UPDATE ItemTable SET value = ?1 WHERE key = ?2", [value, key])
        } else {
            conn.execute("INSERT INTO ItemTable (key, value) VALUES (?1, ?2)", [key, value])
        };
        if result.is_ok() {
            updated_keys.push(key.to_string());
        }
    }

    serde_json::json!({
        "success": true,
        "message": "无感换号成功",
        "email": email,
        "updatedKeys": updated_keys
    })
}

// ========== Tauri commands ==========

#[tauri::command]
pub async fn patch_ext_host(card_code: Option<String>) -> serde_json::Value {
    let paths = cursor_paths::get_cursor_paths();
    let base_path = match paths.base_path {
        Some(ref bp) if paths.error.is_none() => bp.clone(),
        _ => {
            return serde_json::json!({
                "success": false, "patched": false,
                "error": paths.error.unwrap_or_else(|| "无法获取Cursor路径".to_string())
            });
        }
    };
    let install_path = cursor_paths::get_cursor_install_from_base_path(&base_path);
    let eh_result = do_patch_ext_host(&install_path);

    // 同时注入 workbench.desktop.main.js（机器码内存重置）
    let wb_result = workbench_inject::patch_workbench(&base_path);
    // 启动本地HTTP服务（供注入JS轮询机器码状态）
    workbench_inject::start_local_server();

    // 注入时同步重置机器码（与参考实现一致：注入 = 注入JS + 重置机器码 + 写入状态）
    // 这样用户重启 Cursor 后立刻使用新的 telemetry ID，不再被识别为旧设备
    let reset_ok = match workbench_inject::perform_machine_reset() {
        Ok(_) => true,
        Err(e) => {
            eprintln!("[patch_ext_host] 机器码重置失败: {}", e);
            false
        }
    };

    // 设置自动换号上下文：当 JS 检测到 401/403/429 时，HTTP 服务器才能调后端拿新账号
    // 与参考实现 cursor_page._do_inject 中调 seamless_server.set_api_client 等价
    if let Some(code) = card_code {
        if !code.is_empty() {
            // 找到 state.vscdb 路径
            let db_path = utils::get_cursor_db_path()
                .map(|p| p.to_string_lossy().to_string())
                .unwrap_or_default();
            workbench_inject::set_auto_switch_context(code, db_path);
        }
    }

    // 合并结果
    let eh_ok = eh_result.get("success").and_then(|v| v.as_bool()).unwrap_or(false);
    let wb_ok = wb_result.get("success").and_then(|v| v.as_bool()).unwrap_or(false);

    serde_json::json!({
        "success": eh_ok,
        "patched": eh_ok,
        "wbPatched": wb_ok,
        "machineReset": reset_ok,
        "wbError": if wb_ok { serde_json::Value::Null } else { wb_result.get("error").cloned().unwrap_or(serde_json::Value::Null) },
    })
}

#[tauri::command]
pub async fn unpatch_ext_host() -> serde_json::Value {
    let paths = cursor_paths::get_cursor_paths();
    let base_path = match paths.base_path {
        Some(ref bp) if paths.error.is_none() => bp.clone(),
        _ => {
            return serde_json::json!({
                "success": false, "patched": false,
                "error": paths.error.unwrap_or_else(|| "无法获取Cursor路径".to_string())
            });
        }
    };
    let install_path = cursor_paths::get_cursor_install_from_base_path(&base_path);
    // 同时移除 workbench 注入
    workbench_inject::unpatch_workbench(&base_path);
    workbench_inject::stop_local_server();
    // 清除自动换号上下文，避免残留导致后续误触发
    workbench_inject::clear_auto_switch_context();
    do_unpatch_ext_host(&install_path)
}

#[tauri::command]
pub async fn check_ext_host_patched() -> bool {
    let paths = cursor_paths::get_cursor_paths();
    if let Some(ref bp) = paths.base_path {
        if paths.error.is_none() {
            let install_path = cursor_paths::get_cursor_install_from_base_path(bp);
            return do_check_ext_host_patched(&install_path);
        }
    }
    false
}

#[tauri::command]
pub async fn write_active_token(token: String) -> bool {
    do_write_active_token(&token)
}

#[tauri::command]
pub async fn read_active_token() -> Option<String> {
    do_read_active_token()
}

#[tauri::command]
pub async fn clear_active_token() -> bool {
    do_clear_active_token()
}

#[tauri::command]
pub async fn check_cursor_usage(access_token: String) -> serde_json::Value {
    do_check_account_status(&access_token).await
}

#[tauri::command]
pub async fn get_cursor_account_quota(access_token: String) -> serde_json::Value {
    // Reuse the usage check which already contains quota info
    do_check_account_status(&access_token).await
}

#[tauri::command]
pub async fn seamless_switch_cmd(
    db_path: String,
    email: String,
    access_token: String,
    refresh_token: String,
) -> serde_json::Value {
    // 先生成机器码，确保 SQLite 和 磁盘/内存使用同一套 ID
    let ids = workbench_inject::generate_machine_ids();
    let result = do_seamless_switch_with_id(
        &db_path, &email, &access_token, &refresh_token,
        Some(&ids.machine_id),
    ).await;

    // 写磁盘 + 推送token+机器码给JS轮询
    if result.get("success").and_then(|v| v.as_bool()).unwrap_or(false) {
        let _ = workbench_inject::update_disk_files(&ids);
        workbench_inject::update_seamless_state(&email, &access_token, &refresh_token, &ids);
    }

    result
}

#[tauri::command]
pub async fn one_click_switch(db_path: String, card_code: String) -> serde_json::Value {
    // 1. Check ExtHost patch status
    let patched = check_ext_host_patched().await;
    if !patched {
        return serde_json::json!({
            "success": false,
            "error": "请先开启请求拦截（ExtensionHost 补丁）"
        });
    }

    // 2. Fetch new account (使用缓存的设备码，确保稳定性)
    let device_id = utils::get_cached_device_id();
    let body = serde_json::json!({
        "cardCode": card_code,
        "deviceId": device_id
    });

    let api_url_owned = utils::api_url(obfstr::obfstr!("/hou/csk/card/renew"));
    let api_url = api_url_owned.as_str();
    let resp = match utils::http_post_json(api_url, &body).await {
        Ok(r) => r,
        Err(e) => {
            return serde_json::json!({"success": false, "error": format!("后端请求失败: {}", e)});
        }
    };

    let success = resp.get("success").and_then(|v| v.as_bool()).unwrap_or(false);
    if !success {
        let msg = resp.get("message").and_then(|v| v.as_str()).unwrap_or("获取账号失败");
        return serde_json::json!({"success": false, "error": msg});
    }

    let email = resp.get("email").and_then(|v| v.as_str()).unwrap_or("");
    let token = resp.get("token").and_then(|v| v.as_str()).unwrap_or("");

    if email.is_empty() || token.is_empty() {
        return serde_json::json!({"success": false, "error": "后端返回的账号信息不完整"});
    }

    // 3. 生成机器码 + 执行无感换号
    let ids = workbench_inject::generate_machine_ids();
    let switch_result = do_seamless_switch_with_id(
        &db_path, email, token, token,
        Some(&ids.machine_id),
    ).await;

    // 4. 写磁盘 + 推送token+机器码给JS轮询
    if switch_result.get("success").and_then(|v| v.as_bool()).unwrap_or(false) {
        let _ = workbench_inject::update_disk_files(&ids);
        workbench_inject::update_seamless_state(email, token, token, &ids);
    }

    let mut result = switch_result;
    if let Some(obj) = result.as_object_mut() {
        obj.insert("email".to_string(), serde_json::json!(email));
    }
    result
}

// ========== 自动换号轮询（与 Electron usageMonitorPoll 一致） ==========

const AUTO_SWITCH_POLL_MIN_SECS: u64 = 20;
const AUTO_SWITCH_POLL_MAX_SECS: u64 = 30;

async fn fetch_new_account_with_retry(
    app: &AppHandle,
    card_code: &str,
) -> Result<(String, String), String> {
    // 使用缓存的设备码，确保稳定性
    let device_id = utils::get_cached_device_id();
    let api_url_owned = utils::api_url(obfstr::obfstr!("/hou/csk/card/renew"));
    let api_url = api_url_owned.as_str();
    let max_retries = 3;

    for retry in 0..=max_retries {
        if !AUTO_SWITCH_ENABLED.load(Ordering::SeqCst) {
            return Err("已关闭自动换号".to_string());
        }

        let body = serde_json::json!({
            "cardCode": card_code,
            "deviceId": device_id
        });

        match utils::http_post_json(api_url, &body).await {
            Ok(resp) => {
                let success = resp.get("success").and_then(|v| v.as_bool()).unwrap_or(false);
                if success {
                    let email = resp.get("email").and_then(|v| v.as_str()).unwrap_or("").to_string();
                    let token = resp.get("token").and_then(|v| v.as_str()).unwrap_or("").to_string();
                    if !email.is_empty() && !token.is_empty() {
                        return Ok((email, token));
                    }
                    return Err("后端返回的账号信息不完整".to_string());
                }

                let msg = resp.get("message").and_then(|v| v.as_str()).unwrap_or("").to_string();

                // 限频检测（与 Electron 一致：包含「频繁」「稍后」「1分钟」）
                if msg.contains("频繁") || msg.contains("稍后") || msg.contains("1分钟") {
                    if retry < max_retries {
                        let wait_sec = if retry == 0 { 30 } else { 65 };
                        let _ = app.emit_all(
                            "auto-switch-status",
                            serde_json::json!({
                                "switching": true,
                                "message": format!("后端限频，{}秒后重试...", wait_sec)
                            }),
                        );
                        tokio::time::sleep(std::time::Duration::from_secs(wait_sec)).await;
                        continue;
                    }
                }

                return Err(if msg.is_empty() { "获取账号失败".to_string() } else { msg });
            }
            Err(e) => {
                if retry < max_retries {
                    tokio::time::sleep(std::time::Duration::from_secs(30)).await;
                    continue;
                }
                return Err(e);
            }
        }
    }

    Err("重试次数用尽".to_string())
}

async fn usage_monitor_poll(app: &AppHandle) {
    let token = match do_read_active_token() {
        Some(t) => t,
        None => return,
    };

    let status = do_check_account_status(&token).await;
    let needs_switch = status
        .get("needsSwitch")
        .and_then(|v| v.as_bool())
        .unwrap_or(false);

    if !needs_switch {
        return;
    }

    // 触发换号
    AUTO_SWITCH_BUSY.store(true, Ordering::SeqCst);

    let card_code = match AUTO_SWITCH_CARD_CODE.lock().ok().and_then(|g| g.clone()) {
        Some(c) => c,
        None => {
            AUTO_SWITCH_BUSY.store(false, Ordering::SeqCst);
            return;
        }
    };

    let percent_used = status.get("percentUsed").and_then(|v| v.as_f64()).unwrap_or(0.0);
    let reason = status
        .get("reason")
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .to_string();

    let _ = app.emit_all(
        "auto-switch-status",
        serde_json::json!({
            "switching": true,
            "message": format!("检测到额度耗尽 ({}%), 原因: {}, 正在换号...", percent_used, reason)
        }),
    );

    // 1. 获取新账号
    let (email, new_token) = match fetch_new_account_with_retry(app, &card_code).await {
        Ok(pair) => pair,
        Err(e) => {
            let _ = app.emit_all(
                "auto-switch-status",
                serde_json::json!({
                    "switching": false,
                    "success": false,
                    "error": e
                }),
            );
            AUTO_SWITCH_BUSY.store(false, Ordering::SeqCst);
            return;
        }
    };

    // 2. 生成机器码 + 执行无感换号
    let ids = workbench_inject::generate_machine_ids();
    let db_path = utils::get_cursor_db_path()
        .map(|p| p.to_string_lossy().to_string())
        .unwrap_or_default();
    let switch_result = do_seamless_switch_with_id(
        &db_path, &email, &new_token, &new_token,
        Some(&ids.machine_id),
    ).await;
    let switch_ok = switch_result
        .get("success")
        .and_then(|v| v.as_bool())
        .unwrap_or(false);

    // 3. 写磁盘 + 推送token+机器码给JS轮询
    if switch_ok {
        let _ = workbench_inject::update_disk_files(&ids);
        workbench_inject::update_seamless_state(&email, &new_token, &new_token, &ids);
    }

    let _ = app.emit_all(
        "auto-switch-status",
        serde_json::json!({
            "switching": false,
            "success": switch_ok,
            "email": email,
            "message": if switch_ok {
                format!("自动换号成功: {}", email)
            } else {
                "自动换号失败".to_string()
            }
        }),
    );

    AUTO_SWITCH_BUSY.store(false, Ordering::SeqCst);
}

async fn usage_monitor_loop(app: AppHandle) {
    // 首次延迟 3 秒
    tokio::time::sleep(std::time::Duration::from_secs(3)).await;

    while AUTO_SWITCH_ENABLED.load(Ordering::SeqCst) {
        if !AUTO_SWITCH_BUSY.load(Ordering::SeqCst) {
            usage_monitor_poll(&app).await;
        }

        // 20-30 秒随机间隔，每秒检查一次 enabled 标志以便快速响应关闭
        let interval_secs = AUTO_SWITCH_POLL_MIN_SECS
            + (rand::random::<u64>() % (AUTO_SWITCH_POLL_MAX_SECS - AUTO_SWITCH_POLL_MIN_SECS + 1));
        for _ in 0..interval_secs {
            if !AUTO_SWITCH_ENABLED.load(Ordering::SeqCst) {
                return;
            }
            tokio::time::sleep(std::time::Duration::from_secs(1)).await;
        }
    }
}

#[tauri::command]
pub async fn toggle_auto_switch(
    app: AppHandle,
    enabled: bool,
    card_code: Option<String>,
) -> serde_json::Value {
    if enabled {
        let cc = match card_code {
            Some(c) if !c.is_empty() => c,
            _ => {
                return serde_json::json!({"success": false, "error": "请先验证卡密"});
            }
        };

        // 1. 注入 ExtHost 补丁 + Workbench 机器码注入
        let paths = cursor_paths::get_cursor_paths();
        if let Some(ref bp) = paths.base_path {
            if paths.error.is_none() {
                let install_path = cursor_paths::get_cursor_install_from_base_path(bp);
                do_unpatch_ext_host(&install_path);
                do_patch_ext_host(&install_path);
                // 注入 workbench.desktop.main.js（机器码内存重置）
                workbench_inject::patch_workbench(bp);
            }
        }

        // 启动本地HTTP服务（供注入JS轮询机器码状态）
        workbench_inject::start_local_server();

        // 2. 保存 card_code
        if let Ok(mut guard) = AUTO_SWITCH_CARD_CODE.lock() {
            *guard = Some(cc);
        }

        // 3. 启动后台轮询任务（仅当从 disabled → enabled 时）
        let was_enabled = AUTO_SWITCH_ENABLED.swap(true, Ordering::SeqCst);
        if !was_enabled {
            let app_clone = app.clone();
            tokio::spawn(async move {
                usage_monitor_loop(app_clone).await;
            });
        }

        serde_json::json!({"success": true, "enabled": true})
    } else {
        AUTO_SWITCH_ENABLED.store(false, Ordering::SeqCst);
        if let Ok(mut guard) = AUTO_SWITCH_CARD_CODE.lock() {
            *guard = None;
        }
        // 停止本地HTTP服务
        workbench_inject::stop_local_server();
        serde_json::json!({"success": true, "enabled": false})
    }
}

#[tauri::command]
pub async fn get_auto_switch_status() -> serde_json::Value {
    serde_json::json!({
        "enabled": AUTO_SWITCH_ENABLED.load(Ordering::SeqCst),
        "busy": AUTO_SWITCH_BUSY.load(Ordering::SeqCst)
    })
}
