use std::fs;
use std::path::Path;
use rusqlite::Connection;

#[tauri::command]
pub async fn save_current_workspace(db_path: String) -> serde_json::Value {
    if !Path::new(&db_path).exists() {
        return serde_json::json!({"success": false, "error": "数据库文件不存在"});
    }

    let conn = match Connection::open_with_flags(&db_path, rusqlite::OpenFlags::SQLITE_OPEN_READ_ONLY) {
        Ok(c) => c,
        Err(e) => {
            return serde_json::json!({"success": false, "error": format!("打开数据库失败: {}", e)});
        }
    };

    let possible_keys = [
        "workbench.panel.recentlyOpenedPathsList",
        "history.recentlyOpenedPathsList",
        "openedPathsList.entries",
        "workspaces.recentlyOpened",
    ];

    let mut workspace_data = None;
    for key in &possible_keys {
        let result: Result<String, _> = conn.query_row(
            "SELECT value FROM ItemTable WHERE key = ?1",
            [key],
            |row| row.get(0),
        );
        if let Ok(value) = result {
            workspace_data = Some(value);
            break;
        }
    }

    let workspace_data = match workspace_data {
        Some(d) => d,
        None => {
            return serde_json::json!({"success": false, "error": "未找到工作区信息"});
        }
    };

    // Parse workspace data
    let parsed: serde_json::Value = match serde_json::from_str(&workspace_data) {
        Ok(v) => v,
        Err(_) => {
            return serde_json::json!({"success": false, "error": "解析工作区数据失败"});
        }
    };

    let mut workspace = None;
    if let Some(entries) = parsed.get("entries").and_then(|v| v.as_array()) {
        if let Some(first) = entries.first() {
            let raw_path = first
                .get("folderUri")
                .or_else(|| first.get("workspace").and_then(|w| w.get("configPath")))
                .and_then(|v| v.as_str());

            if let Some(mut path_str) = raw_path.map(String::from) {
                // Handle file:/// prefix
                if path_str.starts_with("file:///") {
                    path_str = path_str[8..].to_string();
                } else if path_str.starts_with("file://") {
                    path_str = path_str[7..].to_string();
                }

                // URL decode
                if let Ok(decoded) = urlencoding::decode(&path_str) {
                    path_str = decoded.to_string();
                }

                // Windows path fixup
                #[cfg(target_os = "windows")]
                {
                    path_str = path_str.replace('/', "\\");
                    if path_str.len() > 1 && path_str.as_bytes()[1] == b':' {
                        let first_char = path_str.chars().next().unwrap().to_uppercase().to_string();
                        path_str = format!("{}{}", first_char, &path_str[1..]);
                    }
                }

                workspace = Some(path_str);
            }
        }
    }

    let workspace = match workspace {
        Some(w) => w,
        None => {
            return serde_json::json!({"success": false, "error": "无法提取工作区路径"});
        }
    };

    // Save to backup file
    let global_storage = Path::new(&db_path).parent().unwrap();
    let backup_path = global_storage.join("workspace-backup.json");
    let backup_data = serde_json::json!({
        "workspace": workspace,
        "timestamp": chrono::Local::now().to_rfc3339(),
        "dbPath": db_path
    });

    match fs::write(&backup_path, serde_json::to_string_pretty(&backup_data).unwrap_or_default()) {
        Ok(_) => serde_json::json!({
            "success": true,
            "workspace": workspace,
            "backupPath": backup_path.to_string_lossy()
        }),
        Err(e) => serde_json::json!({"success": false, "error": e.to_string()}),
    }
}

#[tauri::command]
pub async fn load_saved_workspace(db_path: String) -> serde_json::Value {
    let global_storage = Path::new(&db_path).parent().unwrap();
    let backup_path = global_storage.join("workspace-backup.json");

    if !backup_path.exists() {
        return serde_json::json!({"success": false, "workspace": null});
    }

    let content = match fs::read_to_string(&backup_path) {
        Ok(c) => c,
        Err(_) => {
            return serde_json::json!({"success": false, "workspace": null});
        }
    };

    let data: serde_json::Value = match serde_json::from_str(&content) {
        Ok(v) => v,
        Err(_) => {
            return serde_json::json!({"success": false, "workspace": null});
        }
    };

    let mut workspace = data.get("workspace").and_then(|v| v.as_str()).unwrap_or("").to_string();

    // URL decode if needed
    if workspace.contains('%') {
        if let Ok(decoded) = urlencoding::decode(&workspace) {
            workspace = decoded.to_string();
        }
    }

    // Windows path fixup
    #[cfg(target_os = "windows")]
    {
        workspace = workspace.replace('/', "\\");
        if workspace.len() > 1 && workspace.as_bytes()[1] == b':' {
            let first_char = workspace.chars().next().unwrap().to_uppercase().to_string();
            workspace = format!("{}{}", first_char, &workspace[1..]);
        }
    }

    serde_json::json!({
        "success": true,
        "workspace": workspace,
        "timestamp": data.get("timestamp")
    })
}
