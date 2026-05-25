/// Machine ID 管理服务
///
/// 负责查看、备份、恢复、重置等完整生命周期管理。
/// 委托 infra 层执行实际 IO 操作。
use crate::domain::identity::*;
use crate::error::AppError;
use crate::infra::cursor::CursorBridge;
use crate::infra::store::{BackupStore, ConfigStore};
use crate::{log_info, log_error, log_debug};
use rand::Rng;
use sha2::{Digest, Sha256, Sha512};
use uuid::Uuid;
use std::path::PathBuf;

/// Machine ID 管理服务
pub struct IdentityService {
    cursor: CursorBridge,
    config: ConfigStore,
}

impl IdentityService {
    pub fn new(cursor: CursorBridge, config: ConfigStore) -> Self {
        Self { cursor, config }
    }

    // === 查看 ===

    /// 读取当前 Machine ID
    pub fn read_current(&self) -> Result<MachineIds, AppError> {
        self.cursor.storage().read_machine_ids()
    }

    /// 获取 Cursor 路径信息
    pub fn get_cursor_paths(&self) -> (String, String) {
        (
            self.cursor.paths.storage_json.to_string_lossy().to_string(),
            self.cursor.paths.sqlite_db.to_string_lossy().to_string(),
        )
    }

    /// 检查 Cursor 是否已安装
    pub fn check_installation(&self) -> bool {
        self.cursor.paths.storage_json.exists()
    }

    // === 备份 ===

    /// 获取统一备份存储
    fn backup_store(&self) -> Result<BackupStore, AppError> {
        let data_dir = crate::get_data_dir().map_err(AppError::from)?;
        Ok(BackupStore::new(&data_dir))
    }

    /// 读取当前完整 Machine ID（含系统级字段）
    fn read_current_full_ids(&self) -> Result<MachineIds, AppError> {
        self.cursor.read_full_machine_ids()
    }

    /// 创建结构化备份到 cursor_data/backup
    pub fn create_backup(&self, reason: &str) -> Result<String, AppError> {
        let ids = self.read_current_full_ids()?;
        let backup = MachineIdBackupFile {
            version: 1,
            backup_type: "machine_ids".to_string(),
            created_at: chrono::Local::now().to_rfc3339(),
            reason: reason.to_string(),
            machine_ids: ids,
        };

        let store = self.backup_store()?;
        let backup_path = store.save_backup(&backup, reason)?;
        log_info!("创建结构化备份: {}", backup_path);
        Ok(backup_path)
    }

    /// 获取所有备份列表
    pub fn list_backups(&self) -> Result<Vec<BackupInfo>, AppError> {
        let store = self.backup_store()?;
        store.find_backups()
    }

    /// 从备份提取 Machine ID
    pub fn extract_ids_from_backup(&self, backup_path: &str) -> Result<MachineIds, AppError> {
        let store = self.backup_store()?;
        let backup = store.load_backup(backup_path)?;
        Ok(backup.machine_ids)
    }

    // === 重置 ===

    /// 生成全新的随机 Machine ID 集合
    pub fn generate_new_ids(&self) -> MachineIds {
        let dev_device_id = Uuid::new_v4().to_string();

        let mut machine_id_data = [0u8; 32];
        rand::thread_rng().fill(&mut machine_id_data);
        let machine_id = format!("{:x}", Sha256::digest(&machine_id_data));

        let mut mac_machine_id_data = [0u8; 64];
        rand::thread_rng().fill(&mut mac_machine_id_data);
        let mac_machine_id = format!("{:x}", Sha512::digest(&mac_machine_id_data));

        let sqm_id = format!("{{{}}}", Uuid::new_v4().to_string().to_uppercase());
        let service_machine_id = Uuid::new_v4().to_string();

        MachineIds {
            dev_device_id: dev_device_id.clone(),
            mac_machine_id,
            machine_id,
            sqm_id: sqm_id.clone(),
            service_machine_id,
            machine_guid: Some(dev_device_id),
            sqm_client_id: Some(sqm_id),
        }
    }

    /// 将 Machine ID 写入所有存储位置
    pub fn apply_ids(&self, ids: &MachineIds) -> Result<Vec<String>, AppError> {
        let mut details = Vec::new();

        // 1. 更新 storage.json
        self.cursor.storage().write_machine_ids(ids)?;
        details.push("更新 storage.json 成功".to_string());

        // 2. 更新 SQLite (state.vscdb)
        if self.cursor.paths.sqlite_db.exists() {
            match self.cursor.sqlite().update_service_machine_id(&ids.service_machine_id) {
                Ok(_) => details.push("更新 state.vscdb 成功".to_string()),
                Err(e) => details.push(format!("更新 state.vscdb 失败: {}", e)),
            }
        }

        // 3. 更新 machineId 文件
        if let Err(e) = self.update_machine_id_file(&ids.dev_device_id) {
            details.push(format!("更新 machineId 文件失败: {}", e));
        } else {
            details.push("更新 machineId 文件成功".to_string());
        }

        // 4. 更新系统 ID（注册表等）
        #[cfg(target_os = "windows")]
        {
            let platform = crate::infra::platform::create();
            match platform.update_system_ids(ids) {
                Ok(_) => details.push("更新系统注册表成功".to_string()),
                Err(e) => details.push(format!("更新系统注册表失败: {}", e)),
            }
        }

        Ok(details)
    }

    /// 重置 Machine ID（先结构化备份，再生成新 ID 写入所有位置）
    pub fn reset(&self) -> Result<ResetResult, AppError> {
        log_info!("开始机器ID重置流程...");
        let mut details = Vec::new();

        if !self.cursor.paths.storage_json.exists() {
            return Ok(ResetResult {
                success: false,
                message: "storage.json 文件不存在".to_string(),
                details,
                new_ids: None,
            });
        }

        match self.create_backup("reset_machine_ids") {
            Ok(path) => details.push(format!("已创建备份: {}", path)),
            Err(e) => details.push(format!("备份失败（继续重置）: {}", e)),
        }

        let new_ids = self.generate_new_ids();
        details.push("已生成新 Machine ID".to_string());

        let apply_details = self.apply_ids(&new_ids)?;
        details.extend(apply_details);

        log_info!("机器ID重置完成");
        Ok(ResetResult {
            success: true,
            message: "Machine ID 重置成功".to_string(),
            details,
            new_ids: Some(new_ids),
        })
    }

    /// 从结构化备份恢复 Machine ID
    pub fn restore_from_backup(&self, backup_path: &str) -> Result<RestoreResult, AppError> {
        let mut details = Vec::new();

        let ids = self.extract_ids_from_backup(backup_path)?;
        details.push(format!("从备份解析到 Machine ID: {}", ids.dev_device_id));

        let apply_details = self.apply_ids(&ids)?;
        details.extend(apply_details);

        Ok(RestoreResult {
            success: true,
            message: "已从备份恢复 Machine ID".to_string(),
            details,
        })
    }

    // === 自定义路径 ===

    pub fn set_custom_path(&self, path: &str) -> Result<String, AppError> {
        self.config.set_custom_cursor_path(path)?;
        log_info!("设置自定义 Cursor 路径: {}", path);
        Ok(format!("已设置自定义路径: {}", path))
    }

    pub fn get_custom_path(&self) -> Option<String> {
        self.config.get_custom_cursor_path()
    }

    pub fn clear_custom_path(&self) -> Result<String, AppError> {
        self.config.clear_custom_cursor_path()?;
        log_info!("已清除自定义 Cursor 路径");
        Ok("已清除自定义路径".to_string())
    }

    // === 内部方法 ===

    /// 更新 machineId 文件
    fn update_machine_id_file(&self, dev_device_id: &str) -> Result<(), AppError> {
        let machine_id_path = Self::get_machine_id_path()?;

        if let Some(parent) = machine_id_path.parent() {
            std::fs::create_dir_all(parent)?;
        }

        std::fs::write(&machine_id_path, dev_device_id)?;
        Ok(())
    }

    /// 获取 machineId 文件路径
    fn get_machine_id_path() -> Result<PathBuf, AppError> {
        #[cfg(target_os = "windows")]
        {
            let appdata = std::env::var("APPDATA")
                .map_err(|_| AppError::CursorNotFound)?;
            Ok(PathBuf::from(appdata).join("Cursor").join("machineId"))
        }

        #[cfg(target_os = "macos")]
        {
            let home = dirs::home_dir().ok_or(AppError::CursorNotFound)?;
            Ok(home.join("Library").join("Application Support").join("Cursor").join("machineId"))
        }

        #[cfg(target_os = "linux")]
        {
            let home = dirs::home_dir().ok_or(AppError::CursorNotFound)?;
            Ok(home.join(".config").join("Cursor").join("machineId"))
        }
    }

    /// 获取 CursorBridge 引用
    pub fn cursor(&self) -> &CursorBridge {
        &self.cursor
    }
}
