param(
    [switch]$Check, [string]$Source = '', [switch]$LockedSource,
    [switch]$AutoStart, [switch]$ExitAfterJob,
    [ValidateSet('cpu', 'gpu')][string]$Device = 'gpu',
    [ValidateSet('simplified', 'traditional')][string]$ChineseScript = 'simplified',
    [string]$Language = 'zh'
)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[System.Windows.Forms.Application]::EnableVisualStyles()

# Native event callbacks queue output; the GUI timer reads it on the UI thread.
if (-not ('PipelineProcess' -as [type])) {
    Add-Type -TypeDefinition @"
using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Diagnostics;
using System.Text;

public sealed class PipelineProcess : IDisposable {
    private Process process;
    private readonly ConcurrentQueue<string> lines = new ConcurrentQueue<string>();
    private volatile bool outputEnded, errorEnded;
    public static string Quote(string value) {
        var result = new StringBuilder("\"");
        int slashes = 0;
        foreach (char c in value) {
            if (c == '\\') { slashes++; continue; }
            if (c == '"') { result.Append('\\', slashes * 2 + 1); result.Append('"'); }
            else { result.Append('\\', slashes); result.Append(c); }
            slashes = 0;
        }
        result.Append('\\', slashes * 2); result.Append('"');
        return result.ToString();
    }
    public void Start(string python, string[] arguments, string directory) {
        var info = new ProcessStartInfo(python, String.Join(" ", Array.ConvertAll(arguments, Quote)));
        info.WorkingDirectory = directory;
        info.UseShellExecute = false;
        info.CreateNoWindow = true;
        info.RedirectStandardOutput = true;
        info.RedirectStandardError = true;
        info.StandardOutputEncoding = Encoding.UTF8;
        info.StandardErrorEncoding = Encoding.UTF8;
        process = new Process { StartInfo = info };
        process.OutputDataReceived += (sender, e) => { if (e.Data == null) outputEnded = true; else lines.Enqueue("O|" + e.Data); };
        process.ErrorDataReceived += (sender, e) => { if (e.Data == null) errorEnded = true; else lines.Enqueue("E|" + e.Data); };
        process.Start();
        process.BeginOutputReadLine(); process.BeginErrorReadLine();
    }
    public string[] ReadLines() {
        var result = new List<string>(); string value;
        while (result.Count < 256 && lines.TryDequeue(out value)) result.Add(value);
        return result.ToArray();
    }
    public bool Finished { get { return process != null && process.HasExited && outputEnded && errorEnded; } }
    public int ExitCode { get { return process.ExitCode; } }
    public void Stop() {
        if (process == null) return;
        try {
            if (process.HasExited) return;
            var info = new ProcessStartInfo("taskkill.exe", "/PID " + process.Id + " /T /F");
            info.UseShellExecute = false; info.CreateNoWindow = true;
            using (var killer = Process.Start(info)) { killer.WaitForExit(3000); }
        } catch { try { process.Kill(); } catch {} }
    }
    public void Dispose() { Stop(); if (process != null) { process.Dispose(); process = null; } }
}
"@
}

$project = $PSScriptRoot
$script:LockedSource = [bool]$LockedSource
$script:worker = $null
$script:clock = New-Object Diagnostics.Stopwatch
$script:cancelled = $false
$script:lastError = ''
$script:lastStderr = ''
$script:stage = ''

$form = New-Object Windows.Forms.Form
$form.Text = 'BilibiliToText — 本地视频转文字'
$form.ClientSize = New-Object Drawing.Size(760, 600)
$form.MinimumSize = New-Object Drawing.Size(780, 639)
$form.StartPosition = 'CenterScreen'
$form.Font = New-Object Drawing.Font('Microsoft YaHei UI', 9)
$form.BackColor = [Drawing.Color]::White

$title = New-Object Windows.Forms.Label
$title.Text = '本地视频转文字'
$title.Font = New-Object Drawing.Font('Microsoft YaHei UI', 18, [Drawing.FontStyle]::Bold)
$title.SetBounds(20, 16, 720, 38)
$form.Controls.Add($title)

$intro = New-Object Windows.Forms.Label
$intro.Text = "选择本地视频，使用本项目内的 Whisper 生成文字和字幕。`r`nTXT 和 SRT 保存在视频原文件夹；按视频语音选择语言，不确定时选自动检测。默认 GPU 和简体中文。"
$intro.ForeColor = [Drawing.Color]::FromArgb(80, 80, 80)
$intro.SetBounds(20, 65, 720, 48)
$intro.Anchor = 'Top, Left, Right'
$form.Controls.Add($intro)

$linkLabel = New-Object Windows.Forms.Label
$linkLabel.Text = '视频文件路径'
$linkLabel.SetBounds(20, 125, 240, 24)
$form.Controls.Add($linkLabel)

$deviceLabel = New-Object Windows.Forms.Label
$deviceLabel.Text = '识别设备'
$deviceLabel.SetBounds(496, 125, 70, 24)
$deviceLabel.Anchor = 'Top, Right'
$form.Controls.Add($deviceLabel)
$deviceBox = New-Object Windows.Forms.ComboBox
$deviceBox.DropDownStyle = 'DropDownList'
[void]$deviceBox.Items.Add('GPU（NVIDIA）')
[void]$deviceBox.Items.Add('CPU')
$deviceBox.SelectedIndex = 0
$deviceBox.SetBounds(574, 122, 166, 26)
$deviceBox.Anchor = 'Top, Right'
$form.Controls.Add($deviceBox)

$scriptLabel = New-Object Windows.Forms.Label
$scriptLabel.Text = '识别语言'
$scriptLabel.SetBounds(276, 125, 70, 24)
$scriptLabel.Anchor = 'Top, Right'
$form.Controls.Add($scriptLabel)
$scriptBox = New-Object Windows.Forms.ComboBox
$scriptBox.DropDownStyle = 'DropDownList'
$modeLanguages = @('en', 'zh', 'ja', 'ru', 'zh', 'auto')
$modeScripts = @('simplified', 'simplified', 'simplified', 'simplified', 'traditional', 'simplified')
@('英语', '简体中文', '日语', '俄语', '繁体中文', '自动检测') | ForEach-Object { [void]$scriptBox.Items.Add($_) }
$scriptBox.SelectedIndex = 1
$scriptBox.SetBounds(350, 122, 126, 26)
$scriptBox.Anchor = 'Top, Right'
$form.Controls.Add($scriptBox)

$linkBox = New-Object Windows.Forms.TextBox
$linkBox.SetBounds(20, 154, 526, 30)
$linkBox.Anchor = 'Top, Left, Right'
$form.Controls.Add($linkBox)

$startButton = New-Object Windows.Forms.Button
$startButton.Text = '开始转换'
$startButton.SetBounds(20, 244, 124, 36)
$form.Controls.Add($startButton)
$form.AcceptButton = $startButton

$cancelButton = New-Object Windows.Forms.Button
$cancelButton.Text = '取消'
$cancelButton.Enabled = $false
$cancelButton.SetBounds(154, 244, 80, 36)
$form.Controls.Add($cancelButton)

$browseButton = New-Object Windows.Forms.Button
$browseButton.Text = if ($script:LockedSource) { '打开文件所在位置' } else { '打开文件...' }
$browseButton.SetBounds(558, 151, 182, 32)
$browseButton.Anchor = 'Top, Right'
$form.Controls.Add($browseButton)
$browseButton.Add_Click({
    if ($script:LockedSource) {
        if (Test-Path -LiteralPath $linkBox.Text -PathType Leaf) {
            Start-Process explorer.exe -ArgumentList ('/select,"' + $linkBox.Text + '"')
        } else { Write-Log '视频不存在，请检查文件是否被移动或删除' }
        return
    }
    $picker = New-Object Windows.Forms.OpenFileDialog
    $picker.Filter = '视频文件|*.mp4;*.mkv;*.mov;*.webm;*.avi;*.m4v;*.flv;*.ts|所有文件|*.*'
    if ($picker.ShowDialog() -eq 'OK') { $linkBox.Text = $picker.FileName }
    $picker.Dispose()
})

$threadsLabel = New-Object Windows.Forms.Label
$threadsLabel.Text = 'CPU 线程'
$threadsLabel.SetBounds(20, 205, 82, 24)
$form.Controls.Add($threadsLabel)
$threadsBox = New-Object Windows.Forms.NumericUpDown
$threadsBox.Minimum = 0
$threadsBox.Maximum = 256
$threadsBox.Value = 8
$threadsBox.SetBounds(108, 201, 74, 26)
$form.Controls.Add($threadsBox)

$overwriteBox = New-Object Windows.Forms.CheckBox
$overwriteBox.Text = '重新识别（覆盖已有文字和字幕）'
$overwriteBox.SetBounds(450, 201, 290, 28)
$overwriteBox.Anchor = 'Top, Right'
$form.Controls.Add($overwriteBox)

$finishButton = New-Object Windows.Forms.Button
$finishButton.Text = '完成'
$finishButton.SetBounds(620, 550, 120, 34)
$finishButton.Anchor = 'Bottom, Right'
$finishButton.Add_Click({ $form.Close() })
$form.Controls.Add($finishButton)

$otherButton = New-Object Windows.Forms.Button
$otherButton.Text = '转换其他视频'
$otherButton.SetBounds(470, 550, 140, 34)
$otherButton.Anchor = 'Bottom, Right'
$otherButton.Visible = [bool]$script:LockedSource
$otherButton.Add_Click({
    if ($null -ne $script:worker) { return }
    $script:LockedSource = $false
    $script:ExitAfterJob = $false
    $linkBox.ReadOnly = $false
    $linkBox.Enabled = $true
    $linkBox.Clear()
    $browseButton.Text = '打开文件...'
    $otherButton.Visible = $false
    $footer.Width = 440
    $statusLabel.Text = '等待选择本地视频'
    $logBox.Clear()
    $script:lastLogWasProgress = $false
    $script:lastError = ''; $script:lastStderr = ''; $script:stage = ''
    $script:cancelled = $false
    $script:clock.Reset()
    $elapsedLabel.Text = '00:00:00'
    $progress.Style = 'Continuous'
    $progress.Value = 0
    $linkBox.Focus()
})
$form.Controls.Add($otherButton)

$outputFolderButton = New-Object Windows.Forms.Button
$outputFolderButton.Text = '打开输出文件夹'
$outputFolderButton.SetBounds(470, 550, 140, 34)
$outputFolderButton.Anchor = 'Bottom, Right'
$form.Controls.Add($outputFolderButton)
function Update-OutputFolderButton {
    $outputFolderButton.Visible = -not [bool]$script:LockedSource
    $path = $linkBox.Text.Trim().Trim([char]34)
    $outputFolderButton.Enabled = [bool]($path -and (Test-Path -LiteralPath $path -PathType Leaf -ErrorAction SilentlyContinue))
}
$linkBox.Add_TextChanged({ Update-OutputFolderButton })
$outputFolderButton.Add_Click({
    $path = $linkBox.Text.Trim().Trim([char]34)
    if (-not (Test-Path -LiteralPath $path -PathType Leaf -ErrorAction SilentlyContinue)) {
        Write-Log '请先选择已有的本地视频文件'
        Update-OutputFolderButton
        return
    }
    try {
        $folder = [IO.Path]::GetDirectoryName([IO.Path]::GetFullPath($path))
        Start-Process explorer.exe -ArgumentList ('"' + $folder + '"')
    } catch { Write-Log ('无法打开输出文件夹：' + $_.Exception.Message) }
})
Update-OutputFolderButton

$statusLabel = New-Object Windows.Forms.Label
$statusLabel.Text = if ($script:LockedSource) { '已接收视频，路径已锁定' } else { '等待选择本地视频' }
$statusLabel.Font = New-Object Drawing.Font('Microsoft YaHei UI', 11)
$statusLabel.SetBounds(20, 296, 585, 28)
$statusLabel.Anchor = 'Top, Left, Right'
$form.Controls.Add($statusLabel)

$elapsedLabel = New-Object Windows.Forms.Label
$elapsedLabel.Text = '00:00:00'
$elapsedLabel.TextAlign = 'MiddleRight'
$elapsedLabel.SetBounds(630, 296, 110, 28)
$elapsedLabel.Anchor = 'Top, Right'
$form.Controls.Add($elapsedLabel)

$progress = New-Object Windows.Forms.ProgressBar
$progress.SetBounds(20, 332, 720, 14)
$progress.Anchor = 'Top, Left, Right'
$form.Controls.Add($progress)

$logBox = New-Object Windows.Forms.TextBox
$logBox.Multiline = $true
$logBox.ReadOnly = $true
$logBox.ScrollBars = 'Vertical'
$logBox.BackColor = [Drawing.Color]::FromArgb(247, 248, 250)
$logBox.SetBounds(20, 361, 720, 176)
$logBox.Anchor = 'Top, Bottom, Left, Right'
$form.Controls.Add($logBox)

$footer = New-Object Windows.Forms.Label
$footer.Text = 'TXT/SRT 保存在视频原文件夹 · 原视频不移动、不改名'
$footer.ForeColor = [Drawing.Color]::Gray
$footer.SetBounds(20, 558, 440, 22)
$footer.Anchor = 'Bottom, Left, Right'
$form.Controls.Add($footer)

function Write-Log([string]$Message, [switch]$Progress) {
    if ($Progress -and $script:lastLogWasProgress -and $logBox.TextLength -gt 0) {
        # Remove only the previous logical progress line, preserving stage/error messages.
        $tail = $logBox.Text.TrimEnd([char[]]"`r`n")
        $start = $tail.LastIndexOf("`n") + 1
        $logBox.Select($start, $logBox.TextLength - $start)
        $logBox.SelectedText = ''
    }
    $script:lastLogWasProgress = $Progress.IsPresent
    $logBox.AppendText(('[' + (Get-Date -Format 'HH:mm:ss') + '] ' + $Message + "`r`n"))
    if ($logBox.TextLength -gt 18000) { $logBox.Text = $logBox.Text.Substring($logBox.TextLength - 12000) }
    $logBox.SelectionStart = $logBox.TextLength
    $logBox.ScrollToCaret()
}

$stageNames = @{
    import = '正在导入本地视频…'; merge = '正在合并视频和音轨…'; extract = '正在提取音频…'
    init = '正在加载语音模型…'; transcribe = '正在识别语音，请稍候…'
    convert = '正在转换中文繁简体…'; save = '正在保存文字和字幕…'; done = '转换完成，TXT 和 SRT 已保存到视频原文件夹'; error = '转换失败'
}

$timer = New-Object Windows.Forms.Timer
$timer.Interval = 150
$timer.Add_Tick({
    if ($null -eq $script:worker) { return }
    $elapsedLabel.Text = $script:clock.Elapsed.ToString('hh\:mm\:ss')
    foreach ($line in $script:worker.ReadLines()) {
        if ($line.StartsWith('E|')) { $script:lastStderr = $line.Substring(2); continue }
        $content = $line.Substring(2)
        if (-not $content.StartsWith('STATUS|')) { continue }
        $parts = $content.Split([char[]]'|', 3, [StringSplitOptions]::None)
        $script:stage = $parts[1]
        $message = $parts[2]
        if ($stageNames.ContainsKey($script:stage)) { $statusLabel.Text = $stageNames[$script:stage] }
        if ($script:stage -eq 'transcribe' -and $message -match '^(GPU|CPU) progress (\d+)%$') {
            $statusLabel.Text = '正在使用 ' + $Matches[1] + ' 识别语音：' + $Matches[2] + '%'
            $progress.Style = 'Continuous'
            $progress.Value = [Math]::Min(100, [int]$Matches[2])
            Write-Log $statusLabel.Text -Progress
        } elseif ($script:stage -eq 'transcribe' -and $message.Contains('NVIDIA GPU')) {
            $statusLabel.Text = '正在使用 NVIDIA GPU 识别语音…'
            Write-Log $statusLabel.Text
        } elseif ($script:stage -eq 'warning' -and $message -match '^Whisper UTF-8 replacements: (\d+)$') {
            Write-Log ('识别结果中有 ' + $Matches[1] + ' 处不完整字符，已用 � 标记，其余文字已保留')
        } elseif ($script:stage -eq 'error') {
            $script:lastError = $message
            Write-Log ('转换失败：' + $message)
        } elseif ($script:stage -eq 'done') {
            Write-Log $statusLabel.Text
            Write-Log $message
        } else { Write-Log $statusLabel.Text }
    }
    if ($script:worker.Finished) {
        $timer.Stop()
        $script:clock.Stop()
        $exitCode = $script:worker.ExitCode
        $script:worker.Dispose()
        $script:worker = $null
        $startButton.Enabled = $true; $linkBox.Enabled = $true
        $cancelButton.Enabled = $false; $browseButton.Enabled = $true; $deviceBox.Enabled = $true; $scriptBox.Enabled = $true
        $threadsBox.Enabled = $true; $overwriteBox.Enabled = $true; $finishButton.Enabled = $true; $otherButton.Enabled = $true
        $progress.Style = 'Continuous'
        if ($script:cancelled) { $statusLabel.Text = '已取消，原视频保留'; $progress.Value = 0; Write-Log $statusLabel.Text }
        elseif ($exitCode -eq 0) { $statusLabel.Text = $stageNames.done; $progress.Value = 100 }
        else {
            $statusLabel.Text = '转换失败，请查看下方日志'; $progress.Value = 0
            if (-not $script:lastError) { Write-Log ('进程退出：' + $exitCode + ' ' + $script:lastStderr) }
        }
        $result = @{ pid = $PID; source = $linkBox.Text; locked_source = [bool]$script:LockedSource; path_readonly = $linkBox.ReadOnly; browse_text = $browseButton.Text; language_selection = $scriptBox.Text; finish_enabled = $finishButton.Enabled; other_video_visible = $otherButton.Visible; other_video_enabled = $otherButton.Enabled; output_folder_visible = $outputFolderButton.Visible; output_folder_enabled = $outputFolderButton.Enabled; exit_code = $exitCode; status = $statusLabel.Text; log = $logBox.Text }
        $result | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $project '.work/gui-last-run.json') -Encoding UTF8
        if ($ExitAfterJob) { $form.Close() }
    }
})

$startButton.Add_Click({
    $videoPath = $linkBox.Text.Trim().Trim([char]34)
    $isLocal = (Test-Path -LiteralPath $videoPath -PathType Leaf -ErrorAction SilentlyContinue) -and ([IO.Path]::GetExtension($videoPath).ToLowerInvariant() -in @('.mp4', '.mkv', '.mov', '.webm', '.avi', '.m4v', '.flv', '.ts'))
    if (-not $isLocal) {
        $statusLabel.Text = '请选择已有的本地视频文件'
        $linkBox.Focus(); return
    }
    $videoPath = [IO.Path]::GetFullPath($videoPath)
    $linkBox.Text = $videoPath
    try {
        $python = $null
        $configPath = Join-Path $project 'config.json'
        if (Test-Path -LiteralPath $configPath) {
            $settings = [IO.File]::ReadAllText($configPath, [Text.Encoding]::UTF8) | ConvertFrom-Json
            if ($settings.python -and (Test-Path -LiteralPath $settings.python)) { $python = $settings.python }
        }
        if (-not $python) { $python = (Get-Command python.exe -CommandType Application -ErrorAction Stop | Select-Object -First 1).Source }
        $device = if ($deviceBox.SelectedIndex -eq 0) { 'gpu' } else { 'cpu' }
        $chineseScript = $modeScripts[$scriptBox.SelectedIndex]
        $selectedLanguage = $modeLanguages[$scriptBox.SelectedIndex]
        $arguments = @('-u', (Join-Path $project 'transcribe_video.py'), $videoPath, '--device', $device, '--chinese-script', $chineseScript, '--lang', $selectedLanguage, '--threads', [string]$threadsBox.Value)
        if ($overwriteBox.Checked) { $arguments += '--overwrite' }
        $script:worker = New-Object PipelineProcess
        $script:worker.Start($python, [string[]]$arguments, $project)
        $script:cancelled = $false; $script:lastError = ''; $script:lastStderr = ''
        $logBox.Clear()
        $script:clock.Restart()
        $startButton.Enabled = $false; $linkBox.Enabled = $false
        $cancelButton.Enabled = $true; $browseButton.Enabled = [bool]$script:LockedSource; $deviceBox.Enabled = $false; $scriptBox.Enabled = $false
        $threadsBox.Enabled = $false; $overwriteBox.Enabled = $false; $finishButton.Enabled = $false; $otherButton.Enabled = $false
        $progress.Style = 'Marquee'; $progress.MarqueeAnimationSpeed = 30
        $statusLabel.Text = '正在启动转换…'
        Write-Log $statusLabel.Text
        $timer.Start()
    } catch {
        if ($null -ne $script:worker) { $script:worker.Dispose(); $script:worker = $null }
        $statusLabel.Text = '无法启动，请检查 Python 环境'
        Write-Log $_.Exception.Message
    }
})
$cancelButton.Add_Click({
    if ($null -ne $script:worker) {
        $script:cancelled = $true; $cancelButton.Enabled = $false
        $statusLabel.Text = '正在取消…'; $script:worker.Stop()
    }
})
$form.Add_FormClosing({
    $timer.Stop()
    if ($null -ne $script:worker) { $script:worker.Dispose(); $script:worker = $null }
})

$linkBox.ReadOnly = [bool]$script:LockedSource
if ($Source) { $linkBox.Text = $Source }
if ($Device -eq 'cpu') { $deviceBox.SelectedIndex = 1 }
$selection = [Array]::IndexOf($modeLanguages, $Language)
if ($selection -lt 0) {
    [void]$scriptBox.Items.Add($Language)
    $modeLanguages += $Language
    $modeScripts += $ChineseScript
    $selection = $modeLanguages.Count - 1
}
if ($Language -eq 'zh' -and $ChineseScript -eq 'traditional') { $selection = 4 }
$scriptBox.SelectedIndex = $selection
if ($AutoStart) { $form.Add_Shown({ $startButton.PerformClick() }) }

if ($Check) {
    $work = Join-Path $project '.work'
    New-Item -ItemType Directory -Force -Path $work | Out-Null
    $form.ShowInTaskbar = $false
    $form.Opacity = 0
    $form.Show()
    [Windows.Forms.Application]::DoEvents()
    $form.PerformLayout()
    $bitmap = New-Object Drawing.Bitmap($form.Width, $form.Height)
    $form.DrawToBitmap($bitmap, (New-Object Drawing.Rectangle(0, 0, $form.Width, $form.Height)))
    $bitmap.Save((Join-Path $work 'gui-preview.png'), [Drawing.Imaging.ImageFormat]::Png)
    @{ source = $linkBox.Text; path_readonly = $linkBox.ReadOnly; browse_text = $browseButton.Text; finish_text = $finishButton.Text; other_video_visible = $otherButton.Visible; other_video_text = $otherButton.Text; output_folder_visible = $outputFolderButton.Visible; output_folder_enabled = $outputFolderButton.Enabled; language_selection = $scriptBox.Text; language_options = @($scriptBox.Items) } |
        ConvertTo-Json | Set-Content -LiteralPath (Join-Path $work 'gui-preview-state.json') -Encoding UTF8
    $bitmap.Dispose(); $form.Dispose(); $timer.Dispose()
    Write-Output 'PASS: GUI controls and background worker compiled; preview written to .work/gui-preview.png'
    return
}
try { [void]$form.ShowDialog() }
finally { $timer.Dispose(); $form.Dispose() }
