/// 平台特定操作
///
/// 通过条件编译分发到各平台实现。

#[cfg(target_os = "windows")]
pub mod windows;

#[cfg(target_os = "macos")]
pub mod macos;

#[cfg(target_os = "linux")]
pub mod linux;

use crate::domain::identity::MachineIds;
use crate::error::AppError;

/// 平台特定操作 trait
pub trait PlatformOps: Send + Sync {
    /// 更新系统级 ID（如注册表）
    fn update_system_ids(&self, ids: &MachineIds) -> Result<(), AppError>;
    /// 检测当前是否有管理员权限
    fn is_admin(&self) -> bool;
}

/// 创建当前平台的操作实例
pub fn create() -> Box<dyn PlatformOps> {
    #[cfg(target_os = "windows")]
    { Box::new(windows::WindowsOps) }

    #[cfg(target_os = "macos")]
    { Box::new(macos::MacOps) }

    #[cfg(target_os = "linux")]
    { Box::new(linux::LinuxOps) }
}

/// 读取系统级机器标识（Windows 注册表中的 MachineGuid 和 SQMClient MachineId）
#[cfg(target_os = "windows")]
pub fn read_registry_ids() -> (Option<String>, Option<String>) {
    use winreg::enums::*;
    use winreg::RegKey;

    let machine_guid = RegKey::predef(HKEY_LOCAL_MACHINE)
        .open_subkey_with_flags("SOFTWARE\\Microsoft\\Cryptography", KEY_READ | KEY_WOW64_64KEY)
        .ok()
        .and_then(|key| key.get_value::<String, _>("MachineGuid").ok())
        .filter(|v| !v.is_empty());

    let sqm_client_id = RegKey::predef(HKEY_LOCAL_MACHINE)
        .open_subkey_with_flags("SOFTWARE\\Microsoft\\SQMClient", KEY_READ | KEY_WOW64_64KEY)
        .ok()
        .and_then(|key| key.get_value::<String, _>("MachineId").ok())
        .filter(|v| !v.is_empty());

    (machine_guid, sqm_client_id)
}

#[cfg(not(target_os = "windows"))]
pub fn read_registry_ids() -> (Option<String>, Option<String>) {
    (None, None)
}
