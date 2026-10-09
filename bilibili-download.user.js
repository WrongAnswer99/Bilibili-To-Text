// ==UserScript==
// @name         BilibiliToText - 下载视频 / 提取文字
// @namespace    local.BilibiliToText
// @version      0.3.1
// @description  使用当前浏览器登录态下载 B 站视频，显示进度、文件名和预期保存位置。
// @match        https://www.bilibili.com/video/*
// @match        https://bilibili.com/video/*
// @run-at       document-idle
// @noframes
// @grant        unsafeWindow
// @grant        GM_xmlhttpRequest
// @grant        GM_download
// @grant        GM_getValue
// @grant        GM_setValue
// @grant        GM_setClipboard
// @grant        GM_info
// @connect      api.bilibili.com
// @connect      bilivideo.com
// @connect      bilivideo.cn
// @connect      biliapi.net
// @connect      biliapi.com
// @connect      acgvideo.com
// ==/UserScript==

(() => {
    'use strict';

    // 这是本机 Windows 的默认下载目录；浏览器实际设置不同，请在面板中修改。
    const DEFAULT_DOWNLOAD_DIRECTORY = String.raw`C:\Users\admin\Downloads`;
    const VERSION = '0.3.1';
    const API = 'https://api.bilibili.com';
    let busy = false;
    let cancelled = false;
    let activeCancel = null;
    let lastReport = '';
    let session = null;
    let importUri = '';

    const host = document.createElement('div');
    host.id = 'bilibili-to-text-download';
    host.style.cssText = 'position:fixed;right:20px;bottom:20px;z-index:2147483647;';
    const root = host.attachShadow({ mode: 'open' });
    root.innerHTML = '<style>' +
        ':host{font:14px/1.5 "Microsoft YaHei",sans-serif;color:#222}' +
        '*{box-sizing:border-box}section{width:370px;max-width:95vw;background:white;' +
        'border:1px solid #ddd;border-radius:12px;padding:16px;box-shadow:0 5px 24px #0003}' +
        'h3{margin:0 0 8px;font-size:17px}p{margin:6px 0;font-size:12px;color:#666}' +
        'input{width:100%;padding:7px;border:1px solid #bbb;border-radius:5px;font:inherit}' +
        '.buttons{display:flex;gap:8px;margin-top:10px}button{cursor:pointer;padding:7px 12px;' +
        'border:1px solid #bbb;border-radius:5px;background:#f5f5f5;font:inherit}' +
        'button:disabled{opacity:.5;cursor:default}#start{background:#00a1d6;color:white;border:0}' +
        'progress{width:100%;margin-top:12px}#progressText{font-size:12px;min-height:18px}' +
        'pre{white-space:pre-wrap;overflow-wrap:anywhere;font:12px/1.6 Consolas,"Microsoft YaHei",' +
        'monospace;max-height:220px;overflow:auto;margin:8px 0 0;background:#f7f8fa;padding:8px}' +
        '</style><section><h3>BilibiliToText · 下载并转字幕 v0.3.1</h3>' +
        '<p>下载视频可独立使用；提取文字和打开文件夹需要本地应用。</p>' +
        '<label for="directory">浏览器下载目录（须与本地应用配置一致）</label>' +
        '<input id="directory" type="text" spellcheck="false">' +
        '<p>请与浏览器下载目录保持一致，并关闭“每次下载询问保存位置”。</p>' +
        '<div class="buttons"><label>设备 <select id="device"><option value="gpu">GPU</option>' +
        '<option value="cpu">CPU</option></select></label>' +
        '<label>语言 <select id="script"><option value="en">英语</option>' +
        '<option value="simplified">简体中文</option><option value="ja">日语</option>' +
        '<option value="ru">俄语</option><option value="traditional">繁体中文</option>' +
        '<option value="auto">自动检测</option></select></label></div>' +
        '<div class="buttons"><button id="start">下载视频</button>' +
        '<button id="downloadText">下载并提取文字</button></div>' +
        '<div class="buttons"><button id="openFolder" disabled>打开文件所在位置</button>' +
        '<button id="cancel" disabled>取消</button><button id="copy" disabled>复制结果</button></div>' +
        '<progress id="progress" max="100" value="0"></progress>' +
        '<div id="progressText">等待开始</div><pre id="log" aria-live="polite"></pre></section>';
    document.body.appendChild(host);
    const ui = Object.fromEntries(['directory', 'start', 'cancel', 'copy', 'progress', 'progressText', 'log', 'device', 'script', 'downloadText', 'openFolder']
        .map(id => [id, root.getElementById(id)]));
    ui.directory.value = GM_getValue('downloadDirectory', DEFAULT_DOWNLOAD_DIRECTORY);
    ui.directory.addEventListener('change', () => GM_setValue('downloadDirectory', ui.directory.value.trim()));
    ui.copy.addEventListener('click', () => GM_setClipboard(lastReport, 'text'));
    ui.cancel.addEventListener('click', () => {
        cancelled = true;
        if (activeCancel) activeCancel();
        ui.cancel.disabled = true;
    });
    ui.device.value = GM_getValue('transcribeDevice', 'gpu');
    ui.script.value = GM_getValue('recognitionLanguage', GM_getValue('chineseScript', 'simplified'));
    ui.device.addEventListener('change', () => GM_setValue('transcribeDevice', ui.device.value));
    ui.script.addEventListener('change', () => GM_setValue('recognitionLanguage', ui.script.value));
    ui.start.addEventListener('click', () => run(false));
    ui.downloadText.addEventListener('click', () => {
        if (busy) return;
        // Reuse a completed download of the current part; retrying a blocked protocol
        // request must not download the same video again.
        const page = new URL(location.href);
        const currentBV = page.pathname.match(/\/video\/(BV[0-9A-Za-z]{10})/);
        const currentPart = Number(page.searchParams.get('p') || 1);
        if (importUri && currentBV && session.video.bvid === currentBV[1] &&
                session.video.part === currentPart) return openLocal();
        return run(true);
    });
    ui.openFolder.addEventListener('click', () => {
        if (busy || !session?.importFiles?.length) return;
        const query = new URLSearchParams({ bv: session.video.bvid, p: String(session.video.part) });
        for (const name of session.importFiles) query.append('file', name);
        try {
            location.href = 'bilibilitotext://open-folder?' + query.toString();
            log('已请求在文件夹中显示下载文件。请允许浏览器打开本地应用。');
        } catch (error) { log('打开文件位置失败：' + (error.message || String(error))); }
    });

    function log(message) {
        const time = new Date().toLocaleTimeString('zh-CN', { hour12: false });
        ui.log.textContent += '[' + time + '] ' + message + '\n';
        ui.log.scrollTop = ui.log.scrollHeight;
    }

    function recognitionOptions(selection) {
        return {
            language: selection === 'simplified' || selection === 'traditional' ? 'zh' : selection,
            script: selection === 'traditional' ? 'traditional' : 'simplified'
        };
    }

    function buildImportUri(info, filenames, device, selection) {
        const options = recognitionOptions(selection);
        const query = new URLSearchParams({
            bv: info.bvid, p: String(info.part), device, script: options.script, lang: options.language
        });
        for (const filename of filenames) query.append('file', filename);
        return 'bilibilitotext://import?' + query.toString();
    }

    function openLocal() {
        if (!importUri) return;
        importUri = buildImportUri(session.video, session.importFiles, ui.device.value, ui.script.value);
        session.localImportUri = importUri;
        session.transcription = { device: ui.device.value, ...recognitionOptions(ui.script.value) };
        log('正在请求打开本地应用。请允许浏览器打开 BilibiliToText；未弹出窗口可再次点击“下载并提取文字”。');
        log('本地程序使用 config.json 中的下载目录；若目录不同，请重新运行 register_protocol.ps1 -DownloadDirectory "实际目录"。');
        try {
            location.href = importUri;
            log('已发送本地协议请求（浏览器不会向脚本确认应用是否启动）。');
        } catch (error) {
            log('本地协议请求失败：' + (error.message || String(error)));
        }
        lastReport = report('下载完成，已请求本地转换', session.completed || [], null);
    }

    function diagnosticUrl(value) {
        try {
            const url = new URL(String(value));
            const visible = new Set(['bvid', 'cid', 'qn', 'fnval', 'fnver', 'platform', 'high_quality', 'p']);
            const query = Array.from(url.searchParams.entries(), ([key, val]) =>
                encodeURIComponent(key) + '=' + (visible.has(key) ? encodeURIComponent(val) : '[省略]'));
            return url.protocol + '//' + url.host + url.pathname + (query.length ? '?' + query.join('&') : '');
        } catch (_) { return '[地址无法解析]'; }
    }

    function diagnosticValue(value, depth = 0, seen = new WeakSet()) {
        if (value === undefined) return '[未返回]';
        if (value === null || typeof value === 'boolean' || typeof value === 'number') return value;
        if (typeof value === 'string') {
            const safe = value.replace(/https?:\/\/[^\s"'<>]+/g, match => diagnosticUrl(match));
            return safe.length > 4000 ? safe.slice(0, 4000) + '…[截断]' : safe;
        }
        if (typeof value !== 'object') return '[' + typeof value + ']';
        if (seen.has(value)) return '[循环引用]';
        if (depth > 5) return '[深度限制]';
        seen.add(value);
        if (typeof Blob !== 'undefined' && value instanceof Blob) {
            return '[Blob ' + value.size + ' bytes]';
        }
        if (Array.isArray(value)) return value.slice(0, 30).map(item => diagnosticValue(item, depth + 1, seen));
        const output = {};
        for (const key of Object.getOwnPropertyNames(value).slice(0, 40)) {
            // 错误细节可以完整复制，但不记录 Cookie、认证信息或响应正文。
            if (/cookie|authorization|sessdata|csrf|token|signature|w_rid|upsig|headers|^response(?:Text|XML)?$/i.test(key)) {
                output[key] = '[省略]';
                continue;
            }
            try { output[key] = diagnosticValue(value[key], depth + 1, seen); }
            catch (_) { output[key] = '[无法读取]'; }
        }
        return output;
    }

    function diagnosticText(value) {
        try { return JSON.stringify(diagnosticValue(value), null, 2); }
        catch (_) { return '[错误信息无法序列化]'; }
    }

    function detailedError(message, details) {
        const error = new Error(message);
        error.diagnostic = diagnosticText(details);
        return error;
    }

    function runtimeInfo() {
        return {
            scriptVersion: VERSION,
            manager: GM_info.scriptHandler || '未返回',
            managerVersion: GM_info.version || '未返回',
            downloadMode: GM_info.downloadMode || '未返回',
            browser: typeof navigator === 'undefined' ? '未返回' : navigator.userAgent
        };
    }

    function report(status, completed, error) {
        return '状态：' + status + '\n' +
            '任务诊断：\n' + diagnosticText(session) + '\n\n' +
            (completed.length ? '已完成文件：\n' + completed.join('\n\n') + '\n\n' : '') +
            (error ? '错误：' + (error.message || String(error)) + '\n底层详情：\n' +
                (error.diagnostic || diagnosticText(error)) + '\n\n' : '') +
            '完整日志：\n' + ui.log.textContent +
            '\n油猴不保证返回真实路径。请在浏览器下载记录中点击“在文件夹中显示”核对；' +
            '另存位置或浏览器改名后，以浏览器记录为准。';
    }

    function checkCancelled() {
        if (cancelled) throw new Error('任务已取消。');
    }

    function operation(start) {
        checkCancelled();
        return new Promise((resolve, reject) => {
            let finished = false;
            let handle;
            const finish = (callback, value) => {
                if (finished) return;
                finished = true;
                if (activeCancel === cancel) activeCancel = null;
                callback(value);
            };
            const cancel = () => {
                finish(reject, new Error('任务已取消。'));
                try { if (handle) handle.abort(); } catch (_) { /* 已结束 */ }
            };
            activeCancel = cancel;
            try {
                handle = start(value => finish(resolve, value), error => finish(reject, error));
            } catch (error) {
                finish(reject, error);
            }
        });
    }

    function getJson(url) {
        const started = Date.now();
        const trace = { url: diagnosticUrl(url), method: 'GET', status: null, apiCode: null };
        log('请求接口：' + trace.url);
        return operation((done, fail) => {
            const failure = (message, event) => {
                trace.elapsedMs = Date.now() - started;
                const error = detailedError(message, { request: trace, event });
                log(message + '\n接口诊断：' + error.diagnostic);
                fail(error);
            };
            return GM_xmlhttpRequest({
                method: 'GET',
                url,
                anonymous: false, // 由浏览器发送 Cookie；不读取、不输出 Cookie。
                headers: { Referer: 'https://www.bilibili.com/' },
                timeout: 30000,
                onload(response) {
                    if (cancelled) return;
                    trace.status = response.status;
                    trace.statusText = response.statusText || '';
                    trace.elapsedMs = Date.now() - started;
                    try {
                        if (response.status !== 200) throw new Error('接口 HTTP ' + response.status);
                        const body = JSON.parse(response.responseText);
                        trace.apiCode = body.code;
                        if (body.code !== 0) {
                            throw new Error('接口错误 ' + body.code + '：' + (body.message || '未知错误'));
                        }
                        if (!body.data) throw new Error('接口未返回视频数据。');
                        log('接口成功：HTTP ' + response.status + '，code=' + body.code + '，' + trace.elapsedMs + ' ms');
                        done(body.data);
                    } catch (error) { failure(error.message, error); }
                },
                onerror(event) { failure('接口请求失败，请检查网络和油猴 @connect 授权。', event); },
                ontimeout(event) { failure('接口请求超时（30 秒），请稍后重试。', event); },
                onabort() { fail(new Error('任务已取消。')); }
            });
        });
    }

    function mediaUrl(value) {
        if (typeof value !== 'string' || !value) throw new Error('视频资源地址为空。');
        const url = new URL(value, 'https://www.bilibili.com/');
        if (!['https:', 'http:'].includes(url.protocol)) throw new Error('视频资源地址格式不支持。');
        return url.href;
    }

    function streamUrl(stream) {
        return mediaUrl(stream.baseUrl || stream.base_url || stream.url);
    }

    async function metadata(pageUrl) {
        const bvid = /\/video\/(BV[0-9A-Za-z]+)(?:\/|$)/.exec(pageUrl.pathname)?.[1];
        if (!bvid) throw new Error('请在 /video/BV… 页面使用此脚本。');
        const rawPart = pageUrl.searchParams.get('p') || '1';
        if (!/^[1-9]\d*$/.test(rawPart)) throw new Error('分 P 参数不正确。');
        const part = Number(rawPart);
        let data;
        try {
            data = await getJson(API + '/x/web-interface/view?bvid=' + encodeURIComponent(bvid));
        } catch (error) {
            checkCancelled();
            const cached = unsafeWindow.__INITIAL_STATE__?.videoData;
            if (cached?.bvid !== bvid || !Array.isArray(cached.pages)) throw error;
            data = cached;
            log('视频信息接口不可用，使用当前页面的视频信息。');
        }
        const page = data.pages?.find(item => Number(item.page) === part);
        if (!page?.cid) throw new Error('找不到第 ' + part + ' P；请刷新视频页面后重试。');
        return { bvid, part, cid: page.cid, title: data.title || bvid };
    }

    function selectFiles(data, stem) {
        // 分离轨道不能假装是完整 MP4；分别保存，后续由本地 FFmpeg 合并。
        if (data.dash) {
            const videos = (data.dash.video || []).filter(item =>
                item.baseUrl || item.base_url || item.url);
            const audios = (data.dash.audio || []).filter(item =>
                item.baseUrl || item.base_url || item.url);
            const ordinaryVideos = videos.filter(item => Number(item.id) <= 80);
            const pool = ordinaryVideos.length ? ordinaryVideos : videos;
            pool.sort((a, b) => Number(b.id) - Number(a.id) ||
                Number(String(b.codecs || '').startsWith('avc1')) -
                Number(String(a.codecs || '').startsWith('avc1')));
            audios.sort((a, b) => Number(b.bandwidth || 0) - Number(a.bandwidth || 0));
            if (!pool.length || !audios.length) throw new Error('接口没有返回可下载的视频轨和音轨。');
            return [
                { name: stem + '.video.m4s', url: streamUrl(pool[0]), kind: '视频轨（无声音）' },
                { name: stem + '.audio.m4s', url: streamUrl(audios[0]), kind: '音轨' }
            ];
        }
        if (!Array.isArray(data.durl) || !data.durl.length) throw new Error('接口没有返回下载资源。');
        const isMp4 = String(data.format || '').toLowerCase().includes('mp4') ||
            new URL(mediaUrl(data.durl[0].url)).pathname.toLowerCase().endsWith('.mp4');
        if (!isMp4) throw new Error('接口返回了不支持的容器：' + (data.format || '未知'));
        return data.durl.map((item, index) => ({
            name: stem + (data.durl.length > 1 ? '.part' + (index + 1) : '') + '.mp4',
            url: mediaUrl(item.url),
            kind: data.durl.length > 1 ? '带声音 MP4 分段 ' + (index + 1) : '带声音 MP4'
        }));
    }

    async function resources(info, stem) {
        const query = new URLSearchParams({
            bvid: info.bvid, cid: String(info.cid), qn: '64', fnver: '0',
            fnval: '1', platform: 'html5', high_quality: '1'
        });
        const errors = [];
        log('尝试获取带声音 MP4（优先 720P，以接口实际返回为准）。');
        try {
            const data = await getJson(API + '/x/player/playurl?' + query);
            if (data.is_preview || data.isPreview) throw new Error('接口只返回试看资源。');
            return selectFiles(data, stem);
        } catch (error) {
            checkCancelled();
            errors.push(error.message);
            log('MP4 接口未成功，尝试当前页面播放资源。');
        }
        // 页面播放资源必须属于相同 BV 和 CID，避免切换视频/分 P 后下载错资源。
        const initial = unsafeWindow.__INITIAL_STATE__;
        const cached = unsafeWindow.__playinfo__?.data;
        const pageCid = initial?.cid || initial?.videoData?.cid;
        if (initial?.videoData?.bvid === info.bvid && Number(pageCid) === Number(info.cid) && cached) {
            try {
                if (cached.is_preview || cached.isPreview) throw new Error('当前播放资源为试看内容。');
                return selectFiles(cached, stem);
            } catch (error) { errors.push(error.message); }
        }
        log('尝试获取音视频分离资源。');
        query.set('fnval', '16');
        query.set('platform', 'pc');
        try {
            const data = await getJson(API + '/x/player/playurl?' + query);
            if (data.is_preview || data.isPreview) throw new Error('接口只返回试看资源。');
            return selectFiles(data, stem);
        } catch (error) {
            checkCancelled();
            errors.push(error.message);
            throw new Error(errors.join('\n') + '\n请确认页面能正常播放，并刷新后重试。');
        }
    }

    function downloadError(event) {
        const messages = {
            not_enabled: '请打开油猴管理面板 → 设置，先将“配置模式”设为“高级”，再在“下载”区域将“下载模式”设为“浏览器 API”，保存并允许下载权限，然后刷新视频页面。',
            not_whitelisted: '请在油猴设置的下载扩展名白名单中加入 mp4 和 m4s。',
            not_permitted: '请允许油猴使用浏览器下载权限。',
            not_supported: '当前下载模式不支持。请打开油猴管理面板 → 设置，先将“配置模式”设为“高级”，再在“下载”区域选择“浏览器 API”，保存并刷新视频页面。',
            not_succeeded: '下载未启动或已失败，请查看下面的底层详情及浏览器下载记录。',
            SERVER_FORBIDDEN: '浏览器报告服务器拒绝下载，请刷新页面重新获取资源后重试。',
            SERVER_UNAUTHORIZED: '浏览器报告服务器要求认证，请确认当前账号可以正常播放视频。',
            SERVER_BAD_CONTENT: '浏览器报告资源内容无效，请查看浏览器下载记录。',
            NETWORK_FAILED: '浏览器报告网络失败，请检查网络连接和代理。',
            NETWORK_TIMEOUT: '浏览器报告网络超时，请稍后重试。',
            NETWORK_DISCONNECTED: '浏览器报告网络连接中断。',
            NETWORK_INVALID_REQUEST: '浏览器报告下载请求无效，请查看底层详情。',
            FILE_ACCESS_DENIED: '浏览器报告无法写入文件，请检查实际下载目录的访问权限。',
            FILE_NO_SPACE: '浏览器报告磁盘空间不足。',
            FILE_NAME_TOO_LONG: '浏览器报告文件路径过长，请缩短浏览器下载目录。',
            USER_CANCELED: '浏览器报告下载被取消；若不是手动取消，请查看下载记录中的原因。',
            USER_SHUTDOWN: '浏览器报告下载因浏览器关闭而中断。'
        };
        const code = typeof event === 'string' ? event :
            (typeof event?.error === 'string' ? event.error :
                event?.error?.code || event?.code || event?.reason || 'unknown');
        const serialized = diagnosticText(event);
        let message = messages[code] || '下载失败，油猴返回了未识别的错误；请查看底层详情。';
        if (/invalid request header|unsafe header|forbidden header/i.test(serialized)) {
            message = '浏览器拒绝了下载请求头。请确认已安装当前脚本版本，下载请求不应包含手动设置的 Referer。';
        }
        const error = detailedError(message + '\n错误码：' + code, event);
        error.code = code;
        return error;
    }

    function download(file, index, count) {
        session.stage = '下载第 ' + (index + 1) + '/' + count + ' 个文件';
        session.currentFile = {
            name: file.name,
            kind: file.kind,
            resource: diagnosticUrl(file.url),
            strategy: 'GM_download 浏览器 API，不手动设置请求头',
            expectedLocation: expectedPath(session.directory, file.name),
            startedAt: new Date().toISOString(),
            loadedBytes: 0,
            totalBytes: null
        };
        const currentFile = session.currentFile;
        const prefix = '(' + (index + 1) + '/' + count + ') ' + file.kind;
        log('开始下载：' + file.name + ' [' + file.kind + ']');
        log('资源地址（签名参数已省略）：' + currentFile.resource);
        log('下载方式：浏览器 API；不手动设置 Referer；预期位置：' + currentFile.expectedLocation);
        ui.progress.removeAttribute('value');
        ui.progressText.textContent = prefix + '：正在下载';
        return operation((done, fail) => GM_download({
            url: file.url,
            name: file.name,
            // Chromium 下载 API 对请求头有限制；下载时不传 Referer 或 Cookie。
            saveAs: false,
            conflictAction: 'uniquify',
            onprogress(event) {
                if (cancelled) return;
                const loaded = Number(event.loaded || 0);
                const total = Number(event.total || 0);
                currentFile.loadedBytes = loaded;
                currentFile.totalBytes = total > 0 ? total : null;
                if (total > 0) {
                    const percent = Math.min(100, Math.floor(loaded / total * 100));
                    ui.progress.value = percent;
                    ui.progressText.textContent = prefix + '：' + percent + '%';
                } else {
                    ui.progressText.textContent = prefix + '：已下载 ' + (loaded / 1048576).toFixed(1) + ' MB';
                }
            },
            onload(details) {
                if (cancelled) return;
                currentFile.completedAt = new Date().toISOString();
                ui.progress.value = 100;
                ui.progressText.textContent = prefix + '：下载完成';
                const path = typeof details?.filename === 'string' ? details.filename : '';
                const actualPath = /^(?:[A-Za-z]:[\\/]|\\\\|\/)/.test(path) ? path : null;
                currentFile.actualLocation = actualPath;
                done(actualPath);
            },
            onerror(event) {
                if (cancelled) return;
                currentFile.failedAt = new Date().toISOString();
                fail(downloadError(event));
            },
            ontimeout(event) {
                if (cancelled) return;
                currentFile.failedAt = new Date().toISOString();
                fail(detailedError('下载超时，请查看浏览器下载记录。', event));
            }
        }));
    }

    function expectedPath(directory, filename) {
        const separator = directory.includes('\\') ? '\\' : '/';
        return directory.replace(/[\\/]+$/, '') + separator + filename;
    }

    async function run(convertAfterDownload = false) {
        if (busy) return;
        busy = true;
        cancelled = false;
        activeCancel = null;
        lastReport = '';
        importUri = '';
        ui.openFolder.disabled = true;
        ui.downloadText.disabled = true;
        ui.device.disabled = true;
        ui.script.disabled = true;
        ui.log.textContent = '';
        ui.copy.disabled = true;
        ui.start.disabled = true;
        ui.directory.disabled = true;
        ui.cancel.disabled = false;
        ui.progress.value = 0;
        ui.progressText.textContent = '正在获取视频信息';
        const started = Date.now();
        session = {
            runtime: runtimeInfo(),
            startedAt: new Date().toISOString(),
            page: diagnosticUrl(location.href),
            stage: '检查下载设置',
            directory: ui.directory.value.trim()
        };
        const completed = [];
        const downloadedNames = [];
        session.importFiles = downloadedNames;
        let finalError = null;
        let status = '下载失败';
        try {
            log('脚本 v' + VERSION + '；油猴：' + session.runtime.manager + ' ' +
                session.runtime.managerVersion + '；下载模式：' + session.runtime.downloadMode);
            session.transcription = { device: ui.device.value, ...recognitionOptions(ui.script.value) };
            const directory = session.directory;
            if (!directory) throw new Error('请填写浏览器实际使用的下载目录。');
            GM_setValue('downloadDirectory', directory);
            if (GM_info.downloadMode !== 'browser') {
                throw new Error('请打开油猴管理面板 → 设置，先将“配置模式”设为“高级”，再在“下载”区域将“下载模式”设为“浏览器 API”，保存并允许下载权限，然后刷新视频页面。');
            }
            const pageUrl = new URL(location.href);
            session.stage = '获取视频信息';
            const info = await metadata(pageUrl);
            session.video = info;
            log(info.title + '\nBV：' + info.bvid + '，第 ' + info.part + ' P，CID：' + info.cid);
            const token = new Date().toISOString().replace(/\D/g, '').slice(0, 17);
            const stem = info.bvid + (info.part > 1 ? '_P' + info.part : '') + '_' + token;
            const browserPage = new URL(location.href).href;
            session.pageAtDownloadStart = diagnosticUrl(browserPage);
            session.stage = '获取播放资源';
            const files = await resources(info, stem);
            session.files = files.map(file => ({
                name: file.name, kind: file.kind, resource: diagnosticUrl(file.url)
            }));
            if (files.length > 1) {
                log('将下载 ' + files.length + ' 个文件，尚未合并。仅下载会保留分离文件；选择“下载并提取文字”后，本地端会合并成 MP4。');
            }
            for (let index = 0; index < files.length; index++) {
                checkCancelled();
                const actualPath = await download(files[index], index, files.length);
                const line = files[index].name + '\n' +
                    (actualPath ? '浏览器返回位置：' + actualPath :
                        '预期位置（按配置目录推算）：' + expectedPath(directory, files[index].name));
                completed.push(line);
                downloadedNames.push(actualPath ? actualPath.split(/[\\/]/).pop() : files[index].name);
                log('下载完成：\n' + line);
            }
            session.completed = completed;
            session.importFiles = downloadedNames;
            importUri = buildImportUri(info, downloadedNames, ui.device.value, ui.script.value);
            session.localImportUri = importUri;
            ui.openFolder.disabled = false;
            session.stage = '完成';
            status = '下载完成';
            log('全部下载完成。请在浏览器下载记录中核对位置。');
            ui.progressText.textContent = '下载完成 · 可复制结果';
        } catch (error) {
            finalError = error;
            status = cancelled ? '已取消' : '下载失败';
            ui.progressText.textContent = status;
            log('失败阶段：' + session.stage);
            log(error.message || String(error));
            log('底层详情：\n' + (error.diagnostic || diagnosticText(error)));
            if (completed.length) log('已完成的文件保留在下载目录中。');
        } finally {
            session.elapsedMs = Date.now() - started;
            session.finishedAt = new Date().toISOString();
            log('任务结束：' + status + '；总耗时 ' + session.elapsedMs + ' ms。');
            lastReport = report(status, completed, finalError);
            busy = false;
            activeCancel = null;
            ui.start.disabled = false;
            ui.downloadText.disabled = false;
            ui.openFolder.disabled = downloadedNames.length === 0;
            ui.directory.disabled = false;
            ui.cancel.disabled = true;
            ui.copy.disabled = !lastReport;
            ui.device.disabled = false;
            ui.script.disabled = false;
        }
        if (status === '下载完成' && convertAfterDownload) openLocal();
    }
})();
