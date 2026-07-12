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
use super::unlock_workbench;

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
/// v9：【临时诊断 3.10.17】开日志，确认 hook 在新版是否拦到对话请求
/// v10：【3.10.17 修复】新增 http1.1 (http/https) 原型级 hook —— 与 util v3 同源修复，
///      应对「配了代理时 Cursor 把请求从 HTTP/2 降级到 HTTP/1.1」导致旧 http2-only hook 失效。
const EH_PATCH_VERSION: u32 = 10;
const EH_PATCH_VERSION_MARKER: &str = "MOCURSO_EH_PATCH_V";

// === util 单例进程补丁（Cursor 3.9+ 把 AI 请求挪到了 electron-utility 单例进程）===
// 该进程用 ESM 命名空间导入 http2（import * as x from "node:http2"），命名空间绑定是
// 快照，require('http2').connect= 覆盖对它无效；因此改为 patch ClientHttp2Session.prototype.request
// —— 所有 client http2 会话共享同一原型，方法在调用时解析，无论怎么导入都能拦到。
//
// v3【3.10.17 修复】新增 http1.1 (http/https) 原型级 hook。
//   背景：Cursor 3.10.17 的 util 进程在「检测到 backend 配了生效代理」时，会主动把请求
//   从 HTTP/2 降级到 HTTP/1.1（源码里那句 "Falling back to HTTP/1.1 because an effective
//   proxy is configured"）。而我们的「模型解锁」会往 settings.json 写 http.proxy=127.0.0.1:8189，
//   正好触发这个降级 → 请求走 Node 的 http/https 模块，绕过只 hook http2 的旧补丁 →
//   authorization 不再被替换成 active_token → Cursor 直接用数据库里的旧 token（无感换号失效）。
//   修复：额外 hook OutgoingMessage.prototype.setHeader（改 authorization）+
//   ClientRequest.prototype.write/end（改 body 机器码）。原型方法在调用时解析，
//   对 ESM 命名空间导入的 http/https 同样生效。http2 + http1.1 双覆盖，是否走代理都健壮。
const UTIL_PATCH_START: &str = "/* MOCURSO_UTIL_PATCH_START */";
const UTIL_PATCH_END: &str = "/* MOCURSO_UTIL_PATCH_END */";
/// util 补丁版本号 —— 每次改 build_util_inject_code 都要 +1（旧版本检测到会自动卸载重装）。
const UTIL_PATCH_VERSION: u32 = 3;
const UTIL_PATCH_VERSION_MARKER: &str = "MOCURSO_UTIL_PATCH_V";
/// util 补丁里 _muLG() 日志开关。release 默认 false（不写 util_patch.log，零开销）。
const UTIL_LOG_ENABLED: bool = false;

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

/// util 单例进程文件路径（Cursor 3.9+ 的 electron-utility 单例进程）。
/// 旧版本 Cursor 没有这个文件，调用方需容忍其不存在。
fn get_util_singleton_js_path(cursor_install_path: &Path) -> PathBuf {
    #[cfg(target_os = "macos")]
    {
        cursor_install_path
            .join("Contents").join("Resources").join("app").join("out")
            .join("vs").join("code").join("electron-utility")
            .join("alwaysLocalSingleton").join("alwaysLocalSingletonMain.js")
    }
    #[cfg(not(target_os = "macos"))]
    {
        cursor_install_path
            .join("resources").join("app").join("out")
            .join("vs").join("code").join("electron-utility")
            .join("alwaysLocalSingleton").join("alwaysLocalSingletonMain.js")
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
try{{const _mcHttp=_mcR('http');const _mcOM=_mcHttp.OutgoingMessage;const _mcCR=_mcHttp.ClientRequest;const _mcIsCur=function(rq){{try{{if(!rq)return false;const cands=[rq.host,rq.getHeader&&rq.getHeader('host'),rq.getHeader&&rq.getHeader(':authority'),rq.path];for(const c of cands){{if(c&&(String(c).includes('cursor.sh')||String(c).includes('cursor.com')))return true;}}return false;}}catch(e){{return false;}}}};if(_mcOM&&_mcOM.prototype&&!_mcOM.prototype.__mcH1P){{_mcOM.prototype.__mcH1P=true;const _oS=_mcOM.prototype.setHeader;_mcOM.prototype.setHeader=function(n,v){{try{{if(_mcIsCur(this)&&typeof n==='string'){{const ln=n.toLowerCase();if(ln==='authorization'){{const t=_mcGT();if(t){{v='Bearer '+t;_mcLG('intercept h1 setHeader authorization token=YES');}}}}else if(typeof v==='string'){{const nv=_mcSR(v);if(nv!==v)v=nv;}}}}}}catch(e){{}}return _oS.call(this,n,v);}};_mcLG('eh h1 patch: setHeader patched');}}if(_mcCR&&_mcCR.prototype&&!_mcCR.prototype.__mcH1BP){{_mcCR.prototype.__mcH1BP=true;const _oW=_mcCR.prototype.write;const _oE=_mcCR.prototype.end;_mcCR.prototype.write=function(c,...rr){{try{{if(_mcIsCur(this)&&c!=null)c=_mcPB(c);}}catch(e){{}}return _oW.call(this,c,...rr);}};_mcCR.prototype.end=function(c,...rr){{try{{if(_mcIsCur(this)&&c!=null&&typeof c!=='function')c=_mcPB(c);}}catch(e){{}}return _oE.call(this,c,...rr);}};_mcLG('eh h1 patch: ClientRequest.write/end patched');}}}}catch(e){{}}\n\
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

/// 构造 util 单例进程的注入代码（patch ClientHttp2Session.prototype.request）。
/// token / 映射文件路径在 JS 端用 os.homedir() 运行时解析，避免烤死绝对路径在异机错位。
fn build_util_inject_code() -> String {
    let vmark = format!("/* {}{} */", UTIL_PATCH_VERSION_MARKER, UTIL_PATCH_VERSION);
    // _muLG 函数体：日志关闭时为空函数（零开销）
    let log_body = if UTIL_LOG_ENABLED {
        r#"try{_muFS.appendFileSync(_muLF,'['+new Date().toISOString()+'] '+m+'\n');}catch(e){}"#
    } else {
        ""
    };
    let js = r##"__START__
__VMARK__
const _muM=await import('node:module');
const _muR=_muM.createRequire(import.meta.url);
const _muOS=_muR('os');
const _muFS=_muR('fs');
const _muH2=_muR('http2');
const _muHOME=_muOS.homedir()||'';
const _muTF=_muHOME+'/.cursor-renewal/active_token';
const _muOF=_muHOME+'/.cursor-renewal/machine_id_override';
const _muLF=_muHOME+'/.cursor-renewal/util_patch.log';
function _muLG(m){__LOGBODY__}
let _muTk=null,_muTt=0;
function _muGT(){const n=Date.now();if(n-_muTt>500){_muTt=n;try{_muTk=_muFS.readFileSync(_muTF,'utf8').trim()||null;}catch(e){_muTk=null;}}return _muTk;}
let _muMap=null,_muMt=0;
function _muGM(){const n=Date.now();if(n-_muMt>500){_muMt=n;try{const r=JSON.parse(_muFS.readFileSync(_muOF,'utf8'));_muMap=Array.isArray(r&&r.mappings)?r.mappings.filter(m=>m&&typeof m.old==='string'&&typeof m.new==='string'&&m.old.length>=8):[];}catch(e){_muMap=[];}}return _muMap||[];}
function _muSR(s){if(typeof s!=='string')return s;const map=_muGM();if(!map.length)return s;let o=s;for(const m of map){if(o.indexOf(m.old)!==-1)o=o.split(m.old).join(m.new);}return o;}
function _muPH(h){if(!h||typeof h!=='object')return;try{for(const k of Object.keys(h)){const v=h[k];if(typeof v==='string'){const nv=_muSR(v);if(nv!==v)h[k]=nv;}else if(Array.isArray(v)){h[k]=v.map(x=>typeof x==='string'?_muSR(x):x);}}}catch(e){}}
function _muBR(buf){const map=_muGM();if(!buf||buf.length<8||!map.length)return buf;let out=buf,n=0;for(const m of map){if(m.old.length!==m.new.length)continue;const ob=Buffer.from(m.old,'utf8'),nb=Buffer.from(m.new,'utf8');if(ob.length!==nb.length)continue;let i=0,w=null;while(true){const f=out.indexOf(ob,i);if(f===-1)break;if(w===null)w=Buffer.from(out);nb.copy(w,f);i=f+ob.length;n++;}if(w!==null)out=w;}return out;}
function _muPB(b){if(b==null)return b;try{if(typeof b==='string'){return _muSR(b);}if(Buffer.isBuffer(b))return _muBR(b);if(b instanceof Uint8Array)return _muBR(Buffer.from(b.buffer,b.byteOffset,b.byteLength));}catch(e){}return b;}
function _muAuthority(sess){try{for(const s of Object.getOwnPropertySymbols(sess)){if(s.toString()==='Symbol(authority)')return String(sess[s]||'');}}catch(e){}return '';}
try{
  let _muProto=null;
  try{const _t=_muH2.connect('http://127.0.0.1:1');_t.on('error',()=>{});_muProto=Object.getPrototypeOf(_t);try{_t.destroy();}catch(e){}}catch(e){_muLG('get proto failed: '+e);}
  if(_muProto&&typeof _muProto.request==='function'&&!_muProto.__muPatched){
    _muProto.__muPatched=true;
    const _origReq=_muProto.request;
    _muProto.request=function(headers,...rest){
      try{
        const auth=_muAuthority(this);
        const hAuth=headers&&(headers[':authority']||headers['host']||'');
        const isCursor=(auth&&(auth.includes('cursor.sh')||auth.includes('cursor.com')))||(hAuth&&(String(hAuth).includes('cursor.sh')||String(hAuth).includes('cursor.com')));
        if(isCursor&&headers&&typeof headers==='object'){
          const t=_muGT();
          if(t)headers['authorization']='Bearer '+t;
          _muPH(headers);
          _muLG('intercept '+auth+' token='+(t?'YES':'NO'));
          const _rs=_origReq.call(this,headers,...rest);
          try{
            const _ow=_rs.write?_rs.write.bind(_rs):null;
            if(_ow)_rs.write=function(c,...rr){return _ow(_muPB(c),...rr);};
            const _oe=_rs.end?_rs.end.bind(_rs):null;
            if(_oe)_rs.end=function(c,...rr){if(c==null)return _oe(...rr);return _oe(_muPB(c),...rr);};
          }catch(e){}
          return _rs;
        }
      }catch(e){_muLG('hook err '+e);}
      return _origReq.call(this,headers,...rest);
    };
    _muLG('util patch v1 loaded, prototype.request patched');
  }else{_muLG('util patch: proto unavailable or already patched');}
}catch(e){_muLG('util patch fatal '+e);}
try{
  const _muHttp=_muR('http');
  const _muOM=_muHttp.OutgoingMessage;
  const _muCR=_muHttp.ClientRequest;
  const _muIsCur=function(rq){try{if(!rq)return false;const cands=[rq.host,rq.getHeader&&rq.getHeader('host'),rq.getHeader&&rq.getHeader(':authority'),rq.path];for(const c of cands){if(c&&(String(c).includes('cursor.sh')||String(c).includes('cursor.com')))return true;}return false;}catch(e){return false;}};
  if(_muOM&&_muOM.prototype&&!_muOM.prototype.__muH1P){
    _muOM.prototype.__muH1P=true;
    const _oSet=_muOM.prototype.setHeader;
    _muOM.prototype.setHeader=function(name,value){
      try{
        if(_muIsCur(this)&&typeof name==='string'){
          const ln=name.toLowerCase();
          if(ln==='authorization'){const t=_muGT();if(t){value='Bearer '+t;_muLG('intercept h1 setHeader authorization token=YES');}}
          else if(typeof value==='string'){const nv=_muSR(value);if(nv!==value)value=nv;}
        }
      }catch(e){_muLG('h1 setHeader err '+e);}
      return _oSet.call(this,name,value);
    };
    _muLG('util h1 patch: OutgoingMessage.setHeader patched');
  }
  if(_muCR&&_muCR.prototype&&!_muCR.prototype.__muH1BP){
    _muCR.prototype.__muH1BP=true;
    const _oW=_muCR.prototype.write;
    const _oE=_muCR.prototype.end;
    _muCR.prototype.write=function(chunk,...rest){
      try{if(_muIsCur(this)&&chunk!=null)chunk=_muPB(chunk);}catch(e){}
      return _oW.call(this,chunk,...rest);
    };
    _muCR.prototype.end=function(chunk,...rest){
      try{if(_muIsCur(this)&&chunk!=null&&typeof chunk!=='function')chunk=_muPB(chunk);}catch(e){}
      return _oE.call(this,chunk,...rest);
    };
    _muLG('util h1 patch: ClientRequest.write/end patched');
  }
}catch(e){_muLG('util h1 patch fatal '+e);}
__END__
"##;
    js.replace("__START__", UTIL_PATCH_START)
        .replace("__END__", UTIL_PATCH_END)
        .replace("__VMARK__", &vmark)
        .replace("__LOGBODY__", log_body)
}

/// 通用：删掉 content 中 start..end 区间（含两端标记），找不到则原样返回。
fn strip_patch_block(content: &str, start: &str, end: &str) -> String {
    if let (Some(s), Some(e)) = (content.find(start), content.find(end)) {
        let end_with = e + end.len();
        let mut out = String::with_capacity(content.len());
        out.push_str(&content[..s]);
        if end_with < content.len() {
            out.push_str(&content[end_with..]);
        }
        out.trim_start().to_string()
    } else {
        content.to_string()
    }
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

// ========== util 单例进程补丁（Cursor 3.9+） ==========

/// 给 util 单例进程注入补丁。旧版本无此文件 → 返回 success:true + skipped:true（不算失败）。
fn do_patch_util_singleton(cursor_install_path: &Path) -> serde_json::Value {
    let path = get_util_singleton_js_path(cursor_install_path);
    crate::ulog!("[Util] patch start, target = {}", path.display());

    if !path.exists() {
        crate::ulog!("[Util] file not found, skip（旧版本无此进程）");
        return serde_json::json!({"success": true, "patched": false, "skipped": true, "message": "无 util 单例进程（旧版本）"});
    }

    let content = match fs::read_to_string(&path) {
        Ok(c) => c,
        Err(e) => {
            crate::ulog!("[Util] ✗ read failed: {}", e);
            return serde_json::json!({"success": false, "patched": false, "error": format!("读取文件失败: {}", e)});
        }
    };

    // 已打补丁 → 检查版本
    let current_version_marker = format!("{}{}", UTIL_PATCH_VERSION_MARKER, UTIL_PATCH_VERSION);
    if content.contains(UTIL_PATCH_START) {
        if content.contains(&current_version_marker) {
            crate::ulog!("[Util] already patched v{} (skip)", UTIL_PATCH_VERSION);
            return serde_json::json!({"success": true, "patched": true, "message": "util 已是最新补丁"});
        }
        crate::ulog!("[Util] old version detected, stripping...");
        let stripped = strip_patch_block(&content, UTIL_PATCH_START, UTIL_PATCH_END);
        let wr = utils::safe_modify_file(&path, || {
            fs::write(&path, &stripped).map_err(|e| format!("剥旧补丁失败: {}", e))
        });
        if let Err(e) = wr {
            crate::ulog!("[Util] ✗ strip failed: {}", e);
            return serde_json::json!({"success": false, "patched": false, "error": e});
        }
    }

    // 备份（仅首次）
    let backup = format!("{}.bak", path.to_string_lossy());
    if !Path::new(&backup).exists() {
        let _ = fs::copy(&path, &backup);
    }

    let current = match fs::read_to_string(&path) {
        Ok(c) => c,
        Err(e) => {
            crate::ulog!("[Util] ✗ re-read after strip failed: {}", e);
            return serde_json::json!({"success": false, "patched": false, "error": format!("剥旧补丁后再读失败: {}", e)});
        }
    };

    let inject = build_util_inject_code();
    let new_content = format!("{}{}", inject, current);

    let wr = utils::safe_modify_file(&path, || {
        fs::write(&path, &new_content).map_err(|e| format!("写入文件失败: {}", e))
    });

    match wr {
        Ok(()) => {
            crate::ulog!("[Util] ✓ injected v{}, size = {} bytes", UTIL_PATCH_VERSION, new_content.len());
            #[cfg(target_os = "macos")]
            {
                let app_path = cursor_install_path.to_string_lossy();
                let _ = std::process::Command::new("xattr").args(["-cr", &app_path]).output();
                let _ = std::process::Command::new("codesign").args(["--force", "--deep", "--sign", "-", &app_path]).output();
            }
            serde_json::json!({"success": true, "patched": true, "message": "util 补丁注入成功"})
        }
        Err(e) => serde_json::json!({"success": false, "patched": false, "error": e}),
    }
}

/// 移除 util 单例进程补丁。文件不存在 / 无补丁 → 视为成功。
fn do_unpatch_util_singleton(cursor_install_path: &Path) -> serde_json::Value {
    let path = get_util_singleton_js_path(cursor_install_path);
    if !path.exists() {
        return serde_json::json!({"success": true, "patched": false, "message": "无 util 文件"});
    }
    let content = match fs::read_to_string(&path) {
        Ok(c) => c,
        Err(e) => return serde_json::json!({"success": false, "error": e.to_string()}),
    };
    if !content.contains(UTIL_PATCH_START) {
        return serde_json::json!({"success": true, "patched": false, "message": "未检测到 util 补丁"});
    }
    let new_content = strip_patch_block(&content, UTIL_PATCH_START, UTIL_PATCH_END);
    let wr = utils::safe_modify_file(&path, || {
        fs::write(&path, &new_content).map_err(|e| format!("写入失败: {}", e))
    });
    match wr {
        Ok(()) => {
            #[cfg(target_os = "macos")]
            {
                let app_path = cursor_install_path.to_string_lossy();
                let _ = std::process::Command::new("xattr").args(["-cr", &app_path]).output();
                let _ = std::process::Command::new("codesign").args(["--force", "--deep", "--sign", "-", &app_path]).output();
            }
            serde_json::json!({"success": true, "patched": false, "message": "util 补丁已移除"})
        }
        Err(e) => serde_json::json!({"success": false, "patched": true, "error": e}),
    }
}

/// 检查 util 补丁：Some(true/false) 表示文件存在且已/未打；None 表示文件不存在（旧版本无需）。
fn do_check_util_singleton_patched(cursor_install_path: &Path) -> Option<bool> {
    let path = get_util_singleton_js_path(cursor_install_path);
    if !path.exists() {
        return None;
    }
    fs::read_to_string(&path).ok().map(|c| c.contains(UTIL_PATCH_START))
}

// ========== 组合：ExtHost + util 两个文件一起处理（版本无关） ==========

/// 同时给 ExtHost 与 util 单例进程打补丁。
/// 老版本只有 ExtHost、新版本（3.9+）两者都有 —— 都打，做到版本无关。
fn do_patch_both(cursor_install_path: &Path) -> serde_json::Value {
    let eh = do_patch_ext_host(cursor_install_path);
    let util = do_patch_util_singleton(cursor_install_path);
    let eh_ok = eh.get("success").and_then(|v| v.as_bool()).unwrap_or(false);
    let util_ok = util.get("success").and_then(|v| v.as_bool()).unwrap_or(false);
    let ok = eh_ok && util_ok;
    let mut errs: Vec<String> = Vec::new();
    if !eh_ok {
        errs.push(format!("ExtHost: {}", eh.get("error").and_then(|v| v.as_str()).unwrap_or("未知错误")));
    }
    if !util_ok {
        errs.push(format!("Util: {}", util.get("error").and_then(|v| v.as_str()).unwrap_or("未知错误")));
    }
    let mut out = serde_json::json!({
        "success": ok,
        "patched": ok,
        "exthost": eh,
        "util": util,
        "message": if ok { "补丁注入成功" } else { "部分补丁失败" }
    });
    if !ok {
        out["error"] = serde_json::Value::String(errs.join("; "));
    }
    out
}

/// 同时移除两个补丁（前端按 ExtHost 结果显示）。
fn do_unpatch_both(cursor_install_path: &Path) -> serde_json::Value {
    let eh = do_unpatch_ext_host(cursor_install_path);
    let _ = do_unpatch_util_singleton(cursor_install_path);
    eh
}

/// 两个目标都满足才算已打补丁：ExtHost 必须已打；util 文件存在则也必须已打（不存在则忽略）。
fn do_check_both_patched(cursor_install_path: &Path) -> bool {
    let eh_ok = do_check_ext_host_patched(cursor_install_path);
    let util_ok = match do_check_util_singleton_patched(cursor_install_path) {
        Some(p) => p,
        None => true,
    };
    eh_ok && util_ok
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

/// 把版本号字符串解析成 (major, minor)，例如 "3.5.1" → (3, 5)、"3.6" → (3, 6)。
/// 解析失败返回 None。允许前缀 'v'，忽略 minor 之后的补丁号。
fn parse_major_minor(ver: &str) -> Option<(u32, u32)> {
    let mut it = ver.trim().trim_start_matches(['v', 'V']).split('.');
    let major = it.next()?.trim().parse::<u32>().ok()?;
    let minor = it.next().unwrap_or("0").trim().parse::<u32>().ok()?;
    Some((major, minor))
}

/// 读取「续杯工具检测到的」Cursor 版本号（来自 package.json），解析成 (major, minor)。
/// 读不到 / 解析失败返回 None。
fn get_cursor_major_minor() -> Option<(u32, u32)> {
    let paths = cursor_paths::get_cursor_paths();
    parse_major_minor(paths.version.as_deref()?)
}

/// 该版本是否走「旧版额度判定」（Cursor <= 3.5，含 3.5）。
/// 旧版没有新版的 auto 模型额度拆分口径，用「总额度用量 > 90%」这一条阈值最稳。
/// 检测不到版本时返回 false —— 回退到新版逻辑（保守，不改变既有行为）。
fn is_legacy_quota_version(mm: Option<(u32, u32)>) -> bool {
    match mm {
        Some((major, minor)) => major < 3 || (major == 3 && minor <= 5),
        None => false,
    }
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
                let auto_percent_used = plan
                    .get("autoPercentUsed")
                    .and_then(|v| v.as_f64())
                    .unwrap_or(0.0);
                total_quota = plan
                    .get("breakdown")
                    .and_then(|b| b.get("total"))
                    .and_then(|v| v.as_f64())
                    .unwrap_or(0.0);

                // 依据「续杯工具检测到的 Cursor 版本号」选择额度判定逻辑：
                //   - Cursor <= 3.5：只看总额度用量，> 90% 即换号（旧版无新版 auto 拆分口径，
                //     沿用总容量阈值最稳，检测口径同「cursor账号服用检测.py」的 totalPercentUsed）
                //   - Cursor >= 3.6（含检测不到版本时回退）：维持原判定逻辑
                if is_legacy_quota_version(get_cursor_major_minor()) {
                    if percent_used > 90.0 {
                        needs_switch = true;
                        reason = "quota_exhausted_percent".to_string();
                    }
                }
                // 判定 1：总用量阈值
                else if percent_used >= 95.0 {
                    needs_switch = true;
                    reason = "quota_exhausted_percent".to_string();
                }
                // 判定 2：Auto 模型耗尽（free 账号典型特征 ——
                // totalPercentUsed 因 breakdown 口径低于 95 不命中，但 auto 池子已经满）
                // 对齐老 Electron 版 checkAccountStatus 第二条判据
                else if auto_percent_used >= 100.0 && total_quota > 0.0 {
                    needs_switch = true;
                    reason = "auto_model_exhausted".to_string();
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
    // === 模型解锁：改写渲染进程 workbench JS（storeMembershipType 强制 pro）===
    // v2 方案：不再用 MITM 代理 + http.proxy（会拖垮 3.11+ 的 AI 流量），
    // 改为直接注入渲染进程 JS。是幂等的，重复激活开销很小。
    let unlock_result = tokio::task::spawn_blocking(|| {
        // 先清理旧 MITM 方案的遗留（老用户升级）：删 settings.json 的 http.proxy、
        // 清 NODE_EXTRA_CA_CERTS、删系统信任根里的 CA。彻底摆脱代理导致的 AI 报错。
        unlock_mitm::cleanup_legacy_mitm();
        // 再注入 workbench 解锁补丁
        unlock_workbench::enable_unlock()
    }).await;
    let unlock_err = match unlock_result {
        Ok(Ok(())) => None,
        Ok(Err(e)) => Some(e),
        Err(e) => Some(format!("解锁任务调度失败: {}", e)),
    };
    if let Some(e) = unlock_err {
        return serde_json::json!({
            "success": false, "patched": false,
            "error": format!("激活无感换号失败: {}", e)
        });
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
    let result = do_patch_both(&install_path);

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
    let unpatch_result = do_unpatch_both(&install_path);

    // 清掉 machine ID 覆盖映射 —— 补丁已经移除，文件不再有意义
    machine_id::clear_machine_id_override();

    // === 模型解锁后置步骤：还原 workbench JS + 清理旧 MITM 遗留 ===
    // 用户关闭「激活无感换号」时彻底回退：还原渲染进程文件；
    // 同时清掉老版本可能残留的 proxy / CA（幂等，无残留则 no-op）。
    let _ = tokio::task::spawn_blocking(|| {
        let _ = unlock_workbench::disable_unlock();
        unlock_mitm::cleanup_legacy_mitm();
    }).await;

    unpatch_result
}

#[tauri::command]
pub async fn check_ext_host_patched(app: AppHandle) -> bool {
    let paths = cursor_paths::get_cursor_paths();
    if let Some(ref bp) = paths.base_path {
        if paths.error.is_none() {
            let install_path = cursor_paths::get_cursor_install_from_base_path(bp);
            let patched = do_check_both_patched(&install_path);
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
            do_check_both_patched(&install_path)
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

    let patched = do_check_both_patched(&install_path);

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
                do_unpatch_both(&install_path);
                do_patch_both(&install_path);
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
