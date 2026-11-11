local paths = require('paths')
-- New foyer board. Borrows a native quest-board mesh; after a save made in the
-- foyer, the native helper loads it (see request_mesh).
local M = {}
local battle_plan=require('battle_plan')
local ROOT = paths.telemetry('junon-colosseum-foyer.json')
local flag='stfMod_JunonColosseum_RocheDefeated'
local board_id='oblMod_JunonColosseum_Noticeboard'
local board_pos={X=-122466.8125,Y=32274.336915,Z=6170}
local board_yaw=60
local mesh,library,display,point=nil,nil,nil,nil
local halted=false
local lever_removed=false
local lever_matched,lever_destroyed=0,0
local next_lever_scan=0
local item_count=-1
local battle_capture_at,battle_captured,field_captured=nil,false,false
local battle_plan_state='not_requested'
local mesh_request='not_requested'
local function valid(o) return o~=nil and o:IsValid() end
-- Opt-in diagnostics: a flag file in the dev.txt telemetry folder. The captures
-- walk thousands of objects (a multi-second hitch), so they never run by default.
local function diagnostics(name)
    local f=paths.open(name,'rb')
    if f then f:close();return true end
    return false
end
local function q(s) return '"'..tostring(s):gsub('\\','\\\\'):gsub('"','\\"'):gsub('[\r\n]',' ')..'"' end
-- The Check point sits at the centre of the board: the centre of the displayed
-- board's bounds, nudged out of the panel along its facing. The mesh origin is
-- off to one side of the panel, so a fixed offset from it put the marker at the
-- panel's left edge. Fixed offset only if the bounds cannot be read.
-- Z stays inside the native hook's foyer box (6000-6500).
local point_front=20
local point_forward,point_height=15,120
local point_source,point_at='none',nil
local function board_centre()
    local origin,extent={},{}
    local ok=pcall(function() display:GetActorBounds(false,origin,extent,false) end)
    if not ok then return nil end
    local ok2,x,y,z,ez=pcall(function() return origin.X,origin.Y,origin.Z,extent.Z end)
    if not ok2 or type(x)~='number' or type(y)~='number' or type(z)~='number' or type(ez)~='number' then return nil end
    local dx,dy=x-board_pos.X,y-board_pos.Y
    if ez<10 or dx*dx+dy*dy>300*300 or math.abs(z-board_pos.Z)>400 then return nil end
    return x,y,z
end
local function point_pos()
    local yaw=math.rad(board_yaw)
    local fx,fy=math.cos(yaw),math.sin(yaw)
    local x,y,z=nil,nil,nil
    if valid(display) then x,y,z=board_centre() end
    if x then
        point_source='board_bounds_centre'
        point_at={X=x+point_front*fx,Y=y+point_front*fy,Z=math.max(6010,math.min(6490,z))}
    else
        point_source='fixed_offset'
        point_at={X=board_pos.X+point_forward*fx,Y=board_pos.Y+point_forward*fy,Z=board_pos.Z+point_height}
    end
    return point_at
end
-- Fit the spawn points to Junon's arena. Our ServerBuild is Gold Saucer's: its
-- spawn offsets reach 26 m from the centre, but Junon's arena floor is a circle
-- of about 20 m radius with gates north and south (navmesh, 2026-11-09), and
-- the territory's no-escape wall is 27 m across. Enemies placed past the walls
-- were stuck outside. Scale every point list's offsets (about the territory
-- point) so none is farther than SPAWN_RADIUS: all ServerBuild spawn, flying,
-- raycast and summon lists (large enemies such as Elfadunk use the _2L-and-up
-- lists, which first went unfitted and put one 25 m out), and the territory's
-- own mob distribution points. Names are from the UE4SS header dump: never
-- read a member a class lacks. Once per loaded actor; each write is verified
-- by reading it back (as the Biome Randomizer does).
local SPAWN_RADIUS=1200
local SERVER_LISTS={}
for _,size in ipairs({'S','M','L','2L','3L','4L'}) do
    for _,kind in ipairs({'TerritoryGroundSpawnPoints_','TerritoryFlySpawnPoints_','TerritoryFlySpawnPointsRaycast_'}) do
        SERVER_LISTS[#SERVER_LISTS+1]=kind..size
    end
end
for _,list in ipairs({'OmenSummonPoints','OmenAdditionalSummonPoints','GroundSummonPoints','GroundAdditionalSummonPoints','AirSummonPoints','AirAdditionalSummonPoints'}) do
    SERVER_LISTS[#SERVER_LISTS+1]=list
end
local TERRITORY_LISTS={'TerritoryMobDistributionSpawnPoints'}
local fitted={}
local fit_state,next_fit,was_ready='not_run',0,false
local fit_whole=0 -- lists that needed the whole-array fallback
local FIT_SETTLE=10 -- seconds after the arena levels are ready, clear of the load
local function fit_list(actor,list)
    local arr=actor[list]
    local n=arr:GetArrayNum()
    if n==0 then return 0,1 end
    local far=0
    for i=1,n do local t=arr[i].Translation; far=math.max(far,math.sqrt(t.X*t.X+t.Y*t.Y)) end
    if far<=SPAWN_RADIUS then return far,1 end
    local scale=SPAWN_RADIUS/far
    -- In place: replacing the whole array frees the engine's old allocation, and
    -- a worker thread reading it during the load then crashes (2026-11-10: six
    -- load crashes on TaskGraphThreadHP since the fit arrived). Whole-array
    -- assignment is kept only as a fallback if the in-place write did not land.
    local copied={}
    for i=1,n do
        local t=arr[i].Translation
        copied[i]={X=t.X*scale,Y=t.Y*scale}
        t.X=copied[i].X; t.Y=copied[i].Y
    end
    local landed=true
    for i=1,n do
        local t=actor[list][i].Translation
        if math.abs(t.X-copied[i].X)>=0.01 or math.abs(t.Y-copied[i].Y)>=0.01 then landed=false;break end
    end
    if not landed then
        local whole={}
        for i=1,n do
            local v=arr[i]
            whole[i]={Rotation={X=v.Rotation.X,Y=v.Rotation.Y,Z=v.Rotation.Z,W=v.Rotation.W},
                      Translation={X=copied[i].X,Y=copied[i].Y,Z=v.Translation.Z},
                      Scale3D={X=v.Scale3D.X,Y=v.Scale3D.Y,Z=v.Scale3D.Z}}
        end
        actor[list]=whole
        fit_whole=fit_whole+1
    end
    local back=actor[list]
    assert(back:GetArrayNum()==n,'point list count changed: '..list)
    for i=1,n do
        local t=back[i].Translation
        assert(math.abs(t.X-copied[i].X)<0.01 and math.abs(t.Y-copied[i].Y)<0.01,'point readback differs: '..list)
    end
    return far,scale
end
-- Exact paths: a lookup by path is cheap; FindAllOf over a class took ~100 ms
-- each time and, repeated every 5 s, caused frame hitches.
local FIT_PATHS={
    EndFieldEnemyTerritoryServerBuildActor='/Game/Level/Game/Field/1300-JUNOA/BattlePlan/1300-JUNOA_BattlePlan_ModJunonColosseum_ServerBuild.1300-JUNOA_BattlePlan_ModJunonColosseum_ServerBuild:PersistentLevel.UCBattle_TerritoryCmnActor',
    EndFieldEnemyTerritoryActor='/Game/Level/Game/Field/1300-JUNOA/BattlePlan/1300-JUNOA_BattlePlan_ModJunonColosseum.1300-JUNOA_BattlePlan_ModJunonColosseum:PersistentLevel.UCBattle_TerritoryCmnActor',
}
local function fit_actor(class,lists)
    local actor=StaticFindObject(FIT_PATHS[class])
    if not valid(actor) then
        -- The native helper's path lookup missed the ServerBuild actor; search the
        -- class instead. Only until fitted (then fit_done stops all lookups).
        actor=nil
        for _,value in ipairs(FindAllOf(class) or {}) do
            if valid(value) and value:GetFullName():find('ModJunonColosseum',1,true) and value:GetFullName():find('UCBattle_TerritoryCmnActor',1,true) then actor=value;break end
        end
    end
    if not valid(actor) then return 'no_'..class end
    local address=actor:GetAddress()
    if fitted[class]==address then return nil end
    fitted[class]=address -- never replay an uncertain write
    local changed,biggest=0,0
    for _,list in ipairs(lists) do
        local far,scale=fit_list(actor,list)
        if scale<1 then changed=changed+1 end
        biggest=math.max(biggest,far)
    end
    local valid_note=''
    if class=='EndFieldEnemyTerritoryServerBuildActor' then
        -- Gold Saucer's flags mark all six ground summon points invalid; Roche's
        -- native arena here marks all six valid. Mu spawns with MuHole sub-characters
        -- and never spawned with them invalid (testing, 2026-11-09).
        local n=actor.GroundSummonPoints:GetArrayNum()
        if actor.ValidGroundSummonPoints:GetArrayNum()==n and n>0 then
            local flags=actor.ValidGroundSummonPoints
            for i=1,n do flags[i]=true end -- in place, as above
            local back,t=actor.ValidGroundSummonPoints,0
            for i=1,back:GetArrayNum() do if back[i]==true then t=t+1 end end
            valid_note=string.format(', ground summon points valid %d/%d',t,n)
        end
    end
    return string.format('%s %d lists fitted (whole-array fallbacks %d), farthest %.0f%s',class,changed,fit_whole,biggest,valid_note)
end
local fit_done=false
local function fit_spawn_points()
    if fit_done then return end
    local parts={}
    for _,result in ipairs({fit_actor('EndFieldEnemyTerritoryServerBuildActor',SERVER_LISTS),fit_actor('EndFieldEnemyTerritoryActor',TERRITORY_LISTS)}) do
        if result then parts[#parts+1]=result end
    end
    if #parts>0 then fit_state=table.concat(parts,'; ') end
    -- Both fitted: stop looking until our levels load again (see M.tick).
    fit_done=fitted.EndFieldEnemyTerritoryServerBuildActor~=nil and fitted.EndFieldEnemyTerritoryActor~=nil
end
-- Read-only scan of the arena's levels and territory actors. `out` names the
-- telemetry file: one capture in battle, one in the foyer once it is ready.
local function capture_battle_plan(out)
    local rows,seen,counts={},{},{}
    local can_package=valid(StaticFindObject('/Script/Engine.LevelStreaming:GetWorldAssetPackageFName'))
    local can_loaded=valid(StaticFindObject('/Script/Engine.LevelStreaming:GetLoadedLevel'))
    for _,class in ipairs({'LevelStreaming','LevelStreamingKismet','LevelStreamingDynamic','LevelStreamingAlwaysLoaded'}) do
        counts[class]=0
        for _,object in ipairs(FindAllOf(class) or {}) do
            if valid(object) then
                counts[class]=counts[class]+1
                local id=object:GetFullName()
                if not seen[id] then
                    seen[id]=true
                    local package=can_package and object:GetWorldAssetPackageFName():ToString() or id
                    local level=can_loaded and object:GetLoadedLevel() or nil
                    local loaded=valid(level) and level:GetFullName() or ''
                    if package:find('BattlePlan',1,true) or package:find('Btl_Navigation',1,true) or package:find('ModJunon',1,true) or loaded:find('ModJunon',1,true) then
                        rows[#rows+1]='{"kind":"streaming","package":'..q(package)..',"loaded":'..q(loaded)..'}'
                    end
                end
            end
        end
    end
    counts.Level=0
    for _,level in ipairs(FindAllOf('Level') or {}) do
        if valid(level) then
            counts.Level=counts.Level+1
            local id=level:GetFullName()
            if id:find('BattlePlan',1,true) or id:find('Btl_Navigation',1,true) or id:find('ModJunon',1,true) then
                rows[#rows+1]='{"kind":"loaded_level","level":'..q(id)..'}'
                -- Never read ULevel.Actors: it is not reflected, and a failed member
                -- lookup leaks UE4SS's Lua C stack even inside pcall (broke this script, 2026-11-09).
            end
        end
    end
    for _,class in ipairs({'EndFieldEnemyTerritoryActor','EndCameraSequenceActor','EndLayoutObjectPack'}) do
        counts[class]=0
        for _,actor in ipairs(FindAllOf(class) or {}) do
            if valid(actor) then
                counts[class]=counts[class]+1
                local id=actor:GetFullName()
                if id:find('ModJunon',1,true) or id:find('UCBattle',1,true) or id:find('VRBattle_TerritoryCmnActor',1,true) or id:find('CSA_VrCoBattle',1,true) or id:find('JNONT',1,true) or id:find('Looche',1,true) then
                    local p=actor:K2_GetActorLocation()
                    local extra=''
                    if class=='EndFieldEnemyTerritoryActor' then
                        -- Was the course's territory activated, and around which point?
                        local ok,active=pcall(function() return actor.IsTerritoryActive end)
                        local ok2,tid=pcall(function() return actor.EnemyTerritoryID:ToString() end)
                        local ok3,b=pcall(function() local v=actor.EnemyTerritoryBasePoint;return {v.X,v.Y,v.Z} end)
                        extra=',"active":'..q(ok and tostring(active) or 'unreadable')..',"territory_id":'..q(ok2 and tid or 'unreadable')
                            ..(ok3 and (',"base":['..b[1]..','..b[2]..','..b[3]..']') or '')
                    end
                    if class=='EndFieldEnemyTerritoryActor' and (id:find('UCBattle',1,true) or id:find('Looche',1,true) or id:find('VRBattle_TerritoryCmnActor',1,true)) then
                        -- Battle-area settings, to compare our arena with Roche's native one here.
                        local props={}
                        pcall(function()
                            local c=actor:GetClass()
                            while c and c:IsValid() do
                                c:ForEachProperty(function(prop)
                                    local name=prop:GetFName():ToString()
                                    if name:find('Area') or name:find('Aria') or name:find('Force') or name:find('Shape') or name:find('Floor') or name:find('Wall') or name:find('Radius') or name:find('Range') or name:find('Battle') or name:find('Size') or name:find('Boundary') or name:find('Base') or name:find('Type') or name:find('Active') then
                                        -- Branch on the property's own type, so no member is ever
                                        -- looked up on a value that lacks it (that leaks the C stack).
                                        local kind=prop:GetClass():GetFName():ToString()
                                        local okv,v=pcall(function() return actor[name] end)
                                        local text='?'
                                        if not okv then text='unreadable'
                                        elseif kind=='ArrayProperty' then text='array n='..tostring(v:GetArrayNum())
                                        elseif kind=='StructProperty' then
                                            local sn=prop:GetStruct():GetFName():ToString()
                                            if sn=='Vector' then text=string.format('[%.0f,%.0f,%.0f]',v.X,v.Y,v.Z) else text='struct '..sn end
                                        elseif kind=='ObjectProperty' then text=(v and v:IsValid()) and v:GetFullName() or 'null'
                                        elseif type(v)=='number' or type(v)=='boolean' then text=tostring(v)
                                        else text=kind end
                                        props[#props+1]=q(name)..':'..q(text)
                                    end
                                end)
                                c=c:GetSuperStruct()
                            end
                        end)
                        extra=extra..',"area_props":{'..table.concat(props,',')..'}'
                    end
                    local oka,addr=pcall(function() return string.format('%x',actor:GetAddress()) end)
                    extra=extra..',"address":'..q(oka and addr or '')
                    rows[#rows+1]='{"kind":'..q(class)..',"actor":'..q(id)..',"x":'..p.X..',"y":'..p.Y..',"z":'..p.Z..extra..'}'
                end
            end
        end
    end
    -- Every character, so a battle with no visible enemies shows whether any were made.
    counts.EndCharacterBase=0
    for _,actor in ipairs(FindAllOf('EndCharacterBase') or {}) do
        if valid(actor) then
            counts.EndCharacterBase=counts.EndCharacterBase+1
            if counts.EndCharacterBase<=80 then
                local p=actor:K2_GetActorLocation()
                rows[#rows+1]='{"kind":"EndCharacterBase","actor":'..q(actor:GetFullName())..',"x":'..p.X..',"y":'..p.Y..',"z":'..p.Z..'}'
            end
        end
    end
    -- The server-build actor that carries the territory's enemy spawn lists:
    -- record which level each matching one is in and its list sizes, as the
    -- Biome Randomizer read them. Read-only; one capture per battle.
    counts.EndFieldEnemyTerritoryServerBuildActor=0
    for _,actor in ipairs(FindAllOf('EndFieldEnemyTerritoryServerBuildActor') or {}) do
        if valid(actor) then
            counts.EndFieldEnemyTerritoryServerBuildActor=counts.EndFieldEnemyTerritoryServerBuildActor+1
            local id=actor:GetFullName()
            if id:find('ModJunon',1,true) or id:find('UCBattle',1,true) or id:find('VRBattle_TerritoryCmnActor',1,true) or id:find('JNONT',1,true) or id:find('Looche',1,true) then
                local sizes={}
                for _,list in ipairs({'TerritoryGroundSpawnPoints_S','TerritoryGroundSpawnPoints_M','TerritoryGroundSpawnPoints_L','GroundSummonPoints'}) do
                    local ok,n=pcall(function() return actor[list]:GetArrayNum() end)
                    sizes[#sizes+1]=q(list)..':'..(ok and tostring(n) or q('unreadable'))
                end
                -- Where the spawn points are: the actor's own location and the first three small-enemy points.
                local where=''
                local okp,p=pcall(function() return actor:K2_GetActorLocation() end)
                if okp and p then where=',"x":'..p.X..',"y":'..p.Y..',"z":'..p.Z end
                local points={}
                for i=1,3 do
                    local ok,text=pcall(function()
                        local e=actor.TerritoryGroundSpawnPoints_S[i]
                        local okt,t=pcall(function() return e.Translation end)
                        local v=(okt and t) or e
                        return '['..v.X..','..v.Y..','..v.Z..']'
                    end)
                    points[#points+1]=ok and text or q('unreadable')
                end
                -- Each list's extent (relative to the territory), to compare our arena's
                -- points (cloned from Gold Saucer's) with Roche's native arena here.
                local extents={}
                -- Summon and fly-ground validity flags (TArray<bool>): count and how many true.
                local flags={}
                if id:find('UCBattle',1,true) or id:find('Looche',1,true) or id:find('VRBattle_TerritoryCmnActor',1,true) then
                    for _,list in ipairs({'ValidSummonAreaSize','ValidGroundSummonPoints','ValidGroundAdditionalSummonPoints','CutSceneGroundAdditionalSummonPoints',
                                          'TerritoryFlySpawnPointsCheckGround_S','TerritoryFlySpawnPointsCheckGround_M','TerritoryFlySpawnPointsCheckGround_L'}) do
                        local ok,text=pcall(function()
                            local arr=actor[list]; local n,t=arr:GetArrayNum(),0
                            local bits={}
                            for i=1,n do local b=arr[i]; if b==true then t=t+1 end; if i<=12 then bits[#bits+1]=(b==true) and '1' or '0' end end
                            return string.format('{"n":%d,"true":%d,"first":"%s"}',n,t,table.concat(bits))
                        end)
                        flags[#flags+1]=q(list)..':'..(ok and text or q('unreadable'))
                    end
                end
                if id:find('UCBattle',1,true) or id:find('Looche',1,true) or id:find('VRBattle_TerritoryCmnActor',1,true) then
                    for _,list in ipairs(SERVER_LISTS) do
                        local ok,text=pcall(function()
                            local arr=actor[list]; local n=arr:GetArrayNum()
                            local lo,hi,far={1e9,1e9,1e9},{-1e9,-1e9,-1e9},0
                            for i=1,n do
                                local e=arr[i]
                                local okt,t=pcall(function() return e.Translation end)
                                local v=(okt and t) or e
                                local c={v.X,v.Y,v.Z}
                                for k=1,3 do lo[k]=math.min(lo[k],c[k]); hi[k]=math.max(hi[k],c[k]) end
                                far=math.max(far,math.sqrt(c[1]*c[1]+c[2]*c[2]))
                            end
                            return string.format('{"n":%d,"min":[%.0f,%.0f,%.0f],"max":[%.0f,%.0f,%.0f],"far":%.0f}',n,lo[1],lo[2],lo[3],hi[1],hi[2],hi[3],far)
                        end)
                        extents[#extents+1]=q(list)..':'..(ok and text or q('unreadable'))
                    end
                end
                rows[#rows+1]='{"kind":"EndFieldEnemyTerritoryServerBuildActor","actor":'..q(id)..where..',"first_points_s":['..table.concat(points,',')..'],"lists":{'..table.concat(sizes,',')..'},"extents":{'..table.concat(extents,',')..'},"flags":{'..table.concat(flags,',')..'}}'
            end
        end
    end
    local totals={}
    for class,count in pairs(counts) do totals[#totals+1]=q(class)..':'..count end
    table.sort(totals)
    local f=(out and io.open(out,'wb')) or paths.open('junon-colosseum-battle-plan.json','wb')
    if f then f:write('{"timestamp_utc":'..q(os.date('!%Y-%m-%dT%H:%M:%SZ'))..',"read_only":true,"scanned":{'..table.concat(totals,',')..'},"rows":['..table.concat(rows,',')..']}');f:close() end
end
local function write(state,err)
    if not ROOT then return end
    local f=io.open(ROOT..'.tmp','wb')
    if not f then return end
    f:write('{"state":'..q(state)..',"timestamp_utc":'..q(os.date('!%Y-%m-%dT%H:%M:%SZ'))..',"error":'..q(err or '')..',"battle_plan_state":'..q(battle_plan_state)..',"battle_plan_package":'..q(battle_plan.package())..',"mesh_cached":'..tostring(valid(mesh))..',"mesh_request":'..q(mesh_request)..',"point_source":'..q(point_source)..(point_at and (',"point_x":'..point_at.X..',"point_y":'..point_at.Y..',"point_z":'..point_at.Z) or '')..',"mesh":'..q(valid(mesh) and mesh:GetFullName() or '')..',"display_spawned":'..tostring(valid(display))..',"point_spawned":'..tostring(valid(point))..',"display":'..q(valid(display) and display:GetFullName() or '')..',"point":'..q(valid(point) and point:GetFullName() or '')..',"board_id":'..q(board_id)..',"lever_removed":'..tostring(lever_removed)..',"lever_matched":'..lever_matched..',"lever_destroyed":'..lever_destroyed..',"invitation_count":'..tostring(item_count)..',"spawn_fit":'..q(fit_state)..'}')
    f:close();os.remove(ROOT);os.rename(ROOT..'.tmp',ROOT)
end
local function collect()
    if valid(mesh) then return end
    for _,variant in ipairs({'01A','02A','03A','04A'}) do
        local name='Quest_Board_'..variant
        local found=StaticFindObject('/Game/Environment/Interior/Model/'..name..'.'..name)
        if valid(found) and not found:HasAnyFlags(EObjectFlags.RF_NeedLoad | EObjectFlags.RF_NeedPostLoad | EObjectFlags.RF_NeedPostLoadSubobjects) then
            mesh=found
            library=StaticConstructObject(StaticFindObject('/Script/Engine.ObjectLibrary'),StaticFindObject('/Script/Engine.Default__KismetSystemLibrary'),0,EObjectFlags.RF_Transient,EInternalObjectFlags.RootSet)
            if not valid(library) then error('Cannot retain quest-board mesh') end
            library.Objects={mesh}
            return
        end
    end
end
-- After a load inside the foyer, streaming has not brought the board mesh in.
-- Ask the game-thread helper to load it, once per game session; an older
-- helper ignores the marker and the board keeps waiting as before.
-- Off the game thread the helper queues the load for a safe game-thread point
-- and renames the kept marker when done, or ModJunonDeferred_ after 3 s (ask
-- again); look at it on later ticks. Give up after MESH_QUEUE_TIMEOUT seconds
-- (untag, destroy, ask again) only if the helper never answers.
M.MESH_QUEUE_TIMEOUT=6
local mesh_marker,mesh_queued_at,mesh_retries=nil,0,0
local function mesh_loaded_now(queued)
    mesh_request='loaded'
    collect() -- the synchronous answer is the same game-thread call: root it before any garbage collection
    if not valid(mesh) then
        -- A queued load is collected a tick later; a garbage collection in
        -- between can take the mesh. Ask again, a few times.
        if queued and mesh_retries<3 then mesh_retries=mesh_retries+1;mesh_request='not_requested'
        else mesh_request='loaded_not_found' end
    end
end
local function check_queued_mesh()
    if not valid(mesh_marker) then mesh_marker=nil;mesh_request='not_requested';return end
    local name=mesh_marker:GetFName():ToString()
    if name:find('ModJunonQueued_',1,true)==1 then
        if os.time()-mesh_queued_at<M.MESH_QUEUE_TIMEOUT then return end
        pcall(function() mesh_marker.Tags={};mesh_marker:K2_DestroyActor() end)
        mesh_marker=nil;mesh_request='not_requested'
        return
    end
    mesh_marker:K2_DestroyActor();mesh_marker=nil
    if name:find('ModJunonDeferred_',1,true)==1 then mesh_request='not_requested';return end
    if name:find('ModJunonBoardMeshLoaded_',1,true)==1 then mesh_loaded_now(true) else mesh_request='refused' end
end
local function request_mesh(pawn)
    if mesh_request=='queued' then check_queued_mesh() end
    if mesh_request~='not_requested' then return end
    mesh_request='refused'
    local world=pawn:GetWorld()
    if not valid(world) then mesh_request='no_field_world';return end
    local marker=world:SpawnActor(StaticFindObject('/Script/Engine.StaticMeshActor'),board_pos,{Pitch=0,Yaw=0,Roll=0})
    if not valid(marker) then mesh_request='marker_failed';return end
    marker:SetActorEnableCollision(false)
    marker.Tags={FName('ModJunonColosseum_LoadBoardMesh')}
    marker:SetActorTickEnabled(false)
    local name=marker:GetFName():ToString()
    -- The helper only loads on the game thread (load crash A, 2026-11-10); off it
    -- the request is queued for its next game-thread call: keep the marker.
    if name:find('ModJunonQueued_',1,true)==1 then
        mesh_marker,mesh_queued_at,mesh_request=marker,os.time(),'queued'
        return
    end
    local loaded=name:find('ModJunonBoardMeshLoaded_',1,true)==1
    marker:K2_DestroyActor()
    -- An older helper defers instead: ask again on a later tick.
    if name:find('ModJunonDeferred_',1,true)==1 then mesh_request='not_requested';return end
    if loaded then mesh_loaded_now(false) end
end
local function remove()
    if valid(point) then point:K2_DestroyActor() end
    if valid(display) then display:K2_DestroyActor() end
    point=nil;display=nil
end
local function remove_old_lever()
    -- Each FindAllOf walks every object (~100 ms): stop once both levers are gone,
    -- and otherwise look only every 30 s (every 5 s caused frame hitches).
    if lever_matched>=2 or os.time()<next_lever_scan then return end
    next_lever_scan=os.time()+30
    local matched,destroyed=0,0
    for _,entry in ipairs({
        {'SampleLeverHWall00_C','obl1350LeverHWall_level_boss1'},
        {'BG9030_00_LeverHWall_Standard_C','BG9030_00_LeverHWall_Standard_2'},
    }) do
        for _,actor in ipairs(FindAllOf(entry[1]) or {}) do
            if valid(actor) and actor:GetFName():ToString()==entry[2] then
                local p=actor:K2_GetActorLocation()
                local dx,dy=p.X+122616.8125,p.Y-32187.734375
                if dx*dx+dy*dy<100*100 and math.abs(p.Z-6170)<100 then
                    matched=matched+1
                    actor:SetActorEnableCollision(false)
                    actor:SetActorHiddenInGame(true)
                    actor:K2_DestroyActor()
                    if actor:IsActorBeingDestroyed() then destroyed=destroyed+1 end
                end
            end
        end
    end
    lever_matched=lever_matched+matched
    lever_destroyed=lever_destroyed+destroyed
    -- No match is unknown, not proof that the lever disappeared.
    lever_removed=lever_matched>=2 and matched==0
end
local function spawn(pawn)
    local world=pawn:GetWorld()
    if not valid(world) then error('No field world') end
    if not valid(display) then
        display=world:SpawnActor(StaticFindObject('/Script/Engine.StaticMeshActor'),board_pos,{Pitch=0,Yaw=board_yaw,Roll=0})
        if not valid(display) then error('Board display spawn failed') end
        display:SetActorEnableCollision(false)
        local component=display.StaticMeshComponent
        component:SetMobility(2);component:SetSimulatePhysics(false);component:SetCollisionEnabled(0)
        if not component:SetStaticMesh(mesh) then error('Board mesh assignment failed') end
    end
    if not valid(point) then
        local gameplay=StaticFindObject('/Script/Engine.Default__GameplayStatics')
        local transform={Rotation={X=0,Y=0,Z=0.5,W=0.8660254038},Translation=point_pos(),Scale3D={X=1,Y=1,Z=1}}
        point=gameplay:BeginDeferredActorSpawnFromClass(world,StaticFindObject('/Script/EndGame.EndBulletinBoardPoint'),transform,1,nil)
        if not valid(point) then error('Deferred noticeboard creation failed') end
        point.Tags={FName(board_id)} -- request token; native Rename establishes identity
        -- Native game-thread hook validates the context class/name/location
        -- and uses UObject::Rename before this actor receives BeginPlay.
        point:SetActorTickEnabled(false)
        if point:GetFName():ToString()~=board_id then
            point:K2_DestroyActor();point=nil
            error('Native noticeboard identity was not established')
        end
        gameplay:FinishSpawningActor(point,transform)
    end
end
-- Opt-in (junon-positions.on in the dev.txt telemetry folder): every 2 s in
-- battle, append each character's distance from the arena floor's centre to
-- junon-positions.tsv. The floor is a ~20 m-radius circle (navmesh view,
-- 2026-11-09); anyone logged beyond it is outside the walls.
local ARENA={X=-123780,Y=28675}
local next_positions=0
local function log_positions()
    if os.time()<next_positions then return end
    next_positions=os.time()+2
    local flag=paths.open('junon-positions.on','rb')
    if not flag then return end
    flag:close()
    local f=paths.open('junon-positions.tsv','ab')
    if not f then return end
    for _,actor in ipairs(FindAllOf('EndCharacterBase') or {}) do
        if valid(actor) then
            local p=actor:K2_GetActorLocation()
            local dx,dy=p.X-ARENA.X,p.Y-ARENA.Y
            local r=math.sqrt(dx*dx+dy*dy)
            if r<6000 then
                local name=actor:GetFName():ToString()
                f:write(string.format('%d\t%s\t%.0f\t%.0f\t%.0f\t%.0f%s\n',os.time(),name,p.X,p.Y,p.Z,r,r>2000 and '\tOUTSIDE' or ''))
            end
        end
    end
    f:close()
end
-- Test tool (junon-kill.on in the dev.txt telemetry folder, one shot): end the
-- current round by asking the game to remove each enemy in our arena as dead
-- (UEndFieldAPI.RequestDestroyEnemyInTerritory). Lets a survey run many rounds
-- in one launch. Writes what it did to junon-kill.tsv.
local function kill_round()
    if not diagnostics('junon-kill.on') then return end
    paths.remove('junon-kill.on')
    local field=StaticFindObject('/Script/EndGame.Default__EndFieldAPI')
    local f=paths.open('junon-kill.tsv','ab')
    if not valid(field) or not f then if f then f:close() end return end
    for _,actor in ipairs(FindAllOf('EndCharacterBase') or {}) do
        if valid(actor) then
            local name=actor:GetFName():ToString()
            local p=actor:K2_GetActorLocation()
            local dx,dy=p.X-ARENA.X,p.Y-ARENA.Y
            if not name:find('^PC') and dx*dx+dy*dy<4000*4000 then
                local okt,tid=pcall(function() return field:GetTerritoryIdFromActorName(actor:GetFName()) end)
                local tids=okt and tid and tid:ToString() or '?'
                local okd=false
                if okt and tid and tids~='None' and tids~='' then
                    okd=pcall(function() field:RequestDestroyEnemyInTerritory(tid,actor:GetFName(),true) end)
                end
                f:write(string.format('%d\t%s\t%s\t%s\n',os.time(),name,tids,tostring(okd)))
            end
        end
    end
    f:close()
end
-- Test tool (junon-status.on, one shot): apply the status IDs listed in the file
-- (one per line, e.g. BSC_Haste) to every party character in battle, for the rest
-- of the battle (UEndBattleAPI.AddStatusChangeID, time type Infinity = 64).
-- The buff wheel will use the same call. Writes results to junon-status.tsv.
local function apply_status_test()
    local fin=paths.open('junon-status.on','rb')
    if not fin then return end
    local ids={}
    for line in fin:lines() do local id=line:gsub('%s',''); if id~='' then ids[#ids+1]=id end end
    fin:close(); paths.remove('junon-status.on')
    local api=StaticFindObject('/Script/EndGame.Default__EndBattleAPI')
    local f=paths.open('junon-status.tsv','ab')
    if not valid(api) or not f then if f then f:close() end return end
    for _,actor in ipairs(FindAllOf('EndCharacterBase') or {}) do
        if valid(actor) and actor:GetFName():ToString():find('^PC') then
            for _,id in ipairs(ids) do
                local ok,err=pcall(function() api:AddStatusChangeID(actor,FName(id),64,true,nil,false) end)
                f:write(string.format('%d\t%s\t%s\t%s\n',os.time(),actor:GetFName():ToString(),id,ok and 'ok' or tostring(err)))
            end
        end
    end
    f:close()
end
-- Live 2026-11-10: two courses hung on the "Get Ready" screen between rounds.
-- In two-team courses the next team's leader waits as a field pawn outside the
-- arena between rounds; one tick that saw it out of range unloaded the arena
-- levels, and the next round never found its arena actor. So the levels stay
-- loaded while a course is in progress, and otherwise only unload after the
-- player has been out of range for UNLOAD_AFTER ticks in a row.
local UNLOAD_AFTER=10
local far_ticks=0
local function course_active()
    local bw=package.loaded['buffwheel']
    return bw~=nil and bw.course_active~=nil and bw.course_active()==true
end
function M.tick(db,pawn,policy)
    if halted then return end
    local enabled=policy.board_enabled
    local ok,err=pcall(function()
        collect()
        item_count=db:GetItemNumBP(3902)
        local p=pawn:K2_GetActorLocation()
        local dx,dy,dz=p.X-board_pos.X,p.Y-board_pos.Y,p.Z-board_pos.Z
        local field=StaticFindObject('/Script/EndGame.Default__EndFieldAPI')
        local battle=valid(field) and field:IsDuringBattle()
        if course_active() and not battle then battle_plan.course_check() end
        local nearby=dx*dx+dy*dy<=10000*10000 and math.abs(dz)<=1500
        if nearby then far_ticks=0 else far_ticks=far_ticks+1 end
        local keep=nearby or course_active() or far_ticks<UNLOAD_AFTER
        local ready,status=battle_plan.update(pawn,enabled and keep,battle)
        if ready and not was_ready then fit_done=false; next_fit=os.time()+FIT_SETTLE end -- levels (re)loaded: fit the new actors once settled
        was_ready=ready
        battle_plan_state=status
        if battle then pcall(log_positions); pcall(kill_round); pcall(apply_status_test) end
        if not enabled or battle or not nearby then
            if valid(display) then display:SetActorHiddenInGame(true) end
            if valid(point) then point:SetActorHiddenInGame(true) end
            write(battle and 'battle_hidden' or 'outside_foyer');return
        end
        if not ready then write('waiting_for_owned_battle_plan',battle_plan.error());return end
        -- FindAllOf costs ~100 ms: look again at most every 5 s.
        if fit_state:sub(1,6)~='failed' and os.time()>=(next_fit or 0) then
            next_fit=os.time()+5
            local okf,errf=pcall(fit_spawn_points)
            if not okf then fit_state='failed: '..tostring(errf) end
        end
        if not valid(mesh) then request_mesh(pawn)
        elseif mesh_marker then check_queued_mesh() end -- found otherwise meanwhile: still tidy the kept marker
        if not valid(mesh) then write('waiting_for_native_quest_board_mesh');return end
        spawn(pawn)
        display:SetActorHiddenInGame(false)
        if valid(point) then point:SetActorHiddenInGame(false) end
        remove_old_lever()
        write(valid(point) and 'native_identity_registered_smoke_test' or 'visual_only_interaction_quarantined')
        if not field_captured and diagnostics('junon-capture.on') then
            field_captured=true -- one read-only capture per session, outside battle
            pcall(capture_battle_plan,paths.telemetry('junon-colosseum-field-scan.json'))
        end
    end)
    if not ok then halted=true;pcall(remove);write('runtime_error',err) end
end
-- Between rounds there is often no field pawn (no foyer.tick then). While a
-- course is active, check our arena levels anyway and, if one is missing, run
-- the usual update with the game's world: it requests a deleted level again
-- (after the usual settling) and waits for one still loading (live
-- 2026-11-11, see battle_plan.course_check).
function M.course_gap(world)
    if halted or not course_active() then return end
    local missing=battle_plan.course_check()
    if missing=='' or not valid(world) then return end
    local ready,status=battle_plan.update(nil,true,false,world)
    battle_plan_state=status
    write('course_gap_levels_missing',missing)
end
function M.hide_for_battle()
    if valid(display) then display:SetActorHiddenInGame(true) end
    if valid(point) then point:SetActorHiddenInGame(true) end
    write('battle_hidden')
    pcall(log_positions)
    pcall(kill_round)
    pcall(apply_status_test)
    battle_capture_at=battle_capture_at or os.time()
    if not battle_captured and os.time()-battle_capture_at>=5 and diagnostics('junon-capture.on') then
        battle_captured=true -- one read-only capture; never retry a failed lookup
        local ok,err=pcall(capture_battle_plan)
        if not ok then
            local f=paths.open('junon-colosseum-battle-plan.json','wb')
            if f then f:write('{"read_only":true,"error":'..q(err)..'}');f:close() end
        end
    end
end
return M
