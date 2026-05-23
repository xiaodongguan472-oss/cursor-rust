#!/usr/bin/env node
/* eslint-disable */
/**
 * 前端 UI 混淆器
 * 处理对象：
 *   1. ui/tauri-bridge.js  → 整文件混淆
 *   2. ui/index.html       → 提取所有 <script> 内联代码混淆后写回
 * 不处理：
 *   - element-plus.js / vue.global.js（第三方库，混淆后体积爆炸 + 兼容问题）
 *   - element-plus.css（CSS 不需要混淆）
 *
 * 防御能力：
 *   - 控制流平坦化（看不到原代码结构）
 *   - 字符串数组 + 索引混淆（"续杯助手" 等关键词全部加密）
 *   - 标识符全部 hex 化（_0xa1b2c3）
 *   - dead code injection
 *   - debug protection（attaches 调试器自动崩溃）
 *   - self defending（被 prettify 后会自我损坏）
 *
 * 用法：
 *   node scripts/obfuscate.js          # 原地混淆 ui/ 目录
 *   node scripts/obfuscate.js --check  # 干跑检查（不写文件，只报告）
 */

const fs = require('fs');
const path = require('path');
const JavaScriptObfuscator = require('javascript-obfuscator');

const ROOT = path.resolve(__dirname, '..');
const SRC_UI = path.join(ROOT, 'ui');
const CHECK_ONLY = process.argv.includes('--check');
const IN_PLACE = process.argv.includes('--inplace'); // CI 模式：直接修改 ui/

// 默认输出到 ui/（打包前覆盖）。本地开发不调用，开发用 ui/ 原文件
// CI 模式：runner 临时环境，直接覆盖 ui/
// 本地手动测试：可以拷贝到 ui-obfuscated/ 比对
const OUT_UI = IN_PLACE ? SRC_UI : path.join(ROOT, 'ui-obfuscated');

const TAURI_BRIDGE_SRC = path.join(SRC_UI, 'tauri-bridge.js');
const INDEX_HTML_SRC = path.join(SRC_UI, 'index.html');
const TAURI_BRIDGE_OUT = path.join(OUT_UI, 'tauri-bridge.js');
const INDEX_HTML_OUT = path.join(OUT_UI, 'index.html');

// 如果输出目录不是源目录，先把整个 ui/ 拷贝过去（包含第三方库）
function prepareOutputDir() {
  if (IN_PLACE || OUT_UI === SRC_UI) return;
  // 干净重建
  if (fs.existsSync(OUT_UI)) {
    fs.rmSync(OUT_UI, { recursive: true, force: true });
  }
  fs.mkdirSync(OUT_UI, { recursive: true });
  // 拷贝所有文件
  for (const f of fs.readdirSync(SRC_UI)) {
    const srcPath = path.join(SRC_UI, f);
    const dstPath = path.join(OUT_UI, f);
    fs.copyFileSync(srcPath, dstPath);
  }
  console.log(`[Obfuscate] 已拷贝 ui/ → ${path.relative(ROOT, OUT_UI)}/`);
}

// ============================================================================
// 混淆参数（高强度但兼顾运行性能）
// ============================================================================
const OBF_OPTS = {
  compact: true,
  controlFlowFlattening: true,
  controlFlowFlatteningThreshold: 0.75,    // 75% 函数走 CFF
  deadCodeInjection: true,
  deadCodeInjectionThreshold: 0.4,
  debugProtection: false,                  // 关掉激进 debugProtection（避免误伤 webview2）
  debugProtectionInterval: 0,
  disableConsoleOutput: true,              // 让 console.log 不输出
  identifierNamesGenerator: 'hexadecimal',
  log: false,
  numbersToExpressions: true,
  renameGlobals: false,                    // 不改全局名（保留 Vue/ElementPlus/__TAURI__）
  selfDefending: true,                     // 反 prettify
  simplify: true,
  splitStrings: true,
  splitStringsChunkLength: 8,
  stringArray: true,
  stringArrayCallsTransform: true,
  stringArrayCallsTransformThreshold: 0.75,
  stringArrayEncoding: ['base64'],
  stringArrayIndexShift: true,
  stringArrayRotate: true,
  stringArrayShuffle: true,
  stringArrayWrappersCount: 2,
  stringArrayWrappersChainedCalls: true,
  stringArrayWrappersParametersMaxCount: 4,
  stringArrayWrappersType: 'function',
  stringArrayThreshold: 0.85,
  transformObjectKeys: true,
  unicodeEscapeSequence: false,            // 关掉，避免膨胀过大
  // 保留全局：让 require()、Vue、ElementPlus、__TAURI__、ipcRenderer 等不被改名
  reservedNames: [
    'require', 'Vue', 'ElementPlus', 'ElMessage', 'ElMessageBox', 'ElMessageBoxComponent',
    '__TAURI__', 'ipcRenderer', 'createApp', 'process'
  ],
  reservedStrings: [
    // 保留必要的 Tauri 命令名（tauri-bridge 的 COMMAND_MAP 必须明文）
    // 由于这些是 string 字面量被 stringArray 编码后会变密文 + 运行时解密，
    // 实际 Tauri 命令仍然能正常拼出，所以这里不需要保留。
  ],
};

function obfuscateCode(source, label) {
  console.log(`[Obfuscate] ${label}: ${source.length} bytes →`);
  const result = JavaScriptObfuscator.obfuscate(source, OBF_OPTS);
  const out = result.getObfuscatedCode();
  console.log(`           ${out.length} bytes (${((out.length / source.length) * 100).toFixed(0)}%)`);
  return out;
}

// ============================================================================
// 任务 1: 混淆 tauri-bridge.js
// ============================================================================
function obfTauriBridge() {
  if (!fs.existsSync(TAURI_BRIDGE_SRC)) {
    console.warn('[Obfuscate] tauri-bridge.js 不存在，跳过');
    return;
  }
  const original = fs.readFileSync(TAURI_BRIDGE_SRC, 'utf-8');
  // 检查是否已经混淆过（避免重复）
  if (original.includes('_0x') && original.length > 30000) {
    console.log('[Obfuscate] tauri-bridge.js 似乎已混淆过，跳过');
    return;
  }
  const obfuscated = obfuscateCode(original, 'tauri-bridge.js');
  if (!CHECK_ONLY) {
    fs.writeFileSync(TAURI_BRIDGE_OUT, obfuscated, 'utf-8');
    console.log(`[Obfuscate] tauri-bridge.js 已写到 ${path.relative(ROOT, TAURI_BRIDGE_OUT)}`);
  }
}

// ============================================================================
// 任务 2: 混淆 index.html 中所有 <script>...</script> 内联块
// ============================================================================
function obfIndexHtml() {
  if (!fs.existsSync(INDEX_HTML_SRC)) {
    console.error('[Obfuscate] index.html 不存在！');
    process.exit(1);
  }
  let html = fs.readFileSync(INDEX_HTML_SRC, 'utf-8');

  // 检查是否已混淆（启发式：业务关键变量 createApp 应该在文中，混淆后会变成乱码）
  // 我们用更可靠的标记：第一个内联 script 是否包含 _0x 前缀的密集变量
  // 简单方法：HTML 文件里 'createApp' 出现次数（应该 > 5 在原版）
  const originalCreateAppCount = (html.match(/createApp/g) || []).length;
  if (originalCreateAppCount === 0) {
    console.log('[Obfuscate] index.html 里 createApp 出现 0 次，可能已混淆，跳过');
    return;
  }

  // 找所有 <script>...</script>（不含外部 src 的）
  // 注意：业务 inline script 的 <script> 标签后面可能没有属性（如 <script>...）
  // 也可能有属性（虽然我们不改这种）
  const scriptRegex = /<script(?![^>]*\bsrc\s*=)[^>]*>([\s\S]*?)<\/script>/gi;

  let count = 0;
  let totalIn = 0;
  let totalOut = 0;

  const newHtml = html.replace(scriptRegex, (match, body) => {
    // 跳过空 script
    if (!body || !body.trim()) return match;

    // 跳过 application/json 等非 JS 类型
    const tagOpen = match.substring(0, match.indexOf('>') + 1);
    if (/type\s*=\s*["'](?!text\/javascript)[^"']+["']/i.test(tagOpen)) {
      console.log(`[Obfuscate]   跳过非 JS 类型 script`);
      return match;
    }

    count++;
    totalIn += body.length;

    // 跳过太短的 script（小于 80 字节，混淆收益极低）
    if (body.length < 80) {
      console.log(`[Obfuscate]   #${count} ${body.length}B 太短，跳过`);
      totalOut += body.length;
      return match;
    }

    try {
      const obfuscated = obfuscateCode(body, `index.html script #${count}`);
      totalOut += obfuscated.length;
      // 重新拼回 <script> 标签（保留原 tagOpen 以保留任何属性）
      return `${tagOpen}\n${obfuscated}\n</script>`;
    } catch (e) {
      console.error(`[Obfuscate]   #${count} 混淆失败:`, e.message);
      totalOut += body.length;
      return match;
    }
  });

  console.log(`[Obfuscate] index.html: ${count} 个内联 script，总 ${totalIn} → ${totalOut} bytes`);

  if (!CHECK_ONLY) {
    fs.writeFileSync(INDEX_HTML_OUT, newHtml, 'utf-8');
    console.log(`[Obfuscate] index.html 已写到 ${path.relative(ROOT, INDEX_HTML_OUT)}`);
  }
}

// ============================================================================
// 主入口
// ============================================================================
console.log('='.repeat(64));
console.log(' UI 混淆开始 ' + (CHECK_ONLY ? '(干跑模式)' : '') + (IN_PLACE ? ' [IN_PLACE 直接覆盖 ui/]' : ' [输出到 ui-obfuscated/]'));
console.log('='.repeat(64));

if (!CHECK_ONLY) prepareOutputDir();

obfTauriBridge();
obfIndexHtml();

console.log('='.repeat(64));
console.log(' UI 混淆完成');
console.log('='.repeat(64));
