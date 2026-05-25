use anyhow::Result;
use chrono::Local;
use std::fs::{File, OpenOptions};
use std::io::{BufRead, BufReader, Write};
use std::path::PathBuf;
use std::sync::Mutex;

// 可配置的日志文件大小限制 (20MB)
const MAX_LOG_SIZE_MB: u64 = 20;
const MAX_LOG_SIZE_BYTES: u64 = MAX_LOG_SIZE_MB * 1024 * 1024;

// 日志文件名
const LOG_FILE_NAME: &str = "MyCursor.log";

// 全局日志器实例
static LOGGER: Mutex<Option<Logger>> = Mutex::new(None);

pub struct Logger {
    log_file_path: PathBuf,
}

impl Logger {
    /// 初始化日志器
    pub fn init() -> Result<()> {
        // 延迟初始化，只设置标记，实际初始化在第一次写日志时进行
        Ok(())
    }

    /// 延迟初始化日志器
    fn lazy_init() -> Result<()> {
        let log_file_path = Self::get_log_file_path()?;
        let logger = Logger { log_file_path };

        // 确保日志目录存在
        if let Some(parent) = logger.log_file_path.parent() {
            std::fs::create_dir_all(parent)?;
        }

        let mut global_logger = LOGGER.lock().unwrap();
        *global_logger = Some(logger);

        Ok(())
    }

    /// 获取日志文件路径
    fn get_log_file_path() -> Result<PathBuf> {
        // 使用跨平台的默认数据目录
        let default_data_dir = Self::get_default_data_dir();

        let data_dir = match crate::get_data_dir() {
            Ok(dir) => dir,
            Err(_) => {
                // 如果无法获取配置的数据目录，使用默认路径
                // 确保默认目录存在
                std::fs::create_dir_all(&default_data_dir).ok();
                default_data_dir
            }
        };

        let log_dir = data_dir.join("logs");
        // 确保日志目录存在
        std::fs::create_dir_all(&log_dir)?;

        Ok(log_dir.join(LOG_FILE_NAME))
    }

    /// 获取默认数据目录（仅在 get_data_dir 失败时作为 fallback）
    fn get_default_data_dir() -> PathBuf {
        if cfg!(target_os = "windows") {
            std::env::current_exe()
                .ok()
                .and_then(|p| p.parent().map(|p| p.join("cursor_data")))
                .unwrap_or_else(|| PathBuf::from("cursor_data"))
        } else {
            dirs::home_dir()
                .unwrap_or_else(|| PathBuf::from("/tmp"))
                .join(".cursor_data")
        }
    }

    /// 写入日志
    pub fn write_log(level: &str, message: &str) {
        // 尝试获取已初始化的logger
        if let Ok(logger_guard) = LOGGER.lock() {
            if let Some(logger) = logger_guard.as_ref() {
                if let Err(e) = logger.write_log_internal(level, message) {
                    eprintln!("Failed to write log: {}", e);
                }
                return;
            }
        }

        // 如果logger未初始化，尝试延迟初始化
        if let Err(_) = Self::lazy_init() {
            // 初始化失败，回退到控制台输出
            let timestamp = Local::now().format("%Y-%m-%d %H:%M:%S%.3f");
            println!("[{}] [{}] {}", timestamp, level, message);
            return;
        }

        // 初始化成功后再次尝试写入
        if let Ok(logger_guard) = LOGGER.lock() {
            if let Some(logger) = logger_guard.as_ref() {
                if let Err(e) = logger.write_log_internal(level, message) {
                    eprintln!("Failed to write log: {}", e);
                }
            }
        }
    }

    /// 内部写入日志方法
    fn write_log_internal(&self, level: &str, message: &str) -> Result<()> {
        // 检查文件大小并清理
        self.check_and_cleanup_log_file()?;

        // 格式化日志条目
        let timestamp = Local::now().format("%Y-%m-%d %H:%M:%S%.3f");
        let log_entry = format!("[{}] [{}] {}", timestamp, level, message);

        // 同时输出到控制台和文件
        println!("{}", log_entry);

        // 追加写入日志文件
        let mut file = OpenOptions::new()
            .create(true)
            .append(true)
            .open(&self.log_file_path)?;

        file.write_all(format!("{}\n", log_entry).as_bytes())?;
        file.flush()?;

        Ok(())
    }

    /// 检查并清理日志文件
    fn check_and_cleanup_log_file(&self) -> Result<()> {
        if !self.log_file_path.exists() {
            return Ok(());
        }

        let file_size = std::fs::metadata(&self.log_file_path)?.len();

        if file_size > MAX_LOG_SIZE_BYTES {
            self.trim_log_file()?;
        }

        Ok(())
    }

    /// 裁剪日志文件，保留后半部分
    /// ✅ 优化：使用两次遍历避免将所有行加载到内存
    fn trim_log_file(&self) -> Result<()> {
        let temp_path = self.log_file_path.with_extension("tmp");
        let backup_path = self.log_file_path.with_extension("old");

        // ✅ 先备份原文件，防止数据丢失
        if self.log_file_path.exists() {
            std::fs::copy(&self.log_file_path, &backup_path)?;
        }

        {
            let input_file = File::open(&self.log_file_path)?;
            let reader = BufReader::new(input_file);

            // ✅ 第一次遍历：只计数，不加载到内存
            let total_lines = reader.lines().count();

            // 计算要跳过的行数（保留后60%）
            let skip_lines = (total_lines as f64 * 0.4) as usize;

            // ✅ 第二次遍历：跳过前面的行，只写入需要保留的行
            let input_file = File::open(&self.log_file_path)?;
            let reader = BufReader::new(input_file);
            let mut temp_file = File::create(&temp_path)?;

            for (index, line) in reader.lines().enumerate() {
                if index >= skip_lines {
                    if let Ok(line_content) = line {
                        writeln!(temp_file, "{}", line_content)?;
                    }
                }
            }

            temp_file.flush()?;
        }

        // ✅ 原子性替换原文件
        std::fs::rename(&temp_path, &self.log_file_path)?;

        // ✅ 删除备份文件（如果成功）
        let _ = std::fs::remove_file(&backup_path);

        // 记录清理操作
        let cleanup_message = format!(
            "Log file trimmed, kept approximately {}% of original content",
            60
        );
        self.write_log_internal("INFO", &cleanup_message)?;

        Ok(())
    }

    /// 获取日志文件路径（用于外部访问）
    pub fn get_log_path() -> Option<PathBuf> {
        if let Ok(logger_guard) = LOGGER.lock() {
            if let Some(logger) = logger_guard.as_ref() {
                return Some(logger.log_file_path.clone());
            }
        }
        None
    }
}

// 便捷的日志宏
#[macro_export]
macro_rules! log_info {
    ($($arg:tt)*) => {
        crate::logger::Logger::write_log("INFO", &format!($($arg)*))
    };
}

#[macro_export]
macro_rules! log_debug {
    ($($arg:tt)*) => {
        crate::logger::Logger::write_log("DEBUG", &format!($($arg)*))
    };
}

#[macro_export]
macro_rules! log_warn {
    ($($arg:tt)*) => {
        crate::logger::Logger::write_log("WARN", &format!($($arg)*))
    };
}

#[macro_export]
macro_rules! log_error {
    ($($arg:tt)*) => {
        crate::logger::Logger::write_log("ERROR", &format!($($arg)*))
    };
}

// 获取日志配置
pub fn get_log_config() -> (u64, &'static str) {
    (MAX_LOG_SIZE_MB, LOG_FILE_NAME)
}

// 更新日志配置（如果需要动态修改）
#[allow(dead_code)]
pub fn update_log_config(max_size_mb: u64) -> Result<()> {
    // 这里可以实现动态更新配置的逻辑
    // 目前使用常量，如果需要可以改为配置文件或环境变量
    log_info!(
        "Log configuration update requested: max_size = {}MB",
        max_size_mb
    );
    Ok(())
}
