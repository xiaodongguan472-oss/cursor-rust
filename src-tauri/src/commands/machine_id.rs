use serde::{Deserialize, Serialize};
use std::fs;
use uuid::Uuid;
use super::utils;

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

/// Reset storage.json machine IDs (telemetry fields)
fn reset_storage_machine_ids() -> ResetResult {
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

    // Generate new IDs (与 Electron performFullMachineIdReset 一致：4 个字段都用 uuidv4)
    let machine_id = Uuid::new_v4().to_string();
    let mac_machine_id = Uuid::new_v4().to_string();
    let dev_device_id = Uuid::new_v4().to_string();
    let sqm_id = format!("{{{}}}", Uuid::new_v4().to_string().to_uppercase());

    let result = utils::safe_modify_file(&storage_path, || {
        let content = fs::read_to_string(&storage_path)
            .map_err(|e| format!("读取storage.json失败: {}", e))?;
        let mut config: serde_json::Value = serde_json::from_str(&content)
            .map_err(|e| format!("解析storage.json失败: {}", e))?;

        if let Some(obj) = config.as_object_mut() {
            obj.insert("telemetry.machineId".to_string(), serde_json::json!(machine_id));
            obj.insert("telemetry.macMachineId".to_string(), serde_json::json!(mac_machine_id));
            obj.insert("telemetry.devDeviceId".to_string(), serde_json::json!(dev_device_id));
            obj.insert("telemetry.sqmId".to_string(), serde_json::json!(sqm_id));
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
            new_ids: Some(serde_json::json!({
                "telemetry.machineId": machine_id,
                "telemetry.macMachineId": mac_machine_id,
                "telemetry.devDeviceId": dev_device_id,
                "telemetry.sqmId": sqm_id,
            })),
        },
        Err(e) => ResetResult {
            success: false,
            message: None,
            error: Some(e),
            new_ids: None,
        },
    }
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

/// Full machine ID reset (storage.json + files)
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

    // 1. Reset storage.json
    let storage_result = reset_storage_machine_ids();

    // 2. Reset cursor_dir/machineId 文件（Electron performFullMachineIdReset 单独处理的一步）
    let machine_id_file = cursor_dir.join("machineId");
    utils::clear_macos_immutable_flag(&machine_id_file);
    let _ = fs::write(&machine_id_file, Uuid::new_v4().to_string());

    // 3. Reset 其他 machine ID 相关文件
    reset_machine_id_files(&cursor_dir);

    // 4. Windows: 更新注册表中的 MachineGuid
    #[cfg(target_os = "windows")]
    {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x08000000;
        let machine_guid = Uuid::new_v4().to_string();
        let _ = std::process::Command::new("reg")
            .args([
                "add",
                "HKEY_LOCAL_MACHINE\\SOFTWARE\\Microsoft\\Cryptography",
                "/v",
                "MachineGuid",
                "/t",
                "REG_SZ",
                "/d",
                &machine_guid,
                "/f",
            ])
            .creation_flags(CREATE_NO_WINDOW)
            .output();
    }

    if storage_result.success {
        ResetResult {
            success: true,
            message: Some("机器码重置成功，重启Cursor后生效".to_string()),
            error: None,
            new_ids: storage_result.new_ids,
        }
    } else {
        // Files were still reset even if storage.json failed
        ResetResult {
            success: true,
            message: Some("机器码文件已重置，storage.json可能未更新".to_string()),
            error: storage_result.error,
            new_ids: None,
        }
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
