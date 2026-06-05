#Requires -Version 5.1
# start.ps1 - Launch the HeadHunter pipeline

$dir     = $PSScriptRoot
$logsDir = Join-Path $dir "logs"
New-Item -ItemType Directory -Force -Path $logsDir | Out-Null

$pidMap = @{}

# --- LLAMA.CPP SERVER ---------------------------------------------------------
$defaultModel = Join-Path $dir "models\Qwen2.5-1.5B-Instruct-Q4_K_M.gguf"
if ($env:LLAMA_MODEL_PATH) {
    $llamaModel = $env:LLAMA_MODEL_PATH
} else {
    $llamaModel = $defaultModel
}

$defaultExe = "C:\Users\Kyle\Desktop\GitHub\llama.cpp\prebuilt\llama-server.exe"
if ($env:LLAMA_SERVER_EXE) {
    $llamaExe = $env:LLAMA_SERVER_EXE
} elseif (Get-Command llama-server -ErrorAction SilentlyContinue) {
    $llamaExe = "llama-server"
} else {
    $llamaExe = $defaultExe
}

$llamaPort = 8081
$llamaUrl  = "http://127.0.0.1:$llamaPort"

if (Test-Path $llamaModel) {
    Write-Host "Starting llama.cpp server..."
    $llamaProc = Start-Process `
        -FilePath $llamaExe `
        -ArgumentList "-m", $llamaModel, "--port", $llamaPort, "-ngl", "99", "-t", "12" `
        -RedirectStandardOutput (Join-Path $logsDir "llama.log") `
        -RedirectStandardError  (Join-Path $logsDir "llama.err") `
        -WindowStyle Hidden `
        -PassThru
    $pidMap["llama"] = $llamaProc.Id

    Write-Host -NoNewline "Waiting for model to load"
    $deadline   = (Get-Date).AddSeconds(300)
    $llamaReady = $false
    while ((Get-Date) -lt $deadline) {
        try {
            $r = Invoke-WebRequest -Uri "$llamaUrl/health" -TimeoutSec 2 -UseBasicParsing -ErrorAction Stop
            if ($r.StatusCode -eq 200 -and $r.Content -match '"ok"') {
                $llamaReady = $true
                break
            }
        } catch {}
        Write-Host -NoNewline "."
        Start-Sleep -Seconds 3
    }
    Write-Host ""

    if ($llamaReady) {
        $errLog = Join-Path $logsDir "llama.err"
        if ((Test-Path $errLog) -and (Select-String -Path $errLog -Pattern "no usable GPU" -Quiet)) {
            Write-Warning "llama.cpp running on CPU only. Inference will be slow."
        } else {
            Write-Host "llama.cpp is ready (GPU)."
        }
    } else {
        Write-Warning "llama.cpp did not become ready within 300s. HeadHunter will fall back to similarity-only mode."
    }
} else {
    Write-Warning "Model not found at: $llamaModel. HeadHunter will fall back to similarity-only mode."
}

Write-Host ""

# --- HEADHUNTER ---------------------------------------------------------------
$log  = Join-Path $logsDir "headhunter.log"
$proc = Start-Process cmd `
    -ArgumentList "/c", "python main.py >> `"$log`" 2>&1" `
    -WorkingDirectory $dir `
    -WindowStyle Hidden `
    -PassThru
$pidMap["headhunter"] = $proc.Id
Write-Host "  [headhunter] started  (PID $($proc.Id))  ->  logs\headhunter.log"

$pidMap | ConvertTo-Json | Set-Content (Join-Path $dir ".pids.json") -Encoding utf8

Write-Host ""
Write-Host "HeadHunter is running."
Write-Host "  UI   : http://localhost:5000"
Write-Host "  LLM  : $llamaUrl"
Write-Host "  Logs : $logsDir"
Write-Host "  Stop : .\stop.ps1"
