use serde::{Deserialize, Serialize};
use std::fs;
use std::path::Path;
use uuid::Uuid;
use super::utils;
use super::cursor_paths;
use super::cursor_modify;

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ResetResult {
    pub success: bool,
    pub message: Option<String>,
    pub error: Option<String>,
    pub new_ids: Option<serde_json::Value>,
}

#[tauri::command]
pub async fn get_machine_id() -> Result<String, String> {
    // Try cached device ID first
    let app_dir = utils::get_app_data_dir();
    let device_id_file = app_dir.join("device_id.txt");

    if device_id_file.exists() {
        if let Ok(cached) = fs::read_to_string(&device_id_file) {
            let cached = cached.trim().to_string();
            if cached.len() > 10 {
                return Ok(cached);
            }
        }
    }

    // Generate new device ID
    let device_id = utils::generate_stable_machine_id();

    // Cache it
    let _ = fs::create_dir_all(&app_dir);
    let _ = fs::write(&device_id_file, &device_id);

    Ok(device_id)
}

/// 完整的 7 字段 Machine ID 集合（与 MyCursor 完全重置对齐）
struct FullMachineIds {
    dev_device_id: String,        // UUID v4
    machine_id: String,           // SHA-256 (64 hex)
    mac_machine_id: String,       // SHA-512 (128 hex)
    sqm_id: String,               // {UUID 大写}
    service_machine_id: String,   // UUID v4
    machine_guid: String,         // UUID v4（与 dev_device_id 相同，作为 system 级 GUID）
    sqm_client_id: String,        // 同 sqm_id
}

impl FullMachineIds {
    fn generate() -> Self {
        let dev = Uuid::new_v4().to_string();
        let sqm = format!("{{{}}}", Uuid::new_v4().to_string().to_uppercase());
        Self {
            dev_device_id: dev.clone(),
            machine_id: utils::generate_machine_id_sha256(),
            mac_machine_id: utils::generate_mac_machine_id_sha512(),
            sqm_id: sqm.clone(),
            service_machine_id: Uuid::new_v4().to_string(),
            machine_guid: dev,
            sqm_client_id: sqm,
        }
    }

    fn to_json_value(&self) -> serde_json::Value {
        let mut m = serde_json::Map::new();
        m.insert(utils::keys::telem_machine(), serde_json::json!(self.machine_id));
        m.insert(utils::keys::telem_mac(), serde_json::json!(self.mac_machine_id));
        m.insert(utils::keys::telem_dev(), serde_json::json!(self.dev_device_id));
        m.insert(utils::keys::telem_sqm(), serde_json::json!(self.sqm_id));
        m.insert(utils::keys::telem_machine_guid(), serde_json::json!(self.machine_guid));
        m.insert(utils::keys::telem_sqm_client(), serde_json::json!(self.sqm_client_id));
        m.insert(utils::keys::storage_service_machine(), serde_json::json!(self.service_machine_id));
        serde_json::Value::Object(m)
    }
}

/// Reset storage.json machine IDs（写入完整 7 个字段，对齐 MyCursor 完全重置）
fn reset_storage_machine_ids_with(ids: &FullMachineIds) -> ResetResult {
    let storage_path = match utils::get_cursor_storage_json_path() {
        Some(p) => p,
        None => {
            return ResetResult {
                success: false,
                message: None,
                error: Some("无法确定storage.json路径".to_string()),
                new_ids: None,
            };
        }
    };

    if !storage_path.exists() {
        return ResetResult {
            success: false,
            message: None,
            error: Some(format!("未找到配置文件: {}", storage_path.display())),
            new_ids: None,
        };
    }

    // Create backup
    let backup_dir = storage_path.parent().unwrap().join("backups");
    let _ = fs::create_dir_all(&backup_dir);
    let backup_name = format!(
        "storage.json.backup_{}",
        chrono::Local::now().format("%Y-%m-%d_%H-%M-%S")
    );
    let _ = fs::copy(&storage_path, backup_dir.join(&backup_name));

    let result = utils::safe_modify_file(&storage_path, || {
        let content = fs::read_to_string(&storage_path)
            .map_err(|e| format!("读取storage.json失败: {}", e))?;
        let mut config: serde_json::Value = serde_json::from_str(&content)
            .map_err(|e| format!("解析storage.json失败: {}", e))?;

        if let Some(obj) = config.as_object_mut() {
            // telemetry.* 系列（5 个字段）
            obj.insert(utils::keys::telem_machine(), serde_json::json!(ids.machine_id));
            obj.insert(utils::keys::telem_mac(), serde_json::json!(ids.mac_machine_id));
            obj.insert(utils::keys::telem_dev(), serde_json::json!(ids.dev_device_id));
            obj.insert(utils::keys::telem_sqm(), serde_json::json!(ids.sqm_id));
            obj.insert(utils::keys::telem_machine_guid(), serde_json::json!(ids.machine_guid));
            obj.insert(utils::keys::telem_sqm_client(), serde_json::json!(ids.sqm_client_id));
            // storage.serviceMachineId（最关键的后端识别字段）
            obj.insert(utils::keys::storage_service_machine(), serde_json::json!(ids.service_machine_id));
        }

        let updated = serde_json::to_string_pretty(&config)
            .map_err(|e| format!("序列化storage.json失败: {}", e))?;
        fs::write(&storage_path, updated)
            .map_err(|e| format!("写入storage.json失败: {}", e))?;
        Ok(())
    });

    match result {
        Ok(()) => ResetResult {
            success: true,
            message: Some("storage.json机器码重置成功".to_string()),
            error: None,
            new_ids: Some(ids.to_json_value()),
        },
        Err(e) => ResetResult {
            success: false,
            message: None,
            error: Some(e),
            new_ids: None,
        },
    }
}

/// 向后兼容入口：旧的命令 reset_cursor_machine_id 仍可调用，生成新 ID 并写入
fn reset_storage_machine_ids() -> ResetResult {
    let ids = FullMachineIds::generate();
    reset_storage_machine_ids_with(&ids)
}

/// Reset machine ID files in the Cursor data directory
fn reset_machine_id_files(cursor_dir: &std::path::Path) {
    let device_id = Uuid::new_v4().to_string();
    let anonymous_id = Uuid::new_v4().to_string();

    let files = [
        (cursor_dir.join("machineid.json"), true),
        (cursor_dir.join("machineid"), false),
        (cursor_dir.join("machineId"), false),
        (
            cursor_dir.join("User").join("globalStorage").join("machine-id"),
            false,
        ),
        (
            cursor_dir.join("User").join("globalStorage").join("anonymousid"),
            false,
        ),
    ];

    for (file_path, is_json) in &files {
        if let Some(parent) = file_path.parent() {
            let _ = fs::create_dir_all(parent);
        }
        // macOS: 清除 chflags uchg 不可变标志（若文件已存在）
        utils::clear_macos_immutable_flag(file_path);

        if *is_json {
            let data = serde_json::json!({"machineId": device_id});
            let _ = fs::write(file_path, serde_json::to_string_pretty(&data).unwrap_or_default());
        } else {
            let id = if file_path.file_name().map(|n| n == "anonymousid").unwrap_or(false) {
                &anonymous_id
            } else {
                &device_id
            };
            let _ = fs::write(file_path, id);
        }
    }
}

/// 更新 state.vscdb 中的 storage.serviceMachineId（与 storage.json 保持同步）
fn update_sqlite_service_machine_id(db_path: &Path, service_machine_id: &str) -> Result<(), String> {
    if !db_path.exists() {
        return Ok(()); // 数据库不存在则跳过
    }

    // macOS: 先清除 immutable flag
    utils::clear_macos_immutable_flag(db_path);

    let conn = rusqlite::Connection::open(db_path)
        .map_err(|e| format!("打开数据库失败: {}", e))?;

    // 检查表是否存在
    let table_exists: bool = conn
        .query_row(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='ItemTable'",
            [],
            |row| row.get::<_, i64>(0),
        )
        .map(|c| c > 0)
        .unwrap_or(false);

    if !table_exists {
        return Ok(());
    }

    let key = utils::keys::storage_service_machine();
    conn.execute(
        "INSERT INTO ItemTable (key, value) VALUES (?1, ?2) \
         ON CONFLICT(key) DO UPDATE SET value = ?2",
        rusqlite::params![key, service_machine_id],
    )
    .map_err(|e| format!("写入 storage.serviceMachineId 失败: {}", e))?;

    Ok(())
}

/// Full machine ID reset (storage.json + state.vscdb + machineId files + 注册表 + main.js 修补)
///
/// 完整流程（与 MyCursor 的"完全重置"对齐）：
/// 1. 生成一组完整 ID（dev/machine/mac/sqm/service/guid/sqmClient）
/// 2. storage.json 写入 7 个字段
/// 3. state.vscdb 同步 storage.serviceMachineId
/// 4. cursor_dir/machineId 文件 → dev_device_id
/// 5. 其他 machineId 散落文件 → 随机 UUID
/// 6. Windows: 注册表 MachineGuid + SQMClient MachineId
/// 7. main.js 修补：去掉 getMachineId/getMacMachineId 的 ?? fallback
pub fn perform_full_machine_id_reset() -> ResetResult {
    let cursor_dir = match utils::get_cursor_data_dir() {
        Some(d) => d,
        None => {
            return ResetResult {
                success: false,
                message: None,
                error: Some("Cursor数据目录不存在".to_string()),
                new_ids: None,
            };
        }
    };

    if !cursor_dir.exists() {
        return ResetResult {
            success: false,
            message: None,
            error: Some(format!("Cursor数据目录不存在: {}", cursor_dir.display())),
            new_ids: None,
        };
    }

    // 生成一组完整的 ID（所有位置共用同一组）
    let ids = FullMachineIds::generate();
    let mut warnings: Vec<String> = Vec::new();

    // 1. 写入 storage.json（7 个字段）
    let storage_result = reset_storage_machine_ids_with(&ids);
    if !storage_result.success {
        if let Some(ref e) = storage_result.error {
            warnings.push(format!("storage.json: {}", e));
        }
    }

    // 2. 写入 state.vscdb 的 storage.serviceMachineId（关键：与 storage.json 保持同步）
    let db_path = cursor_dir.join("User").join("globalStorage").join("state.vscdb");
    if let Err(e) = update_sqlite_service_machine_id(&db_path, &ids.service_machine_id) {
        warnings.push(format!("state.vscdb: {}", e));
    }

    // 3. 写入 cursor_dir/machineId 文件（dev_device_id）
    let machine_id_file = cursor_dir.join("machineId");
    utils::clear_macos_immutable_flag(&machine_id_file);
    if let Some(parent) = machine_id_file.parent() {
        let _ = fs::create_dir_all(parent);
    }
    let _ = fs::write(&machine_id_file, &ids.dev_device_id);

    // 4. 写入其他 machine ID 散落文件
    reset_machine_id_files(&cursor_dir);

    // 5. Windows: 更新注册表中的 MachineGuid 和 SQMClient MachineId
    #[cfg(target_os = "windows")]
    {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x08000000;
        // MachineGuid
        let _ = std::process::Command::new("reg")
            .args([
                "add",
                "HKEY_LOCAL_MACHINE\\SOFTWARE\\Microsoft\\Cryptography",
                "/v",
                "MachineGuid",
                "/t",
                "REG_SZ",
                "/d",
                &ids.machine_guid,
                "/f",
            ])
            .creation_flags(CREATE_NO_WINDOW)
            .output();
        // SQMClient MachineId
        let _ = std::process::Command::new("reg")
            .args([
                "add",
                "HKEY_LOCAL_MACHINE\\SOFTWARE\\Microsoft\\SQMClient",
                "/v",
                "MachineId",
                "/t",
                "REG_SZ",
                "/d",
                &ids.sqm_client_id,
                "/f",
            ])
            .creation_flags(CREATE_NO_WINDOW)
            .output();
    }
    // macOS / Linux 无系统级注册表，不做处理（与 MyCursor 行为一致）

    // 6. 修补 main.js（最关键：去掉 ?? fallback，让 Cursor 永远使用 storage.json 里的新 ID）
    let cursor_paths_info = cursor_paths::get_cursor_paths();
    if let Some(main_path_str) = cursor_paths_info.main_path {
        let main_path = Path::new(&main_path_str);
        match cursor_modify::patch_main_js_file(main_path) {
            Ok(true) => {}, // main.js 已修补
            Ok(false) => {}, // main.js 之前已修补过或无需修补，正常情况
            Err(e) => warnings.push(format!("main.js 修补失败: {}", e)),
        }
    } else {
        warnings.push("未找到 Cursor 安装路径，main.js 未修补".to_string());
    }

    let warning_msg = if warnings.is_empty() {
        None
    } else {
        Some(warnings.join("; "))
    };

    ResetResult {
        success: true,
        message: Some(if warning_msg.is_some() {
            "机器码已重置（部分步骤有警告），重启Cursor后生效".to_string()
        } else {
            "机器码完全重置成功，重启Cursor后生效".to_string()
        }),
        error: warning_msg,
        new_ids: Some(ids.to_json_value()),
    }
}

#[tauri::command]
pub async fn reset_cursor_machine_id() -> ResetResult {
    reset_storage_machine_ids()
}

#[tauri::command]
pub async fn reset_machine_ids_standalone() -> ResetResult {
    perform_full_machine_id_reset()
}
