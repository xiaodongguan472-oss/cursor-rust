use std::fs;
use rusqlite::Connection;
use super::utils;

#[tauri::command]
pub async fn set_cursor_default_model(model: Option<String>) -> serde_json::Value {
    let model = model.unwrap_or_else(|| obfstr::obfstr!("claude-3.5-sonnet").to_string());

    let mut results = serde_json::json!({
        "settingsFile": { "attempted": false, "success": false, "path": "", "error": null },
        "database": { "attempted": false, "success": false, "path": "", "error": null, "updatedKeys": [] }
    });

    // Method 1: Modify settings.json
    let settings_path = {
        #[cfg(target_os = "windows")]
        { dirs::home_dir().map(|h| h.join("AppData").join("Roaming").join("Cursor").join("User").join("settings.json")) }
        #[cfg(target_os = "macos")]
        { dirs::home_dir().map(|h| h.join("Library").join("Application Support").join("Cursor").join("User").join("settings.json")) }
        #[cfg(target_os = "linux")]
        { dirs::home_dir().map(|h| h.join(".config").join("Cursor").join("User").join("settings.json")) }
    };

    if let Some(ref sp) = settings_path {
        results["settingsFile"]["attempted"] = serde_json::json!(true);
        results["settingsFile"]["path"] = serde_json::json!(sp.to_string_lossy());

        if let Some(parent) = sp.parent() {
            let _ = fs::create_dir_all(parent);
        }

        let mut cursor_settings: serde_json::Value = if sp.exists() {
            fs::read_to_string(sp)
                .ok()
                .and_then(|c| serde_json::from_str(&c).ok())
                .unwrap_or(serde_json::json!({}))
        } else {
            serde_json::json!({})
        };

        // 模型 key 全部 obfstr 加密（防 .rdata 暴露 cursor.chat.defaultModel 等特征）
        let suffix = obfstr::obfstr!(".defaultModel").to_string();
        let model_keys: [String; 6] = [
            format!("{}{}", obfstr::obfstr!("cursor.chat"), suffix),
            format!("{}{}", obfstr::obfstr!("cursor.general"), suffix),
            format!("{}{}", obfstr::obfstr!("cursor"), suffix),
            format!("{}{}", obfstr::obfstr!("chat"), suffix),
            format!("{}{}", obfstr::obfstr!("ai"), suffix),
            format!("{}{}", obfstr::obfstr!("workbench.chat"), suffix),
        ];

        if let Some(obj) = cursor_settings.as_object_mut() {
            for key in &model_keys {
                obj.insert(key.clone(), serde_json::json!(model));
            }
        }

        // Backup
        if sp.exists() {
            let backup = format!("{}.bak", sp.to_string_lossy());
            let _ = fs::copy(sp, &backup);
        }

        let serialized = serde_json::to_string_pretty(&cursor_settings).unwrap_or_default();
        let write_result = utils::safe_modify_file(sp, || {
            fs::write(sp, &serialized).map_err(|e| e.to_string())
        });
        match write_result {
            Ok(_) => { results["settingsFile"]["success"] = serde_json::json!(true); }
            Err(e) => { results["settingsFile"]["error"] = serde_json::json!(e); }
        }
    }

    // Method 2: Modify database
    let db_path = {
        #[cfg(target_os = "windows")]
        { dirs::home_dir().map(|h| h.join("AppData").join("Roaming").join("Cursor").join("User").join("globalStorage").join("state.vscdb")) }
        #[cfg(target_os = "macos")]
        { dirs::home_dir().map(|h| h.join("Library").join("Application Support").join("Cursor").join("User").join("globalStorage").join("state.vscdb")) }
        #[cfg(target_os = "linux")]
        { dirs::home_dir().map(|h| h.join(".config").join("Cursor").join("User").join("globalStorage").join("state.vscdb")) }
    };

    if let Some(ref dp) = db_path {
        results["database"]["attempted"] = serde_json::json!(true);
        results["database"]["path"] = serde_json::json!(dp.to_string_lossy());

        if dp.exists() {
            // macOS: 清除 chflags uchg，确保 SQLite 能写入
            utils::clear_macos_immutable_flag(dp);
            match Connection::open(dp) {
                Ok(conn) => {
                    let table_exists: bool = conn
                        .query_row(
                            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='ItemTable'",
                            [],
                            |row| row.get::<_, i64>(0),
                        )
                        .map(|c| c > 0)
                        .unwrap_or(false);

                    if table_exists {
                        // 模型 key 全部 obfstr 加密
                        let suffix = obfstr::obfstr!(".defaultModel").to_string();
                        let model_keys: [String; 7] = [
                            format!("{}{}", obfstr::obfstr!("cursor.chat"), suffix),
                            format!("{}{}", obfstr::obfstr!("cursor.general"), suffix),
                            format!("{}{}", obfstr::obfstr!("cursor"), suffix),
                            format!("{}{}", obfstr::obfstr!("chat"), suffix),
                            format!("{}{}", obfstr::obfstr!("ai"), suffix),
                            format!("{}{}", obfstr::obfstr!("workbench.chat"), suffix),
                            format!("{}{}", obfstr::obfstr!("vscode.chat"), suffix),
                        ];

                        let mut updated = Vec::new();
                        for key in &model_keys {
                            let count: i64 = conn
                                .query_row("SELECT COUNT(*) FROM ItemTable WHERE key = ?1", [key.as_str()], |row| row.get(0))
                                .unwrap_or(0);
                            let result = if count > 0 {
                                conn.execute("UPDATE ItemTable SET value = ?1 WHERE key = ?2", [model.as_str(), key.as_str()])
                            } else {
                                conn.execute("INSERT INTO ItemTable (key, value) VALUES (?1, ?2)", [key.as_str(), model.as_str()])
                            };
                            if result.is_ok() {
                                updated.push(key.clone());
                            }
                        }

                        results["database"]["success"] = serde_json::json!(true);
                        results["database"]["updatedKeys"] = serde_json::json!(updated);
                    } else {
                        results["database"]["error"] = serde_json::json!("ItemTable表不存在");
                    }
                }
                Err(e) => {
                    results["database"]["error"] = serde_json::json!(format!("数据库操作失败: {}", e));
                }
            }
        } else {
            results["database"]["error"] = serde_json::json!("数据库文件不存在");
        }
    }

    let overall_success = results["settingsFile"]["success"].as_bool().unwrap_or(false)
        || results["database"]["success"].as_bool().unwrap_or(false);

    serde_json::json!({
        "success": overall_success,
        "message": if overall_success { format!("已成功设置默认AI模型为: {}", model) } else { "设置默认模型失败".to_string() },
        "model": model,
        "details": results
    })
}
