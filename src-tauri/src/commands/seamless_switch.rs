use std::collections::HashMap;
use std::fs;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Mutex;
use std::sync::OnceLock;
use sha2::{Sha256, Digest};
use rusqlite::Connection;
use tauri::{AppHandle, Manager};
use super::utils;
use super::cursor_paths;
use super::machine_id;
use super::unlock_mitm;

static AUTO_SWITCH_ENABLED: AtomicBool = AtomicBool::new(false);
static AUTO_SWITCH_BUSY: AtomicBool = AtomicBool::new(false);
static AUTO_SWITCH_CARD_CODE: Mutex<Option<String>> = Mutex::new(None);

// 持久化 HTTP 客户端（连接复用 + keep-alive）
static HTTP_CLIENT: OnceLock<reqwest::Client> = OnceLock::new();
// Cloudflare cookie 持久化存储（domain → cookie string）
static CF_COOKIES: Mutex<Option<HashMap<String, String>>> = Mutex::new(None);

// 自动重补丁监控 —— 检测 Cursor 自更新覆盖 extensionHostProcess.js 后自动重新注入
static AUTO_REPATCH_ENABLED: AtomicBool = AtomicBool::new(false);
const AUTO_REPATCH_INTERVAL_SECS: u64 = 67;

const EH_PATCH_START: &str = "/* MOCURSO_EH_PATCH_START */";
const EH_PATCH_END: &str = "/* MOCURSO_EH_PATCH_END */";
/// 补丁版本号 —— 每次改 build_eh_inject_code 都要 +1。
/// do_patch_ext_host 检测到旧版本会自动卸载重装。
/// v2：加 machine ID 覆盖映射（仅 JSON body）
/// v3：扩展到 Buffer 字节级查找替换，覆盖 protobuf / gRPC 二进制 body
/// v4：诊断模式 —— dump 未匹配的候选 ID
/// v5：累积式 mapping（机器人启动时缓存的 ID 永远能被替换）+ header 替换 log
///     —— 关键修复：x-cursor-checksum = `00000000${machineId}/${macMachineId}`
///     从 Cursor 启动时的内存值拼接；我们重置 storage.json 不影响内存里的"原始旧 ID"。
///     mapping 改为累积式后，无论 Cursor 内存里是 1 代/2 代/N 代前的旧 ID，都能映射到当前新值。
/// v6：日志总开关 —— 默认关掉 JS 端 _mcLG()，不再创建 ~/.cursor-renewal/exthost.log
const EH_PATCH_VERSION: u32 = 6;
const EH_PATCH_VERSION_MARKER: &str = "MOCURSO_EH_PATCH_V";

/// JS 端 ExtHost 补丁里 _mcLG() 日志总开关。
/// release 默认 false（不创建 exthost.log 文件、零 fs.appendFileSync 调用）。
/// 开发调试时改成 true 重新激活无感换号 → 旧补丁被剥掉 → 新补丁带回完整日志。
const EXTHOST_LOG_ENABLED: bool = false;
const CURSOR_API: &str = "https://api2.cursor.sh";
const CURSOR_WEB: &str = "https://cursor.com";
const CURSOR_USER_AGENT: &str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Cursor/0.50.5 Chrome/128.0.6613.186 Electron/32.2.7 Safari/537.36";

fn get_data_dir() -> PathBuf {
    let home = dirs::home_dir().unwrap_or_default();
    home.join(".cursor-renewal")
}

fn get_active_token_file() -> PathBuf {
    get_data_dir().join("active_token")
}

fn get_ext_host_js_path(cursor_install_path: &Path) -> PathBuf {
    #[cfg(target_os = "macos")]
    {
        cursor_install_path
            .join("Contents")
            .join("Resources")
            .join("app")
            .join("out")
            .join("vs")
            .join("workbench")
            .join("api")
            .join("node")
            .join("extensionHostProcess.js")
    }
    #[cfg(not(target_os = "macos"))]
    {
        cursor_install_path
            .join("resources")
            .join("app")
            .join("out")
            .join("vs")
            .join("workbench")
            .join("api")
            .join("node")
            .join("extensionHostProcess.js")
    }
}

fn build_eh_inject_code() -> String {
    // 与 Electron 原版保持一致：路径中的反斜杠统一为正斜杠
    let token_file = get_active_token_file();
    let token_path = token_file.to_string_lossy().replace('\\', "/");

    // 同目录下的 machine_id_override 文件 —— 由 machine_id::perform_full_machine_id_reset 写入
    // 内容：{"mappings": [{"old": "...", "new": "..."}, ...]}
    let override_file = get_data_dir().join("machine_id_override");
    let override_path = override_file.to_string_lossy().replace('\\', "/");

    // ExtHost 自检日志 —— 补丁里每次成功替换会 append 一行到这里，
    // 用户在 UI 的「查看日志」里能看到。证明补丁活着 + 映射在生效。
    let exthost_log_file = get_data_dir().join("exthost.log");
    let exthost_log_path = exthost_log_file.to_string_lossy().replace('\\', "/");

    let version_marker = format!("/* {}{} */", EH_PATCH_VERSION_MARKER, EH_PATCH_VERSION);

    // _mcLG 函数体：日志开关关闭时是空函数（零开销），开启时写文件
    let mclg_body = if EXTHOST_LOG_ENABLED {
        "try{_mcF.appendFileSync(_mcLF,'['+new Date().toISOString()+'] '+msg+'\\n');}catch(e){}"
    } else {
        "" // no-op：不创建 exthost.log 文件，所有 _mcLG() 调用直接 return undefined
    };

    format!(
        "{start}\n\
{vmark}\n\
const _mcM=await import('node:module');\n\
const _mcR=_mcM.createRequire(import.meta.url);\n\
const _mcF=_mcR('fs');\n\
const _mcTF='{token}';\n\
const _mcOF='{override}';\n\
const _mcLF='{exthost_log}';\n\
let _mcTk=null,_mcLt=0;\n\
let _mcMap=null,_mcMlt=0;\n\
function _mcLG(msg){{{mclg_body}}}\n\
try{{_mcLG('exthost patch v{ver} loaded; override file = '+_mcOF);}}catch(e){{}}\n\
function _mcGT(){{const n=Date.now();if(n-_mcLt>500){{_mcLt=n;try{{_mcTk=_mcF.readFileSync(_mcTF,'utf8').trim()||null;}}catch(e){{_mcTk=null;}}}}return _mcTk;}}\n\
function _mcGM(){{const n=Date.now();if(n-_mcMlt>500){{_mcMlt=n;try{{const r=JSON.parse(_mcF.readFileSync(_mcOF,'utf8'));_mcMap=Array.isArray(r&&r.mappings)?r.mappings.filter(m=>m&&typeof m.old==='string'&&typeof m.new==='string'&&m.old.length>=8):[];}}catch(e){{_mcMap=[];}}}}return _mcMap||[];}}\n\
function _mcSR(s){{if(typeof s!=='string')return s;const map=_mcGM();if(!map.length)return s;let out=s,hit=0;for(const m of map){{if(out.indexOf(m.old)!==-1){{out=out.split(m.old).join(m.new);hit++;}}}}return out;}}\n\
function _mcPH(h){{if(!h||typeof h!=='object')return;try{{let replaced=0,checksumBefore=null,checksumAfter=null;for(const k of Object.keys(h)){{const v=h[k];if(typeof v==='string'){{const nv=_mcSR(v);if(nv!==v){{h[k]=nv;replaced++;if(k.toLowerCase()==='x-cursor-checksum'){{checksumBefore=v.length;checksumAfter=nv.length;}}}}}}else if(Array.isArray(v)){{const nva=v.map(x=>typeof x==='string'?_mcSR(x):x);if(JSON.stringify(nva)!==JSON.stringify(v)){{h[k]=nva;replaced++;}}}}}}if(replaced>0){{try{{_mcLG('header REPLACED '+replaced+' value(s)'+(checksumBefore?' [x-cursor-checksum updated, len '+checksumBefore+'->'+checksumAfter+']':''));}}catch(e){{}}}}}}catch(e){{}}}}\n\
function _mcBR(buf){{const map=_mcGM();if(!buf||buf.length<8)return buf;let out=buf,replacedTotal=0;if(map.length){{for(const m of map){{if(m.old.length!==m.new.length)continue;const oldB=Buffer.from(m.old,'utf8');const newB=Buffer.from(m.new,'utf8');if(oldB.length!==newB.length)continue;let idx=0,localCount=0,working=null;while(true){{const found=out.indexOf(oldB,idx);if(found===-1)break;if(working===null)working=Buffer.from(out);newB.copy(working,found);idx=found+oldB.length;localCount++;}}if(localCount>0){{out=working;replacedTotal+=localCount;}}}}}}if(replacedTotal>0){{try{{_mcLG('replaced '+replacedTotal+' id occurrence(s) in buffer size='+buf.length);}}catch(e){{}}}}else if(buf.length>=16&&buf.length<8192){{try{{const ascii=buf.toString('latin1');const uuidR=/[0-9a-fA-F]{{8}}-[0-9a-fA-F]{{4}}-[0-9a-fA-F]{{4}}-[0-9a-fA-F]{{4}}-[0-9a-fA-F]{{12}}/g;const shaR=/[0-9a-fA-F]{{64}}|[0-9a-fA-F]{{128}}/g;const cands=new Set();let mm;while((mm=uuidR.exec(ascii))!==null){{cands.add(mm[0]);if(cands.size>=10)break;}}while((mm=shaR.exec(ascii))!==null){{cands.add(mm[0]);if(cands.size>=10)break;}}if(cands.size>0){{const list=[...cands].slice(0,8).join('|');_mcLG('DIAG: buffer size='+buf.length+' has '+cands.size+' candidate id(s) NOT in mapping: '+list);}}}}catch(e){{}}}}return out;}}\n\
function _mcPB(b){{if(b==null)return b;try{{if(typeof b==='string'){{const t=b.trim();if(t.startsWith('{{')||t.startsWith('[')){{try{{const o=JSON.parse(b);return _mcSR(JSON.stringify(o));}}catch(e){{}}}}return _mcSR(b);}}if(Buffer.isBuffer(b)){{return _mcBR(b);}}if(b instanceof Uint8Array){{return _mcBR(Buffer.from(b.buffer,b.byteOffset,b.byteLength));}}if(b&&b.buffer instanceof ArrayBuffer&&typeof b.byteLength==='number'){{return _mcBR(Buffer.from(b.buffer,b.byteOffset||0,b.byteLength));}}}}catch(e){{}}return b;}}\n\
try{{const _h2=_mcR('http2');const _oC=_h2.connect;_h2.connect=function(a,...r){{const s=_oC.call(_h2,a,...r);if(typeof a==='string'&&(a.includes('cursor.sh')||a.includes('cursor.com'))){{try{{_mcLG('http2 connect to '+a);}}catch(e){{}}const _oR=s.request.bind(s);s.request=function(h,...ra){{const t=_mcGT();if(t&&h)h['authorization']='Bearer '+t;_mcPH(h);const _rs=_oR(h,...ra);try{{const _ow=_rs.write?_rs.write.bind(_rs):null;if(_ow){{_rs.write=function(c,...rr){{return _ow(_mcPB(c),...rr);}};}}const _oe=_rs.end?_rs.end.bind(_rs):null;if(_oe){{_rs.end=function(c,...rr){{if(c==null)return _oe(...rr);return _oe(_mcPB(c),...rr);}};}}}}catch(e){{}}return _rs;}};}}return s;}};}}catch(e){{}}\n\
try{{const _hs=_mcR('https');const _oR=_hs.request;_hs.request=function(o,...ra){{const ish=o&&typeof o==='object'&&o.hostname&&(o.hostname.includes('cursor.sh')||o.hostname.includes('cursor.com'));if(ish){{try{{_mcLG('https request to '+o.hostname+(o.path||''));}}catch(e){{}}const t=_mcGT();if(t&&o.headers)o.headers['authorization']='Bearer '+t;_mcPH(o&&o.headers);}}const _rq=_oR.call(_hs,o,...ra);if(ish){{try{{const _ow=_rq.write?_rq.write.bind(_rq):null;if(_ow){{_rq.write=function(c,...rr){{return _ow(_mcPB(c),...rr);}};}}const _oe=_rq.end?_rq.end.bind(_rq):null;if(_oe){{_rq.end=function(c,...rr){{if(c==null)return _oe(...rr);return _oe(_mcPB(c),...rr);}};}}}}catch(e){{}}}}return _rq;}};}}catch(e){{}}\n\
try{{if(typeof globalThis.fetch==='function'&&!globalThis._mcOF2){{globalThis._mcOF2=globalThis.fetch;globalThis.fetch=function(i,init){{const t=_mcGT();let u=typeof i==='string'?i:(i instanceof URL?i.href:i?.url||'');const ish=u&&(u.includes('cursor.sh')||u.includes('cursor.com'));if(ish){{try{{_mcLG('fetch to '+u);}}catch(e){{}}init=init||{{}};init.headers=init.headers||{{}};if(t){{if(typeof init.headers.set==='function')init.headers.set('authorization','Bearer '+t);else init.headers['authorization']='Bearer '+t;}}try{{if(init.headers&&typeof init.headers==='object'&&typeof init.headers.set!=='function'){{_mcPH(init.headers);}}else if(init.headers&&typeof init.headers.forEach==='function'){{const ks=[];init.headers.forEach((v,k)=>ks.push([k,v]));for(const [k,v] of ks){{if(typeof v==='string'){{const nv=_mcSR(v);if(nv!==v)init.headers.set(k,nv);}}}}}}if(init.body!=null){{init.body=_mcPB(init.body);}}}}catch(e){{}}}}return globalThis._mcOF2(i,init);}};}}}}catch(e){{}}\n\
{end}\n",
        start = EH_PATCH_START,
        end = EH_PATCH_END,
        vmark = version_marker,
        ver = EH_PATCH_VERSION,
        token = token_path,
        override = override_path,
        exthost_log = exthost_log_path,
        mclg_body = mclg_body,
    )
}

/// 把文件里 EH_PATCH_START..EH_PATCH_END 区间删掉（含两端标记），返回剩余内容。
/// 找不到标记就原样返回。用于补丁版本升级前先剥旧的。
fn strip_old_patch_block(content: &str) -> String {
    if let (Some(start_idx), Some(end_idx)) = (
        content.find(EH_PATCH_START),
        content.find(EH_PATCH_END),
    ) {
        let end_with_marker = end_idx + EH_PATCH_END.len();
        let mut out = String::with_capacity(content.len());
        out.push_str(&content[..start_idx]);
        if end_with_marker < content.len() {
            out.push_str(&content[end_with_marker..]);
        }
        out.trim_start().to_string()
    } else {
        content.to_string()
    }
}

fn do_patch_ext_host(cursor_install_path: &Path) -> serde_json::Value {
    let eh_path = get_ext_host_js_path(cursor_install_path);
    crate::ulog!("[ExtHost] patch start, target = {}", eh_path.display());

    if !eh_path.exists() {
        crate::ulog!("[ExtHost] ✗ file not found");
        return serde_json::json!({
            "success": false, "patched": false,
            "error": format!("extensionHostProcess.js not found: {}", eh_path.display())
        });
    }

    let content = match fs::read_to_string(&eh_path) {
        Ok(c) => c,
        Err(e) => {
            crate::ulog!("[ExtHost] ✗ read failed: {}", e);
            return serde_json::json!({
                "success": false, "patched": false,
                "error": format!("读取文件失败: {}", e)
            });
        }
    };

    // 已经打过补丁了 —— 检查版本号是不是最新的
    let current_version_marker = format!("{}{}", EH_PATCH_VERSION_MARKER, EH_PATCH_VERSION);
    if content.contains(EH_PATCH_START) {
        if content.contains(&current_version_marker) {
            crate::ulog!("[ExtHost] already patched at version {} (skip)", EH_PATCH_VERSION);
            return serde_json::json!({"success": true, "patched": true, "message": "已经注入过补丁"});
        }
        // 旧版本补丁 → 先剥掉，再下面正常路径重新注入新版本
        crate::ulog!("[ExtHost] old version detected, stripping...");
        let stripped = strip_old_patch_block(&content);
        let write_result = utils::safe_modify_file(&eh_path, || {
            fs::write(&eh_path, &stripped).map_err(|e| format!("剥旧补丁失败: {}", e))
        });
        if let Err(e) = write_result {
            crate::ulog!("[ExtHost] ✗ strip failed: {}", e);
            return serde_json::json!({"success": false, "patched": false, "error": e});
        }
        // 落到下面重新注入
    }

    // Create backup（旧补丁剥掉之后 content 已变，重新读一份）
    let backup = format!("{}.bak", eh_path.to_string_lossy());
    if !Path::new(&backup).exists() {
        let _ = fs::copy(&eh_path, &backup);
    }

    let current = match fs::read_to_string(&eh_path) {
        Ok(c) => c,
        Err(e) => {
            crate::ulog!("[ExtHost] ✗ re-read after strip failed: {}", e);
            return serde_json::json!({
                "success": false, "patched": false,
                "error": format!("剥旧补丁后再读失败: {}", e)
            });
        }
    };

    let inject_code = build_eh_inject_code();
    let new_content = format!("{}{}", inject_code, current);

    let write_result = utils::safe_modify_file(&eh_path, || {
        fs::write(&eh_path, &new_content).map_err(|e| format!("写入文件失败: {}", e))
    });

    match write_result {
        Ok(()) => {
            crate::ulog!("[ExtHost] ✓ injected v{}, size = {} bytes", EH_PATCH_VERSION, new_content.len());
            // macOS: 清除扩展属性（避免 Gatekeeper 拦截）+ ad-hoc 重签
            #[cfg(target_os = "macos")]
            {
                let app_path = cursor_install_path.to_string_lossy();
                // 1. 递归清除 quarantine、FinderInfo 等扩展属性
                let _ = std::process::Command::new("xattr")
                    .args(["-cr", &app_path])
                    .output();
                // 2. ad-hoc 重签
                let _ = std::process::Command::new("codesign")
                    .args(["--force", "--deep", "--sign", "-", &app_path])
                    .output();
            }

            serde_json::json!({"success": true, "patched": true, "message": "补丁注入成功"})
        }
        Err(e) => serde_json::json!({"success": false, "patched": false, "error": e}),
    }
}

fn do_unpatch_ext_host(cursor_install_path: &Path) -> serde_json::Value {
    let eh_path = get_ext_host_js_path(cursor_install_path);

    if !eh_path.exists() {
        return serde_json::json!({"success": false, "patched": false, "error": "文件不存在"});
    }

    let content = match fs::read_to_string(&eh_path) {
        Ok(c) => c,
        Err(e) => {
            return serde_json::json!({"success": false, "patched": false, "error": e.to_string()});
        }
    };

    if !content.contains(EH_PATCH_START) {
        return serde_json::json!({"success": true, "patched": false, "message": "未检测到补丁"});
    }

    // Remove patch
    let new_content = if let (Some(start_idx), Some(end_idx)) = (
        content.find(EH_PATCH_START),
        content.find(EH_PATCH_END),
    ) {
        let end_with_marker = end_idx + EH_PATCH_END.len();
        let mut result = String::new();
        result.push_str(&content[..start_idx]);
        if end_with_marker < content.len() {
            result.push_str(&content[end_with_marker..]);
        }
        result.trim_start().to_string()
    } else {
        content
    };

    let write_result = utils::safe_modify_file(&eh_path, || {
        fs::write(&eh_path, &new_content).map_err(|e| format!("写入失败: {}", e))
    });

    match write_result {
        Ok(()) => {
            #[cfg(target_os = "macos")]
            {
                let app_path = cursor_install_path.to_string_lossy();
                let _ = std::process::Command::new("xattr")
                    .args(["-cr", &app_path])
                    .output();
                let _ = std::process::Command::new("codesign")
                    .args(["--force", "--deep", "--sign", "-", &app_path])
                    .output();
            }
            serde_json::json!({"success": true, "patched": false, "message": "补丁已移除"})
        }
        Err(e) => serde_json::json!({"success": false, "patched": true, "error": e}),
    }
}

fn do_check_ext_host_patched(cursor_install_path: &Path) -> bool {
    let eh_path = get_ext_host_js_path(cursor_install_path);
    if let Ok(content) = fs::read_to_string(&eh_path) {
        content.contains(EH_PATCH_START)
    } else {
        false
    }
}

// ========== Token file operations ==========

fn do_write_active_token(token: &str) -> bool {
    let file = get_active_token_file();
    let _ = fs::create_dir_all(file.parent().unwrap());
    fs::write(&file, token).is_ok()
}

fn do_read_active_token() -> Option<String> {
    let file = get_active_token_file();
    fs::read_to_string(&file).ok().map(|s| s.trim().to_string()).filter(|s| !s.is_empty())
}

fn do_clear_active_token() -> bool {
    let file = get_active_token_file();
    if file.exists() { fs::remove_file(&file).is_ok() } else { true }
}

// ========== Usage checking ==========

fn get_http_client() -> &'static reqwest::Client {
    HTTP_CLIENT.get_or_init(|| {
        reqwest::Client::builder()
            .timeout(std::time::Duration::from_secs(15))
            .pool_idle_timeout(std::time::Duration::from_secs(30))
            .pool_max_idle_per_host(2)
            .build()
            .expect("failed to build HTTP client")
    })
}

fn store_cf_cookies(domain: &str, set_cookie_headers: &[String]) {
    if set_cookie_headers.is_empty() {
        return;
    }
    let cookies: Vec<&str> = set_cookie_headers
        .iter()
        .map(|c| c.split(';').next().unwrap_or(""))
        .filter(|c| !c.is_empty())
        .collect();
    if cookies.is_empty() {
        return;
    }
    let cookie_str = cookies.join("; ");
    if let Ok(mut guard) = CF_COOKIES.lock() {
        let map = guard.get_or_insert_with(HashMap::new);
        map.insert(domain.to_string(), cookie_str);
    }
}

fn get_cf_cookies(domain: &str) -> Option<String> {
    CF_COOKIES
        .lock()
        .ok()
        .and_then(|g| g.as_ref().and_then(|m| m.get(domain).cloned()))
}

fn extract_domain(url: &str) -> String {
    url.split("//")
        .nth(1)
        .and_then(|s| s.split('/').next())
        .unwrap_or("")
        .to_string()
}

/// 浏览器风格 HTTP GET，带 Cloudflare bypass 头和 cookie 持久化
async fn browser_get(
    url: &str,
    headers: &[(&str, &str)],
) -> Result<serde_json::Value, String> {
    let client = get_http_client();
    let domain = extract_domain(url);

    let mut req = client
        .get(url)
        .header("User-Agent", CURSOR_USER_AGENT)
        .header(
            "Accept",
            "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        )
        .header("Accept-Language", "en-US,en;q=0.9")
        .header("sec-ch-ua", "\"Chromium\";v=\"128\", \"Not;A=Brand\";v=\"24\"")
        .header("sec-ch-ua-mobile", "?0")
        .header("sec-ch-ua-platform", "\"Windows\"")
        .header("sec-fetch-dest", "empty")
        .header("sec-fetch-mode", "cors")
        .header("sec-fetch-site", "same-origin")
        .header("upgrade-insecure-requests", "1");

    // 合并 Cloudflare 持久化 cookie 和自定义 cookie
    let mut cookie_parts: Vec<String> = Vec::new();
    if let Some(cf_cookie) = get_cf_cookies(&domain) {
        cookie_parts.push(cf_cookie);
    }

    for (k, v) in headers {
        if k.eq_ignore_ascii_case("cookie") {
            cookie_parts.push(v.to_string());
        } else {
            req = req.header(*k, *v);
        }
    }

    if !cookie_parts.is_empty() {
        req = req.header("Cookie", cookie_parts.join("; "));
    }

    let resp = req.send().await.map_err(|e| e.to_string())?;
    let status = resp.status().as_u16();

    // 提取 Set-Cookie（含 __cf_bm 等 Cloudflare cookie）——必须在消费 body 之前
    let set_cookies: Vec<String> = resp
        .headers()
        .get_all("set-cookie")
        .iter()
        .filter_map(|v| v.to_str().ok())
        .map(String::from)
        .collect();

    if status == 401 || status == 403 {
        store_cf_cookies(&domain, &set_cookies);
        return Err(format!("HTTP {}", status));
    }

    let text = resp.text().await.map_err(|e| e.to_string())?;
    store_cf_cookies(&domain, &set_cookies);

    // 检测 Cloudflare challenge 页面（HTML 而非 JSON）
    let trimmed = text.trim_start();
    if trimmed.starts_with('<')
        || text.contains("cf-browser-verification")
        || text.contains("cf-challenge")
        || text.contains("Just a moment")
    {
        return Err("cloudflare_challenge".to_string());
    }

    serde_json::from_str(&text).map_err(|e| {
        format!(
            "JSON parse error: {} (response: {})",
            e,
            &text[..text.len().min(200)]
        )
    })
}

/// 带 Cloudflare 重试的 HTTP GET
/// 首次请求如被 CF 拦截，等待后利用已存储的 cookie 重试
async fn browser_get_with_retry(
    url: &str,
    headers: &[(&str, &str)],
    max_retries: u32,
) -> Result<serde_json::Value, String> {
    let mut last_err = String::new();

    for attempt in 0..=max_retries {
        match browser_get(url, headers).await {
            Ok(json) => return Ok(json),
            Err(e) => {
                last_err = e.clone();
                if e.contains("cloudflare") && attempt < max_retries {
                    // CF 可能在首次请求的响应中设置了 cookie，等待后带 cookie 重试
                    tokio::time::sleep(std::time::Duration::from_secs(2)).await;
                    continue;
                }
                if attempt < max_retries && !e.contains("401") && !e.contains("403") {
                    tokio::time::sleep(std::time::Duration::from_secs(1)).await;
                    continue;
                }
            }
        }
    }

    Err(last_err)
}

fn decode_jwt_payload(token: &str) -> Option<serde_json::Value> {
    let parts: Vec<&str> = token.split('.').collect();
    if parts.len() < 2 { return None; }
    let payload = parts[1];
    // Add padding
    let _padded = match payload.len() % 4 {
        2 => format!("{}==", payload),
        3 => format!("{}=", payload),
        _ => payload.to_string(),
    };
    let decoded = base64::Engine::decode(
        &base64::engine::general_purpose::URL_SAFE_NO_PAD,
        payload,
    ).ok()?;
    serde_json::from_slice(&decoded).ok()
}

fn extract_user_id(token: &str) -> Option<String> {
    let payload = decode_jwt_payload(token)?;
    payload.get("sub").and_then(|v| v.as_str()).map(String::from)
}

fn is_token_expired(token: &str) -> bool {
    if let Some(payload) = decode_jwt_payload(token) {
        if let Some(exp) = payload.get("exp").and_then(|v| v.as_i64()) {
            let now = chrono::Utc::now().timestamp();
            return now >= exp;
        }
    }
    false
}

async fn fetch_usage_summary(token: &str) -> Result<serde_json::Value, String> {
    let user_id = extract_user_id(token).unwrap_or_default();
    let url = format!("{}/api/usage-summary?user={}", CURSOR_WEB, user_id);
    let cookie = format!("WorkosCursorSessionToken={}%3A%3A{}", user_id, token);
    let auth = format!("Bearer {}", token);
    let referer = format!("{}/settings", CURSOR_WEB);
    browser_get_with_retry(
        &url,
        &[
            ("Cookie", &cookie),
            ("Authorization", &auth),
            ("Referer", &referer),
            ("Content-Type", "application/json"),
        ],
        1,
    )
    .await
}

async fn fetch_stripe_profile(token: &str) -> Result<serde_json::Value, String> {
    let url = format!("{}/auth/full_stripe_profile", CURSOR_API);
    let auth = format!("Bearer {}", token);
    browser_get_with_retry(
        &url,
        &[
            ("Authorization", &auth),
            ("Content-Type", "application/json"),
        ],
        1,
    )
    .await
}

async fn do_check_account_status(token: &str) -> serde_json::Value {
    // ── 检查 1: token 是否过期 ──
    if token.is_empty() {
        return serde_json::json!({
            "needsSwitch": true, "reason": "no_token", "percentUsed": 0
        });
    }
    if is_token_expired(token) {
        return serde_json::json!({
            "needsSwitch": true, "reason": "token_expired", "percentUsed": 0
        });
    }

    // ── 检查 2: 调 /api/usage-summary ──
    let mut percent_used: f64 = 0.0;
    let membership;
    let display_message;
    let mut total_quota: f64 = 0.0;
    let mut needs_switch = false;
    let mut reason = String::new();

    match fetch_usage_summary(token).await {
        Ok(usage) => {
            membership = usage
                .get("membershipType")
                .and_then(|v| v.as_str())
                .unwrap_or("")
                .to_string();
            display_message = usage
                .get("autoModelSelectedDisplayMessage")
                .and_then(|v| v.as_str())
                .unwrap_or("")
                .to_string();

            if let Some(plan) = usage.get("individualUsage").and_then(|v| v.get("plan")) {
                percent_used = plan
                    .get("totalPercentUsed")
                    .and_then(|v| v.as_f64())
                    .unwrap_or(0.0);
                total_quota = plan
                    .get("breakdown")
                    .and_then(|b| b.get("total"))
                    .and_then(|v| v.as_f64())
                    .unwrap_or(0.0);

                if percent_used >= 95.0 {
                    needs_switch = true;
                    reason = "quota_exhausted_percent".to_string();
                }
            }
        }
        Err(e) => {
            if e.contains("401") || e.contains("403") {
                return serde_json::json!({
                    "needsSwitch": false,
                    "reason": "api_auth_failed",
                    "percentUsed": 0,
                    "error": e
                });
            }
            if e.contains("cloudflare") {
                return serde_json::json!({
                    "needsSwitch": false,
                    "reason": "cloudflare_blocked",
                    "percentUsed": 0,
                    "error": e
                });
            }
            return serde_json::json!({
                "needsSwitch": false,
                "reason": "network_error",
                "percentUsed": 0,
                "error": e
            });
        }
    }

    // ── 检查 3: 付费账号额外检测 full_stripe_profile ──
    if !needs_switch && !membership.is_empty() && membership != "free" {
        if let Ok(profile) = fetch_stripe_profile(token).await {
            if let Some(usage_data) = profile.get("usageData").and_then(|v| v.as_array()) {
                for u in usage_data {
                    let exhausted = u
                        .get("usage")
                        .and_then(|x| x.get("exhausted"))
                        .and_then(|v| v.as_bool())
                        .unwrap_or(false);
                    if exhausted {
                        needs_switch = true;
                        reason = format!(
                            "model_exhausted:{}",
                            u.get("modelType").and_then(|v| v.as_str()).unwrap_or("")
                        );
                        break;
                    }
                    let num_requests = u.get("numRequests").and_then(|v| v.as_f64()).unwrap_or(0.0);
                    let max_request = u
                        .get("maxRequestUsage")
                        .and_then(|v| v.as_f64())
                        .unwrap_or(0.0);
                    if max_request > 0.0 && num_requests >= max_request {
                        needs_switch = true;
                        reason = format!(
                            "model_limit_reached:{}",
                            u.get("modelType").and_then(|v| v.as_str()).unwrap_or("")
                        );
                        break;
                    }
                }
            }
        }
    }

    serde_json::json!({
        "needsSwitch": needs_switch,
        "reason": reason,
        "percentUsed": percent_used,
        "membership": membership,
        "totalQuota": total_quota,
        "displayMessage": display_message,
    })
}

async fn do_seamless_switch(
    db_path: &str,
    email: &str,
    access_token: &str,
    refresh_token: &str,
) -> serde_json::Value {
    // Write active token
    do_write_active_token(access_token);

    // Update database
    if !Path::new(db_path).exists() {
        return serde_json::json!({"success": false, "error": "数据库文件不存在"});
    }

    // macOS: 清除 chflags uchg
    utils::clear_macos_immutable_flag(Path::new(db_path));

    let conn = match Connection::open(db_path) {
        Ok(c) => c,
        Err(e) => {
            return serde_json::json!({"success": false, "error": format!("打开数据库失败: {}", e)});
        }
    };

    // Generate new telemetry machine ID (sha256 hex 格式，与 Cursor 原生一致)
    let new_machine_id = {
        let mut hasher = Sha256::new();
        hasher.update(rand::random::<[u8; 32]>());
        hex::encode(hasher.finalize())
    };

    // SQLite 字段名 obfstr 加密：反编译看 .rdata 看不到 cursorAuth/* / telemetry.* 明文
    let key_access = utils::keys::auth_access();
    let key_refresh = utils::keys::auth_refresh();
    let key_email = utils::keys::auth_email();
    let key_signup = utils::keys::auth_signup();
    let key_machine = utils::keys::telem_machine();
    let auth0_value = utils::keys::auth0_value();

    let updates: [(&str, &str); 5] = [
        (key_access.as_str(), access_token),
        (key_refresh.as_str(), refresh_token),
        (key_email.as_str(), email),
        (key_signup.as_str(), &auth0_value),
        (key_machine.as_str(), &new_machine_id),
    ];

    let mut updated_keys = Vec::new();
    for (key, value) in &updates {
        let count: i64 = conn
            .query_row("SELECT COUNT(*) FROM ItemTable WHERE key = ?1", [key], |row| row.get(0))
            .unwrap_or(0);
        let result = if count > 0 {
            conn.execute("UPDATE ItemTable SET value = ?1 WHERE key = ?2", [value, key])
        } else {
            conn.execute("INSERT INTO ItemTable (key, value) VALUES (?1, ?2)", [key, value])
        };
        if result.is_ok() {
            updated_keys.push(key.to_string());
        }
    }

    serde_json::json!({
        "success": true,
        "message": "无感换号成功",
        "email": email,
        "updatedKeys": updated_keys
    })
}

// ========== Tauri commands ==========

#[tauri::command]
pub async fn patch_ext_host(app: AppHandle) -> serde_json::Value {
    // === 模型解锁前置步骤：保证 MITM 链路已就绪 ===
    // 用户开启「激活无感换号」时，先确保 UI 解锁（CA + 环境变量 + settings.json + MITM）已部署。
    // 如果已经部署过（重启程序场景），unlock_enable 内部各步骤都是幂等的，开销很小。
    let unlock_result = tokio::task::spawn_blocking(|| {
        unlock_mitm::enable_unlock()
    }).await;
    let unlock_err = match unlock_result {
        Ok(Ok(())) => None,
        Ok(Err(e)) => Some(e),
        Err(e) => Some(format!("解锁任务调度失败: {}", e)),
    };
    if let Some(e) = unlock_err {
        return serde_json::json!({
            "success": false, "patched": false,
            "error": format!("模型解锁部署失败: {}", e)
        });
    }
    // MITM 需要在 tokio runtime 上启动（spawn_blocking 内不能 spawn 异步任务到代理）
    if !unlock_mitm::is_mitm_running() {
        let _ = unlock_mitm::start_mitm_in_background();
    }

    let paths = cursor_paths::get_cursor_paths();
    let base_path = match paths.base_path {
        Some(ref bp) if paths.error.is_none() => bp.clone(),
        _ => {
            return serde_json::json!({
                "success": false, "patched": false,
                "error": paths.error.unwrap_or_else(|| "无法获取Cursor路径".to_string())
            });
        }
    };
    let install_path = cursor_paths::get_cursor_install_from_base_path(&base_path);
    let result = do_patch_ext_host(&install_path);

    // 补丁注入成功（或已存在）→ 启动自动重补监控
    if result.get("success").and_then(|v| v.as_bool()).unwrap_or(false) {
        start_auto_repatch_monitor(app);
    }

    result
}

#[tauri::command]
pub async fn unpatch_ext_host() -> serde_json::Value {
    // 先停掉自动重补监控（否则刚卸下来又被自动补回去）
    stop_auto_repatch_monitor();

    let paths = cursor_paths::get_cursor_paths();
    let base_path = match paths.base_path {
        Some(ref bp) if paths.error.is_none() => bp.clone(),
        _ => {
            return serde_json::json!({
                "success": false, "patched": false,
                "error": paths.error.unwrap_or_else(|| "无法获取Cursor路径".to_string())
            });
        }
    };
    let install_path = cursor_paths::get_cursor_install_from_base_path(&base_path);
    let unpatch_result = do_unpatch_ext_host(&install_path);

    // 清掉 machine ID 覆盖映射 —— 补丁已经移除，文件不再有意义
    machine_id::clear_machine_id_override();

    // === 模型解锁后置步骤：关闭 MITM、清环境变量 / settings.json / 删 CA ===
    // 用户关闭「激活无感换号」时彻底回退：证书 + 环境变量 + 代理键都清掉。
    unlock_mitm::stop_mitm();
    let _ = tokio::task::spawn_blocking(|| {
        let _ = unlock_mitm::disable_unlock();
    }).await;

    unpatch_result
}

#[tauri::command]
pub async fn check_ext_host_patched(app: AppHandle) -> bool {
    let paths = cursor_paths::get_cursor_paths();
    if let Some(ref bp) = paths.base_path {
        if paths.error.is_none() {
            let install_path = cursor_paths::get_cursor_install_from_base_path(bp);
            let patched = do_check_ext_host_patched(&install_path);
            // 覆盖场景：用户重开工具时，前端 initSeamlessSwitch 会先调这个；
            // 如果检测到 patch 还在，就把自动重补监控也拉起来 —— 否则用户
            // 关掉工具再开就丢监控了。重复 start 是幂等的（内部 was_enabled 守卫）。
            if patched {
                start_auto_repatch_monitor(app);
            }
            return patched;
        }
    }
    false
}

#[tauri::command]
pub async fn write_active_token(token: String) -> bool {
    do_write_active_token(&token)
}

#[tauri::command]
pub async fn read_active_token() -> Option<String> {
    do_read_active_token()
}

#[tauri::command]
pub async fn clear_active_token() -> bool {
    do_clear_active_token()
}

#[tauri::command]
pub async fn check_cursor_usage(access_token: String) -> serde_json::Value {
    do_check_account_status(&access_token).await
}

#[tauri::command]
pub async fn get_cursor_account_quota(access_token: String) -> serde_json::Value {
    // Reuse the usage check which already contains quota info
    do_check_account_status(&access_token).await
}

#[tauri::command]
pub async fn seamless_switch_cmd(
    db_path: String,
    email: String,
    access_token: String,
    refresh_token: String,
) -> serde_json::Value {
    // 1. 先重置机器码（换号前）
    let _ = machine_id::perform_full_machine_id_reset();

    // 2. 执行换号
    let result = do_seamless_switch(&db_path, &email, &access_token, &refresh_token).await;

    // 3. 换号成功后再次重置机器码（确保新账号使用新机器码）
    if result.get("success").and_then(|v| v.as_bool()).unwrap_or(false) {
        let _ = machine_id::perform_full_machine_id_reset();
    }

    result
}

#[tauri::command]
pub async fn one_click_switch(db_path: String, card_code: String) -> serde_json::Value {
    // 1. Check ExtHost patch status —— 这里只读状态，不触发自动重补监控
    let paths = cursor_paths::get_cursor_paths();
    let patched = match paths.base_path {
        Some(ref bp) if paths.error.is_none() => {
            let install_path = cursor_paths::get_cursor_install_from_base_path(bp);
            do_check_ext_host_patched(&install_path)
        }
        _ => false,
    };
    if !patched {
        return serde_json::json!({
            "success": false,
            "error": "请先开启请求拦截（ExtensionHost 补丁）"
        });
    }

    // 2. Fetch new account (使用缓存的设备码，确保稳定性)
    let device_id = utils::get_cached_device_id();
    let body = serde_json::json!({
        "cardCode": card_code,
        "deviceId": device_id
    });

    let api_url_owned = utils::api_url(obfstr::obfstr!("/hou/csk/card/renew"));
    let api_url = api_url_owned.as_str();
    let resp = match utils::http_post_json(api_url, &body).await {
        Ok(r) => r,
        Err(e) => {
            return serde_json::json!({"success": false, "error": format!("后端请求失败: {}", e)});
        }
    };

    let success = resp.get("success").and_then(|v| v.as_bool()).unwrap_or(false);
    if !success {
        let msg = resp.get("message").and_then(|v| v.as_str()).unwrap_or("获取账号失败");
        return serde_json::json!({"success": false, "error": msg});
    }

    let email = resp.get("email").and_then(|v| v.as_str()).unwrap_or("");
    let token = resp.get("token").and_then(|v| v.as_str()).unwrap_or("");

    if email.is_empty() || token.is_empty() {
        return serde_json::json!({"success": false, "error": "后端返回的账号信息不完整"});
    }

    // 3. 先重置机器码（换号前）—— 捕获结果是为了把状态带回前端做反馈
    let pre_reset = machine_id::perform_full_machine_id_reset();
    let pre_reset_ok = pre_reset.success;
    let pre_details = pre_reset.details.clone();

    // 4. Execute seamless switch
    let switch_result = do_seamless_switch(&db_path, email, token, token).await;
    let switch_ok = switch_result
        .get("success")
        .and_then(|v| v.as_bool())
        .unwrap_or(false);

    // 5. 换号成功后再次重置机器码（确保新账号使用新机器码）
    let (post_reset_ok, post_details) = if switch_ok {
        let post = machine_id::perform_full_machine_id_reset();
        (post.success, post.details.clone())
    } else {
        (false, Vec::new())
    };

    let mut result = switch_result;
    if let Some(obj) = result.as_object_mut() {
        obj.insert("email".to_string(), serde_json::json!(email));
        // 给前端：只要 pre 或 post 任一成功就算重置生效（两次互相兜底）
        obj.insert(
            "machineIdReset".to_string(),
            serde_json::json!(pre_reset_ok || post_reset_ok),
        );
        // 把每一步执行细节也带回前端 —— 方便用户在 DevTools console 验证机器码确实重置了
        // 包括 macOS 路径上的 storage.json / state.vscdb / machineId 文件 / main.js 修补
        obj.insert(
            "machineIdResetDetails".to_string(),
            serde_json::json!({
                "preReset": { "success": pre_reset_ok, "steps": pre_details },
                "postReset": { "success": post_reset_ok, "steps": post_details }
            }),
        );
    }
    result
}

// ========== 自动换号轮询（与 Electron usageMonitorPoll 一致） ==========

const AUTO_SWITCH_POLL_MIN_SECS: u64 = 20;
const AUTO_SWITCH_POLL_MAX_SECS: u64 = 30;

async fn fetch_new_account_with_retry(
    app: &AppHandle,
    card_code: &str,
) -> Result<(String, String), String> {
    // 使用缓存的设备码，确保稳定性
    let device_id = utils::get_cached_device_id();
    let api_url_owned = utils::api_url(obfstr::obfstr!("/hou/csk/card/renew"));
    let api_url = api_url_owned.as_str();
    let max_retries = 3;

    for retry in 0..=max_retries {
        if !AUTO_SWITCH_ENABLED.load(Ordering::SeqCst) {
            return Err("已关闭自动换号".to_string());
        }

        let body = serde_json::json!({
            "cardCode": card_code,
            "deviceId": device_id
        });

        match utils::http_post_json(api_url, &body).await {
            Ok(resp) => {
                let success = resp.get("success").and_then(|v| v.as_bool()).unwrap_or(false);
                if success {
                    let email = resp.get("email").and_then(|v| v.as_str()).unwrap_or("").to_string();
                    let token = resp.get("token").and_then(|v| v.as_str()).unwrap_or("").to_string();
                    if !email.is_empty() && !token.is_empty() {
                        return Ok((email, token));
                    }
                    return Err("后端返回的账号信息不完整".to_string());
                }

                let msg = resp.get("message").and_then(|v| v.as_str()).unwrap_or("").to_string();

                // 限频检测（与 Electron 一致：包含「频繁」「稍后」「1分钟」）
                if msg.contains("频繁") || msg.contains("稍后") || msg.contains("1分钟") {
                    if retry < max_retries {
                        let wait_sec = if retry == 0 { 30 } else { 65 };
                        let _ = app.emit_all(
                            "auto-switch-status",
                            serde_json::json!({
                                "switching": true,
                                "message": format!("后端限频，{}秒后重试...", wait_sec)
                            }),
                        );
                        tokio::time::sleep(std::time::Duration::from_secs(wait_sec)).await;
                        continue;
                    }
                }

                return Err(if msg.is_empty() { "获取账号失败".to_string() } else { msg });
            }
            Err(e) => {
                if retry < max_retries {
                    tokio::time::sleep(std::time::Duration::from_secs(30)).await;
                    continue;
                }
                return Err(e);
            }
        }
    }

    Err("重试次数用尽".to_string())
}

/// 调用后端验证服务二次确认 token 额度（经主后端转发，绕过客户端 Cloudflare 拦截）
/// 返回 None 表示服务不可达
async fn call_verify_service(token: &str) -> Option<serde_json::Value> {
    let api_url_owned = utils::api_url(obfstr::obfstr!("/hou/csk/verify-token-v2"));
    let api_url = api_url_owned.as_str();
    let body = serde_json::json!({ "token": token });

    match utils::http_post_json(api_url, &body).await {
        Ok(data) => {
            crate::ulog!(
                "[VerifyService] 结果: canSwitch={} | {}% | reason={}",
                data.get("canSwitch").and_then(|v| v.as_bool()).unwrap_or(false),
                data.get("percentUsed").and_then(|v| v.as_f64()).unwrap_or(0.0),
                data.get("reason").and_then(|v| v.as_str()).unwrap_or("")
            );
            Some(data)
        }
        Err(e) => {
            crate::ulog!("[VerifyService] 不可达: {}", e);
            None
        }
    }
}

async fn usage_monitor_poll(app: &AppHandle) {
    let token = match do_read_active_token() {
        Some(t) => t,
        None => return,
    };

    // 首次检测：本地直接调 Cursor 官方 API
    let mut status = do_check_account_status(&token).await;
    let has_error = status.get("error").is_some();
    let reason = status
        .get("reason")
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .to_string();

    // token 问题（过期/不存在）是确定性结论，无需二次检测
    let is_token_issue = reason == "no_token" || reason == "token_expired";

    if !is_token_issue && has_error {
        // ── 本地检测失败（Cloudflare/网络/认证），调后端验证服务二次确认 ──
        crate::ulog!(
            "[AutoSwitch] 本地检测失败({}), 调用验证服务二次确认...",
            reason
        );

        match call_verify_service(&token).await {
            Some(verify) => {
                let can_switch = verify
                    .get("canSwitch")
                    .and_then(|v| v.as_bool())
                    .unwrap_or(false);
                if !can_switch {
                    crate::ulog!(
                        "[AutoSwitch] 验证服务确认: 还有额度({}%), 不换号",
                        verify.get("percentUsed").and_then(|v| v.as_f64()).unwrap_or(0.0)
                    );
                    return;
                }
                crate::ulog!(
                    "[AutoSwitch] 验证服务确认: 需要换号({}%, {})",
                    verify.get("percentUsed").and_then(|v| v.as_f64()).unwrap_or(0.0),
                    verify.get("reason").and_then(|v| v.as_str()).unwrap_or("")
                );
                if let Some(obj) = status.as_object_mut() {
                    obj.insert("needsSwitch".to_string(), serde_json::json!(true));
                    if let Some(p) = verify.get("percentUsed") {
                        obj.insert("percentUsed".to_string(), p.clone());
                    }
                    if let Some(r) = verify.get("reason") {
                        obj.insert("reason".to_string(), r.clone());
                    }
                    obj.remove("error");
                }
            }
            None => {
                // 验证服务不可达 → 保守策略，不换号
                crate::ulog!("[AutoSwitch] 验证服务不可达，保守不换号");
                return;
            }
        }
    }

    let needs_switch = status
        .get("needsSwitch")
        .and_then(|v| v.as_bool())
        .unwrap_or(false);

    if !needs_switch {
        return;
    }

    // 触发换号 —— 原子声明 BUSY（防止双 loop 同时进入），并用 RAII 守卫保证
    // **不管哪条路径退出（正常 / 早返回 / panic）BUSY 都自动复位**。
    // 之前的 `BUSY.store(false)` 散落在 4 处，任意一处遗漏或 panic 都会让 BUSY 永远卡 true。
    if AUTO_SWITCH_BUSY
        .compare_exchange(false, true, Ordering::SeqCst, Ordering::SeqCst)
        .is_err()
    {
        // 另一个 loop 已经在跑了，让出
        return;
    }
    let _busy_guard = BusyGuard;

    let card_code = match AUTO_SWITCH_CARD_CODE.lock().ok().and_then(|g| g.clone()) {
        Some(c) => c,
        None => {
            // BusyGuard drop 会复位 BUSY，无需手动
            return;
        }
    };

    let percent_used = status.get("percentUsed").and_then(|v| v.as_f64()).unwrap_or(0.0);
    let reason = status
        .get("reason")
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .to_string();

    let _ = app.emit_all(
        "auto-switch-status",
        serde_json::json!({
            "switching": true,
            "message": format!("检测到额度耗尽 ({}%), 原因: {}, 正在换号...", percent_used, reason)
        }),
    );

    // 1. 获取新账号
    let (email, new_token) = match fetch_new_account_with_retry(app, &card_code).await {
        Ok(pair) => pair,
        Err(e) => {
            let _ = app.emit_all(
                "auto-switch-status",
                serde_json::json!({
                    "switching": false,
                    "success": false,
                    "error": e
                }),
            );
            // BusyGuard drop 会复位 BUSY
            return;
        }
    };

    // 2. 先重置机器码（换号前）
    let _ = machine_id::perform_full_machine_id_reset();

    // 3. 执行无感换号
    let db_path = utils::get_cursor_db_path()
        .map(|p| p.to_string_lossy().to_string())
        .unwrap_or_default();
    let switch_result = do_seamless_switch(&db_path, &email, &new_token, &new_token).await;
    let switch_ok = switch_result
        .get("success")
        .and_then(|v| v.as_bool())
        .unwrap_or(false);

    // 4. 换号成功后再次重置机器码（确保新账号使用新机器码）
    if switch_ok {
        let _ = machine_id::perform_full_machine_id_reset();
    }

    let _ = app.emit_all(
        "auto-switch-status",
        serde_json::json!({
            "switching": false,
            "success": switch_ok,
            "email": email,
            "message": if switch_ok {
                format!("自动换号成功: {}", email)
            } else {
                "自动换号失败".to_string()
            }
        }),
    );
    // _busy_guard drop → BUSY = false
}

/// BUSY 标志的 RAII 守卫：实例 drop 时（包括 panic 退栈时）自动复位 BUSY 到 false。
/// 这是「自动换号开了就永不失效」的最后一道保险 —— 哪怕换号流程里的某行代码出现意外
/// panic / 提前 return，BUSY 也不会永远卡在 true。
struct BusyGuard;
impl Drop for BusyGuard {
    fn drop(&mut self) {
        AUTO_SWITCH_BUSY.store(false, Ordering::SeqCst);
    }
}

async fn usage_monitor_loop(app: AppHandle) {
    // 首次延迟 3 秒
    tokio::time::sleep(std::time::Duration::from_secs(3)).await;

    while AUTO_SWITCH_ENABLED.load(Ordering::SeqCst) {
        if !AUTO_SWITCH_BUSY.load(Ordering::SeqCst) {
            // 把 poll 放到独立子任务跑：
            // - 即使 poll 因为某行罕见的 panic 退栈（JSON / IO / mutex 中毒等），
            //   panic 被困在子任务里，loop 自身继续存活
            // - JoinError 不会再被传播为 panic
            // - 同时 BusyGuard 会在 panic 展开时 drop，自动复位 BUSY
            let app_clone = app.clone();
            let _ = tokio::spawn(async move {
                usage_monitor_poll(&app_clone).await;
            })
            .await;
        }

        // 20-30 秒随机间隔，每秒检查一次 enabled 标志以便快速响应关闭
        let interval_secs = AUTO_SWITCH_POLL_MIN_SECS
            + (rand::random::<u64>() % (AUTO_SWITCH_POLL_MAX_SECS - AUTO_SWITCH_POLL_MIN_SECS + 1));
        for _ in 0..interval_secs {
            if !AUTO_SWITCH_ENABLED.load(Ordering::SeqCst) {
                return;
            }
            tokio::time::sleep(std::time::Duration::from_secs(1)).await;
        }
    }
}

// ========== 自动重补丁监控（应对 Cursor 自更新覆盖 extensionHostProcess.js）==========
//
// Cursor 用 Squirrel 静默后台下载更新，重启时整个替换 resources/app/ 目录。
// 这会冲掉我们在 extensionHostProcess.js 里的 MOCURSO_EH_PATCH_START 注入块。
// 工具如果一直开着，要能自动发现并提醒用户。
//
// 策略（用户决定）：
//   - 67s 间隔轮询（避开 60s 缓存窗）
//   - 仅在「激活无感换号」开启时启动；关闭时停掉
//   - 检测到补丁缺失 → emit `patch-missing-alert` 事件，由前端弹模态窗口提示用户手动
//     重新激活无感换号（关闭再开启）+ 重启 Cursor
//   - 后端只在「连续缺失」中的首次发出 alert，避免每 67s 反复推；用户重新打补丁后状态
//     回到 patched，下次再缺失时重新触发

/// 标记上一次 tick 时补丁是否缺失，用于去重 alert
static AUTO_REPATCH_LAST_MISSING: AtomicBool = AtomicBool::new(false);

async fn auto_repatch_loop(app: AppHandle) {
    // 首次延迟 60 秒，避开刚刚 patch 完成的窗口 +
    // 让 usage_monitor_loop（3s 启动）有充足时间完成第一次轮询
    tokio::time::sleep(std::time::Duration::from_secs(60)).await;

    while AUTO_REPATCH_ENABLED.load(Ordering::SeqCst) {
        // 如果自动换号正在忙（写 SQLite / 拉新账号 / emit 事件），
        // 跳过本次 tick 避免跟换号 I/O 竞争。等下一周期再说。
        if !AUTO_SWITCH_BUSY.load(Ordering::SeqCst) {
            // 把同步的 file I/O 放到 spawn_blocking —— 否则读几 MB 的
            // extensionHostProcess.js 会阻塞 tokio worker 线程，导致同 worker 上
            // usage_monitor_poll 里 await 中的 HTTPS 调用被卡住（极端情况下会超时）。
            let app_clone = app.clone();
            let _ = tokio::task::spawn_blocking(move || {
                auto_repatch_tick(&app_clone);
            }).await;
        }

        // 67s 间隔，每秒检查 enabled 标志快速响应关闭
        for _ in 0..AUTO_REPATCH_INTERVAL_SECS {
            if !AUTO_REPATCH_ENABLED.load(Ordering::SeqCst) {
                return;
            }
            tokio::time::sleep(std::time::Duration::from_secs(1)).await;
        }
    }
}

fn auto_repatch_tick(app: &AppHandle) {
    let paths = cursor_paths::get_cursor_paths();
    if paths.error.is_some() {
        return;
    }
    let base_path = match paths.base_path {
        Some(bp) => bp,
        None => return,
    };
    let install_path = cursor_paths::get_cursor_install_from_base_path(&base_path);

    let patched = do_check_ext_host_patched(&install_path);

    if patched {
        // 补丁还在 → 重置 missing 标记，啥都不用做
        AUTO_REPATCH_LAST_MISSING.store(false, Ordering::SeqCst);
        return;
    }

    // 补丁缺失 → 如果上次 tick 也是缺失，说明用户还没处理，跳过本次 emit 避免连续轰炸
    let prev_missing = AUTO_REPATCH_LAST_MISSING.swap(true, Ordering::SeqCst);
    if prev_missing {
        return;
    }

    // 首次发现缺失 → 取 Cursor 版本号一起带过去，前端模态可以展示
    let cursor_version = paths.version.clone().unwrap_or_default();
    let _ = app.emit_all(
        "patch-missing-alert",
        serde_json::json!({
            "version": cursor_version,
        }),
    );
}

/// 启动自动重补监控（幂等：已运行则 no-op）
fn start_auto_repatch_monitor(app: AppHandle) {
    AUTO_REPATCH_LAST_MISSING.store(false, Ordering::SeqCst);
    let was_enabled = AUTO_REPATCH_ENABLED.swap(true, Ordering::SeqCst);
    if !was_enabled {
        tokio::spawn(async move {
            auto_repatch_loop(app).await;
        });
    }
}

/// 停止自动重补监控
fn stop_auto_repatch_monitor() {
    AUTO_REPATCH_ENABLED.store(false, Ordering::SeqCst);
    AUTO_REPATCH_LAST_MISSING.store(false, Ordering::SeqCst);
}

#[tauri::command]
pub async fn toggle_auto_switch(
    app: AppHandle,
    enabled: bool,
    card_code: Option<String>,
) -> serde_json::Value {
    if enabled {
        let cc = match card_code {
            Some(c) if !c.is_empty() => c,
            _ => {
                return serde_json::json!({"success": false, "error": "请先验证卡密"});
            }
        };

        // 防御性清理：上一次会话残留的 BUSY 标志（极端情况下若上次 BusyGuard
        // 也未能复位）—— 新开启的会话从 BUSY=false 起跑
        AUTO_SWITCH_BUSY.store(false, Ordering::SeqCst);

        // 1. 注入 ExtHost 补丁
        let paths = cursor_paths::get_cursor_paths();
        if let Some(ref bp) = paths.base_path {
            if paths.error.is_none() {
                let install_path = cursor_paths::get_cursor_install_from_base_path(bp);
                do_unpatch_ext_host(&install_path);
                do_patch_ext_host(&install_path);
            }
        }

        // 2. 保存 card_code
        if let Ok(mut guard) = AUTO_SWITCH_CARD_CODE.lock() {
            *guard = Some(cc);
        }

        // 3. 启动后台轮询任务（仅当从 disabled → enabled 时）
        let was_enabled = AUTO_SWITCH_ENABLED.swap(true, Ordering::SeqCst);
        if !was_enabled {
            let app_clone = app.clone();
            tokio::spawn(async move {
                usage_monitor_loop(app_clone).await;
            });
        }

        serde_json::json!({"success": true, "enabled": true})
    } else {
        AUTO_SWITCH_ENABLED.store(false, Ordering::SeqCst);
        // 关闭时也清 BUSY，确保下次开启从干净状态开始
        AUTO_SWITCH_BUSY.store(false, Ordering::SeqCst);
        if let Ok(mut guard) = AUTO_SWITCH_CARD_CODE.lock() {
            *guard = None;
        }
        serde_json::json!({"success": true, "enabled": false})
    }
}

#[tauri::command]
pub async fn get_auto_switch_status() -> serde_json::Value {
    serde_json::json!({
        "enabled": AUTO_SWITCH_ENABLED.load(Ordering::SeqCst),
        "busy": AUTO_SWITCH_BUSY.load(Ordering::SeqCst)
    })
}
