[CmdletBinding()]
param(
    # A new folder outside Git; the zip, hashes and the full foyer build land here.
    [Parameter(Mandatory)][string]$ArtifactRoot,
    [Parameter(Mandatory)][string]$Version,
    # The helper DLL built from native/ (Release/main.dll of a CMake build root).
    [Parameter(Mandatory)][string]$HelperDll,
    # Development only: passed to Build-Foyer (a dev arrival pose).
    [string]$ArrivalPose='',
    # Development only: a diagnostic spec and its Lua data (combined rounds' T2 test:
    # apply_course_design.py --combined-mode new --out <spec> --lua-out <lua>).
    [string]$SpecPath='',
    [string]$LuaDataPath='',
    # Machine paths, passed on to Build-Foyer.ps1. Each falls back to the same key in
    # build-config.local.json beside the scripts (copy build-config.example.json), or in -ConfigPath.
    # Training Dummy's table rows travel in our archive (shown only when that mod
    # is installed; see compat.lua), so one package works with or without it.
    [string]$ConfigPath='',
    [string]$TrainingDummySpec='',
    [string]$NativeLayoutSource='',
    [string]$NativeBattlePlanSource='',
    [string]$NativeServerBuildSource=''
)
# Builds a player package: the archive triplet, the Lua runtime without
# development tools, the helper DLL, enabled.txt, README.txt, LICENSE.txt and
# CHANGELOG.md, zipped with SHA-256 hashes. No dev.txt: release installs write no telemetry.
$ErrorActionPreference='Stop'
if (Test-Path -LiteralPath $ArtifactRoot) { throw 'Use a new artifact root; retain prior candidates.' }
if (-not (Test-Path -LiteralPath $HelperDll -PathType Leaf)) { throw "Missing $HelperDll" }
function Hash([string]$p) { (Get-FileHash -LiteralPath $p -Algorithm SHA256).Hash }
function CopyVerified([string]$from,[string]$to) {
    New-Item -ItemType Directory -Path (Split-Path $to -Parent) -Force | Out-Null
    Copy-Item -LiteralPath $from -Destination $to
    if ((Hash $from) -ne (Hash $to)) { throw "Copy verification failed: $to" }
}
if(-not $ConfigPath){$ConfigPath=Join-Path $PSScriptRoot 'build-config.local.json'}
$config=@{}
if(Test-Path -LiteralPath $ConfigPath -PathType Leaf){(Get-Content -LiteralPath $ConfigPath -Raw | ConvertFrom-Json).PSObject.Properties | ForEach-Object { $config[$_.Name]=$_.Value }}
function Setting([string]$key,[string]$value) {
    if($value){return $value}
    if($config[$key]){return [string]$config[$key]}
    throw "Set -$key, or $key in $ConfigPath (see build-config.example.json)"
}
# A player package always carries the arrival layout (Build-Foyer treats it as optional).
$TrainingDummySpec=Setting 'TrainingDummySpec' $TrainingDummySpec
$NativeLayoutSource=Setting 'NativeLayoutSource' $NativeLayoutSource
$NativeBattlePlanSource=Setting 'NativeBattlePlanSource' $NativeBattlePlanSource
$NativeServerBuildSource=Setting 'NativeServerBuildSource' $NativeServerBuildSource
$base=$TrainingDummySpec
if (-not (Test-Path -LiteralPath $base -PathType Leaf)) { throw "Missing $base" }
$repoRoot=Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
foreach ($doc in 'LICENSE','CHANGELOG.md') { if (-not (Test-Path -LiteralPath (Join-Path $repoRoot $doc) -PathType Leaf)) { throw "Missing $doc at the repository root" } }
$foyer=Join-Path $ArtifactRoot 'Foyer'
New-Item -ItemType Directory -Path $ArtifactRoot | Out-Null
& (Join-Path $PSScriptRoot 'Build-Foyer.ps1') -Mode Build -ArtifactRoot $foyer -ConfigPath $ConfigPath -TrainingDummySpec $base `
    -NativeLayoutSource $NativeLayoutSource -NativeBattlePlanSource $NativeBattlePlanSource -NativeServerBuildSource $NativeServerBuildSource -ArrivalPose $ArrivalPose -SpecPath $SpecPath -LuaDataPath $LuaDataPath
if (-not (Test-Path -LiteralPath (Join-Path $foyer 'manifest.json'))) { throw 'Foyer build did not finish' }
$manifest=Get-Content -LiteralPath (Join-Path $foyer 'manifest.json') -Raw | ConvertFrom-Json

$folder="JunonColosseum-$Version"
$out=Join-Path $ArtifactRoot $folder
$paks=Join-Path $out 'End\Content\Paks\~mods'
$mod=Join-Path $out 'End\Binaries\Win64\ue4ss\Mods\JunonColosseum'
foreach ($file in $manifest.files) {
    $from=Join-Path $foyer "Package\$($file.name)"
    if ((Hash $from) -ne $file.sha256) { throw 'Package hash mismatch' }
    CopyVerified $from (Join-Path $paks $file.name)
}
foreach ($file in $manifest.runtime) {
    if ($file.name -eq 'devtools.lua') { continue } # development only; main.lua runs without it
    $from=Join-Path $foyer "Runtime\$($file.name)"
    if ((Hash $from) -ne $file.sha256) { throw 'Runtime hash mismatch' }
    CopyVerified $from (Join-Path $mod "Scripts\$($file.name)")
}
CopyVerified $HelperDll (Join-Path $mod 'dlls\main.dll')
[IO.File]::WriteAllText((Join-Path $mod 'enabled.txt'),'',(New-Object Text.UTF8Encoding($false)))
$readme=Get-Content -LiteralPath (Join-Path $PSScriptRoot 'RELEASE-README.txt') -Raw
$readme=$readme.Replace('{VERSION}',$Version)
[IO.File]::WriteAllText((Join-Path $out 'README.txt'),$readme.Replace("`r`n","`n").Replace("`n","`r`n"),(New-Object Text.UTF8Encoding($false)))
CopyVerified (Join-Path $repoRoot 'LICENSE') (Join-Path $out 'LICENSE.txt')
CopyVerified (Join-Path $repoRoot 'CHANGELOG.md') (Join-Path $out 'CHANGELOG.md')

# Release checks: nothing development-only and no machine paths in the scripts.
if (Get-ChildItem -LiteralPath $out -Recurse -File | Where-Object { $_.Name -in 'dev.txt','devtools.lua' }) { throw 'Development file in release' }
$leaks=@(Get-ChildItem -LiteralPath (Join-Path $mod 'Scripts') -File | Select-String -Pattern '[A-Za-z]:[\\/]' -SimpleMatch:$false)
if ($leaks) { throw "Machine path in release scripts: $($leaks[0])" }
$dllText=[Text.Encoding]::ASCII.GetString([IO.File]::ReadAllBytes((Join-Path $mod 'dlls\main.dll')))
$dllPaths=@([regex]::Matches($dllText,'[A-Za-z]:[\\/][ -~]{4,120}') | ForEach-Object Value | Where-Object { $_ -match 'Telemetry' })
if ($dllPaths) { throw "Telemetry path compiled into the helper: $($dllPaths[0])" }

$files=@(Get-ChildItem -LiteralPath $out -Recurse -File | Sort-Object FullName | ForEach-Object {
    [pscustomobject]@{path=$_.FullName.Substring($out.Length+1).Replace('\','/');sha256=(Hash $_.FullName);bytes=$_.Length}
})
$zip=Join-Path $ArtifactRoot "$folder.zip"
Compress-Archive -Path (Join-Path $out '*') -DestinationPath $zip
$files | ForEach-Object { "$($_.sha256)  $($_.path)" } | Set-Content -LiteralPath (Join-Path $ArtifactRoot 'SHA256SUMS.txt') -Encoding ascii
"$(Hash $zip)  $folder.zip" | Add-Content -LiteralPath (Join-Path $ArtifactRoot 'SHA256SUMS.txt') -Encoding ascii
@{version=$Version;zip="$folder.zip";zip_sha256=(Hash $zip);files=$files;helper_sha256=(Hash $HelperDll);
  training_dummy_spec_sha256=(Hash $base);foyer_candidate=$manifest.candidate;native_acceptance='pending'} |
    ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $ArtifactRoot 'release-manifest.json') -Encoding utf8
"RELEASE_BUILT=$zip"
