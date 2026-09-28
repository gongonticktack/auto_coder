param([switch]$CheckOnly)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$runtime = Join-Path $root '.runtime'
$downloads = Join-Path $runtime 'downloads'
$logs = Join-Path $runtime 'logs'
$launched = @()
$serverJob = $null

Add-Type -TypeDefinition @'
using System;
using System.ComponentModel;
using System.Diagnostics;
using System.Runtime.InteropServices;

public sealed class FretlabServerJob : IDisposable {
    [StructLayout(LayoutKind.Sequential)]
    private struct BasicLimitInformation {
        public long PerProcessUserTimeLimit, PerJobUserTimeLimit;
        public uint LimitFlags;
        public UIntPtr MinimumWorkingSetSize, MaximumWorkingSetSize;
        public uint ActiveProcessLimit;
        public UIntPtr Affinity;
        public uint PriorityClass, SchedulingClass;
    }
    [StructLayout(LayoutKind.Sequential)]
    private struct IoCounters {
        public ulong ReadOperationCount, WriteOperationCount, OtherOperationCount;
        public ulong ReadTransferCount, WriteTransferCount, OtherTransferCount;
    }
    [StructLayout(LayoutKind.Sequential)]
    private struct ExtendedLimitInformation {
        public BasicLimitInformation BasicLimitInformation;
        public IoCounters IoInfo;
        public UIntPtr ProcessMemoryLimit, JobMemoryLimit, PeakProcessMemoryUsed, PeakJobMemoryUsed;
    }
    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern IntPtr CreateJobObject(IntPtr attributes, string name);
    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern bool SetInformationJobObject(IntPtr job, int infoClass, ref ExtendedLimitInformation info, uint length);
    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern bool AssignProcessToJobObject(IntPtr job, IntPtr process);
    [DllImport("kernel32.dll")]
    private static extern bool CloseHandle(IntPtr handle);

    private IntPtr handle;
    public FretlabServerJob() {
        handle = CreateJobObject(IntPtr.Zero, null);
        if (handle == IntPtr.Zero) throw new Win32Exception(Marshal.GetLastWin32Error());
        var info = new ExtendedLimitInformation();
        info.BasicLimitInformation.LimitFlags = 0x2000; // JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if (!SetInformationJobObject(handle, 9, ref info, (uint)Marshal.SizeOf(typeof(ExtendedLimitInformation)))) {
            int error = Marshal.GetLastWin32Error();
            Dispose();
            throw new Win32Exception(error);
        }
    }
    public void Add(Process process) {
        if (!AssignProcessToJobObject(handle, process.Handle))
            throw new Win32Exception(Marshal.GetLastWin32Error());
    }
    public void Dispose() {
        if (handle != IntPtr.Zero) { CloseHandle(handle); handle = IntPtr.Zero; }
        GC.SuppressFinalize(this);
    }
    ~FretlabServerJob() { Dispose(); }
}
'@

function Say([string]$message) { Write-Host "[Fretlab] $message" }

function Assert-Exit([string]$step) {
  if ($LASTEXITCODE -ne 0) { throw "$step failed (exit code $LASTEXITCODE)." }
}

function Download-File([string]$url, [string]$path) {
  if (Test-Path -LiteralPath $path) { return }
  Say "Downloading $url"
  Invoke-WebRequest -Uri $url -OutFile $path -UseBasicParsing
  if (-not (Test-Path -LiteralPath $path)) { throw "Download failed: $url" }
}

function Python-Valid([string]$path) {
  if (-not (Test-Path -LiteralPath $path)) { return $false }
  & $path -c 'import sys; assert sys.version_info[:2] in ((3, 10), (3, 11))' 2>$null
  return $LASTEXITCODE -eq 0
}

function Web-Ready {
  try {
    $response = Invoke-WebRequest 'http://127.0.0.1:5173/' -UseBasicParsing -TimeoutSec 2
    return $response.StatusCode -eq 200 -and $response.Content -match '<title>Fretlab'
  } catch { return $false }
}

function Api-Ready {
  try {
    $health = Invoke-RestMethod 'http://127.0.0.1:8000/api/health' -TimeoutSec 2
    return $health.ok -eq $true -and $health.ffmpeg -eq $true
  } catch { return $false }
}

function Wait-Ready([scriptblock]$probe, [string]$name, [int]$processId) {
  for ($attempt = 0; $attempt -lt 60; $attempt++) {
    if (& $probe) { return }
    $process = Get-Process -Id $processId -ErrorAction SilentlyContinue
    if (-not $process) { throw "$name exited. Check .runtime\logs for details." }
    Start-Sleep -Milliseconds 500
  }
  throw "$name did not become ready. Check .runtime\logs for details."
}

try {
  if (-not [Environment]::Is64BitOperatingSystem -or $env:PROCESSOR_ARCHITECTURE -ne 'AMD64') {
    throw 'This launcher currently supports 64-bit Windows on x64 PCs.'
  }
  New-Item -ItemType Directory -Force -Path $runtime, $downloads, $logs | Out-Null

  # Use an existing Node.js 20+ or download a verified portable official build.
  $nodeCommand = Get-Command node.exe -ErrorAction SilentlyContinue
  $npmCommand = Get-Command npm.cmd -ErrorAction SilentlyContinue
  $nodeExe = $null
  $npmExe = $null
  if ($nodeCommand -and $npmCommand) {
    $nodeVersion = & $nodeCommand.Source --version 2>$null
    if ($LASTEXITCODE -eq 0 -and $nodeVersion -match '^v(\d+)' -and [int]$Matches[1] -ge 20) {
      $nodeExe = $nodeCommand.Source
      $npmExe = $npmCommand.Source
    }
  }
  if (-not $nodeExe) {
    $nodeVersion = '22.23.3'
    $archiveName = "node-v$nodeVersion-win-x64.zip"
    $nodeDir = Join-Path $runtime "node-v$nodeVersion-win-x64"
    $nodeExe = Join-Path $nodeDir 'node.exe'
    $npmExe = Join-Path $nodeDir 'npm.cmd'
    if (-not (Test-Path -LiteralPath $nodeExe)) {
      if ($CheckOnly) { throw 'Node.js 20+ is missing.' }
      $archive = Join-Path $downloads $archiveName
      $manifest = Join-Path $downloads "node-v$nodeVersion-SHASUMS256.txt"
      $base = "https://nodejs.org/dist/v$nodeVersion"
      Download-File "$base/SHASUMS256.txt" $manifest
      Download-File "$base/$archiveName" $archive
      $line = Get-Content -LiteralPath $manifest | Where-Object { $_ -match ('\s+' + [regex]::Escape($archiveName) + '$') } | Select-Object -First 1
      if (-not $line) { throw 'Node.js checksum entry is missing.' }
      $expected = ($line -split '\s+')[0].ToLowerInvariant()
      $actual = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant()
      if ($actual -ne $expected) { throw 'Node.js archive checksum mismatch.' }
      Say 'Extracting Node.js...'
      Expand-Archive -LiteralPath $archive -DestinationPath $runtime -Force
    }
  }
  if (-not (Test-Path -LiteralPath $npmExe)) { throw 'npm.cmd was not found.' }
  $env:PATH = "$(Split-Path -Parent $nodeExe);$env:PATH"
  Say "Node.js: $(& $nodeExe --version)"

  $lockfile = Join-Path $root 'package-lock.json'
  $webStamp = Join-Path $runtime 'package-lock.sha256'
  $lockHash = (Get-FileHash -LiteralPath $lockfile -Algorithm SHA256).Hash
  if (-not (Test-Path -LiteralPath (Join-Path $root 'node_modules\vite\bin\vite.js')) -or
      -not (Test-Path -LiteralPath $webStamp) -or
      (Get-Content -LiteralPath $webStamp -Raw).Trim() -ne $lockHash) {
    if ($CheckOnly) { throw 'Web dependencies are not ready.' }
    Say 'Installing web libraries from package-lock.json...'
    Push-Location $root
    try {
      & $npmExe install --no-audit --no-fund
      Assert-Exit 'npm install'
    } finally { Pop-Location }
    Set-Content -LiteralPath $webStamp -Value $lockHash -Encoding ascii
  }

  # Python.org's application-local ZIP includes pip and venv. No system install is needed.
  $venvPython = Join-Path $runtime 'venv\Scripts\python.exe'
  if (-not (Python-Valid $venvPython)) {
    $pythonExe = $null
    if ($env:FRETLAB_PYTHON -and (Python-Valid $env:FRETLAB_PYTHON)) {
      $pythonExe = $env:FRETLAB_PYTHON
    } else {
      $localPython = Join-Path $runtime 'python311\python.exe'
      if (Python-Valid $localPython) { $pythonExe = $localPython }
    }
    if (-not $pythonExe) {
      if ($CheckOnly) { throw 'Python 3.11 is missing.' }
      $archive = Join-Path $downloads 'python-3.11.9-amd64.zip'
      Download-File 'https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.zip' $archive
      $expected = '4ba90a4ab8990891033d37ff04d2047fdae8948d0d2729a68d3a6a17c585b681'
      $actual = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant()
      if ($actual -ne $expected) { throw 'Python archive checksum mismatch.' }
      $target = Join-Path $runtime 'python311'
      Say 'Extracting Python 3.11 locally...'
      Expand-Archive -LiteralPath $archive -DestinationPath $target -Force
      $pythonExe = Join-Path $target 'python.exe'
      if (-not (Python-Valid $pythonExe)) { throw 'Python 3.11 runtime could not be verified.' }
    }
    Say 'Creating the project Python environment...'
    & $pythonExe -m venv (Join-Path $runtime 'venv')
    Assert-Exit 'Python venv'
    if (-not (Python-Valid $venvPython)) { throw 'Python environment could not be verified.' }
  }
  Say "Python: $(& $venvPython --version)"

  $requirements = Join-Path $root 'backend\requirements.txt'
  $apiStamp = Join-Path $runtime 'requirements.sha256'
  $requirementsHash = (Get-FileHash -LiteralPath $requirements -Algorithm SHA256).Hash
  if (-not (Test-Path -LiteralPath $apiStamp) -or
      (Get-Content -LiteralPath $apiStamp -Raw).Trim() -ne $requirementsHash) {
    if ($CheckOnly) { throw 'API dependencies are not ready.' }
    Say 'Installing FastAPI, audio libraries, and AI models. This first run can take several minutes...'
    & $venvPython -m pip install --disable-pip-version-check -r $requirements
    Assert-Exit 'pip install'
    Set-Content -LiteralPath $apiStamp -Value $requirementsHash -Encoding ascii
  }
  & $venvPython -c 'from imageio_ffmpeg import get_ffmpeg_exe; from basic_pitch import ICASSP_2022_MODEL_PATH; import tensorflow, demucs; from backend.transcription import predict_notes; print(get_ffmpeg_exe()); print(ICASSP_2022_MODEL_PATH)'
  Assert-Exit 'Audio dependency check'

  $env:TORCH_HOME = Join-Path $runtime 'torch'
  $env:HF_HOME = Join-Path $runtime 'huggingface'
  $env:HF_HUB_DISABLE_SYMLINKS_WARNING = '1'
  New-Item -ItemType Directory -Force -Path $env:TORCH_HOME, $env:HF_HOME | Out-Null
  if ($env:FRETLAB_SKIP_DEMUCS -ne '1') {
    $modelStamp = Join-Path $runtime 'htdemucs_6s.hf.ready'
    if (-not (Test-Path -LiteralPath $modelStamp)) {
      if ($CheckOnly) { throw 'Demucs model weights are not ready.' }
      Say 'Downloading Demucs htdemucs_6s model weights...'
      & $venvPython -c "from demucs.pretrained import get_model; get_model('htdemucs_6s')"
      Assert-Exit 'Demucs model download'
      Set-Content -LiteralPath $modelStamp -Value 'htdemucs_6s' -Encoding ascii
    }
  }

  if ($CheckOnly) { Say 'All required runtimes, libraries, and model weights are ready.'; exit 0 }

  if (Api-Ready -or Web-Ready) {
    throw 'A Fretlab server is already running. Close its original console before starting another one.'
  }
  $serverJob = [FretlabServerJob]::new()

  if (-not (Api-Ready)) {
    $apiOut = Join-Path $logs 'api.out.log'
    $apiErr = Join-Path $logs 'api.err.log'
    Say 'Starting API...'
    $apiProcess = Start-Process -FilePath $venvPython -ArgumentList @('-m','uvicorn','backend.main:app','--host','127.0.0.1','--port','8000') `
      -WorkingDirectory $root -WindowStyle Hidden -RedirectStandardOutput $apiOut -RedirectStandardError $apiErr -PassThru
    $launched += $apiProcess
    $serverJob.Add($apiProcess)
    Wait-Ready ${function:Api-Ready} 'API' $apiProcess.Id
  }

  if (-not (Web-Ready)) {
    Say 'Preparing alphaTab fonts and starting web server...'
    Push-Location $root
    try { & $nodeExe (Join-Path $root 'scripts\copy-font.mjs'); Assert-Exit 'alphaTab fonts' }
    finally { Pop-Location }
    $webOut = Join-Path $logs 'web.out.log'
    $webErr = Join-Path $logs 'web.err.log'
    $webProcess = Start-Process -FilePath $nodeExe -ArgumentList @('node_modules/vite/bin/vite.js','--host','127.0.0.1','--port','5173','--strictPort') `
      -WorkingDirectory $root -WindowStyle Hidden -RedirectStandardOutput $webOut -RedirectStandardError $webErr -PassThru
    $launched += $webProcess
    $serverJob.Add($webProcess)
    Wait-Ready ${function:Web-Ready} 'Web server' $webProcess.Id
  }

  Say 'Ready: http://127.0.0.1:5173/'
  Say 'Keep this console open. Closing it stops both servers.'
  Say "Server logs: $logs"
  if ($env:FRETLAB_NO_BROWSER -ne '1') { Start-Process 'http://127.0.0.1:5173/' }
  while ($true) {
    Start-Sleep -Seconds 2
    foreach ($process in $launched) {
      if ($process.HasExited) { throw "A server exited. Check $logs for details." }
    }
  }
} catch {
  Write-Error "[Fretlab] $($_.Exception.Message)"
  exit 1
} finally {
  if ($serverJob) { $serverJob.Dispose() }
}
