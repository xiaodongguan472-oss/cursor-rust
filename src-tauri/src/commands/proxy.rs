use std::fs;
use std::path::PathBuf;
use super::utils;

fn find_cursor_settings_path() -> Option<PathBuf> {
    #[cfg(target_os = "windows")]
    {
        // Check current user first
        if let Some(home) = dirs::home_dir() {
            let p = home.join("AppData").join("Roaming").join("Cursor").join("User").join("settings.json");
            if p.exists() { return Some(p); }
        }
        // Search all drives/users
        for c in b'A'..=b'Z' {
            let drive = format!("{}:\\", c as char);
            let users_dir = PathBuf::from(&drive).join("Users");
            if !users_dir.exists() { continue; }
            if let Ok(entries) = fs::read_dir(&users_dir) {
                for entry in entries.flatten() {
                    let p = entry.path().join("AppData").join("Roaming").join("Cursor").join("User").join("settings.json");
                    if p.exists() { return Some(p); }
                }
            }
        }
    }
    #[cfg(target_os = "macos")]
    {
        if let Some(home) = dirs::home_dir() {
            let p = home.join("Library").join("Application Support").join("Cursor").join("User").join("settings.json");
            if p.exists() { return Some(p); }
        }
    }
    #[cfg(target_os = "linux")]
    {
        if let Some(home) = dirs::home_dir() {
            let p = home.join(".config").join("Cursor").join("User").join("settings.json");
            if p.exists() { return Some(p); }
        }
    }
    None
}

async fn fetch_current_proxy_config() -> Option<serde_json::Value> {
    let api_url_owned = utils::api_url(obfstr::obfstr!("/hou/csk/proxy-config/current"));
    let api_url = api_url_owned.as_str();
    let client = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(5))
        .build().ok()?;
    let resp = client.get(api_url)
        .header("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
        .send().await.ok()?;
    let data: serde_json::Value = resp.json().await.ok()?;
    if data.get("success").and_then(|v| v.as_bool()).unwrap_or(false) {
        data.get("data").cloned()
    } else {
        None
    }
}

#[tauri::command]
pub async fn check_cursor_settings_status() -> serde_json::Value {
    let settings_path = match find_cursor_settings_path() {
        Some(p) => p,
        None => {
            return serde_json::json!({
                "success": true, "enabled": false, "message": "未找到配置文件"
            });
        }
    };

    let content = match fs::read_to_string(&settings_path) {
        Ok(c) => c,
        Err(_) => {
            return serde_json::json!({
                "success": true, "enabled": false, "message": "无法读取配置文件"
            });
        }
    };

    let settings: serde_json::Value = match serde_json::from_str(&content) {
        Ok(v) => v,
        Err(_) => {
            return serde_json::json!({
                "success": true, "enabled": false, "message": "配置文件格式错误"
            });
        }
    };

    let has_proxy = settings.get("http.proxy").and_then(|v| v.as_str()).map(|s| !s.is_empty()).unwrap_or(false);
    let has_support = settings.get("http.proxySupport").and_then(|v| v.as_str()) == Some("override");
    let has_disable_h2 = settings.get("cursor.general.disableHttp2").and_then(|v| v.as_bool()).unwrap_or(false);

    if !has_proxy || !has_support || !has_disable_h2 {
        return serde_json::json!({
            "success": true, "enabled": false, "message": "未配置代理", "proxyUrl": null
        });
    }

    let current_proxy = settings["http.proxy"].as_str().unwrap_or("").to_string();

    // Check against database proxy list
    let api_url_owned = utils::api_url(obfstr::obfstr!("/hou/csk/proxy-config/proxy-urls"));
    let api_url = api_url_owned.as_str();
    match utils::http_get_json(api_url).await {
        Ok(resp) => {
            let success = resp.get("success").and_then(|v| v.as_bool()).unwrap_or(false);
            if success {
                if let Some(data) = resp.get("data").and_then(|v| v.as_array()) {
                    let proxy_urls: Vec<&str> = data.iter().filter_map(|v| v.as_str()).collect();
                    let is_in_db = proxy_urls.contains(&current_proxy.as_str());
                    return serde_json::json!({
                        "success": true,
                        "enabled": is_in_db,
                        "message": if is_in_db { "代理已开启" } else { "当前代理不在数据库中，视为已关闭" },
                        "proxyUrl": if is_in_db { Some(&current_proxy) } else { None }
                    });
                }
            }
            // Fallback
            serde_json::json!({
                "success": true,
                "enabled": has_proxy && has_support && has_disable_h2,
                "message": "代理已开启（未验证数据库）",
                "proxyUrl": current_proxy
            })
        }
        Err(_) => {
            serde_json::json!({
                "success": true,
                "enabled": has_proxy && has_support && has_disable_h2,
                "message": "代理已开启（未验证数据库）",
                "proxyUrl": current_proxy
            })
        }
    }
}

#[tauri::command]
pub async fn update_cursor_settings(enabled: bool) -> serde_json::Value {
    let settings_path = match find_cursor_settings_path() {
        Some(p) => p,
        None => {
            return serde_json::json!({
                "success": false,
                "error": "未找到Cursor配置文件",
                "message": "请先打开Cursor进入首页，确保Cursor已正确初始化后再使用此功能"
            });
        }
    };

    if !settings_path.exists() {
        return serde_json::json!({
            "success": false,
            "error": "配置文件不存在",
            "message": "请先打开Cursor进入首页，确保Cursor已正确初始化后再使用此功能"
        });
    }

    if enabled {
        // Enable: fetch proxy config from backend (强制要求服务器返回，不再硬编码 fallback)
        let settings_content = match fetch_current_proxy_config().await {
            Some(config) => config,
            None => {
                return serde_json::json!({
                    "success": false,
                    "error": "无法获取代理配置",
                    "message": "代理配置服务器暂不可用，请稍后重试或检查网络"
                });
            }
        };

        let serialized = serde_json::to_string_pretty(&settings_content).unwrap_or_default();
        let write_result = utils::safe_modify_file(&settings_path, || {
            fs::write(&settings_path, &serialized).map_err(|e| e.to_string())
        });
        match write_result {
            Ok(_) => serde_json::json!({
                "success": true,
                "message": "已开启地区限制突破",
                "config": settings_content.get("http.proxy")
            }),
            Err(e) => serde_json::json!({
                "success": false,
                "error": e
            }),
        }
    } else {
        // Disable: write basic config
        let basic = serde_json::json!({
            "database-client.autoSync": true,
            "update.enableWindowsBackgroundUpdates": false,
            "update.mode": "none",
            "http.proxyAuthorization": null,
            "json.schemas": []
        });

        let serialized = serde_json::to_string_pretty(&basic).unwrap_or_default();
        let write_result = utils::safe_modify_file(&settings_path, || {
            fs::write(&settings_path, &serialized).map_err(|e| e.to_string())
        });
        match write_result {
            Ok(_) => serde_json::json!({
                "success": true,
                "message": "已关闭地区限制突破",
                "config": null
            }),
            Err(e) => serde_json::json!({
                "success": false,
                "error": e
            }),
        }
    }
}
