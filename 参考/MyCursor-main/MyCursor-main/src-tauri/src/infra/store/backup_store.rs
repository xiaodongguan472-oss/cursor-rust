/// 备份文件管理
use crate::domain::identity::{BackupInfo, MachineIdBackupFile};
use crate::error::AppError;
use std::path::PathBuf;

/// 备份文件存储
pub struct BackupStore {
    backup_dir: PathBuf,
}

impl BackupStore {
    pub fn new(data_dir: &PathBuf) -> Self {
        Self {
            backup_dir: data_dir.join("backup"),
        }
    }

    /// 获取备份目录
    pub fn backup_dir(&self) -> &PathBuf {
        &self.backup_dir
    }

    /// 确保备份目录存在
    pub fn ensure_dir(&self) -> Result<(), AppError> {
        std::fs::create_dir_all(&self.backup_dir)?;
        Ok(())
    }

    /// 生成新的备份文件路径
    pub fn new_backup_path(&self, reason: &str) -> Result<PathBuf, AppError> {
        self.ensure_dir()?;
        let timestamp = chrono::Local::now().format("%Y%m%d_%H%M%S").to_string();
        let sanitized_reason = reason
            .chars()
            .map(|c| if c.is_ascii_alphanumeric() { c } else { '_' })
            .collect::<String>();
        Ok(self.backup_dir.join(format!(
            "machine_ids_{}_{}.json",
            sanitized_reason,
            timestamp
        )))
    }

    /// 保存结构化备份
    pub fn save_backup(&self, backup: &MachineIdBackupFile, reason: &str) -> Result<String, AppError> {
        let path = self.new_backup_path(reason)?;
        let content = serde_json::to_string_pretty(backup)?;
        std::fs::write(&path, content)?;
        Ok(path.to_string_lossy().to_string())
    }

    /// 读取结构化备份
    pub fn load_backup(&self, backup_path: &str) -> Result<MachineIdBackupFile, AppError> {
        let path = PathBuf::from(backup_path);
        if !path.exists() {
            return Err(AppError::BackupNotFound(backup_path.to_string()));
        }
        let content = std::fs::read_to_string(path)?;
        let backup = serde_json::from_str::<MachineIdBackupFile>(&content)?;
        Ok(backup)
    }

    /// 查找所有备份文件
    pub fn find_backups(&self) -> Result<Vec<BackupInfo>, AppError> {
        let mut backups = Vec::new();

        if !self.backup_dir.exists() {
            return Ok(backups);
        }

        for entry in std::fs::read_dir(&self.backup_dir)? {
            let entry = entry?;
            let path = entry.path();
            let filename = entry.file_name().to_string_lossy().to_string();

            if path.extension().and_then(|e| e.to_str()) != Some("json") {
                continue;
            }

            if !filename.starts_with("machine_ids_") {
                continue;
            }

            let content = match std::fs::read_to_string(&path) {
                Ok(content) => content,
                Err(_) => continue,
            };

            let parsed = match serde_json::from_str::<MachineIdBackupFile>(&content) {
                Ok(parsed) if parsed.backup_type == "machine_ids" => parsed,
                _ => continue,
            };

            let metadata = entry.metadata()?;
            let modified_secs = metadata
                .modified()
                .ok()
                .and_then(|t| t.duration_since(std::time::UNIX_EPOCH).ok())
                .map(|d| d.as_secs())
                .unwrap_or_default();

            let date_formatted = chrono::DateTime::<chrono::Local>::from(
                std::time::UNIX_EPOCH + std::time::Duration::from_secs(modified_secs),
            )
            .format("%Y-%m-%d %H:%M:%S")
            .to_string();

            backups.push(BackupInfo {
                path: path.to_string_lossy().to_string(),
                filename,
                timestamp: parsed.created_at,
                size: metadata.len(),
                date_formatted,
            });
        }

        backups.sort_by(|a, b| b.date_formatted.cmp(&a.date_formatted));
        Ok(backups)
    }
}
