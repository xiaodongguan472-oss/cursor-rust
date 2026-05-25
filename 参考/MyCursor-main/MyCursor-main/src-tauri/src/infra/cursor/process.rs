/// Cursor 进程检测与管理
use crate::error::AppError;
use crate::{log_info, log_error};

/// 进程管理器
pub struct ProcessManager;

impl ProcessManager {
    pub fn new() -> Self {
        Self
    }

    /// 确保 Cursor 未在运行（写入操作前调用）
    pub fn ensure_not_running(&self) -> Result<(), AppError> {
        if self.is_running() {
            return Err(AppError::CursorRunning);
        }
        Ok(())
    }

    /// 检查 Cursor 是否正在运行
    pub fn is_running(&self) -> bool {
        #[cfg(target_os = "windows")]
        {
            Self::check_process_windows("Cursor.exe")
        }

        #[cfg(target_os = "macos")]
        {
            Self::check_process_unix("Cursor")
        }

        #[cfg(target_os = "linux")]
        {
            Self::check_process_unix("cursor")
        }
    }

    /// 强制关闭 Cursor 进程，返回是否成功执行
    pub fn force_close(&self) -> bool {
        if !self.is_running() {
            return true;
        }

        #[cfg(target_os = "windows")]
        {
            use std::os::windows::process::CommandExt;
            const CREATE_NO_WINDOW: u32 = 0x08000000;

            match std::process::Command::new("taskkill")
                .args(&["/F", "/IM", "Cursor.exe"])
                .creation_flags(CREATE_NO_WINDOW)
                .output()
            {
                Ok(_) => {
                    log_info!("已终止 Cursor 进程");
                    std::thread::sleep(std::time::Duration::from_millis(500));
                    true
                }
                Err(e) => {
                    log_error!("终止 Cursor 失败: {}", e);
                    false
                }
            }
        }

        #[cfg(target_os = "macos")]
        {
            match std::process::Command::new("pkill").args(&["-f", "Cursor"]).output() {
                Ok(_) => {
                    log_info!("已终止 Cursor 进程");
                    std::thread::sleep(std::time::Duration::from_millis(500));
                    true
                }
                Err(e) => {
                    log_error!("终止 Cursor 失败: {}", e);
                    false
                }
            }
        }

        #[cfg(target_os = "linux")]
        {
            let _ = std::process::Command::new("pkill").args(&["-f", "cursor.*--"]).output();
            let _ = std::process::Command::new("pkill").args(&["-f", "cursor.*AppImage"]).output();
            log_info!("已尝试终止 Cursor 进程");
            std::thread::sleep(std::time::Duration::from_millis(500));
            true
        }
    }

    #[cfg(target_os = "windows")]
    fn check_process_windows(name: &str) -> bool {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x08000000;

        std::process::Command::new("tasklist")
            .args(&["/FI", &format!("IMAGENAME eq {}", name)])
            .creation_flags(CREATE_NO_WINDOW)
            .output()
            .map(|o| String::from_utf8_lossy(&o.stdout).contains(name))
            .unwrap_or(false)
    }

    #[cfg(any(target_os = "macos", target_os = "linux"))]
    fn check_process_unix(name: &str) -> bool {
        std::process::Command::new("pgrep")
            .args(&["-x", name])
            .output()
            .map(|o| o.status.success())
            .unwrap_or(false)
    }
}
