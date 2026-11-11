param(
    [Parameter(Mandatory)][string]$BuildDirectory,
    # Machine paths. Each falls back to the same key in build-config.local.json
    # beside this script (copy build-config.example.json), or in -ConfigPath.
    [string]$ConfigPath='',
    # cmake.exe (Visual Studio 2022's bundled CMake works).
    [string]$CMake='',
    # RE-UE4SS v3.0.1 source with its submodules (the C++ mod template's RE-UE4SS folder).
    [string]$Ue4ssSource='',
    # The UEPseudo headers that match it (needs Epic-linked GitHub access).
    [string]$UEPseudoSource='',
    [string]$ImguiSource='',
    [string]$ImguiTextEditSource='',
    # UE4SS.lib, the import library of the UE4SS 3.0.1 DLL the mod runs under.
    [string]$Ue4ssImportLib=''
)
# Builds the native helper (Release\main.dll) from native/. The release zip's
# Mods\JunonColosseum\dlls\main.dll is this file.
$ErrorActionPreference='Stop'
if(-not $ConfigPath){$ConfigPath=Join-Path $PSScriptRoot 'build-config.local.json'}
$config=@{}
if(Test-Path -LiteralPath $ConfigPath -PathType Leaf){(Get-Content -LiteralPath $ConfigPath -Raw | ConvertFrom-Json).PSObject.Properties | ForEach-Object { $config[$_.Name]=$_.Value }}
function Setting([string]$key,[string]$value) {
    if($value){return $value}
    if($config[$key]){return [string]$config[$key]}
    throw "Set -$key, or $key in $ConfigPath (see build-config.example.json)"
}
$cmakeExe=Setting 'CMake' $CMake
& $cmakeExe -S (Join-Path $PSScriptRoot 'native') -B $BuildDirectory -G 'Visual Studio 17 2022' -A x64 `
    "-DUE4SS_SOURCE=$(Setting 'Ue4ssSource' $Ue4ssSource)" `
    "-DUEPSEUDO_SOURCE=$(Setting 'UEPseudoSource' $UEPseudoSource)" `
    "-DIMGUI_SOURCE=$(Setting 'ImguiSource' $ImguiSource)" `
    "-DIMGUI_TEXT_EDIT_SOURCE=$(Setting 'ImguiTextEditSource' $ImguiTextEditSource)" `
    "-DUE4SS_IMPORT_LIB=$(Setting 'Ue4ssImportLib' $Ue4ssImportLib)"
if($LASTEXITCODE -ne 0){throw 'Native identity configure failed'}
& $cmakeExe --build $BuildDirectory --config Release -- /m
if($LASTEXITCODE -ne 0){throw 'Native identity compilation failed'}
Get-FileHash -LiteralPath (Join-Path $BuildDirectory 'Release\main.dll') -Algorithm SHA256
