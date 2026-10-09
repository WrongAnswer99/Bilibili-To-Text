const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('bilibili-download.user.js', 'utf8');

const bvid = 'BV1ewwxesEu4';
const video = { bvid, cid: 123, title: '测试视频', pages: [{ page: 1, cid: 123 }, { page: 2, cid: 456 }] };
const mp4 = { format: 'mp4720', durl: [{ url: 'https://example.bilivideo.com/test.mp4' }] };
const dash = { dash: {
    video: [
        { id: 64, codecs: 'avc1.4D4020', baseUrl: 'https://example.bilivideo.com/avc.m4s' },
        { id: 64, codecs: 'hev1.1.6', baseUrl: 'https://example.bilivideo.com/hevc.m4s' }
    ],
    audio: [{ bandwidth: 192000, baseUrl: 'https://example.bilivideo.com/audio.m4s' }]
} };

async function scenario(options = {}) {
    const elements = Object.fromEntries(['directory', 'start', 'cancel', 'copy', 'progress', 'progressText', 'log', 'device', 'script', 'downloadText', 'openFolder'].map(id => [id, {
        value: '', textContent: '', disabled: false, listeners: {},
        addEventListener(event, callback) { this.listeners[event] = callback; },
        removeAttribute() {}, scrollTop: 0, scrollHeight: 0
    }]));
    const downloads = [];
    const requests = [];
    const storage = {};
    let aborted = false;
    const root = { innerHTML: '', getElementById(id) { return elements[id]; } };
    const context = {
        document: { body: { appendChild() {} }, createElement() { return {
            style: {}, attachShadow() { return root; }
        }; }},
        URL, URLSearchParams, Date, console,
        location: { href: 'https://www.bilibili.com/video/' + bvid + '/' + (options.part ? '?p=' + options.part : '') },
        unsafeWindow: options.cached || {},
        GM_info: { downloadMode: options.mode || 'browser', version: '5.3.2', scriptHandler: 'Tampermonkey' },
        navigator: { userAgent: 'Test Edge Browser' },
        GM_getValue: (key, fallback) => key === 'downloadDirectory' ? 'C:\\Users\\admin\\Downloads' : (options[key] || fallback),
        GM_setValue(key, value) { storage[key] = value; },
        GM_setClipboard(value) { storage.clipboard = value; },
        GM_xmlhttpRequest(details) {
            requests.push(details);
            const url = new URL(details.url);
            const payload = url.pathname.endsWith('/view')
                ? (options.viewError ? { code: -412, message: 'test view error' } : { code: 0, data: video })
                : (options.apiError ? { code: -400, message: 'test api error' } : { code: 0, data: options.data || mp4 });
            setImmediate(() => details.onload({
                status: options.httpStatus || 200,
                statusText: options.httpStatus ? 'Forbidden' : 'OK',
                responseText: options.invalidJson ? '<html>error</html>' : JSON.stringify(payload)
            }));
            return { abort() { details.onabort(); } };
        },
        GM_download(details) {
            downloads.push(details);
            if (options.syncError) throw new Error('Invalid request header name: Referer');
            const index = downloads.length;
            setImmediate(() => {
                if (options.cancel) { elements.cancel.listeners.click(); return; }
                if (options.downloadError || (options.failSecond && index === 2)) {
                    details.onerror(options.errorEvent || { error: options.downloadError || 'SERVER_FORBIDDEN' });
                    return;
                }
                details.onprogress({ loaded: 50, total: 100 });
                details.onload(options.actualPath ? { filename: options.actualPath } : undefined);
            });
            return { abort() { aborted = true; } };
        }
    };
    vm.runInNewContext(source, context);
    await elements[options.convert === false ? 'start' : 'downloadText'].listeners.click();
    if (!elements.copy.disabled) elements.copy.listeners.click();
    return { elements, downloads, requests, storage, aborted, context };
}

(async () => {
    let s = await scenario();
    assert.equal(s.downloads.length, 1);
    assert.match(s.downloads[0].name, /^BV1ewwxesEu4_\d{17}\.mp4$/);
    assert.equal(s.downloads[0].saveAs, false);
    assert.equal(s.downloads[0].headers, undefined, 'Do not pass restricted HTTP headers to browser downloads');
    assert.match(s.elements.log.textContent, /预期位置.*C:\\Users\\admin\\Downloads\\/);
    assert.doesNotMatch(s.elements.log.textContent, /浏览器返回位置/);
    assert.equal(s.elements.start.disabled, false);
    assert.match(s.storage.clipboard, /油猴不保证返回真实路径/);
    assert.equal(s.requests[0].anonymous, false);
    assert.equal(s.elements.openFolder.disabled, false);
    let uri = new URL(s.context.location.href);
    assert.equal(uri.protocol, 'bilibilitotext:');
    assert.equal(uri.hostname, 'import');
    assert.equal(uri.searchParams.get('bv'), bvid);
    assert.equal(uri.searchParams.get('device'), 'gpu');
    assert.equal(uri.searchParams.get('script'), 'simplified');
    assert.deepEqual(uri.searchParams.getAll('file'), [s.downloads[0].name]);
    s.elements.device.value = 'cpu';
    s.elements.script.value = 'traditional';
    const previousDownloads = s.downloads.length;
    s.context.location.href = 'https://www.bilibili.com/video/' + bvid + '/';
    await s.elements.downloadText.listeners.click();
    assert.equal(s.downloads.length, previousDownloads, 'Retry must reuse the completed download');
    uri = new URL(s.context.location.href);
    assert.equal(uri.searchParams.get('device'), 'cpu');
    assert.equal(uri.searchParams.get('script'), 'traditional');

    for (const [selection, language, script] of [
        ['en', 'en', 'simplified'], ['simplified', 'zh', 'simplified'],
        ['ja', 'ja', 'simplified'], ['ru', 'ru', 'simplified'],
        ['traditional', 'zh', 'traditional'], ['auto', 'auto', 'simplified']
    ]) {
        const selected = await scenario({ recognitionLanguage: selection });
        const request = new URL(selected.context.location.href);
        assert.equal(request.searchParams.get('lang'), language);
        assert.equal(request.searchParams.get('script'), script);
    }

    s = await scenario({ convert: false });
    assert.equal(s.downloads.length, 1);
    assert.match(s.context.location.href, /^https:/, 'Download-only must never open a local application');
    assert.equal(s.elements.openFolder.disabled, false);
    s.elements.openFolder.listeners.click();
    uri = new URL(s.context.location.href);
    assert.equal(uri.hostname, 'open-folder');
    assert.deepEqual(uri.searchParams.getAll('file'), [s.downloads[0].name]);
    assert.equal(s.downloads.length, 1, 'Opening the folder must not redownload');

    s = await scenario({ data: dash });
    assert.equal(s.downloads.length, 2);
    assert.equal(s.downloads[0].url, 'https://example.bilivideo.com/avc.m4s');
    assert.match(s.downloads[0].name, /\.video\.m4s$/);
    assert.match(s.downloads[1].name, /\.audio\.m4s$/);
    assert.match(s.elements.log.textContent, /无声音/);
    assert.deepEqual(new URL(s.context.location.href).searchParams.getAll('file'),
                     s.downloads.map(item => item.name));

    s = await scenario({ part: 2 });
    assert.match(s.downloads[0].name, /_P2_/);
    assert.equal(new URL(s.requests[1].url).searchParams.get('cid'), '456');

    s = await scenario({ viewError: true, cached: { __INITIAL_STATE__: { videoData: video } } });
    assert.equal(s.downloads.length, 1);
    assert.match(s.elements.log.textContent, /使用当前页面的视频信息/);

    s = await scenario({ apiError: true, cached: {
        __INITIAL_STATE__: { cid: 123, videoData: video }, __playinfo__: { data: dash }
    }});
    assert.equal(s.downloads.length, 2);

    s = await scenario({ apiError: true, cached: {
        __INITIAL_STATE__: { cid: 456, videoData: video }, __playinfo__: { data: dash }
    }});
    assert.equal(s.downloads.length, 0, 'Must not use stale playback data from another part');
    assert.equal(s.elements.progressText.textContent, '下载失败');

    s = await scenario({ downloadError: 'not_whitelisted' });
    assert.equal(s.elements.progressText.textContent, '下载失败');
    assert.match(s.elements.log.textContent, /白名单/);
    assert.equal(s.elements.openFolder.disabled, true);
    assert.match(s.context.location.href, /^https:/);
    assert.doesNotMatch(s.elements.log.textContent, /全部下载完成/);

    s = await scenario({ cancel: true });
    assert.equal(s.aborted, true);
    assert.equal(s.elements.progressText.textContent, '已取消');
    assert.equal(s.elements.start.disabled, false);
    assert.doesNotMatch(s.elements.log.textContent, /全部下载完成/);

    s = await scenario({ mode: 'disabled' });
    assert.equal(s.requests.length, 0);
    assert.match(s.elements.log.textContent, /浏览器 API/);

    s = await scenario({ actualPath: 'D:\\Custom\\download.mp4' });
    assert.match(s.elements.log.textContent, /浏览器返回位置：D:\\Custom\\download.mp4/);

    const errorEvent = { error: 'unknown', details: {
        message: 'Invalid request header name: Referer',
        source: 'https://example.bilivideo.com/a.mp4?upsig=TOPSECRET&deadline=999999',
        Cookie: 'SESSDATA=PRIVATE', Authorization: 'PRIVATE', responseText: 'PRIVATE'
    }};
    errorEvent.details.cycle = errorEvent;
    s = await scenario({ downloadError: 'unknown', errorEvent });
    assert.match(s.storage.clipboard, /Invalid request header name: Referer/);
    assert.match(s.storage.clipboard, /错误码：unknown/);
    assert.match(s.storage.clipboard, /失败阶段：下载第 1\/1 个文件/);
    assert.match(s.storage.clipboard, /脚本 v0.3.1/);
    assert.match(s.storage.clipboard, /Tampermonkey 5.3.2/);
    assert.match(s.storage.clipboard, /Test Edge Browser/);
    assert.match(s.storage.clipboard, /循环引用/);
    assert.match(s.storage.clipboard, /完整日志/);
    assert.doesNotMatch(s.storage.clipboard, /TOPSECRET|PRIVATE/);

    s = await scenario({ syncError: true });
    assert.match(s.storage.clipboard, /Invalid request header name: Referer/);
    assert.match(s.storage.clipboard, /stack/);
    assert.equal(s.elements.start.disabled, false);

    s = await scenario({ data: dash, failSecond: true });
    assert.equal(s.elements.progressText.textContent, '下载失败');
    assert.match(s.storage.clipboard, /已完成文件/);
    assert.match(s.storage.clipboard, /错误码：SERVER_FORBIDDEN/);
    assert.match(s.storage.clipboard, /失败阶段：下载第 2\/2 个文件/);

    s = await scenario({ httpStatus: 403 });
    assert.equal(s.downloads.length, 0);
    assert.match(s.storage.clipboard, /接口 HTTP 403/);
    assert.match(s.storage.clipboard, /"status": 403/);

    s = await scenario({ invalidJson: true });
    assert.equal(s.downloads.length, 0);
    assert.match(s.storage.clipboard, /接口诊断/);

    console.log('PASS: 16 userscript scenarios plus 6 language selections including independent download, linked conversion, folder opening, retry and parameter forwarding (MP4, DASH, current part, page fallback, stale data rejection, error, cancel, permission, paths).');
})().catch(error => { console.error(error); process.exitCode = 1; });
