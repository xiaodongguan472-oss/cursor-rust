/// 用量统计服务
///
/// 负责管理用量数据缓存和事件数据缓存的读写。
/// API 请求部分仍由 lib.rs 中的命令直接处理（过渡期间）。
use crate::error::AppError;
use crate::infra::api::CursorApiClient;
use crate::infra::store::{UsageCache, EventsCache};
use crate::{log_info, log_error};

/// 用量统计服务
pub struct AnalyticsService {
    api: CursorApiClient,
    usage_cache: UsageCache,
    events_cache: EventsCache,
}

impl AnalyticsService {
    pub fn new(api: CursorApiClient, usage_cache: UsageCache, events_cache: EventsCache) -> Self {
        Self {
            api,
            usage_cache,
            events_cache,
        }
    }

    // === 用量缓存 ===

    /// 保存用量缓存
    pub fn save_usage_cache(&self, data: &str) -> Result<(), AppError> {
        self.usage_cache.save(data)
    }

    /// 加载用量缓存
    pub fn load_usage_cache(&self) -> Result<serde_json::Value, AppError> {
        self.usage_cache.load()
    }

    /// 清除用量缓存
    pub fn clear_usage_cache(&self) -> Result<(), AppError> {
        self.usage_cache.clear()
    }

    // === 事件缓存 ===

    /// 保存事件缓存
    pub fn save_events_cache(&self, data: &str) -> Result<(), AppError> {
        self.events_cache.save(data)
    }

    /// 加载事件缓存
    pub fn load_events_cache(&self) -> Result<serde_json::Value, AppError> {
        self.events_cache.load()
    }

    /// 清除事件缓存
    pub fn clear_events_cache(&self) -> Result<(), AppError> {
        self.events_cache.clear()
    }

    // === 引用 ===

    pub fn api(&self) -> &CursorApiClient {
        &self.api
    }

    pub fn usage_cache_ref(&self) -> &UsageCache {
        &self.usage_cache
    }

    pub fn events_cache_ref(&self) -> &EventsCache {
        &self.events_cache
    }
}
