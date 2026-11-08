$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$compiler = Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
if (-not (Test-Path -LiteralPath $compiler)) {
    throw 'The Windows .NET Framework C# compiler was not found. Use Start.cmd or python app.py instead.'
}
$sourcePath = Join-Path $projectRoot 'launcher.cs'
$manifestPath = Join-Path $projectRoot 'app.manifest'
$outputPath = Join-Path $projectRoot 'ProblemReview.exe'
& $compiler /nologo /codepage:65001 /platform:x64 /target:winexe /reference:System.Windows.Forms.dll "/win32manifest:$manifestPath" "/out:$outputPath" $sourcePath
if ($LASTEXITCODE -ne 0) { throw 'Launcher build failed.' }
Write-Output "Built $outputPath"
