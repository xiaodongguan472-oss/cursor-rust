"""Cursor JS 注入器 — 修改 workbench.desktop.main.js 实现无感换号"""
from __future__ import annotations

import json
import os
import re
import sys
import shutil
import platform
import subprocess
import tempfile

_WORKBENCH_REL = os.path.join(
    "app", "out", "vs", "workbench", "workbench.desktop.main.js",
)

_EXTHOST_REL = os.path.join(
    "app", "out", "vs", "workbench", "api", "node", "extensionHostProcess.js",
)

# JS 变量名模式（minified identifier）
_V = r'[a-zA-Z_$][a-zA-Z0-9_$]*'

# ── CursorPro Minimal Patch（让 Claude 模型走 anthropicBaseUrl）──
# Cursor 内置两个 API Base URL：openAIBaseUrl 和 anthropicBaseUrl。
# 默认所有请求走 openAIBaseUrl，此补丁让 Claude 模型走 anthropicBaseUrl。
# 两个 URL 都指向同一个中转站时，这保证了请求格式正确。

_ANTHROPIC_PATCH_OLD = (
    'openaiApiBaseUrl:this._reactiveStorageService'
    '.applicationUserPersistentStorage.openAIBaseUrl??void 0,'
    'bedrockState:o,maxMode:t})'
)

_ANTHROPIC_PATCH_NEW = (
    "openaiApiBaseUrl:(a&&(a.startsWith('claude-')||a.includes('claude')))"
    '?(this._reactiveStorageService.applicationUserPersistentStorage.anthropicBaseUrl'
    '||(this._reactiveStorageService.applicationUserPersistentStorage.openAIBaseUrl??void 0))'
    ':(this._reactiveStorageService.applicationUserPersistentStorage.openAIBaseUrl??void 0),'
    'bedrockState:o,maxMode:t})/*wxAnthropicPatch*/'
)

# ── 正则补丁（完整性绕过）─────────────────────────────────────
_REGEX_PATCHES = [
    {
        "id": "ispure",
        "pattern": r'return\{isPure:(' + _V + r'),proof:(' + _V + r')\}',
        "replace": r'return{isPure:true/*wxPure*/,proof:\2}',
    },
    {
        "id": "tab_allowed",
        "pattern": r'isAllowedCpp\(\)\{',
        "replace": 'isAllowedCpp(){return true;/*wxTab*/',
    },
    {
        "id": "ext_verify",
        "pattern": (
            r'if\(!(' + _V + r')\.valid\)throw this\._logService\.error\([^)]+\),'
            r'this\._logService\.flush\(\),new Error\([^)]+\)'
        ),
        "replace": (
            r'if(!\1.valid){this._logService.warn('
            r'"Extension verification bypassed");/*wxExtV*/}'
        ),
    },
]

# 注入标记（用于检测是否已注入）
_RELAY_MARKERS = [b"/*wxPure*/", b"/*wxTab*/", b"/*wxAnthropicPatch*/"]


def _apply_regex_patches(content: str) -> tuple[str, list[str]]:
    """对 JS 内容应用所有正则补丁。返回 (修改后内容, 结果列表)。"""
    results: list[str] = []
    for patch in _REGEX_PATCHES:
        new_content, count = re.subn(patch["pattern"], patch["replace"], content, count=1)
        if count > 0:
            content = new_content
            results.append(patch["id"] + ":ok")
        else:
            results.append(patch["id"] + ":miss")
    return content, results


def _cursor_install_root() -> str | None:
    """定位 Cursor 的 resources 目录（包含 workbench JS 的那一层）

    严格模式：只信标准官方安装路径，不再扫 ~/Downloads / ~/Desktop / 全盘，
    也不再缓存上一次的检测结果。统一委托给 `core.cursor_process`，避免两套
    检测逻辑得出不一致的结果。
    """
    from core.cursor_process import _cursor_install_root as _detect
    return _detect()


def _find_workbench_js() -> str | None:
    """定位 workbench.desktop.main.js 的完整路径"""
    res_root = _cursor_install_root()
    if not res_root:
        return None
    candidate = os.path.join(res_root, _WORKBENCH_REL)
    if os.path.isfile(candidate):
        return candidate
    return None


def _find_exthost_js() -> str | None:
    """定位 extensionHostProcess.js 的完整路径"""
    res_root = _cursor_install_root()
    if not res_root:
        return None
    candidate = os.path.join(res_root, _EXTHOST_REL)
    if os.path.isfile(candidate):
        return candidate
    return None


_INJECT0_MARKER = "/*i0*/"

_INJECT0_SEARCH = "_showNotification(){"
_INJECT0_REPLACE = "_showNotification(){return;/*i0*/"


# ── 文本补丁（软匹配，未命中只告警，不中断注入）────────────────────
# 这套补丁是 cursor-free-vip / bypass_token_limit 那一脉的市面标准做法，
# 纯字符串替换。Cursor 更新后某条可能失配，整体流程仍可继续。
_TEXT_PATCHES = [
    # 1. Pro Trial 徽章 → Pro（Cursor 3.0.16 仍存在多处）
    {
        "id": "pro_trial_badge",
        "search": "<div>Pro Trial",
        "replace": "<div>Pro",
    },
    # 2. 另一个常见变体
    {
        "id": "pro_trial_span",
        "search": "<span>Pro Trial",
        "replace": "<span>Pro",
    },
    # 3. 隐藏 Upgrade toast 通知
    {
        "id": "hide_upgrade_toasts",
        "search": 'class="notifications-toasts',
        "replace": 'class="notifications-toasts hidden',
    },
    # 4. 抹掉 "Premium models are only available on paid plans."
    {
        "id": "premium_paid_plans",
        "search": '"Premium models are only available on paid plans."',
        "replace": '""',
    },
    # 5. 抹掉 "Premium models are only available on paid plans" 变体（无句号）
    {
        "id": "premium_paid_plans_v2",
        "search": '"Premium models are only available on paid plans"',
        "replace": '""',
    },
]


# 注入点1：暴露 window.store + 通知系统
_INJECT1_SEARCH = "this.database.getItems()))"
_INJECT1_CODE = (
    '/*i1s*/;(function(e){try{'
    # 鸭子类型：只要是带 get/set 的 StorageService 就绑上 window.store。
    # 原先用 e.get("releaseNotes/lastVersion") 做守卫，对从未打开过 release notes
    # 的新用户不成立，会导致 window.store 永远 undefined → 整条无感换号链路失效。
    'if(!window.store&&e&&typeof e.get===\'function\'&&typeof e.set===\'function\')'
    '{window.store=e;if(!window.$csSuccess){(function(){'
    'let c=null,i=0;'
    'function initC(){'
    'if(!c){c=document.createElement(\'div\');c.id=\'cs-notifications\';'
    'c.style.cssText=\'position:fixed;top:20px;right:20px;z-index:999999;'
    'display:flex;flex-direction:column;gap:8px;max-width:400px\';'
    'document.body.appendChild(c);'
    'if(!document.getElementById(\'cs-notification-styles\')){'
    'const s=document.createElement(\'style\');s.id=\'cs-notification-styles\';'
    's.textContent=\'@keyframes csSlideInRight{from{transform:translateX(450px);'
    'opacity:0}to{transform:translateX(0);opacity:1}}'
    '@keyframes csSlideOutRight{from{transform:translateX(0);opacity:1}'
    'to{transform:translateX(450px);opacity:0}}'
    '@keyframes csProgressIndeterminate{0%{transform:translateX(-100%)}'
    '100%{transform:translateX(400%)}}\';document.head.appendChild(s);}}return c}'
    'function createNotification(msg,type,opts){'
    'opts=opts||{};const container=initC();const id=++i;'
    'const n=document.createElement(\'div\');n.dataset.id=id;'
    'const styles={success:{color:\'#4ec9b0\',icon:\'\\u2713\',borderColor:\'#4ec9b0\'},'
    'error:{color:\'#f48771\',icon:\'\\u2715\',borderColor:\'#f48771\'},'
    'warning:{color:\'#cca700\',icon:\'\\u26A0\',borderColor:\'#cca700\'},'
    'info:{color:\'#3794ff\',icon:\'\\u2139\',borderColor:\'#3794ff\'}};'
    'const st=styles[type]||styles.info;'
    'n.style.cssText=`background:#252526;border-left:3px solid ${st.borderColor};'
    'padding:12px 16px;border-radius:4px;box-shadow:0 2px 8px rgba(0,0,0,.25);'
    'display:flex;align-items:flex-start;gap:12px;'
    'animation:csSlideInRight .3s ease-out;min-width:350px`;'
    'const iconEl=document.createElement(\'div\');'
    'iconEl.style.cssText=`width:20px;height:20px;border-radius:50%;'
    'background:${st.color};color:#252526;display:flex;align-items:center;'
    'justify-content:center;font-size:12px;font-weight:bold;flex-shrink:0;'
    'margin-top:2px`;iconEl.textContent=st.icon;'
    'const content=document.createElement(\'div\');'
    'content.style.cssText=\'flex:1;display:flex;flex-direction:column;gap:8px\';'
    'const messageEl=document.createElement(\'div\');'
    'messageEl.style.cssText=\'color:#cccccc;font-size:13px;line-height:1.4;'
    'font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif\';'
    'messageEl.textContent=msg;content.appendChild(messageEl);'
    'if(opts.loading){const progressBar=document.createElement(\'div\');'
    'progressBar.style.cssText=\'width:100%;height:2px;background:rgba(255,255,255,.1);'
    'border-radius:1px;overflow:hidden;margin-top:4px\';'
    'const progressFill=document.createElement(\'div\');'
    'progressFill.style.cssText=`height:100%;background:${st.color};width:100%;'
    'animation:csProgressIndeterminate 1.5s ease-in-out infinite`;'
    'progressBar.appendChild(progressFill);content.appendChild(progressBar)}'
    'const closeBtn=document.createElement(\'button\');closeBtn.textContent=\'\\u2715\';'
    'closeBtn.style.cssText=\'background:transparent;border:none;color:#ccc;'
    'font-size:16px;cursor:pointer;padding:4px;width:24px;height:24px;'
    'display:flex;align-items:center;justify-content:center;border-radius:4px\';'
    'closeBtn.onclick=()=>removeNotification(id);'
    'n.appendChild(iconEl);n.appendChild(content);n.appendChild(closeBtn);'
    'container.appendChild(n);'
    'if(!opts.loading){setTimeout(()=>removeNotification(id),opts.duration||5000)}'
    'return id}'
    'function removeNotification(id){'
    'if(!c)return;const n=c.querySelector(`[data-id="${id}"]`);'
    'if(n){n.style.animation=\'csSlideOutRight .3s ease-in\';'
    'setTimeout(()=>{if(n.parentNode){n.parentNode.removeChild(n)}'
    'if(c.children.length===0&&c.parentNode){c.parentNode.removeChild(c);c=null}},300)}}'
    'window.$csSuccess=(msg,opts)=>createNotification(msg,\'success\',opts);'
    'window.$csError=(msg,opts)=>createNotification(msg,\'error\',opts);'
    'window.$csWarning=(msg,opts)=>createNotification(msg,\'warning\',opts);'
    'window.$csInfo=(msg,opts)=>createNotification(msg,\'info\',opts);'
    'window.$csLoading=(msg)=>createNotification(msg,\'info\',{loading:true});'
    'window.$csHideLoading=(id)=>removeNotification(id);'
    '})()}console.log(\'[CursorSeamless] init done, store bound\');}}'
    'catch(_e){console.warn(\'[CursorSeamless] i1 error:\',_e);}})(this);/*i1e*/'
)

# 注入点2：Token 轮询 + fetch 拦截自动换号
_INJECT2_CODE = (
    '/*i2s*/'
    'try{'

    # ── Token 轮询：每秒检查本地服务，拾取新 token；未登录/退出登录时自动获取 ──
    'var _lastAppliedToken=(window.store&&window.store.get("cursorAuth/accessToken",-1))||"";'
    'var _lastNotifiedEmail="";'

    # 全局换号锁 + 频率控制
    'var _gSwitching=false,_gLastSuccess=0,_gConsecFail=0;'
    'var _gBaseCooldown=30000,_gMaxCooldown=300000;'
    'var _origFetch=window.fetch;'
    'function _switchCooldown(){'
    'if(_gConsecFail<=0)return _gBaseCooldown;'
    'return Math.min(_gBaseCooldown*Math.pow(2,_gConsecFail),_gMaxCooldown);}'
    'function _doSwitch(reason){'
    'if(_gSwitching)return;'
    'var now=Date.now();'
    'if(now-_gLastSuccess<_switchCooldown())return;'
    '_gSwitching=true;'
    'console.log(\'[CursorSeamless] \'+reason+\', auto-switching... (fails:\'+_gConsecFail+\')\');'
    'var _lid;if(window.$csLoading){_lid=window.$csLoading(\'正在自动切换账号...\');}'
    '_origFetch(\'http://127.0.0.1:14520/api/auto-switch\','
    '{method:\'POST\',headers:{\'Content-Type\':\'application/json\'},'
    'signal:AbortSignal.timeout(15000)}'
    ').then(function(r){return r.json()}).then(function(d){'
    'if(window.$csHideLoading&&_lid){window.$csHideLoading(_lid);}'
    'if(d.success){_gLastSuccess=Date.now();_gConsecFail=0;}'
    'else if(d.expired){'
    'if(window.$csError){window.$csError(d.message||\"激活码已到期，请联系客服续费\",{duration:15000});}'
    '_gLastSuccess=Date.now()+120000;_gConsecFail=0;'
    '}else{_gConsecFail++;_gLastSuccess=Date.now();}'
    '_gSwitching=false;'
    '}).catch(function(e){'
    'if(window.$csHideLoading&&_lid){window.$csHideLoading(_lid);}'
    '_gConsecFail++;_gLastSuccess=Date.now();'
    'if(window.$csError&&e.name!=="AbortError"){'
    'window.$csError("自动换号失败，请确保助手在后台运行",{duration:8000});}'
    '_gSwitching=false;'
    '});}'

    # 未登录检测（非阻塞，5 秒重试）
    'var _lastNoLoginCheck=0;'
    'function _checkNoLogin(){'
    'if(!window.store||_gSwitching)return;'
    'var t=window.store.get(\'cursorAuth/accessToken\',-1);'
    'if(t&&t!==\'\'&&t!==\'undefined\')return;'
    'var now=Date.now();'
    'if(now-_lastNoLoginCheck<5000)return;'
    '_lastNoLoginCheck=now;'
    '_lastAppliedToken="";_lastNotifiedEmail="";'
    '_doSwitch(\'No login detected\');'
    '}'

    # 主轮询：拾取新 token + 检查未登录
    'setInterval(async()=>{'
    'try{'
    'if(!window.store)return;'
    '_checkNoLogin();'

    'var resp=await _origFetch(\'http://127.0.0.1:14520/api/get-token\','
    '{signal:AbortSignal.timeout(3000)});'
    'if(resp.ok){'
    'var data=await resp.json();'
    'if(!data.config||!data.config.enabled){return;}'
    'if(!data.accessToken||data.accessToken===_lastAppliedToken){return;}'
    '_lastAppliedToken=data.accessToken;'
    'window.store.set(\'cursorAuth/accessToken\',data.accessToken,-1);'
    'if(data.refreshToken){'
    'window.store.set(\'cursorAuth/refreshToken\',data.refreshToken,-1);}'
    'if(data.email){'
    'window.store.set(\'cursorAuth/cachedEmail\',data.email,-1);}'
    'window.store.set(\'cursorAuth/stripeMembershipType\',\'pro\',-1);'
    'window.store.set(\'cursorAuth/stripeSubscriptionStatus\',\'active\',-1);'
    'if(data.is_new&&data.machineIds){'
    'window.store.set(\'telemetry.devDeviceId\',data.machineIds.devDeviceId,-1);'
    'window.store.set(\'telemetry.machineId\',data.machineIds.machineId,-1);'
    'window.store.set(\'telemetry.macMachineId\',data.machineIds.macMachineId,-1);'
    'window.store.set(\'telemetry.sqmId\',data.machineIds.sqmId,-1);'
    '_origFetch(\"http://127.0.0.1:14520/api/ack-new\",{method:\"POST\"}).catch(function(){});}'
    'if(data.email&&data.email!==_lastNotifiedEmail){'
    '_lastNotifiedEmail=data.email;'
    'if(window.$csSuccess){window.$csSuccess(\'账号已切换: \'+data.email);}}'
    'console.log(\'[CursorSeamless] Token applied:\',data.email);'
    '}}'
    'catch(e){if(e.name!==\'AbortError\'&&e.name!==\'TypeError\'){'
    'console.warn(\'[CursorSeamless] Poll error:\',e);}}'
    '},1000);'

    # fetch 拦截：HTTP 状态码
    'window.fetch=async function(){'
    'var resp=await _origFetch.apply(this,arguments);'
    'try{'
    'var _a0=arguments[0];'
    'var url=typeof _a0===\'string\'?_a0:'
    '(_a0&&typeof _a0.url===\'string\'?_a0.url:'
    '(_a0&&_a0.toString?_a0.toString():\'\'));'
    'if(url.includes(\'cursor.sh\')||url.includes(\'cursor.com\')'
    '||url.includes(\'cursor.so\')){'
    'if(resp.status===401||resp.status===403||resp.status===429){'
    '_doSwitch(\'HTTP \'+resp.status);}'
    '}}catch(_fe){}'
    'return resp;};'

    # DOM 监听：只匹配明确的限额通知弹窗，触发后暂停 60 秒
    'var _domPaused=false;'
    'var _DOM_KW=/you.{0,5}(have|ve).{0,5}(hit|reached).{0,10}(usage|limit)'
    '|too many free.{0,5}trial|free trial.{0,10}(ended|expired|over)/i;'
    'var _obs=new MutationObserver(function(muts){'
    'if(_domPaused||_gSwitching)return;'
    'for(var i=0;i<muts.length;i++){'
    'var added=muts[i].addedNodes;'
    'for(var j=0;j<added.length;j++){'
    'var n=added[j];'
    'if(n.nodeType!==1)continue;'
    'if(n.closest&&n.closest(\"#cs-notifications\"))continue;'
    'var txt=n.textContent||\"\";'
    'if(txt.length>10&&txt.length<500&&_DOM_KW.test(txt)){'
    'console.log(\"[CursorSeamless] DOM limit:\",txt.substring(0,80));'
    '_domPaused=true;'
    '_doSwitch(\"DOM limit\");'
    'setTimeout(function(){_domPaused=false;},60000);'
    'return;}'
    '}}'
    '});'
    'setTimeout(function(){'
    '_obs.observe(document.body,{childList:true,subtree:true});'
    'console.log(\"[CursorSeamless] Ready\");'
    '},3000);'

    '}catch(_csErr){console.error(\"[CursorSeamless] Init error:\",_csErr);}'

    '/*i2e*/'
)


# 注入点 3：Pro 会员状态运行时强化（市面"方案 A"核心）
#   a) 每秒把 stripeMembershipType=pro / subscriptionStatus=active 写回 store
#   b) DOM MutationObserver 把 "Pro Trial" / "Free Plan" 等文案实时改成 "Pro"
#   c) CSS 隐藏所有 Upgrade 按钮/横幅
#   d) window.fetch 对已知会员相关 JSON 端点做 200/pro 响应兜底
_INJECT3_CODE = (
    '/*i3s*/'

    # ── (a) 周期强化 pro 会员状态 (每 1s) ──
    'setInterval(function(){'
    'try{'
    'if(window.store){'
    'window.store.set(\'cursorAuth/stripeMembershipType\',\'pro\',-1);'
    'window.store.set(\'cursorAuth/stripeSubscriptionStatus\',\'active\',-1);'
    '}'
    '}catch(_){}'
    '},1000);'

    # ── (b) DOM 文本替换（文本补丁失配时的兜底）──
    'function _wxReplaceIn(root){'
    'if(!root||root.nodeType!==1&&root.nodeType!==3)return;'
    'try{'
    'if(root.closest&&root.closest(\'#cs-notifications\'))return;'
    'var walker=document.createTreeWalker(root,NodeFilter.SHOW_TEXT,null);'
    'var n;while(n=walker.nextNode()){'
    'var t=n.nodeValue;if(!t||t.length>200)continue;'
    'var p=n.parentNode;'
    'if(p&&(p.tagName===\'INPUT\'||p.tagName===\'TEXTAREA\''
    '||p.tagName===\'CODE\'||p.tagName===\'PRE\'||p.tagName===\'SCRIPT\''
    '||p.tagName===\'STYLE\'))continue;'
    'var nt=t;'
    'nt=nt.replace(/Pro Trial/g,\'Pro\');'
    'nt=nt.replace(/\\bFree Plan\\b/g,\'Pro Plan\');'
    'nt=nt.replace(/\\bHobby\\b/g,\'Pro\');'
    'nt=nt.replace(/Upgrade to Pro/g,\'\\u2713 Pro\');'
    'if(nt!==t)n.nodeValue=nt;'
    '}'
    '}catch(_){}'
    '}'
    'var _wxObs=new MutationObserver(function(muts){'
    'for(var i=0;i<muts.length;i++){'
    'var m=muts[i];'
    'if(m.type===\'characterData\'){_wxReplaceIn(m.target);continue;}'
    'for(var j=0;j<m.addedNodes.length;j++){_wxReplaceIn(m.addedNodes[j]);}'
    '}'
    '});'
    'setTimeout(function(){try{'
    '_wxReplaceIn(document.body);'
    '_wxObs.observe(document.body,{childList:true,subtree:true,characterData:true});'
    '}catch(_){}},1500);'

    # ── (c) CSS 隐藏 Upgrade 按钮与 Free-tier 横幅 ──
    'setTimeout(function(){try{'
    'var s=document.createElement(\'style\');s.id=\'wx-pro-css\';'
    's.textContent=\''
    '[aria-label*="Upgrade"i],[title*="Upgrade"i],'
    'a[href*="upgrade"i],button[data-testid*="upgrade"i]{display:none!important;}'
    '.cursor-free-tier-notice,.cursor-upgrade-banner,'
    '.cursor-trial-banner,.pro-trial-banner{display:none!important;}'
    '\';document.head.appendChild(s);'
    '}catch(_){}},2000);'

    # ── (d) fetch 兜底：会员相关 JSON 端点 401/403/404 时返回 pro ──
    'var _wxProEndpoints=['
    '\'/api/auth/me\','
    '\'/api/stripe/profile\','
    '\'/api/usage\','
    '\'/api/full_stripe_profile\','
    '\'/api/auth/stripe\''
    '];'
    'var _wxProJson={membershipType:\'pro\',subscriptionStatus:\'active\','
    'isOnFreeTrial:false,trialEligible:false,daysRemainingOnTrial:0,'
    'verified:true,email:(window.store&&window.store.get(\'cursorAuth/cachedEmail\',-1))||\'\'};'
    '(function(){'
    'if(!window.fetch||window.__wx_pro_fetch)return;window.__wx_pro_fetch=true;'
    'var _innerFetch=window.fetch;'
    'window.fetch=async function(){'
    'var a0=arguments[0];'
    'var url=typeof a0===\'string\'?a0:(a0&&typeof a0.url===\'string\'?a0.url:\'\');'
    'var hit=false;'
    'if(url){for(var i=0;i<_wxProEndpoints.length;i++){'
    'if(url.indexOf(_wxProEndpoints[i])>=0){hit=true;break;}}}'
    'var resp;try{resp=await _innerFetch.apply(this,arguments);}'
    'catch(e){'
    'if(hit){return new Response(JSON.stringify(_wxProJson),'
    '{status:200,headers:{\'content-type\':\'application/json\'}});}'
    'throw e;}'
    'try{if(hit&&resp&&(resp.status===401||resp.status===403||resp.status===404)){'
    'return new Response(JSON.stringify(_wxProJson),'
    '{status:200,headers:{\'content-type\':\'application/json\'}});}'
    '}catch(_){}'
    'return resp;};'
    '})();'

    # ── (e) 弹窗猎杀：匹配 Named-models / Free-plan 拦截对话框并立即删除 ──
    'var _wxKillPatterns=['
    '/Named models unavailable/i,'
    '/Free plans?.{0,30}only use Auto/i,'
    '/upgrade plans to continue/i,'
    '/This model requires.{0,20}Pro/i,'
    '/This model is only available.{0,30}Pro/i,'
    '/Upgrade to unlock premium/i,'
    '/Premium models are only available/i'
    '];'
    'function _wxShouldKill(txt){'
    'if(!txt||txt.length<8||txt.length>600)return false;'
    'for(var k=0;k<_wxKillPatterns.length;k++){'
    'if(_wxKillPatterns[k].test(txt))return true;}'
    'return false;'
    '}'
    'function _wxKillNode(n){'
    'try{'
    'if(!n||n.nodeType!==1)return false;'
    'if(n.closest&&n.closest(\'#cs-notifications\'))return false;'
    'var txt=n.textContent||\'\';'
    'if(!_wxShouldKill(txt))return false;'
    'var host=n.closest?'
    '(n.closest(\'.notification-toast\')'
    '||n.closest(\'.notifications-toasts\')'
    '||n.closest(\'[class*="notification"]\')'
    '||n.closest(\'[class*="toast"]\')'
    '||n.closest(\'[role="dialog"]\')'
    '||n.closest(\'[class*="dialog"]\')'
    '||n.closest(\'[class*="modal"]\'))'
    ':null;'
    '(host||n).remove();'
    'console.log(\'[wx i3] killed blocker:\',txt.substring(0,80));'
    'return true;'
    '}catch(_){return false;}'
    '}'
    'var _wxKillObs=new MutationObserver(function(muts){'
    'for(var i=0;i<muts.length;i++){'
    'var added=muts[i].addedNodes;'
    'for(var j=0;j<added.length;j++){'
    'var n=added[j];'
    'if(n.nodeType!==1)continue;'
    'if(_wxKillNode(n))continue;'
    'try{var sub=n.querySelectorAll?n.querySelectorAll(\'*\'):[];'
    'for(var k=0;k<sub.length;k++){if(_wxKillNode(sub[k]))break;}'
    '}catch(_){}'
    '}}'
    '});'
    'setTimeout(function(){try{'
    # 启动时扫一遍
    'document.querySelectorAll(\'*\').forEach(_wxKillNode);'
    '_wxKillObs.observe(document.body,{childList:true,subtree:true});'
    '}catch(_){}},1500);'

    # ── (f) 拦截 "Switch to Auto" 按钮点击，防止模型被回滚 ──
    'document.addEventListener(\'click\',function(ev){'
    'try{'
    'var t=ev.target;if(!t||!t.closest)return;'
    'var btn=t.closest(\'button,a,[role="button"]\');if(!btn)return;'
    'var txt=(btn.textContent||\'\').trim();'
    'if(/^Switch to Auto$/i.test(txt)||/^Upgrade plans?$/i.test(txt)){'
    'ev.preventDefault();ev.stopPropagation();ev.stopImmediatePropagation();'
    'var host=btn.closest(\'[role="dialog"]\')||btn.closest(\'[class*="notification"]\')'
    '||btn.closest(\'[class*="toast"]\')||btn.closest(\'[class*="dialog"]\')'
    '||btn.closest(\'[class*="modal"]\');'
    'if(host)host.remove();'
    'console.log(\'[wx i3] swallowed click:\',txt);'
    '}'
    '}catch(_){}}'
    ',true);'

    'console.log(\'[wx i3] pro-state reinforcement installed\');'

    '/*i3e*/'
)


def _needs_privilege(path: str) -> bool:
    """检测文件或其所在目录是否需要提权才能写入"""
    parent = os.path.dirname(path)
    if os.access(parent, os.W_OK) and (not os.path.exists(path) or os.access(path, os.W_OK)):
        return False
    return True


def _ensure_writable(path: str) -> tuple[bool, str]:
    """Linux 下若权限不足则通过 pkexec/sudo 提权。macOS 不走此函数。
    返回 (success, error_message)。
    """
    parent = os.path.dirname(path)
    if os.access(parent, os.W_OK) and (not os.path.exists(path) or os.access(path, os.W_OK)):
        return True, ""

    system = platform.system()

    if system == "Linux":
        uid = os.getuid()
        gid = os.getgid()
        esc_parent = parent.replace("'", "'\\''")
        cmd = f"chown -R {uid}:{gid} '{esc_parent}'"
        for elevator in ["pkexec", "sudo"]:
            if shutil.which(elevator):
                try:
                    subprocess.run(
                        [elevator, "sh", "-c", cmd],
                        check=True, capture_output=True, timeout=60,
                    )
                    return True, ""
                except subprocess.TimeoutExpired:
                    return False, "授权超时，请重试"
                except subprocess.CalledProcessError:
                    continue
                except Exception as e:
                    return False, f"权限处理异常: {e}"
        return False, "文件无写入权限，请用 sudo 运行本程序"

    elif system == "Darwin":
        return True, ""

    return False, "文件无写入权限，请以管理员身份运行本程序"


def _mac_bak_path(js_path: str) -> str:
    """macOS 备份路径：存到 ~/.wuxian-assistant/ 避免 App Management 限制"""
    bak_dir = os.path.join(os.path.expanduser("~"), ".wuxian-assistant")
    os.makedirs(bak_dir, exist_ok=True)
    return os.path.join(bak_dir, "workbench.desktop.main.js.bak")


def _mac_find_app_root(path: str) -> str:
    """从文件路径向上找到 .app 目录"""
    p = path
    while p and p != "/":
        if p.endswith(".app"):
            return p
        p = os.path.dirname(p)
    return ""


def _mac_replace_file_in_app(src_file: str, target_path: str):
    """macOS: 将 src_file 原子替换到 target_path（必须在某个 .app Bundle 内）。

    采用「整包副本 → 在副本里改 → 由内向外 ad-hoc 重签 → 原子替换」的策略，
    绕过 macOS Sonoma/Sequoia 的 App Management TCC 拦截（即便 osascript 提权到
    root，对 /Applications 内已识别 .app 的原地写仍会 EPERM）。

    调用方需要保证 src_file 已经写好；本函数会通过 osascript 提权执行。
    任何一步失败都会立即中断（&& 串联），失败时原 .app 保持不变，残留的
    .wxtmp 目录会在下次调用时被清理。
    """
    app_root = _mac_find_app_root(target_path)
    if not app_root:
        raise RuntimeError(f"未定位到 .app 根目录: {target_path}")

    rel = os.path.relpath(target_path, app_root)
    tmp_app = app_root + ".wxtmp"

    def esc(s: str) -> str:
        return s.replace("'", "'\\''")

    e_app = esc(app_root)
    e_tmp = esc(tmp_app)
    e_src = esc(src_file)
    e_rel = esc(rel)
    e_fw = esc(os.path.join(tmp_app, "Contents", "Frameworks"))

    parts = [
        # 1) 清掉可能残留的旧副本
        f"rm -rf '{e_tmp}'",
        # 2) 整包复制（APFS 下 cp -a 走 clonefile，秒级完成，占用极小）。
        #    这步把改动目标从"已识别 App"转到"新目录"，绕开 App Management。
        f"cp -a '{e_app}' '{e_tmp}'",
        # 3) 副本解锁：清 unchg flag、chmod +w、清扩展属性与隔离
        f"chflags -R nouchg '{e_tmp}'",
        f"chmod -R u+w '{e_tmp}'",
        f"xattr -cr '{e_tmp}'",
        # 4) 把注入后的文件写入副本内的目标相对路径
        f"cp -f '{e_src}' '{e_tmp}/{e_rel}'",
        # 5) 移除旧签名（若 bundle 未签名会非零，用子 shell 包起来容错；
        #    直接写 "A || true" 会被外层 && 左结合串错，导致前面任一步失败被吞）
        f"(codesign --remove-signature '{e_tmp}' || true)",
        # 6) Apple Silicon 关键：由内向外签所有嵌套 Helper Bundle。
        #    --deep 在 macOS 15 上对嵌套 .app 不可靠，必须显式逐个签。
        (
            f"if [ -d '{e_fw}' ]; then "
            f"find '{e_fw}' -name '*.app' -type d -print0 "
            f"| xargs -0 -I HELPER codesign --force --timestamp=none --sign - 'HELPER'; "
            f"fi"
        ),
        # 7) 再签外层 bundle
        f"codesign --force --timestamp=none --sign - '{e_tmp}'",
        # 8) 原子替换：rm 旧的 + mv 新的（同卷 mv 是原子操作）
        f"rm -rf '{e_app}'",
        f"mv '{e_tmp}' '{e_app}'",
    ]
    cmd = " && ".join(parts)
    script = f'do shell script "{cmd}" with administrator privileges'
    subprocess.run(
        ["osascript", "-e", script],
        check=True, capture_output=True, timeout=300,
    )


def _mac_privileged_write(src: str, dst: str):
    """macOS: 把 src 替换到 .app 内的 dst（副本修改 + 重签 + 原子替换）。"""
    _mac_replace_file_in_app(src, dst)


def _mac_inject_write(js_path: str, content: str, need_backup: bool):
    """macOS: 写入注入后的 JS 内容到 .app 内路径，走 App Management 安全路径。"""
    fd, tmp = tempfile.mkstemp(suffix=".js", prefix="cursor_inject_")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(content.encode("utf-8"))

        if need_backup:
            bak = _mac_bak_path(js_path)
            shutil.copy2(js_path, bak)
            print(f"[Injector] Backup created: {bak}")

        _mac_replace_file_in_app(tmp, js_path)
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def _mac_privilege_error_msg(stderr: str) -> str:
    """根据 osascript 的 stderr 生成用户友好的错误提示"""
    s = stderr.lower()
    if "user canceled" in s or "-128" in s:
        return "您取消了授权，请重新操作并在弹出的密码框中输入密码"
    if "not permitted" in s or "operation not permitted" in s or "permission denied" in s:
        return (
            "macOS 系统拦截了写入操作（App 管理保护）。请按以下步骤操作：\n"
            "1. 打开「系统设置 → 隐私与安全性 → App 管理」\n"
            "2. 把「AI 助手」和「终端」加入列表并打开开关\n"
            "3. 完全退出 AI 助手后重新打开，再次尝试注入"
        )
    if "codesign" in s and ("failed" in s or "error" in s or "invalid" in s):
        return (
            "Cursor.app 重签名失败，可能导致启动黑屏。请执行：\n"
            "1. 彻底删除 Cursor.app：sudo rm -rf /Applications/Cursor.app\n"
            "2. 重新安装：brew reinstall --cask cursor（或官网重下 dmg）\n"
            "3. 先手动启动一次 Cursor 再来注入\n"
            f"详细错误：{stderr[:300]}"
        )
    if stderr:
        return f"提权写入失败: {stderr}"
    return "提权写入失败，请确保在弹出的密码框中输入密码"


def _clear_cache_safe():
    """清除 V8 字节码缓存，防止 Electron 加载旧编译缓存导致黑屏"""
    try:
        from core.cursor_process import clear_cursor_cache
        clear_cursor_cache()
    except Exception as e:
        print(f"[Injector] Cache clear failed: {e}")


class CursorInjector:
    """管理 Cursor 的 JS 注入（分 Basic / Pro 两档）：

      Basic（无感换号，inject(pro=False)）:
        - i0           完整性检查绕过
        - i1s..i1e     暴露 window.store + 通知系统
        - i2s..i2e     Token 轮询 + fetch 状态码监测 + 无感换号

      Pro（完整代理，inject(pro=True)）:
        - Basic 的全部（i0 + i1 + i2）
        - i3s..i3e     Pro 会员状态运行时强化
        - 域名替换     将 Cursor agent/API 域名替换为中继站域名
        - 文本补丁     静态替换（token 上限 / Pro Trial 徽章 / 隐藏 upgrade）
        - 正则补丁     isPure / tab completion / ext_verify 绕过

      extensionHostProcess.js（仅 Pro）:
        - 域名替换     将 Cursor agent/API 域名替换为中继站域名
        - 正则补丁     ext_verify 绕过
    """

    def __init__(self):
        self._js_path = _find_workbench_js()
        self._exthost_path = _find_exthost_js()

    @property
    def js_path(self) -> str | None:
        return self._js_path

    @property
    def exthost_path(self) -> str | None:
        return self._exthost_path

    def is_available(self) -> bool:
        return self._js_path is not None and os.path.isfile(self._js_path)

    def is_injected(self) -> bool:
        """Basic 注入检测：i0 + i1 + i2（无感换号）。
        Pro 注入也是 is_injected() == True（超集）。"""
        if not self.is_available():
            return False
        try:
            with open(self._js_path, "rb") as f:
                raw = f.read()
            return (
                b"/*i0*/" in raw
                and b"/*i1s*/" in raw
                and b"/*i2s*/" in raw
            )
        except Exception:
            return False

    def is_pro_injected(self) -> bool:
        """Pro 注入检测：Anthropic 补丁 + 完整性绕过标记。"""
        if not self.is_available():
            return False
        try:
            with open(self._js_path, "rb") as f:
                raw = f.read()
            return any(m in raw for m in _RELAY_MARKERS)
        except Exception:
            return False

    def is_exthost_injected(self) -> bool:
        if not self._exthost_path or not os.path.isfile(self._exthost_path):
            return False
        try:
            with open(self._exthost_path, "rb") as f:
                raw = f.read()
            return any(m in raw for m in _RELAY_MARKERS)
        except Exception:
            return False

    def _backup(self):
        bak = self._js_path + ".bak"
        if not os.path.exists(bak):
            shutil.copy2(self._js_path, bak)
            print(f"[Injector] Backup created: {bak}")

    def inject(self, pro: bool = False) -> tuple[bool, str]:
        """注入 JS 代码。

        pro=False: 仅注入 i0+i1+i2（无感换号）
        pro=True:  注入全部（i0+i1+i2+i3 + 域名替换 + 正则补丁 + 文本补丁）

        返回 (success, message)
        """
        if not self.is_available():
            return False, "未检测到 Cursor 安装，请确认已正确安装并至少启动过一次"

        # 不做"已注入则跳过"，始终清理旧注入后重新注入（确保注入代码为最新版本）

        # Linux: 提前获取写入权限
        ok, err = _ensure_writable(self._js_path)
        if not ok:
            return False, err

        try:
            with open(self._js_path, "rb") as f:
                raw = f.read()
            content = raw.decode("utf-8")
            print(f"[Injector] Read {len(raw)} bytes from {self._js_path}")
        except Exception as e:
            return False, f"读取文件失败: {e}"

        # 修复可能被 Windows Python 文本模式污染的 CRLF（\r\n → \n）
        crlf_count = content.count("\r\n")
        if crlf_count > 0:
            content = content.replace("\r\n", "\n")
            print(f"[Injector] Fixed {crlf_count} CRLF → LF (previous text-mode corruption)")

        # 先还原可能存在的部分注入残留
        content = self._strip_markers(content)

        # 注入点 0：绕过完整性检查
        if _INJECT0_SEARCH not in content:
            return False, f"未找到注入点 0 的匹配代码，Cursor 版本可能不兼容"
        content = content.replace(_INJECT0_SEARCH, _INJECT0_REPLACE, 1)

        # 注入点 1：暴露 window.store + 通知系统
        if _INJECT1_SEARCH not in content:
            return False, f"未找到注入点 1 的匹配代码，Cursor 版本可能不兼容"
        content = content.replace(
            _INJECT1_SEARCH,
            _INJECT1_SEARCH + _INJECT1_CODE,
            1,
        )

        # 注入点 2：Token 轮询（紧跟在 i1e 后面）
        i1e_pos = content.find("/*i1e*/")
        if i1e_pos < 0:
            return False, "注入点 1 插入异常"
        insert_pos = i1e_pos + len("/*i1e*/")
        content = content[:insert_pos] + _INJECT2_CODE + content[insert_pos:]

        # 清理旧版 Renderer 头部注入（如果存在）
        content = _remove_between(content, "/*wxrs*/", "/*wxre*/")

        # ── Pro 专属补丁（仅 pro=True 时应用）──────────────────────
        if pro:
            # 注入点 3：Pro 会员状态运行时强化（紧跟在 i2e 后面）
            i2e_pos = content.find("/*i2e*/")
            if i2e_pos < 0:
                return False, "注入点 2 插入异常"
            insert_pos = i2e_pos + len("/*i2e*/")
            content = content[:insert_pos] + _INJECT3_CODE + content[insert_pos:]

            # Anthropic Base URL 路由补丁（CursorPro 核心方案）
            # 让 Claude 模型走 anthropicBaseUrl，其他走 openAIBaseUrl
            if _ANTHROPIC_PATCH_NEW in content:
                print("[Injector] anthropic patch: already applied")
            elif _ANTHROPIC_PATCH_OLD in content:
                content = content.replace(
                    _ANTHROPIC_PATCH_OLD, _ANTHROPIC_PATCH_NEW, 1)
                print("[Injector] anthropic patch: applied")
            else:
                print("[Injector] anthropic patch: pattern not found (version mismatch?)")

            # 正则补丁（isPure / tab / ext_verify）
            content, regex_results = _apply_regex_patches(content)
            print(f"[Injector] regex patches: {', '.join(regex_results)}")

            # 静态文本补丁（Pro Trial 徽章、token 上限等，软匹配）
            text_results: list[str] = []
            for patch in _TEXT_PATCHES:
                if patch["search"] in content:
                    content = content.replace(patch["search"], patch["replace"])
                    text_results.append(patch["id"] + ":ok")
                else:
                    text_results.append(patch["id"] + ":miss")
            print(f"[Injector] text patches: {', '.join(text_results)}")

        is_mac_priv = platform.system() == "Darwin" and _needs_privilege(self._js_path)
        if is_mac_priv:
            need_backup = not os.path.exists(_mac_bak_path(self._js_path))
        else:
            need_backup = not os.path.exists(self._js_path + ".bak")

        # macOS: 用 osascript 提权写入
        if is_mac_priv:
            try:
                _mac_inject_write(self._js_path, content, need_backup)
            except subprocess.CalledProcessError as e:
                stderr = (e.stderr or b"").decode(errors="replace").strip()
                print(f"[Injector] osascript failed: rc={e.returncode} stderr={stderr}")
                return False, _mac_privilege_error_msg(stderr)
            except subprocess.TimeoutExpired:
                return False, "授权超时，请重试"
            except Exception as e:
                return False, f"写入文件失败: {e}"
        else:
            try:
                self._backup()
            except Exception as e:
                return False, f"创建备份失败: {e}"
            try:
                out_bytes = content.encode("utf-8")
                with open(self._js_path, "wb") as f:
                    f.write(out_bytes)
                print(f"[Injector] Wrote {len(out_bytes)} bytes (binary mode, LF only)")
            except Exception as e:
                return False, f"写入文件失败: {e}"

        # 写后验证：确认磁盘文件与写入内容一致
        try:
            with open(self._js_path, "rb") as f:
                verify = f.read()
            if verify == content.encode("utf-8"):
                print(f"[Injector] Write verification OK ({len(verify)} bytes)")
            else:
                print(f"[Injector] WARNING: Write verification MISMATCH! "
                      f"expected {len(content.encode('utf-8'))} got {len(verify)}")
        except Exception as e:
            print(f"[Injector] Write verification failed: {e}")

        # 注入成功后自动禁用 Cursor 自动更新（避免更新覆盖注入）
        try:
            from core.cursor_process import disable_cursor_auto_update
            if disable_cursor_auto_update():
                print("[Injector] Auto-update disabled")
        except Exception:
            pass

        # 清除 V8 字节码缓存（不清除会导致 Electron 加载旧的编译缓存而非修改后的 JS → 黑屏）
        _clear_cache_safe()

        if pro:
            print("[Injector] Pro injection complete (anthropic patch + integrity bypass)")
            return True, "JS 补丁已应用，重启 Cursor 后生效"
        else:
            print("[Injector] Basic injection complete (seamless switch only)")
            return True, "注入成功（无感换号），重启 Cursor 后生效"

    def restore(self) -> tuple[bool, str]:
        """还原注入，优先使用 .bak 备份，否则移除 marker 代码"""
        if not self.is_available():
            return False, "未找到 Cursor 安装目录"

        ok, err = _ensure_writable(self._js_path)
        if not ok:
            return False, err

        is_mac_priv = platform.system() == "Darwin" and _needs_privilege(self._js_path)

        # 确定备份路径（macOS 在用户目录，其他在原位）
        if is_mac_priv:
            bak = _mac_bak_path(self._js_path)
        else:
            bak = self._js_path + ".bak"

        if os.path.exists(bak):
            try:
                if is_mac_priv:
                    _mac_privileged_write(bak, self._js_path)
                else:
                    shutil.copy2(bak, self._js_path)
                print("[Injector] Restored from backup")
                _clear_cache_safe()
                return True, "已从备份还原"
            except subprocess.CalledProcessError as e:
                stderr = (e.stderr or b"").decode(errors="replace").strip()
                return False, _mac_privilege_error_msg(stderr)
            except subprocess.TimeoutExpired:
                return False, "授权超时，请重试"
            except Exception as e:
                return False, f"备份还原失败: {e}"

        if not self.is_injected():
            return True, "当前未注入，无需还原"

        try:
            with open(self._js_path, "rb") as f:
                content = f.read().decode("utf-8")
            if "\r\n" in content:
                content = content.replace("\r\n", "\n")
            content = self._strip_markers(content)

            if is_mac_priv:
                fd, tmp = tempfile.mkstemp(suffix=".js", prefix="cursor_restore_")
                try:
                    with os.fdopen(fd, "wb") as f:
                        f.write(content.encode("utf-8"))
                    _mac_privileged_write(tmp, self._js_path)
                finally:
                    try:
                        os.unlink(tmp)
                    except OSError:
                        pass
            else:
                with open(self._js_path, "wb") as f:
                    f.write(content.encode("utf-8"))
            print("[Injector] Restored by stripping markers")
            _clear_cache_safe()
            return True, "已还原"
        except subprocess.CalledProcessError as e:
            stderr = (e.stderr or b"").decode(errors="replace").strip()
            return False, _mac_privilege_error_msg(stderr)
        except Exception as e:
            return False, f"还原失败: {e}"

    # ── ExtensionHost: 域名替换 + 正则补丁 ─────────────────

    def inject_exthost(self) -> tuple[bool, str]:
        """在 extensionHostProcess.js 中替换 API 域名 + 应用正则补丁。"""
        if not self._exthost_path or not os.path.isfile(self._exthost_path):
            return False, "未找到 extensionHostProcess.js"

        ok, err = _ensure_writable(self._exthost_path)
        if not ok:
            return False, err

        try:
            with open(self._exthost_path, "rb") as f:
                content = f.read().decode("utf-8")
        except Exception as e:
            return False, f"读取 ExtHost 失败: {e}"

        if "\r\n" in content:
            content = content.replace("\r\n", "\n")
            print(f"[Injector] Fixed CRLF contamination in ExtHost JS")

        content = _remove_between(content, "/*wxs*/", "/*wxe*/")

        # 正则补丁（完整性绕过）
        content, regex_results = _apply_regex_patches(content)
        print(f"[Injector] ExtHost regex patches: {', '.join(regex_results)}")

        is_mac_priv = platform.system() == "Darwin" and _needs_privilege(self._exthost_path)

        # 备份
        try:
            if is_mac_priv:
                bak_dir = os.path.join(os.path.expanduser("~"), ".wuxian-assistant")
                os.makedirs(bak_dir, exist_ok=True)
                bak = os.path.join(bak_dir, "extensionHostProcess.js.bak")
            else:
                bak = self._exthost_path + ".bak"
            if not os.path.exists(bak):
                shutil.copy2(self._exthost_path, bak)
                print(f"[Injector] ExtHost backup created: {bak}")
        except Exception as e:
            return False, f"创建 ExtHost 备份失败: {e}"

        if is_mac_priv:
            fd, tmp = tempfile.mkstemp(suffix=".js", prefix="cursor_exthost_")
            try:
                with os.fdopen(fd, "wb") as f:
                    f.write(content.encode("utf-8"))
                try:
                    _mac_privileged_write(tmp, self._exthost_path)
                except subprocess.CalledProcessError as e:
                    stderr = (e.stderr or b"").decode(errors="replace").strip()
                    return False, _mac_privilege_error_msg(stderr)
                except subprocess.TimeoutExpired:
                    return False, "授权超时，请重试"
            finally:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
        else:
            try:
                with open(self._exthost_path, "wb") as f:
                    f.write(content.encode("utf-8"))
            except Exception as e:
                return False, f"写入 ExtHost 失败: {e}"

        return True, "ExtHost 完整性绕过补丁已应用"

    def restore_exthost(self) -> tuple[bool, str]:
        """从备份或通过 marker 移除来还原 ExtHost。"""
        if not self._exthost_path or not os.path.isfile(self._exthost_path):
            return True, "ExtHost 文件不存在，跳过"

        ok, err = _ensure_writable(self._exthost_path)
        if not ok:
            return False, err

        is_mac_priv = platform.system() == "Darwin" and _needs_privilege(self._exthost_path)

        if is_mac_priv:
            bak_dir = os.path.join(os.path.expanduser("~"), ".wuxian-assistant")
            bak = os.path.join(bak_dir, "extensionHostProcess.js.bak")
        else:
            bak = self._exthost_path + ".bak"

        if os.path.exists(bak):
            try:
                if is_mac_priv:
                    _mac_privileged_write(bak, self._exthost_path)
                else:
                    shutil.copy2(bak, self._exthost_path)
                return True, "ExtHost 已从备份还原"
            except subprocess.CalledProcessError as e:
                stderr = (e.stderr or b"").decode(errors="replace").strip()
                return False, _mac_privilege_error_msg(stderr)
            except Exception as e:
                return False, f"ExtHost 还原失败: {e}"

        if not self.is_exthost_injected():
            return True, "ExtHost 未注入，无需还原"

        try:
            with open(self._exthost_path, "rb") as f:
                content = f.read().decode("utf-8")
            if "\r\n" in content:
                content = content.replace("\r\n", "\n")
            content = _remove_between(content, "/*wxs*/", "/*wxe*/")
            if is_mac_priv:
                fd, tmp = tempfile.mkstemp(suffix=".js", prefix="cursor_exthost_restore_")
                try:
                    with os.fdopen(fd, "wb") as f:
                        f.write(content.encode("utf-8"))
                    _mac_privileged_write(tmp, self._exthost_path)
                finally:
                    try:
                        os.unlink(tmp)
                    except OSError:
                        pass
            else:
                with open(self._exthost_path, "wb") as f:
                    f.write(content.encode("utf-8"))
            return True, "ExtHost 已通过标记移除还原"
        except subprocess.CalledProcessError as e:
            stderr = (e.stderr or b"").decode(errors="replace").strip()
            return False, _mac_privilege_error_msg(stderr)
        except Exception as e:
            return False, f"ExtHost 还原失败: {e}"

    @staticmethod
    def _strip_markers(content: str) -> str:
        """移除所有注入标记和其间代码。

        文本补丁（_TEXT_PATCHES）和 H2 正则补丁的完整反向还原依赖 .bak
        备份文件，此函数只处理标记式代码块。
        """
        content = content.replace(_INJECT0_REPLACE, _INJECT0_SEARCH)
        # 兼容旧版 i0（_showNotificationOld 方式）
        _OLD_I0_REPLACE = "_showNotification(){/*i0*/}_showNotificationOld(){"
        content = content.replace(_OLD_I0_REPLACE, _INJECT0_SEARCH)
        # Restore anthropic patch
        if _ANTHROPIC_PATCH_NEW in content:
            content = content.replace(_ANTHROPIC_PATCH_NEW, _ANTHROPIC_PATCH_OLD)
        content = _remove_between(content, "/*wxFetchIntercept*/", "/*wxFetchInterceptEnd*/")
        content = _remove_between(content, "/*wxrs*/", "/*wxre*/")
        content = _remove_between(content, "/*i1s*/", "/*i1e*/")
        content = _remove_between(content, "/*i2s*/", "/*i2e*/")
        content = _remove_between(content, "/*i3s*/", "/*i3e*/")

        # 文本补丁反转：仅当 replace 值足够特异时才尝试，
        # 避免把 "" 这种通用模式在整个文件中反向展开。
        for patch in _TEXT_PATCHES:
            rep = patch["replace"]
            if not rep or len(rep) < 8:
                continue
            if rep in content and patch["search"] not in content:
                content = content.replace(rep, patch["search"])

        return content


def _remove_between(text: str, start_marker: str, end_marker: str) -> str:
    """移除从 start_marker 到 end_marker（含标记本身）的内容"""
    s = text.find(start_marker)
    if s < 0:
        return text
    e = text.find(end_marker, s)
    if e < 0:
        return text
    return text[:s] + text[e + len(end_marker):]
