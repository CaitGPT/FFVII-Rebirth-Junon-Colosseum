[CmdletBinding(SupportsShouldProcess)]
param(
    # Builds the archive and stages the Lua runtime in a new ArtifactRoot. It never
    # touches the game install; Build-Release.ps1 lays out the player zip from it.
    [ValidateSet('Build')][string]$Mode='Build',
    [Parameter(Mandatory)][string]$ArtifactRoot,
    # Machine paths. Each falls back to the same key in build-config.local.json
    # beside this script (copy build-config.example.json), or in -ConfigPath.
    [string]$ConfigPath='',
    [string]$GameRoot='',
    [string]$VanillaRoot='',
    [string]$TrainingDummySpec='',
    [string]$NativeLayoutSource='',
    [string]$NativeBattlePlanSource='',
    [string]$NativeServerBuildSource='',
    # The menu backdrop: the native Musclehead backdrop package (retoc get from pakchunk3,
    # chunk f3d1b7a58bb4056000000002) and 1920x1920 BC7 pixels (our arena photo,
    # blurred and vignetted). Both stay outside Git.
    [string]$BackdropSource='',
    [string]$BackdropPixels='',
    [string]$SpecPath='',
    # Combined rounds' new-row build option (apply_course_design.py --combined-mode new --out ... --lua-out ...):
    # the buffwheel_data.lua that matches -SpecPath. Default: the repository's own.
    [string]$LuaDataPath='',
    # Development only: another arrival pose (e.g. on the arena floor for a screenshot).
    [string]$ArrivalPose='',
    [string]$Retoc='',
    [string]$Packer=''
)
$ErrorActionPreference='Stop'
if(-not $ConfigPath){$ConfigPath=Join-Path $PSScriptRoot 'build-config.local.json'}
$config=@{}
if(Test-Path -LiteralPath $ConfigPath -PathType Leaf){(Get-Content -LiteralPath $ConfigPath -Raw | ConvertFrom-Json).PSObject.Properties | ForEach-Object { $config[$_.Name]=$_.Value }}
function Setting([string]$key,[string]$value,[switch]$Optional) {
    if($value){return $value}
    if($config[$key]){return [string]$config[$key]}
    if($Optional){return ''}
    throw "Set -$key, or $key in $ConfigPath (see build-config.example.json)"
}
$GameRoot=Setting 'GameRoot' $GameRoot
$VanillaRoot=Setting 'VanillaRoot' $VanillaRoot
$TrainingDummySpec=Setting 'TrainingDummySpec' $TrainingDummySpec
$NativeLayoutSource=Setting 'NativeLayoutSource' $NativeLayoutSource -Optional
$NativeBattlePlanSource=Setting 'NativeBattlePlanSource' $NativeBattlePlanSource
$NativeServerBuildSource=Setting 'NativeServerBuildSource' $NativeServerBuildSource
$BackdropSource=Setting 'BackdropSource' $BackdropSource
$BackdropPixels=Setting 'BackdropPixels' $BackdropPixels
$Retoc=Setting 'Retoc' $Retoc
$Packer=Setting 'Packer' $Packer
if(-not $SpecPath){$SpecPath=Join-Path $PSScriptRoot 'data\junon-arena.json'}
if(-not $ArrivalPose){$ArrivalPose=Join-Path $PSScriptRoot 'data\arrival-pose.json'}
$name='JunonColosseum_999_P'
$oldName='JunonColosseum_P'
$paks=Join-Path $GameRoot 'End\Content\Paks'
$stage=Join-Path $ArtifactRoot 'Staging'
$package=Join-Path $ArtifactRoot 'Package'
$runtimeStage=Join-Path $ArtifactRoot 'Runtime'
function Hash([string]$p) { (Get-FileHash -LiteralPath $p -Algorithm SHA256).Hash }
function CopyVerified([string]$from,[string]$to) {
    Copy-Item -LiteralPath $from -Destination $to
    if ((Hash $from) -ne (Hash $to)) { throw "Copy verification failed: $to" }
}
if ($Mode -eq 'Build') {
    if (Test-Path -LiteralPath $ArtifactRoot) { throw 'Use a new artifact root; retain prior candidates.' }
    foreach ($path in @($TrainingDummySpec,$Packer,$SpecPath,$Retoc) + @($LuaDataPath | Where-Object {$_})) {
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Missing $path" }
    }
    $courseSpec=Get-Content -LiteralPath $SpecPath -Raw | ConvertFrom-Json
    $needsBattlePlan=@($courseSpec.tables | Where-Object asset -EQ 'DataObject/Resident/Colosseum.uasset' | ForEach-Object rows | Where-Object {$_.set.UserLevelName -eq '1300-JUNOA_BattlePlan_ModJunonColosseum'}).Count -gt 0
    if($needsBattlePlan -and -not $NativeBattlePlanSource){throw 'Owned Junon courses require -NativeBattlePlanSource; do not pack missing arena assets'}
    if(-not $NativeBattlePlanSource){throw 'The foyer archive now requires the owned arena plans and their native package registrations'}
    # The plan's territory actor gets its enemy spawn/summon lists from the
    # same-named server-build actor in the plan's _ServerBuild companion.
    if(-not $NativeServerBuildSource){throw 'The owned arena also requires -NativeServerBuildSource (2360-UNDRS_BattlePlan_Resident_ServerBuild)'}
    if (-not $PSCmdlet.ShouldProcess($ArtifactRoot,'Build composed data tables and stage the foyer runtime; game installation is unchanged')) { return }
    New-Item -ItemType Directory -Path $stage,$package,$runtimeStage -Force | Out-Null
    $builderRoot=Join-Path $ArtifactRoot 'BuildTools'
    & dotnet build (Join-Path $PSScriptRoot 'tools\DataBuilder\DataBuilder.csproj') -c Release --nologo -v quiet --configfile (Join-Path $PSScriptRoot 'tools\DataBuilder\NuGet.Config') -o $builderRoot
    if ($LASTEXITCODE -ne 0) { throw 'Builder compilation failed' }
    $builder=Join-Path $builderRoot 'JunonColosseum.DataBuilder.dll'
    # The game build the install holds (from its pakchunk4optional prefix): it picks the
    # native store facts and the container prefix. VanillaRoot must be an export of the same build.
    $gameBuild=(& dotnet $builder game-build $paks)
    if ($LASTEXITCODE -ne 0) { throw "Unknown game build in $paks" }
    $storeFacts=if($gameBuild -eq 'steam-2025-01'){Join-Path $PSScriptRoot 'data'}else{Join-Path $PSScriptRoot "data\$gameBuild"}
    foreach($f in 'battle-plan-store.json','battle-plan-serverbuild-store.json','backdrop-store.json'){ if(-not (Test-Path -LiteralPath (Join-Path $storeFacts $f))){ throw "No $f for game build $gameBuild" } }
    "GAME_BUILD=$gameBuild"
    $merged=Join-Path $ArtifactRoot 'merged-spec.json'
    & python (Join-Path $PSScriptRoot 'tools\merge_specs.py') $TrainingDummySpec $SpecPath $merged --show-base-courses-with stfMod_JunonColosseum_TrainingDummyShown
    if ($LASTEXITCODE -ne 0) { throw 'Spec composition failed' }
    & dotnet $builder build $merged $VanillaRoot $stage
    if ($LASTEXITCODE -ne 0) { throw 'Data validation failed' }
    if ($NativeLayoutSource) {
        $layoutOutput=Join-Path $stage 'End\Content\Level\Game\Field\1300-JUNOA\LevelPlan\1300-JUNOA_LevelPlan_MapPoint_Resident.umap'
        & dotnet $builder layout-arrival $NativeLayoutSource $ArrivalPose $layoutOutput
        if ($LASTEXITCODE -ne 0) { throw 'Native arrival layout validation failed' }
        $returnPose=Join-Path $PSScriptRoot 'data\gate-return-pose.json'
        if (Test-Path -LiteralPath $returnPose) {
            & dotnet $builder layout-arrival $layoutOutput $returnPose $layoutOutput
            if ($LASTEXITCODE -ne 0) { throw 'Native gate-return layout validation failed' }
        }
    }
    if($NativeBattlePlanSource){
        foreach($region in '1300-JUNOA','1350-JNONT'){
            $battleOutput=Join-Path $stage "End\Content\Level\Game\Field\$region\BattlePlan\1300-JUNOA_BattlePlan_ModJunonColosseum.umap"
            & dotnet $builder clone-battle-plan $NativeBattlePlanSource (Join-Path $PSScriptRoot 'data\battle-pose.json') $battleOutput
            if($LASTEXITCODE -ne 0){throw 'Owned battle-plan validation failed'}
            $serverOutput=Join-Path $stage "End\Content\Level\Game\Field\$region\BattlePlan\1300-JUNOA_BattlePlan_ModJunonColosseum_ServerBuild.umap"
            & dotnet $builder clone-battle-plan $NativeServerBuildSource (Join-Path $PSScriptRoot 'data\battle-pose.json') $serverOutput
            if($LASTEXITCODE -ne 0){throw 'Owned battle-plan ServerBuild validation failed'}
        }
    }
    $backdropOutput=Join-Path $stage 'End\Content\Menu\Billboard\Common\U_Com_JunonArena_Bg1.uasset'
    & dotnet $builder clone-backdrop $BackdropSource $BackdropPixels $backdropOutput
    if($LASTEXITCODE -ne 0){throw 'Backdrop texture validation failed'}
    foreach ($file in 'main.lua','gate.lua','foyer.lua','invitation.lua','flow.lua','battle_plan.lua','buffwheel.lua','buffwheel_data.lua','devtools.lua','branding.lua','paths.lua','compat.lua','leash.lua') { $from=if($file -eq 'buffwheel_data.lua' -and $LuaDataPath){$LuaDataPath}else{Join-Path $PSScriptRoot "ue4ss\JunonColosseum\Scripts\$file"}; CopyVerified $from (Join-Path $runtimeStage $file) }
    # UnrealReZen supplies an empty pak stub, but its zen archive omits new
    # packages and their store entries. Retain that output for diagnosis; stage
    # and register all actual raw packages through the native-format writer.
    $legacy=Join-Path $ArtifactRoot 'LegacyPackage'
    $raw=Join-Path $ArtifactRoot 'RawContainer'
    $rawPacked=Join-Path $ArtifactRoot 'RawPackage'
    New-Item -ItemType Directory -Path $legacy,$rawPacked -Force | Out-Null
    Push-Location -LiteralPath (Split-Path $Packer -Parent)
    try {
        & $Packer --content-path $stage --compression-format Zlib --engine-version GAME_UE4_26 --game-dir $paks --output-path (Join-Path $legacy "$name.utoc")
        if ($LASTEXITCODE -ne 0) { throw 'Packaging failed' }
    } finally { Pop-Location }
    # Every merged table, the arrival layout and the four owned arena maps.
    $mergedSpec=Get-Content -LiteralPath $merged -Raw | ConvertFrom-Json
    $expectedPaths=@($mergedSpec.tables.asset | Sort-Object -Unique).Count + [int][bool]$NativeLayoutSource + 5
    & dotnet $builder stage-raw-container $stage ((Join-Path $storeFacts 'battle-plan-store.json')+';'+(Join-Path $storeFacts 'battle-plan-serverbuild-store.json')+';'+(Join-Path $storeFacts 'backdrop-store.json')) $raw $expectedPaths $paks
    if($LASTEXITCODE -ne 0){throw 'Raw package registration failed'}
    & $Retoc pack-raw $raw (Join-Path $rawPacked "$name.utoc")
    if($LASTEXITCODE -ne 0){throw 'Native raw-container packing failed'}
    & dotnet $builder prefix-container (Join-Path $rawPacked "$name.utoc") (Join-Path $package "$name.utoc") $expectedPaths $paks
    if($LASTEXITCODE -ne 0){throw 'Lossless container prefix/offset validation failed'}
    CopyVerified (Join-Path $legacy "$name.pak") (Join-Path $package "$name.pak")
    & $Retoc verify (Join-Path $package "$name.utoc")
    if($LASTEXITCODE -ne 0){throw 'Final archive chunk verification failed'}
    $readback=Join-Path $ArtifactRoot 'ArchiveReadback'
    & $Retoc unpack-raw (Join-Path $package "$name.utoc") $readback
    if($LASTEXITCODE -ne 0){throw 'Final archive could not be read back'}
    $rawManifest=Get-Content -LiteralPath (Join-Path $raw 'manifest.json') -Raw | ConvertFrom-Json
    $readManifest=Get-Content -LiteralPath (Join-Path $readback 'manifest.json') -Raw | ConvertFrom-Json
    $chunkFiles=@(Get-ChildItem -LiteralPath (Join-Path $raw 'chunks') -File)
    if($chunkFiles.Count -ne $expectedPaths+1 -or @($readManifest.chunk_paths.PSObject.Properties).Count -ne $expectedPaths){throw 'Final archive omitted an expected package'}
    foreach($chunk in $chunkFiles){if((Hash $chunk.FullName) -ne (Hash (Join-Path $readback "chunks\$($chunk.Name)"))){throw 'Final archive changed a chunk'}}
    foreach($entry in $rawManifest.chunk_paths.PSObject.Properties){if($readManifest.chunk_paths.($entry.Name) -ne $entry.Value){throw 'Final package path mismatch'}}
    $info=(& $Retoc info (Join-Path $package "$name.utoc")) -join "`n"
    if($LASTEXITCODE -ne 0 -or $info -notmatch '(?m)^\s+packages: 5\s*$'){throw 'All four new arena packages and the backdrop must have native store registrations'}
    $info | Set-Content -LiteralPath (Join-Path $ArtifactRoot 'archive-info.txt')
    @{exact_chunk_readbacks=$expectedPaths+1;package_paths=$expectedPaths;registered_new_packages=5;native_acceptance='pending'} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $ArtifactRoot 'archive-readback.json')
    $files=@(foreach ($extension in '.pak','.ucas','.utoc') {
        $p=Join-Path $package ($name+$extension)
        @{name=(Split-Path $p -Leaf);sha256=(Hash $p);bytes=(Get-Item -LiteralPath $p).Length}
    })
    $scripts=@(foreach ($file in 'main.lua','gate.lua','foyer.lua','invitation.lua','flow.lua','battle_plan.lua','buffwheel.lua','buffwheel_data.lua','devtools.lua','branding.lua','paths.lua','compat.lua','leash.lua') { @{name=$file;sha256=(Hash (Join-Path $runtimeStage $file))} })
    @{candidate=(Split-Path $ArtifactRoot -Leaf);game_build=$gameBuild;vanilla_root=$VanillaRoot;package=$name;previous_package=$oldName;files=$files;runtime=$scripts;spec_sha256=(Hash $SpecPath);training_dummy_spec_sha256=(Hash $TrainingDummySpec);builder_sha256=(Hash $builder);retoc_sha256=(Hash $Retoc);archive_paths=$expectedPaths;archive_registered_new_packages=5;archive_chunks=$expectedPaths+1;archive_readback_exact=$true;native_layout_source=$NativeLayoutSource;native_battle_plan_source=$NativeBattlePlanSource;native_server_build_source=$NativeServerBuildSource;arrival_pose_sha256=(Hash $ArrivalPose);native_acceptance='pending'} | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $ArtifactRoot 'manifest.json') -Encoding utf8
    'FOYER_BUILT=true'
    return
}
