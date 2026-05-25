/// Cursor IDE 交互 Facade
///
/// 所有需要与 Cursor 文件/进程交互的操作都通过此模块访问。
pub mod paths;
pub mod storage;
pub mod sqlite;
pub mod workbench;
pub mod process;

use crate::error::AppError;
use std::path::{Path, PathBuf};

/// 已解析的 Cursor 路径集合
///
/// 在 CursorBridge 构造时解析一次，所有模块共享此实例。
#[derive(Debug, Clone)]
pub struct ResolvedPaths {
    /// storage.json 文件路径
    pub storage_json: PathBuf,
    /// state.vscdb SQLite 数据库路径
    pub sqlite_db: PathBuf,
    /// workbench.desktop.main.js 路径
    pub workbench_js: Option<PathBuf>,
    /// main.js 路径
    pub main_js: Option<PathBuf>,
    /// Cursor 应用目录
    pub app_dir: Option<PathBuf>,
}

/// Cursor IDE 交互入口（Facade 模式）
///
/// 所有需要与 Cursor 文件/进程交互的操作都通过此结构体访问。
/// 路径在构造时解析一次，后续所有子模块复用同一份路径。
#[derive(Debug, Clone)]
pub struct CursorBridge {
    pub paths: ResolvedPaths,
}

impl CursorBridge {
    /// 使用自定义路径或自动检测构造
    pub fn new(custom_path: Option<&str>) -> Result<Self, AppError> {
        let paths = paths::resolve(custom_path)?;
        Ok(Self { paths })
    }

    /// 获取 storage.json 操作接口
    pub fn storage(&self) -> storage::StorageJson<'_> {
        storage::StorageJson::new(&self.paths.storage_json)
    }

    /// 获取 SQLite 操作接口
    pub fn sqlite(&self) -> sqlite::CursorSqlite<'_> {
        sqlite::CursorSqlite::new(&self.paths.sqlite_db)
    }

    /// 获取 workbench 补丁操作接口
    pub fn workbench(&self) -> workbench::WorkbenchPatcher<'_> {
        workbench::WorkbenchPatcher::new(&self.paths)
    }

    /// 获取进程管理接口
    pub fn process(&self) -> process::ProcessManager {
        process::ProcessManager::new()
    }

    /// 获取完整的 Machine IDs（综合 storage.json + state.vscdb + 系统注册表）
    ///
    /// serviceMachineId 优先从 state.vscdb 读取（权威来源），回退到 storage.json。
    /// machineGuid 和 sqmClientId 从系统注册表补充（Windows）。
    pub fn read_full_machine_ids(&self) -> Result<crate::domain::identity::MachineIds, AppError> {
        let mut ids = self.storage().read_machine_ids()?;

        if ids.service_machine_id.is_empty() {
            if let Ok(Some(db_value)) = self.sqlite().read_service_machine_id() {
                ids.service_machine_id = db_value;
            }
        }

        let (guid, sqm) = crate::infra::platform::read_registry_ids();
        if ids.machine_guid.is_none() { ids.machine_guid = guid; }
        if ids.sqm_client_id.is_none() { ids.sqm_client_id = sqm; }

        Ok(ids)
    }
}
