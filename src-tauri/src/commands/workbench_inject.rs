use std::fs;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Mutex;
use sha2::{Sha256, Sha512, Digest};
use uuid::Uuid;
use rand::Rng;
use super::utils;
#[allow(unused_imports)]
use super::cursor_paths;

// ========== 常量 ==========

const WB_PATCH_START: &str = "/* MC_WB_PATCH_START */";
const WB_PATCH_END: &str = "/* MC_WB_PATCH_END */";
const LOCAL_SERVER_PORT: u16 = 14521; // 本地HTTP服务端口

// ========== 全局状态 ==========

static SERVER_RUNNING: AtomicBool = AtomicBool::new(false);
/// 与参考实现的 seamless_state.json 对齐的统一状态
static SEAMLESS_STATE: Mutex<Option<SeamlessState>> = Mutex::new(None);
static INJECT_STATUS: Mutex<InjectStatus> = Mutex::new(InjectStatus {
    js_connected: false,
    store_captured: false,
    last_heartbeat: 0,
    last_reset_ack: 0,
    reset_count: 0,
});

#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct InjectStatus {
    pub js_connected: bool,
    pub store_captured: bool,
    pub last_heartbeat: u64,
    pub last_reset_ack: u64,
    pub reset_count: u32,
}

fn now_ts() -> u64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs()
}

#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct MachineIds {
    pub dev_device_id: String,
    pub mac_machine_id: String,
    pub machine_id: String,
    pub sqm_id: String,
    pub service_machine_id: String,
}

/// 统一状态结构（对应参考实现的 seamless_state.json）
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct SeamlessState {
    pub config: SeamlessConfig,
    pub access_token: String,
    pub refresh_token: String,
    pub email: String,
    pub is_new: bool,
    pub machine_ids: MachineIds,
}

#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct SeamlessConfig {
    pub enabled: bool,
}

// ========== 机器码生成（与AI助手文档一致的算法） ==========

/// 生成全套新机器码（5个随机字段）
/// - devDeviceId: UUID4
/// - macMachineId: SHA512(random 64 bytes) = 128 hex chars
/// - machineId: SHA256(random 32 bytes) = 64 hex chars
/// - sqmId: {UUID4-UPPERCASE}
/// - serviceMachineId: UUID4
pub fn generate_machine_ids() -> MachineIds {
    let dev_device_id = Uuid::new_v4().to_string();

    let mac_machine_id = {
        let mut rng = rand::thread_rng();
        let mut buf = [0u8; 64];
        rng.fill(&mut buf);
        let mut hasher = Sha512::new();
        hasher.update(&buf);
        hex::encode(hasher.finalize())
    };

    let machine_id = {
        let mut hasher = Sha256::new();
        hasher.update(rand::random::<[u8; 32]>());
        hex::encode(hasher.finalize())
    };

    let sqm_id = format!("{{{}}}", Uuid::new_v4().to_string().to_uppercase());

    let service_machine_id = Uuid::new_v4().to_string();

    MachineIds {
        dev_device_id,
        mac_machine_id,
        machine_id,
        sqm_id,
        service_machine_id,
    }
}

// ========== 磁盘文件更新 ==========

/// 更新磁盘上的机器码文件（machineId文件 + storage.json）
pub fn update_disk_files(ids: &MachineIds) -> Result<(), String> {
    let cursor_dir = utils::get_cursor_data_dir()
        .ok_or_else(|| "无法确定Cursor数据目录".to_string())?;

    if !cursor_dir.exists() {
        return Err(format!("Cursor数据目录不存在: {}", cursor_dir.display()));
    }

    // 1. 写入 machineId 文件
    let machine_id_file = cursor_dir.join("machineId");
    utils::clear_macos_immutable_flag(&machine_id_file);
    fs::write(&machine_id_file, &ids.machine_id)
        .map_err(|e| format!("写入machineId文件失败: {}", e))?;

    // 2. 更新 storage.json
    let storage_path = cursor_dir.join("User").join("globalStorage").join("storage.json");
    if storage_path.exists() {
        utils::clear_macos_immutable_flag(&storage_path);
        let content = fs::read_to_string(&storage_path)
            .map_err(|e| format!("读取storage.json失败: {}", e))?;
        let mut config: serde_json::Value = serde_json::from_str(&content)
            .map_err(|e| format!("解析storage.json失败: {}", e))?;

        if let Some(obj) = config.as_object_mut() {
            obj.insert(utils::keys::telem_machine(), serde_json::json!(ids.machine_id));
            obj.insert(utils::keys::telem_mac(), serde_json::json!(ids.mac_machine_id));
            obj.insert(utils::keys::telem_dev(), serde_json::json!(ids.dev_device_id));
            obj.insert(utils::keys::telem_sqm(), serde_json::json!(ids.sqm_id));
            // serviceMachineId
            let svc_key = obfstr::obfstr!("storage.serviceMachineId").to_string();
            obj.insert(svc_key, serde_json::json!(ids.service_machine_id));
        }

        let updated = serde_json::to_string_pretty(&config)
            .map_err(|e| format!("序列化storage.json失败: {}", e))?;
        fs::write(&storage_path, updated)
            .map_err(|e| format!("写入storage.json失败: {}", e))?;
    }

    Ok(())
}

// ========== 重置机器码核心函数 ==========

/// 执行完整的机器码重置（生成新ID + 写磁盘 + 更新状态供JS拉取）
pub fn perform_machine_reset() -> Result<MachineIds, String> {
    let ids = generate_machine_ids();

    // 写入磁盘文件
    update_disk_files(&ids)?;

    // 更新状态（供注入的JS轮询拉取）
    if let Ok(mut state) = SEAMLESS_STATE.lock() {
        if let Some(ref mut s) = *state {
            s.is_new = true;
            s.machine_ids = ids.clone();
        } else {
            *state = Some(SeamlessState {
                config: SeamlessConfig { enabled: true },
                access_token: String::new(),
                refresh_token: String::new(),
                email: String::new(),
                is_new: true,
                machine_ids: ids.clone(),
            });
        }
    }

    Ok(ids)
}

/// 更新无感换号状态（token + machineIds 一起推送给JS轮询拾取）
/// 与参考实现的 write_state(seamless_state.json) 对应
pub fn update_seamless_state(
    email: &str,
    access_token: &str,
    refresh_token: &str,
    ids: &MachineIds,
) {
    if let Ok(mut state) = SEAMLESS_STATE.lock() {
        *state = Some(SeamlessState {
            config: SeamlessConfig { enabled: true },
            access_token: access_token.to_string(),
            refresh_token: refresh_token.to_string(),
            email: email.to_string(),
            is_new: true,
            machine_ids: ids.clone(),
        });
    }
}

/// 仅将已有的机器码推送给JS（更新状态供轮询拉取，不重新生成也不写磁盘）
#[allow(dead_code)]
pub fn push_ids_to_js(ids: &MachineIds) {
    if let Ok(mut state) = SEAMLESS_STATE.lock() {
        if let Some(ref mut s) = *state {
            s.is_new = true;
            s.machine_ids = ids.clone();
        } else {
            *state = Some(SeamlessState {
                config: SeamlessConfig { enabled: true },
                access_token: String::new(),
                refresh_token: String::new(),
                email: String::new(),
                is_new: true,
                machine_ids: ids.clone(),
            });
        }
    }
}

// ========== 本地HTTP服务器（供注入JS轮询） ==========

/// 启动本地HTTP服务器（非阻塞，后台运行）
pub fn start_local_server() {
    if SERVER_RUNNING.load(Ordering::SeqCst) {
        return;
    }

    SERVER_RUNNING.store(true, Ordering::SeqCst);

    // 安全启动：检测 tokio runtime 是否可用
    // 如果在 tauri setup 之前调用（无 runtime），则自建线程+runtime
    let spawn_ok = tokio::runtime::Handle::try_current()
        .map(|handle| {
            handle.spawn(run_server());
            true
        })
        .unwrap_or(false);

    if !spawn_ok {
        std::thread::spawn(|| {
            let rt = tokio::runtime::Builder::new_current_thread()
                .enable_all()
                .build()
                .expect("failed to create tokio runtime for local server");
            rt.block_on(run_server());
        });
    }
}

async fn run_server() {
    use tokio::net::TcpListener;
    use tokio::io::{AsyncReadExt, AsyncWriteExt};

    let addr = format!("127.0.0.1:{}", LOCAL_SERVER_PORT);
    let listener = match TcpListener::bind(&addr).await {
        Ok(l) => l,
        Err(_) => {
            SERVER_RUNNING.store(false, Ordering::SeqCst);
            return;
        }
    };

    while SERVER_RUNNING.load(Ordering::SeqCst) {
        let accept_result = tokio::select! {
            result = listener.accept() => result,
            _ = tokio::time::sleep(std::time::Duration::from_secs(1)) => continue,
        };

        let (mut stream, _) = match accept_result {
            Ok(s) => s,
            Err(_) => continue,
        };

        tokio::spawn(async move {
            let mut buf = vec![0u8; 4096];
            let n = match stream.read(&mut buf).await {
                Ok(n) if n > 0 => n,
                _ => return,
            };

            let request = String::from_utf8_lossy(&buf[..n]).to_string();
            let response = handle_request(&request);

            let http_response = format!(
                "HTTP/1.1 200 OK\r\n\
                 Content-Type: application/json\r\n\
                 Access-Control-Allow-Origin: *\r\n\
                 Access-Control-Allow-Methods: GET, POST, OPTIONS\r\n\
                 Access-Control-Allow-Headers: Content-Type\r\n\
                 Content-Length: {}\r\n\
                 Connection: close\r\n\
                 \r\n\
                 {}",
                response.len(),
                response
            );

            let _ = stream.write_all(http_response.as_bytes()).await;
        });
    }
}

/// 停止本地HTTP服务器
pub fn stop_local_server() {
    SERVER_RUNNING.store(false, Ordering::SeqCst);
}

fn handle_request(request: &str) -> String {
    let first_line = request.lines().next().unwrap_or("");

    if first_line.contains("OPTIONS") {
        return "{}".to_string();
    }

    // 与参考实现一致的 /api/get-token（JS 每秒轮询）
    if first_line.contains("GET /api/get-token") {
        return handle_get_token();
    }

    // 兼容旧版 /api/machine-state
    if first_line.contains("GET /api/machine-state") {
        return handle_get_token();
    }

    // JS 确认已消费新机器码
    if first_line.contains("POST /api/ack-new") {
        return handle_ack_new();
    }

    // 兼容旧版 /api/ack-reset
    if first_line.contains("POST /api/ack-reset") {
        return handle_ack_new();
    }

    // JS心跳 + 状态上报
    if first_line.contains("POST /api/heartbeat") {
        return handle_heartbeat(request);
    }

    // 自动换号请求（JS fetch拦截401/403/429时触发）
    if first_line.contains("POST /api/auto-switch") {
        return handle_auto_switch();
    }

    serde_json::json!({"error": "not found"}).to_string()
}

/// 处理 /api/get-token — 与参考实现的 seamless_state.json 格式一致
fn handle_get_token() -> String {
    let state = SEAMLESS_STATE.lock().ok().and_then(|g| g.clone());

    match state {
        Some(s) => serde_json::json!({
            "config": {"enabled": s.config.enabled},
            "accessToken": s.access_token,
            "refreshToken": s.refresh_token,
            "email": s.email,
            "is_new": s.is_new,
            "machineIds": {
                "devDeviceId": s.machine_ids.dev_device_id,
                "macMachineId": s.machine_ids.mac_machine_id,
                "machineId": s.machine_ids.machine_id,
                "sqmId": s.machine_ids.sqm_id,
            },
        }).to_string(),
        None => serde_json::json!({
            "config": {"enabled": false},
            "is_new": false,
        }).to_string(),
    }
}

/// 处理 /api/ack-new — JS 确认已消费新机器码/token
fn handle_ack_new() -> String {
    if let Ok(mut state) = SEAMLESS_STATE.lock() {
        if let Some(ref mut s) = *state {
            s.is_new = false;
        }
    }
    if let Ok(mut status) = INJECT_STATUS.lock() {
        status.last_reset_ack = now_ts();
        status.reset_count += 1;
    }
    serde_json::json!({"ok": true}).to_string()
}

/// 处理 /api/auto-switch — JS 检测到 401/403/429 时触发
fn handle_auto_switch() -> String {
    // 此处仅返回成功，实际换号逻辑由 seamless_switch 模块的轮询处理
    serde_json::json!({"success": false, "message": "auto-switch via polling"}).to_string()
}

fn handle_heartbeat(request: &str) -> String {
    // 解析 body 中的 store_captured 字段
    let store_captured = request.contains("\"store_captured\":true")
        || request.contains("\"store_captured\": true");

    if let Ok(mut status) = INJECT_STATUS.lock() {
        status.js_connected = true;
        status.last_heartbeat = now_ts();
        if store_captured {
            status.store_captured = true;
        }
    }
    serde_json::json!({"success": true}).to_string()
}

/// 获取注入状态（供前端查询）
pub fn get_inject_status() -> InjectStatus {
    let mut status = INJECT_STATUS.lock()
        .map(|s| s.clone())
        .unwrap_or(InjectStatus {
            js_connected: false,
            store_captured: false,
            last_heartbeat: 0,
            last_reset_ack: 0,
            reset_count: 0,
        });
    // 如果超过 10 秒没有心跳，认为 JS 已断开
    if status.last_heartbeat > 0 && now_ts() - status.last_heartbeat > 10 {
        status.js_connected = false;
    }
    status
}

// ========== Workbench JS 注入 ==========

/// 获取 workbench.desktop.main.js 路径
fn get_workbench_js_path(base_path: &str) -> PathBuf {
    Path::new(base_path)
        .join("out")
        .join("vs")
        .join("workbench")
        .join("workbench.desktop.main.js")
}

/// 构建注入到 workbench.desktop.main.js 的 JS 代码
/// 与参考实现完全对齐：
/// - 注入点1（i1）：在 getItems() 处捕获 StorageService → window.store
/// - 注入点2（i2）：轮询 /api/get-token 拉取 token + machineIds，用 .set() 写入内存
fn build_workbench_inject_code() -> String {
    let port = LOCAL_SERVER_PORT;

    format!(
        r#"{start}
;(function(){{
var _mcBase='http://127.0.0.1:{port}';
var _origFetch=window.fetch;

/* === 注入点2: Token 轮询 + 机器码重置 + fetch 拦截 === */
try{{
var _lastAppliedToken='';
var _lastNotifiedEmail='';
var _gSwitching=false,_gLastSuccess=0;

function _doSwitch(reason){{
if(_gSwitching)return;
var now=Date.now();
if(now-_gLastSuccess<30000)return;
_gSwitching=true;
_origFetch(_mcBase+'/api/auto-switch',{{method:'POST',headers:{{'Content-Type':'application/json'}},signal:AbortSignal.timeout(15000)}}).then(function(r){{return r.json()}}).then(function(d){{
if(d.success){{_gLastSuccess=Date.now();}}else{{_gLastSuccess=Date.now();}}
_gSwitching=false;
}}).catch(function(e){{_gLastSuccess=Date.now();_gSwitching=false;}});
}}

setInterval(async()=>{{
try{{
if(!window.store)return;
var resp=await _origFetch(_mcBase+'/api/get-token',{{signal:AbortSignal.timeout(3000)}});
if(resp.ok){{
var data=await resp.json();
if(!data.config||!data.config.enabled)return;
if(data.accessToken&&data.accessToken!==_lastAppliedToken){{
_lastAppliedToken=data.accessToken;
window.store.set('cursorAuth/accessToken',data.accessToken,-1);
if(data.refreshToken)window.store.set('cursorAuth/refreshToken',data.refreshToken,-1);
if(data.email)window.store.set('cursorAuth/cachedEmail',data.email,-1);
window.store.set('cursorAuth/stripeMembershipType','pro',-1);
window.store.set('cursorAuth/stripeSubscriptionStatus','active',-1);
}}
if(data.is_new&&data.machineIds){{
window.store.set('telemetry.devDeviceId',data.machineIds.devDeviceId,-1);
window.store.set('telemetry.machineId',data.machineIds.machineId,-1);
window.store.set('telemetry.macMachineId',data.machineIds.macMachineId,-1);
window.store.set('telemetry.sqmId',data.machineIds.sqmId,-1);
_origFetch(_mcBase+'/api/ack-new',{{method:'POST'}}).catch(function(){{}});
}}
if(data.email&&data.email!==_lastNotifiedEmail){{
_lastNotifiedEmail=data.email;
}}
}}
}}catch(e){{}}
}},1000);

/* fetch 拦截: HTTP 401/403/429 自动换号 */
window.fetch=async function(){{
var resp=await _origFetch.apply(this,arguments);
try{{
var a0=arguments[0];
var url=typeof a0==='string'?a0:(a0&&typeof a0.url==='string'?a0.url:'');
if(url.includes('cursor.sh')||url.includes('cursor.com')){{
if(resp.status===401||resp.status===403||resp.status===429){{
_doSwitch('HTTP '+resp.status);
}}
}}
}}catch(e){{}}
return resp;
}};

/* 心跳 */
setInterval(function(){{try{{_origFetch(_mcBase+'/api/heartbeat',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{store_captured:!!window.store}})}}).catch(function(){{}});}}catch(e){{}}}},5000);
setTimeout(function(){{try{{_origFetch(_mcBase+'/api/heartbeat',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{store_captured:!!window.store}})}}).catch(function(){{}});}}catch(e){{}}}},2000);

}}catch(e){{}}
}})();
{end}
"#,
        start = WB_PATCH_START,
        end = WB_PATCH_END,
        port = port,
    )
}

/// 注入点1的搜索字符串（与参考实现一致，在 StorageService 初始化处插入）
const INJECT1_SEARCH: &str = "this.database.getItems()))";

/// 构建注入点1的代码：捕获 StorageService → window.store
fn build_inject1_code() -> String {
    format!(
        r#"/*i1s*/;(function(e){{try{{if(!window.store&&e&&typeof e.get==='function'&&typeof e.set==='function'){{window.store=e;console.log('[MC] store bound');}}}}catch(_e){{}}}})(this);/*i1e*/"#
    )
}

/// 注入 workbench.desktop.main.js
pub fn patch_workbench(base_path: &str) -> serde_json::Value {
    let wb_path = get_workbench_js_path(base_path);

    if !wb_path.exists() {
        return serde_json::json!({
            "success": false,
            "error": format!("workbench.desktop.main.js不存在: {}", wb_path.display())
        });
    }

    let content = match fs::read_to_string(&wb_path) {
        Ok(c) => c,
        Err(e) => {
            return serde_json::json!({
                "success": false,
                "error": format!("读取文件失败: {}", e)
            });
        }
    };

    // 已注入过？先移除旧的（末尾注入块 + 内联注入点1）
    let mut content = if content.contains(WB_PATCH_START) {
        remove_patch_from_content(&content)
    } else {
        content
    };
    // 移除旧版注入点1标记
    content = remove_between(&content, "/*i1s*/", "/*i1e*/");

    // 创建备份
    let backup = format!("{}.mc_bak", wb_path.to_string_lossy());
    if !Path::new(&backup).exists() {
        let _ = fs::copy(&wb_path, &backup);
    }

    // 注入点1（关键）：在 getItems() 处插入代码捕获 StorageService → window.store
    // 与参考实现完全一致的注入位置
    if !content.contains(INJECT1_SEARCH) {
        return serde_json::json!({
            "success": false,
            "error": format!("未找到注入点1的匹配代码 ({}), Cursor 版本可能不兼容", INJECT1_SEARCH)
        });
    }
    let inject1 = build_inject1_code();
    content = content.replacen(
        INJECT1_SEARCH,
        &format!("{}{}", INJECT1_SEARCH, inject1),
        1,
    );

    // 注入点2：轮询 + fetch 拦截（追加到文件末尾）
    let inject_code = build_workbench_inject_code();
    let new_content = format!("{}\n{}", content, inject_code);

    let write_result = utils::safe_modify_file(&wb_path, || {
        fs::write(&wb_path, &new_content).map_err(|e| format!("写入文件失败: {}", e))
    });

    match write_result {
        Ok(()) => {
            // 清除 V8 字节码缓存
            clear_v8_cache();

            // macOS: 重签名
            #[cfg(target_os = "macos")]
            {
                let install_path = cursor_paths::get_cursor_install_from_base_path(base_path);
                let app_path = install_path.to_string_lossy();
                let _ = std::process::Command::new("xattr")
                    .args(["-cr", &*app_path])
                    .output();
                let _ = std::process::Command::new("codesign")
                    .args(["--force", "--deep", "--sign", "-", &*app_path])
                    .output();
            }

            serde_json::json!({"success": true, "message": "机器码注入成功"})
        }
        Err(e) => serde_json::json!({"success": false, "error": e}),
    }
}

/// 移除 workbench.desktop.main.js 中的注入
pub fn unpatch_workbench(base_path: &str) -> serde_json::Value {
    let wb_path = get_workbench_js_path(base_path);

    if !wb_path.exists() {
        return serde_json::json!({"success": true, "message": "文件不存在，无需移除"});
    }

    let content = match fs::read_to_string(&wb_path) {
        Ok(c) => c,
        Err(e) => {
            return serde_json::json!({"success": false, "error": e.to_string()});
        }
    };

    if !content.contains(WB_PATCH_START) {
        return serde_json::json!({"success": true, "message": "未检测到注入"});
    }

    let new_content = remove_patch_from_content(&content);

    let write_result = utils::safe_modify_file(&wb_path, || {
        fs::write(&wb_path, &new_content).map_err(|e| format!("写入失败: {}", e))
    });

    match write_result {
        Ok(()) => {
            #[cfg(target_os = "macos")]
            {
                let install_path = cursor_paths::get_cursor_install_from_base_path(base_path);
                let app_path = install_path.to_string_lossy();
                let _ = std::process::Command::new("xattr")
                    .args(["-cr", &*app_path])
                    .output();
                let _ = std::process::Command::new("codesign")
                    .args(["--force", "--deep", "--sign", "-", &*app_path])
                    .output();
            }
            serde_json::json!({"success": true, "message": "注入已移除"})
        }
        Err(e) => serde_json::json!({"success": false, "error": e}),
    }
}

/// 检查 workbench 是否已注入
#[allow(dead_code)]
pub fn check_workbench_patched(base_path: &str) -> bool {
    let wb_path = get_workbench_js_path(base_path);
    if let Ok(content) = fs::read_to_string(&wb_path) {
        content.contains(WB_PATCH_START)
    } else {
        false
    }
}

/// 移除两个标记之间的内容（含标记本身）
fn remove_between(content: &str, start_marker: &str, end_marker: &str) -> String {
    if let Some(s) = content.find(start_marker) {
        if let Some(e) = content.find(end_marker) {
            let end_pos = e + end_marker.len();
            let mut result = String::new();
            result.push_str(&content[..s]);
            result.push_str(&content[end_pos..]);
            return result;
        }
    }
    content.to_string()
}

fn remove_patch_from_content(content: &str) -> String {
    if let (Some(start_idx), Some(end_idx)) = (
        content.find(WB_PATCH_START),
        content.find(WB_PATCH_END),
    ) {
        let end_with_marker = end_idx + WB_PATCH_END.len();
        let mut result = String::new();
        result.push_str(&content[..start_idx]);
        if end_with_marker < content.len() {
            // 跳过紧跟的换行符
            let remaining = &content[end_with_marker..];
            let trimmed = remaining.strip_prefix('\n').unwrap_or(remaining);
            result.push_str(trimmed);
        }
        result
    } else {
        content.to_string()
    }
}

/// 程序启动时自动检测：如果 workbench 已注入，则自动启动 HTTP 服务
pub fn auto_start_if_patched() {
    let paths = super::cursor_paths::get_cursor_paths();
    if let Some(ref bp) = paths.base_path {
        if paths.error.is_none() && check_workbench_patched(bp) {
            start_local_server();
        }
    }
}

/// 清除 V8 字节码缓存（Electron 加载旧缓存会导致注入失效）
fn clear_v8_cache() {
    let cursor_dir = match utils::get_cursor_data_dir() {
        Some(d) => d,
        None => return,
    };

    // GPUCache 和 Code Cache 目录
    let cache_dirs = [
        cursor_dir.join("GPUCache"),
        cursor_dir.join("Code Cache"),
        cursor_dir.join("CachedData"),
    ];

    for dir in &cache_dirs {
        if dir.exists() {
            let _ = fs::remove_dir_all(dir);
        }
    }
}
