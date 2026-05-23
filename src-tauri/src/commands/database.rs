use serde::{Deserialize, Serialize};
use std::fs;
use std::path::{Path, PathBuf};
use rusqlite::Connection;
use uuid::Uuid;
use super::utils;
use super::machine_id;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DatabaseInfo {
    pub username: String,
    pub path: String,
    pub size: u64,
    pub modified: String,
    #[serde(rename = "userDataPath")]
    pub user_data_path: String,
    #[serde(skip_serializing_if = "Option::is_none", rename = "isManualSearch")]
    pub is_manual_search: Option<bool>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DatabaseSearchResult {
    pub success: bool,
    pub databases: Vec<DatabaseInfo>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub error: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none", rename = "searchPath")]
    pub search_path: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DbUpdateResult {
    pub success: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub message: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub error: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none", rename = "updatedKeys")]
    pub updated_keys: Option<Vec<String>>,
    #[serde(skip_serializing_if = "Option::is_none", rename = "newIds")]
    pub new_ids: Option<serde_json::Value>,
    #[serde(skip_serializing_if = "Option::is_none", rename = "deletedKeys")]
    pub deleted_keys: Option<Vec<String>>,
    #[serde(skip_serializing_if = "Option::is_none", rename = "activationSuccess")]
    pub activation_success: Option<bool>,
}

fn get_file_info(path: &Path, username: &str, user_data_path: &str) -> Option<DatabaseInfo> {
    let metadata = fs::metadata(path).ok()?;
    let modified = metadata
        .modified()
        .ok()
        .map(|t| {
            let dt: chrono::DateTime<chrono::Local> = t.into();
            dt.to_rfc3339()
        })
        .unwrap_or_default();

    Some(DatabaseInfo {
        username: username.to_string(),
        path: path.to_string_lossy().to_string(),
        size: metadata.len(),
        modified,
        user_data_path: user_data_path.to_string(),
        is_manual_search: None,
    })
}

#[tauri::command]
pub async fn find_all_cursor_databases() -> DatabaseSearchResult {
    let mut found = Vec::new();

    #[cfg(target_os = "windows")]
    {
        // Search all drives and user profiles
        let drives: Vec<String> = (b'A'..=b'Z')
            .filter_map(|c| {
                let drive = format!("{}:\\", c as char);
                if Path::new(&drive).exists() { Some(drive) } else { None }
            })
            .collect();

        for drive in &drives {
            let users_dir = PathBuf::from(drive).join("Users");
            if !users_dir.exists() { continue; }
            if let Ok(entries) = fs::read_dir(&users_dir) {
                for entry in entries.flatten() {
                    if !entry.file_type().map(|t| t.is_dir()).unwrap_or(false) { continue; }
                    let username = entry.file_name().to_string_lossy().to_string();
                    if ["Public", "Default", "Default User", "All Users"].contains(&username.as_str()) {
                        continue;
                    }
                    let cursor_path = entry.path().join("AppData").join("Roaming").join("Cursor");
                    let db_path = cursor_path.join("User").join("globalStorage").join("state.vscdb");
                    if db_path.exists() {
                        if let Some(info) = get_file_info(&db_path, &username, &cursor_path.to_string_lossy()) {
                            found.push(info);
                        }
                    }
                }
            }
        }

        // Also check environment variable paths
        let env_paths: Vec<PathBuf> = [
            std::env::var("APPDATA").ok().map(|p| PathBuf::from(p).join("Cursor")),
            std::env::var("LOCALAPPDATA").ok().map(|p| PathBuf::from(p).join("Cursor")),
        ]
        .iter()
        .filter_map(|p| p.clone())
        .collect();

        for env_path in env_paths {
            let db_path = env_path.join("User").join("globalStorage").join("state.vscdb");
            if db_path.exists() && !found.iter().any(|d| d.path == db_path.to_string_lossy().to_string()) {
                let username = whoami::username();
                if let Some(info) = get_file_info(&db_path, &format!("{} (Env)", username), &env_path.to_string_lossy()) {
                    found.push(info);
                }
            }
        }
    }

    #[cfg(target_os = "macos")]
    {
        let users_dir = Path::new("/Users");
        if let Ok(entries) = fs::read_dir(users_dir) {
            for entry in entries.flatten() {
                let name = entry.file_name().to_string_lossy().to_string();
                if name.starts_with('.') || name == "Shared" || name == ".localized" { continue; }
                let cursor_path = entry.path().join("Library").join("Application Support").join("Cursor");
                let db_path = cursor_path.join("User").join("globalStorage").join("state.vscdb");
                if db_path.exists() {
                    if let Some(info) = get_file_info(&db_path, &name, &cursor_path.to_string_lossy()) {
                        found.push(info);
                    }
                }
            }
        }
    }

    #[cfg(target_os = "linux")]
    {
        let users_dir = Path::new("/home");
        if let Ok(entries) = fs::read_dir(users_dir) {
            for entry in entries.flatten() {
                let name = entry.file_name().to_string_lossy().to_string();
                let cursor_path = entry.path().join(".config").join("Cursor");
                let db_path = cursor_path.join("User").join("globalStorage").join("state.vscdb");
                if db_path.exists() {
                    if let Some(info) = get_file_info(&db_path, &name, &cursor_path.to_string_lossy()) {
                        found.push(info);
                    }
                }
            }
        }
    }

    // Fallback to current user
    if found.is_empty() {
        if let Some(cursor_dir) = utils::get_cursor_data_dir() {
            let db_path = cursor_dir.join("User").join("globalStorage").join("state.vscdb");
            if db_path.exists() {
                let username = whoami::username();
                if let Some(info) = get_file_info(&db_path, &username, &cursor_dir.to_string_lossy()) {
                    found.push(info);
                }
            }
        }
    }

    // Sort by modified time descending
    found.sort_by(|a, b| b.modified.cmp(&a.modified));

    DatabaseSearchResult {
        success: true,
        databases: found,
        error: None,
        search_path: None,
    }
}

#[tauri::command]
pub async fn manual_search_cursor_database(search_path: String) -> DatabaseSearchResult {
    if search_path.is_empty() || !Path::new(&search_path).exists() {
        return DatabaseSearchResult {
            success: false,
            databases: vec![],
            error: Some("指定的搜索路径不存在".to_string()),
            search_path: Some(search_path),
        };
    }

    let mut found = Vec::new();
    search_recursive(&PathBuf::from(&search_path), 3, &mut found);

    DatabaseSearchResult {
        success: true,
        databases: found,
        error: None,
        search_path: Some(search_path),
    }
}

fn search_recursive(current: &Path, max_depth: u32, found: &mut Vec<DatabaseInfo>) {
    if max_depth == 0 { return; }
    let entries = match fs::read_dir(current) {
        Ok(e) => e,
        Err(_) => return,
    };

    for entry in entries.flatten() {
        let path = entry.path();
        if path.is_file() && entry.file_name() == "state.vscdb" {
            let parent_dir = path
                .parent()
                .and_then(|p| p.parent())
                .and_then(|p| p.parent())
                .map(|p| p.to_string_lossy().to_string())
                .unwrap_or_default();
            if let Some(mut info) = get_file_info(&path, &format!("手动搜索@{}", Path::new(&parent_dir).file_name().unwrap_or_default().to_string_lossy()), &parent_dir) {
                info.is_manual_search = Some(true);
                found.push(info);
            }
        } else if path.is_dir() {
            let name = entry.file_name().to_string_lossy().to_string();
            if !name.starts_with('.') && name != "node_modules" {
                search_recursive(&path, max_depth - 1, found);
            }
        }
    }
}

fn upsert_item_table(conn: &Connection, key: &str, value: &str) -> Result<(), String> {
    let count: i64 = conn
        .query_row(
            "SELECT COUNT(*) FROM ItemTable WHERE key = ?1",
            [key],
            |row| row.get(0),
        )
        .map_err(|e| format!("查询键{}失败: {}", key, e))?;

    if count > 0 {
        conn.execute("UPDATE ItemTable SET value = ?1 WHERE key = ?2", [value, key])
            .map_err(|e| format!("更新键{}失败: {}", key, e))?;
    } else {
        conn.execute("INSERT INTO ItemTable (key, value) VALUES (?1, ?2)", [key, value])
            .map_err(|e| format!("插入键{}失败: {}", key, e))?;
    }
    Ok(())
}

#[tauri::command]
pub async fn update_cursor_sqlite_db(db_path: String) -> DbUpdateResult {
    if !Path::new(&db_path).exists() {
        return DbUpdateResult {
            success: true,
            message: Some("数据库文件不存在，跳过更新".to_string()),
            error: None,
            updated_keys: None,
            new_ids: None,
            deleted_keys: None,
            activation_success: None,
        };
    }

    // Generate new IDs
    let machine_id = Uuid::new_v4().to_string();
    let anonymous_id = Uuid::new_v4().to_string();
    let machine_id_hash = {
        let hash = md5::compute(Uuid::new_v4().to_string().as_bytes());
        format!("{:x}", hash)
    };

    // Create backup
    let backup = format!("{}.bak", db_path);
    if !Path::new(&backup).exists() {
        let _ = fs::copy(&db_path, &backup);
    }

    // macOS: 清除 chflags uchg
    utils::clear_macos_immutable_flag(Path::new(&db_path));

    let conn = match Connection::open(&db_path) {
        Ok(c) => c,
        Err(e) => {
            return DbUpdateResult {
                success: false,
                message: None,
                error: Some(format!("打开数据库失败: {}", e)),
                updated_keys: None,
                new_ids: None,
                deleted_keys: None,
                activation_success: None,
            };
        }
    };

    // Check ItemTable exists
    let table_exists: bool = conn
        .query_row(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='ItemTable'",
            [],
            |row| row.get::<_, i64>(0),
        )
        .map(|c| c > 0)
        .unwrap_or(false);

    if !table_exists {
        return DbUpdateResult {
            success: true,
            message: Some("ItemTable表不存在，跳过更新".to_string()),
            error: None,
            updated_keys: None,
            new_ids: None,
            deleted_keys: None,
            activation_success: None,
        };
    }

    let ids = [
        ("machineId", machine_id.as_str()),
        ("anonymousId", anonymous_id.as_str()),
        ("machineIdHash", machine_id_hash.as_str()),
    ];

    let mut updated = Vec::new();
    for (key, value) in &ids {
        if upsert_item_table(&conn, key, value).is_ok() {
            updated.push(key.to_string());
        }
    }

    DbUpdateResult {
        success: true,
        message: Some("数据库更新成功".to_string()),
        error: None,
        updated_keys: Some(updated),
        new_ids: Some(serde_json::json!({
            "machineId": machine_id,
            "anonymousId": anonymous_id,
            "machineIdHash": machine_id_hash,
        })),
        deleted_keys: None,
        activation_success: None,
    }
}

#[tauri::command]
pub async fn update_cursor_auth(
    db_path: String,
    email: String,
    access_token: String,
    refresh_token: String,
    machine_id_reset: Option<bool>,
) -> DbUpdateResult {
    if !Path::new(&db_path).exists() {
        return DbUpdateResult {
            success: false, message: None,
            error: Some("数据库文件不存在".to_string()),
            updated_keys: None, new_ids: None, deleted_keys: None, activation_success: None,
        };
    }

    // Backup
    let backup = format!("{}.bak", db_path);
    if !Path::new(&backup).exists() {
        let _ = fs::copy(&db_path, &backup);
    }

    // Reset machine IDs if requested
    if machine_id_reset.unwrap_or(true) {
        if let Some(_cursor_dir) = Path::new(&db_path).parent().and_then(|p| p.parent()).and_then(|p| p.parent()) {
            // Best-effort reset
            let _ = machine_id::perform_full_machine_id_reset();
        }
    }

    // macOS: 清除 chflags uchg
    utils::clear_macos_immutable_flag(Path::new(&db_path));

    let conn = match Connection::open(&db_path) {
        Ok(c) => c,
        Err(e) => {
            return DbUpdateResult {
                success: false, message: None,
                error: Some(format!("打开数据库失败: {}", e)),
                updated_keys: None, new_ids: None, deleted_keys: None, activation_success: None,
            };
        }
    };

    // Delete serverConfig (key 通过 obfstr 函数拼接，反编译看不到明文)
    let server_config_key = utils::keys::ai_server_config();
    let _ = conn.execute("DELETE FROM ItemTable WHERE key = ?1", [&server_config_key]);

    // 准备所有 SQLite key
    let k_email = utils::keys::auth_email();
    let k_access = utils::keys::auth_access();
    let k_refresh = utils::keys::auth_refresh();
    let k_signup = utils::keys::auth_signup();
    let auth0 = utils::keys::auth0_value();

    let mut updates: Vec<(&str, String)> = Vec::new();
    if !email.is_empty() {
        updates.push((k_email.as_str(), email.clone()));
    }
    if !access_token.is_empty() {
        updates.push((k_access.as_str(), access_token.clone()));
    }
    if !refresh_token.is_empty() {
        updates.push((k_refresh.as_str(), refresh_token.clone()));
        updates.push((k_signup.as_str(), auth0.clone()));
    }

    let mut updated_keys = Vec::new();
    for (key, value) in &updates {
        if upsert_item_table(&conn, key, value).is_ok() {
            updated_keys.push(key.to_string());
        }
    }

    DbUpdateResult {
        success: true,
        message: Some("认证信息更新成功".to_string()),
        error: None,
        updated_keys: Some(updated_keys),
        new_ids: None,
        deleted_keys: None,
        activation_success: None,
    }
}

#[tauri::command]
pub async fn logout_current_cursor_account(db_path: String) -> DbUpdateResult {
    if db_path.is_empty() || !Path::new(&db_path).exists() {
        return DbUpdateResult {
            success: false, message: None,
            error: Some("数据库文件不存在".to_string()),
            updated_keys: None, new_ids: None, deleted_keys: None, activation_success: None,
        };
    }

    // macOS: 清除 chflags uchg
    utils::clear_macos_immutable_flag(Path::new(&db_path));

    let conn = match Connection::open(&db_path) {
        Ok(c) => c,
        Err(e) => {
            return DbUpdateResult {
                success: false, message: None,
                error: Some(format!("数据库操作失败: {}", e)),
                updated_keys: None, new_ids: None, deleted_keys: None, activation_success: None,
            };
        }
    };

    // 通过 obfstr 函数拼接所有要删除的 key（反编译看不到明文）
    let keys_to_delete: [String; 11] = [
        utils::keys::auth_email(),
        utils::keys::auth_access(),
        utils::keys::auth_refresh(),
        utils::keys::auth_signup(),
        utils::keys::ai_feature_status(),
        utils::keys::ai_feature_config(),
        utils::keys::auth_stripe(),
        utils::keys::ai_server_config(),
        utils::keys::auth_user(),
        utils::keys::auth_session(),
        utils::keys::vscode_chat_token(),
    ];

    let mut deleted = Vec::new();
    for key in &keys_to_delete {
        match conn.execute("DELETE FROM ItemTable WHERE key = ?1", [key]) {
            Ok(changes) if changes > 0 => {
                deleted.push(key.to_string());
            }
            _ => {}
        }
    }

    DbUpdateResult {
        success: true,
        message: Some("成功退出当前登录账号".to_string()),
        error: None,
        updated_keys: None,
        new_ids: None,
        deleted_keys: Some(deleted),
        activation_success: None,
    }
}

#[tauri::command]
pub async fn python_style_account_switch(
    db_path: String,
    email: String,
    access_token: String,
    refresh_token: String,
) -> DbUpdateResult {
    if db_path.is_empty() || email.is_empty() || access_token.is_empty() || refresh_token.is_empty() {
        return DbUpdateResult {
            success: false, message: None,
            error: Some("参数不能为空".to_string()),
            updated_keys: None, new_ids: None, deleted_keys: None, activation_success: None,
        };
    }

    if !Path::new(&db_path).exists() {
        return DbUpdateResult {
            success: false, message: None,
            error: Some(format!("数据库文件不存在: {}", db_path)),
            updated_keys: None, new_ids: None, deleted_keys: None, activation_success: None,
        };
    }

    // Backup
    let backup = format!("{}.bak", db_path);
    if !Path::new(&backup).exists() {
        let _ = fs::copy(&db_path, &backup);
    }

    // Step 1: Reset machine IDs
    let _ = machine_id::perform_full_machine_id_reset();

    // macOS: 清除 chflags uchg
    utils::clear_macos_immutable_flag(Path::new(&db_path));

    // Step 2: Update database auth
    let conn = match Connection::open(&db_path) {
        Ok(c) => c,
        Err(e) => {
            return DbUpdateResult {
                success: false, message: None,
                error: Some(format!("数据库操作失败: {}", e)),
                updated_keys: None, new_ids: None, deleted_keys: None, activation_success: None,
            };
        }
    };

    // Check table exists
    let table_exists: bool = conn
        .query_row(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='ItemTable'",
            [],
            |row| row.get::<_, i64>(0),
        )
        .map(|c| c > 0)
        .unwrap_or(false);

    if !table_exists {
        return DbUpdateResult {
            success: false, message: None,
            error: Some("ItemTable表不存在".to_string()),
            updated_keys: None, new_ids: None, deleted_keys: None, activation_success: None,
        };
    }

    let k_email = utils::keys::auth_email();
    let k_access = utils::keys::auth_access();
    let k_refresh = utils::keys::auth_refresh();
    let k_signup = utils::keys::auth_signup();
    let auth0 = utils::keys::auth0_value();
    let updates: [(&str, &str); 4] = [
        (k_email.as_str(), email.as_str()),
        (k_access.as_str(), access_token.as_str()),
        (k_refresh.as_str(), refresh_token.as_str()),
        (k_signup.as_str(), auth0.as_str()),
    ];

    let mut updated_keys = Vec::new();
    for (key, value) in &updates {
        if upsert_item_table(&conn, key, value).is_ok() {
            updated_keys.push(key.to_string());
        }
    }

    DbUpdateResult {
        success: true,
        message: Some("Python风格账号切换成功".to_string()),
        error: None,
        updated_keys: Some(updated_keys),
        new_ids: None,
        deleted_keys: None,
        activation_success: Some(true),
    }
}
