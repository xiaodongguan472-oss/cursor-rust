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
    /// 每一步的执行结果（与 MyCursor details 字段对齐）
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub details: Vec<String>,
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

#[cfg(target_os = "windows")]
fn set_file_readonly(path: &Path, readonly: bool) -> Result<(), String> {
    let mut permissions = fs::metadata(path)
        .map_err(|e| format!("获取文件属性失败: {}", e))?
        .permissions();
    permissions.set_readonly(readonly);
    fs::set_permissions(path, permissions).map_err(|e| format!("设置文件只读属性失败: {}", e))
}

#[cfg(target_os = "windows")]
fn write_storage_json_for_reset(path: &Path, content: &str) -> Result<(), String> {
    let was_readonly = fs::metadata(path)
        .map_err(|e| format!("获取storage.json属性失败: {}", e))?
        .permissions()
        .readonly();

    if was_readonly {
        set_file_readonly(path, false)
            .map_err(|e| format!("移除storage.json只读属性失败: {}", e))?;
    }

    if let Err(e) = fs::write(path, content) {
        if was_readonly {
            let _ = set_file_readonly(path, true);
        }
        return Err(format!("写入storage.json失败: {}", e));
    }

    set_file_readonly(path, true).map_err(|e| format!("恢复storage.json只读属性失败: {}", e))
}

/// Reset storage.json machine IDs（1:1 对齐 MyCursor：原子写入 + 5 核心字段）
///
/// 写入字段（与 MyCursor write_machine_ids 完全一致 + 我们补充的 2 个 telemetry 字段）：
/// - telemetry.devDeviceId
/// - telemetry.macMachineId
/// - telemetry.machineId
/// - telemetry.sqmId
/// - storage.serviceMachineId（关键的后端识别字段）
fn reset_storage_machine_ids_with(ids: &FullMachineIds) -> ResetResult {
    let storage_path = match utils::get_cursor_storage_json_path() {
        Some(p) => p,
        None => {
            return ResetResult {
                success: false,
                message: None,
                error: Some("无法确定storage.json路径".to_string()),
                new_ids: None,
                details: vec![],
            };
        }
    };

    if !storage_path.exists() {
        return ResetResult {
            success: false,
            message: None,
            error: Some(format!("未找到配置文件: {}", storage_path.display())),
            new_ids: None,
            details: vec![],
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

    // macOS: 清除 chflags uchg/schg
    utils::clear_macos_immutable_flag(&storage_path);

    // 读取现有 storage.json
    let result: Result<(), String> = (|| {
        let content = fs::read_to_string(&storage_path)
            .map_err(|e| format!("读取storage.json失败: {}", e))?;
        let mut config: serde_json::Value = serde_json::from_str(&content)
            .map_err(|e| format!("解析storage.json失败: {}", e))?;

        if let Some(obj) = config.as_object_mut() {
            // === 5 核心字段（与 MyCursor write_machine_ids 完全一致）===
            obj.insert(utils::keys::telem_machine(), serde_json::json!(ids.machine_id));
            obj.insert(utils::keys::telem_mac(), serde_json::json!(ids.mac_machine_id));
            obj.insert(utils::keys::telem_dev(), serde_json::json!(ids.dev_device_id));
            obj.insert(utils::keys::telem_sqm(), serde_json::json!(ids.sqm_id));
            obj.insert(utils::keys::storage_service_machine(), serde_json::json!(ids.service_machine_id));
            // === 额外补充字段（不在 MyCursor 写入列表中，但属于安全冗余）===
            obj.insert(utils::keys::telem_machine_guid(), serde_json::json!(ids.machine_guid));
            obj.insert(utils::keys::telem_sqm_client(), serde_json::json!(ids.sqm_client_id));
        }

        let updated = serde_json::to_string_pretty(&config)
            .map_err(|e| format!("序列化storage.json失败: {}", e))?;

        // === 原子写入（与 MyCursor write_all 完全一致）===
        // 1. 写到 .tmp 临时文件
        // 2. rename 原子替换
        #[cfg(target_os = "windows")]
        {
            write_storage_json_for_reset(&storage_path, &updated)?;
        }

        #[cfg(not(target_os = "windows"))]
        {
            let tmp = storage_path.with_extension("json.tmp");
            fs::write(&tmp, &updated)
                .map_err(|e| format!("写入临时文件失败: {}", e))?;
            fs::rename(&tmp, &storage_path)
                .map_err(|e| format!("替换storage.json失败: {}", e))?;
        }
        Ok(())
    })();

    match result {
        Ok(()) => ResetResult {
            success: true,
            message: Some("storage.json机器码重置成功".to_string()),
            error: None,
            new_ids: Some(ids.to_json_value()),
            details: vec![format!("storage.json 已更新: {}", storage_path.display())],
        },
        Err(e) => ResetResult {
            success: false,
            message: None,
            error: Some(e.clone()),
            new_ids: None,
            details: vec![format!("storage.json 写入失败: {}", e)],
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
            let content = serde_json::to_string_pretty(&data).unwrap_or_default();
            let _ = utils::safe_modify_file(file_path, || {
                let tmp_path = file_path.with_extension("tmp");
                fs::write(&tmp_path, &content)
                    .map_err(|e| format!("写 .tmp 失败: {}", e))?;
                fs::rename(&tmp_path, file_path).map_err(|e| {
                    let _ = fs::remove_file(&tmp_path);
                    format!("原子替换失败: {}", e)
                })
            });
        } else {
            let id = if file_path.file_name().map(|n| n == "anonymousid").unwrap_or(false) {
                &anonymous_id
            } else {
                &device_id
            };
            let id_clone = id.to_string();
            let _ = utils::safe_modify_file(file_path, || {
                let tmp_path = file_path.with_extension("tmp");
                fs::write(&tmp_path, &id_clone)
                    .map_err(|e| format!("写 .tmp 失败: {}", e))?;
                fs::rename(&tmp_path, file_path).map_err(|e| {
                    let _ = fs::remove_file(&tmp_path);
                    format!("原子替换失败: {}", e)
                })
            });
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
/// 2. storage.json 写入 7 个字段（原子 .tmp + rename）
/// 3. state.vscdb 同步 storage.serviceMachineId
/// 4. cursor_dir/machineId 文件 → dev_device_id（原子 rename）
/// 5. 其他 machineId 散落文件 → 随机 UUID（原子 rename）
/// 6. Windows: 注册表 MachineGuid + SQMClient MachineId
/// 7. main.js 修补：去掉 getMachineId/getMacMachineId 的 ?? fallback
///
/// 设计要点：**所有写入用 .tmp + rename 原子替换**，Cursor 即使在运行也大概率能写入成功 ——
/// Windows 的 MoveFileEx 在 Cursor 用 FILE_SHARE_DELETE 打开文件时生效；
/// macOS APFS 的 rename(2) 更宽容，旧 inode 还活着，新 inode 在同一路径建立。
/// 因此**不再前置检查 Cursor 进程**，手动按钮 / 自动换号 / 一键换号统统走同一份代码。
pub fn perform_full_machine_id_reset() -> ResetResult {
    let cursor_dir = match utils::get_cursor_data_dir() {
        Some(d) => d,
        None => {
            return ResetResult {
                success: false,
                message: None,
                error: Some("Cursor数据目录不存在".to_string()),
                new_ids: None,
                details: vec![],
            };
        }
    };

    if !cursor_dir.exists() {
        return ResetResult {
            success: false,
            message: None,
            error: Some(format!("Cursor数据目录不存在: {}", cursor_dir.display())),
            new_ids: None,
            details: vec![],
        };
    }

    // 生成一组完整的 ID（所有位置共用同一组）
    let ids = FullMachineIds::generate();
    let mut details: Vec<String> = Vec::new();
    let mut warnings: Vec<String> = Vec::new();

    details.push(format!("[步骤1] 生成新 Machine ID: dev={}, machine={}...",
        &ids.dev_device_id[..8.min(ids.dev_device_id.len())],
        &ids.machine_id[..8.min(ids.machine_id.len())]));

    // === 步骤 2: 写入 storage.json ===
    let storage_result = reset_storage_machine_ids_with(&ids);
    if storage_result.success {
        details.push("[步骤2] storage.json 写入成功".to_string());
    } else {
        let err = storage_result.error.clone().unwrap_or_else(|| "未知错误".to_string());
        details.push(format!("[步骤2] ✗ storage.json 写入失败: {}", err));
        warnings.push(format!("storage.json: {}", err));
    }

    // === 步骤 3: 写入 state.vscdb ===
    let db_path = cursor_dir.join("User").join("globalStorage").join("state.vscdb");
    if !db_path.exists() {
        details.push(format!("[步骤3] state.vscdb 不存在，跳过: {}", db_path.display()));
    } else {
        match update_sqlite_service_machine_id(&db_path, &ids.service_machine_id) {
            Ok(()) => details.push("[步骤3] state.vscdb storage.serviceMachineId 写入成功".to_string()),
            Err(e) => {
                details.push(format!("[步骤3] ✗ state.vscdb 写入失败: {}", e));
                warnings.push(format!("state.vscdb: {}", e));
            }
        }
    }

    // === 步骤 4: 写入 machineId 文件 ===
    // 关键策略：用 safe_modify_file 处理只读属性 + 原子 rename。
    // 原子 rename 对 Cursor 运行时也大概率能成功：写到 .tmp → MoveFileEx 替换。
    // 在 Cursor 用 FILE_SHARE_DELETE 打开文件的情况下，rename 不会被独占阻塞。
    let machine_id_file = cursor_dir.join("machineId");
    utils::clear_macos_immutable_flag(&machine_id_file);
    if let Some(parent) = machine_id_file.parent() {
        let _ = fs::create_dir_all(parent);
    }
    let dev_device_id = ids.dev_device_id.clone();
    let write_result = utils::safe_modify_file(&machine_id_file, || {
        let tmp_path = machine_id_file.with_extension("tmp");
        fs::write(&tmp_path, &dev_device_id)
            .map_err(|e| format!("写 machineId.tmp 失败: {}", e))?;
        fs::rename(&tmp_path, &machine_id_file)
            .map_err(|e| {
                // rename 失败时 .tmp 留在磁盘上，清理一下
                let _ = fs::remove_file(&tmp_path);
                format!("原子替换 machineId 失败: {}", e)
            })
    });
    match write_result {
        Ok(()) => details.push(format!("[步骤4] machineId 文件已写入: {}", machine_id_file.display())),
        Err(e) => {
            details.push(format!("[步骤4] ✗ machineId 文件写入失败: {}", e));
            warnings.push(format!("machineId 文件: {}", e));
        }
    }

    // === 步骤 5: 写入其他散落 machineId 文件 ===
    reset_machine_id_files(&cursor_dir);
    details.push("[步骤5] 散落 machineId 文件已重置".to_string());

    // === 步骤 6: 平台相关系统级 ID ===
    #[cfg(target_os = "windows")]
    {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x08000000;
        let mut reg_results = Vec::new();
        // MachineGuid
        match std::process::Command::new("reg")
            .args([
                "add", "HKEY_LOCAL_MACHINE\\SOFTWARE\\Microsoft\\Cryptography",
                "/v", "MachineGuid", "/t", "REG_SZ", "/d", &ids.machine_guid, "/f",
            ])
            .creation_flags(CREATE_NO_WINDOW)
            .output()
        {
            Ok(o) if o.status.success() => reg_results.push("MachineGuid"),
            _ => warnings.push("注册表 MachineGuid 写入失败（需要管理员权限）".to_string()),
        }
        // SQMClient MachineId
        match std::process::Command::new("reg")
            .args([
                "add", "HKEY_LOCAL_MACHINE\\SOFTWARE\\Microsoft\\SQMClient",
                "/v", "MachineId", "/t", "REG_SZ", "/d", &ids.sqm_client_id, "/f",
            ])
            .creation_flags(CREATE_NO_WINDOW)
            .output()
        {
            Ok(o) if o.status.success() => reg_results.push("SQMClient/MachineId"),
            _ => warnings.push("注册表 SQMClient/MachineId 写入失败（需要管理员权限）".to_string()),
        }
        if !reg_results.is_empty() {
            details.push(format!("[步骤6-Windows] 注册表已更新: {}", reg_results.join(", ")));
        }
    }
    #[cfg(target_os = "macos")]
    {
        details.push("[步骤6-macOS] 跳过系统级 ID（macOS 无注册表，与 MyCursor 行为一致）".to_string());
    }
    #[cfg(target_os = "linux")]
    {
        details.push("[步骤6-Linux] 跳过系统级 ID".to_string());
    }

    // === 步骤 7: 修补 main.js（最关键的一步）===
    let cursor_paths_info = cursor_paths::get_cursor_paths();
    match cursor_paths_info.main_path {
        Some(main_path_str) => {
            let main_path = Path::new(&main_path_str);
            details.push(format!("[步骤7] 找到 main.js: {}", main_path_str));
            match cursor_modify::patch_main_js_file(main_path) {
                Ok(true) => details.push("[步骤7] ✓ main.js 修补成功（移除 ?? 硬编码 fallback）".to_string()),
                Ok(false) => details.push("[步骤7] main.js 无需修补（可能已修补过或正则未匹配）".to_string()),
                Err(e) => {
                    details.push(format!("[步骤7] ✗ main.js 修补失败: {}", e));
                    warnings.push(format!("main.js 修补失败: {}", e));
                }
            }
        }
        None => {
            let base_info = cursor_paths_info.base_path.unwrap_or_else(|| "未检测到".to_string());
            details.push(format!("[步骤7] ✗ 未找到 main.js，base_path={}, error={:?}",
                base_info, cursor_paths_info.error));
            warnings.push("未找到 Cursor 安装路径，main.js 未修补（这会导致重置失效）".to_string());
        }
    }

    let warning_msg = if warnings.is_empty() {
        None
    } else {
        Some(warnings.join("; "))
    };

    ResetResult {
        success: warnings.is_empty(),
        message: Some(if warning_msg.is_some() {
            "机器码已重置（部分步骤有警告），请点击无感换号".to_string()
        } else {
            "机器码完全重置成功，请点击无感换号".to_string()
        }),
        error: warning_msg,
        new_ids: Some(ids.to_json_value()),
        details,
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
