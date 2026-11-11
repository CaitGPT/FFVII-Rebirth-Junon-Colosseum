-- Load the levels the Junon arena's battles need, in order, after an eligible
-- field visit:
-- 1. Junon town's battle navigation (1350-JNONT_Btl_Navigation_Mod, its
--    ServerBuild companion first). It holds Roche's own arena battle setup
--    at this spot, but the open world never streams it: in the foyer
--    1350-JNONT's is not even registered and 1300-JUNOA's is not loaded
--    (live 2026-11-09). Native arenas fight inside a loaded battle
--    navigation level; ours stalled on Get Ready without one.
-- 2. Our owned arena plan (territory actor, points, cameras), ServerBuild
--    companion first (enemy spawn/summon lists), as in the native prison
--    arena, whose ServerBuild loads first (store load order 71801 < 610000).
-- Each level is requested once, and the next only when it is loaded and
-- visible. A short UserLevelName does not itself register a new map.
local M={}
local folder='/Game/Level/Game/Field/1300-JUNOA/BattlePlan/'
local leaf='1300-JUNOA_BattlePlan_ModJunonColosseum'
local package=folder..leaf
local nav='/Game/Level/Game/Field/1350-JNONT/Layout/1350-JNONT_Btl_Navigation_Mod'
local LEVELS={
    {name=nav..'_ServerBuild',tag='ModJunonColosseum_LoadJunonBtlNavServerBuild',ack='ModJunonBtlNavServerBuildAccepted_',state='loading_navigation_serverbuild'},
    {name=nav,tag='ModJunonColosseum_LoadJunonBtlNav',ack='ModJunonBtlNavAccepted_',state='loading_navigation'},
    {name=package..'_ServerBuild',tag='ModJunonColosseum_LoadOwnedServerBuild',ack='ModJunonServerBuildAccepted_',state='loading_serverbuild'},
    {name=package,tag='ModJunonColosseum_LoadOwnedPlan',ack='ModJunonPlanAccepted_',state='loading'},
}
local streams,active,world_id={}, {}, nil
-- Levels the game had already loaded itself: used, never unloaded by us.
local borrowed={}
local failed=false
local state,err='not_requested',''
local function valid(o) return o~=nil and o:IsValid() end
local function level_ready(stream)
    return stream:IsLevelLoaded()==true and stream:IsLevelVisible()==true and valid(stream:GetLoadedLevel())
end
-- Streams given up on as stuck (see unstick): never picked again.
local stale={}
local function key(o)
    local ok,address=pcall(function() return o:GetAddress() end)
    if ok and address then return address end
    return o
end
local function stream_of(level)
    for _,candidate in ipairs(FindAllOf('LevelStreamingDynamic') or {}) do
        if valid(candidate) and not stale[key(candidate)] and candidate:GetWorldAssetPackageFName():ToString()==level.name then return candidate end
    end
    error('Requested arena streaming object was not found: '..level.name)
end
-- A line in the development telemetry folder (nothing in a release).
local function note(text)
    M.last_event=text
    pcall(function()
        local paths=require('paths')
        local path=paths.telemetry and paths.telemetry('junon-battle-plan-events.log')
        local f=path and io.open(path,'ab')
        if f then f:write(os.date('!%Y-%m-%dT%H:%M:%SZ')..' '..text..'\n');f:close() end
    end)
end
-- Requests the helper has queued for the game thread: level index ->
-- {marker=, since=}. The marker is kept until the helper answers on it.
-- The helper serves a queued request at a safe point within 3 s or answers
-- ModJunonDeferred_ (ask again); it never serves one older than that. Our own
-- give-up is only for a helper that never answers, and comes later, so it
-- cannot race a late serve.
local queued={}
M.QUEUE_TIMEOUT=6
local function drop_marker(marker)
    -- Untag first: the helper serves only a marker that still carries its tag.
    pcall(function() if valid(marker) then marker.Tags={};marker:K2_DestroyActor() end end)
end
local function forget_queued()
    for i,q in pairs(queued) do drop_marker(q.marker);queued[i]=nil end
end
-- UE4SS3.0.1 leaves a non-struct out table on the argument stack, making a
-- following FString fail before ProcessEvent. Ask our game-thread helper to
-- call the exact reflected native function; it acknowledges by renaming.
-- Returns the stream, or nil plus 'queued' / 'deferred'.
local function request(world,level,i)
    local marker=world:SpawnActor(StaticFindObject('/Script/Engine.StaticMeshActor'),{X=-122488,Y=32969,Z=6170},{Pitch=0,Yaw=0,Roll=0})
    if not valid(marker) then error('Arena load marker creation failed') end
    marker:SetActorEnableCollision(false)
    marker.Tags={FName(level.tag)}
    marker:SetActorTickEnabled(false)
    local name=marker:GetFName():ToString()
    -- Load crash A (2026-11-10): our tick can run on a worker thread, where a
    -- level load crashes the async loader. The helper then queues the request
    -- for its next game-thread call and renames the marker when it is done:
    -- keep the marker and look at it on later ticks (see collect).
    if name:find('ModJunonQueued_',1,true)==1 then
        queued[i]={marker=marker,since=os.time()}
        return nil,'queued'
    end
    local accepted=name:find(level.ack,1,true)==1
    marker:K2_DestroyActor()
    -- An older helper defers instead: the request is made again on a later tick.
    if name:find('ModJunonDeferred_',1,true)==1 then return nil,'deferred' end
    if not accepted then error('Native helper refused '..level.name) end
    return stream_of(level)
end
-- A queued request: the stream once the helper accepted it; nil plus 'queued'
-- while it waits; nil (ask again) if the marker is gone or the wait timed out.
local function collect(i,level)
    local q=queued[i]
    if not valid(q.marker) then queued[i]=nil;return nil,'gone' end
    local name=q.marker:GetFName():ToString()
    if name:find('ModJunonQueued_',1,true)==1 then
        if os.time()-q.since<M.QUEUE_TIMEOUT then return nil,'queued' end
        queued[i]=nil;drop_marker(q.marker)
        M.queue_timeouts=(M.queue_timeouts or 0)+1
        return nil,'timeout'
    end
    queued[i]=nil
    q.marker:K2_DestroyActor()
    -- Not served at a safe point in time: ask again (this tick).
    if name:find('ModJunonDeferred_',1,true)==1 then
        M.queue_deferred=(M.queue_deferred or 0)+1
        return nil,'deferred'
    end
    if name:find(level.ack,1,true)~=1 then error('Native helper refused '..level.name) end
    return stream_of(level)
end
local function fail(message)
    failed=true;err=tostring(message);state='load_error'
    return false,state
end
local function activate(stream) stream:SetShouldBeLoaded(true);stream:SetShouldBeVisible(true) end
local function deactivate(stream) stream:SetShouldBeVisible(false);stream:SetShouldBeLoaded(false) end
-- Live 2026-11-10 evening: after a longer settle the game had already streamed
-- Junon's battle navigation itself, and a second LoadLevelInstance of the same
-- package returns nothing (the helper reported it as refused). So a level the
-- game already has loaded is borrowed instead of requested.
local function existing(level)
    for _,c in ipairs(FindAllOf('LevelStreamingDynamic') or {}) do
        if valid(c) and not stale[key(c)] and c:IsLevelLoaded()==true then
            local ok,name=pcall(function() return c:GetWorldAssetPackageFName():ToString() end)
            if ok and name==level.name then return c end
        end
    end
    return nil
end
-- Development only: junon-noplan.on in the dev.txt telemetry folder skips every
-- level request (crash bisect, 2026-11-10).
local function dev_off()
    local ok,paths=pcall(require,'paths')
    local path=ok and paths.telemetry and paths.telemetry('junon-noplan.on')
    local f=path and io.open(path,'rb')
    if f then f:close();return true end
    return false
end
-- Live 2026-11-10: requesting these levels while a save is still streaming in
-- crashed the game in its async loader, on a worker thread (EXCEPTION_ACCESS_VIOLATION
-- writing 0x39 at ff7rebirth_.exe+0x872ceb), on about one load in five into the
-- foyer. So a new world waits SETTLE seconds before the first request.
M.SETTLE=12
local settle_until=0
-- 8 s alone was not enough (crash on the fourth level, 2026-11-10 13:19): the save's
-- own levels can still be streaming. So also wait until the set of pending
-- streaming levels has stopped changing for QUIET seconds (some never finish,
-- e.g. 1350-JNONT_Airport_Terrain_Strip in the foyer), checked every 2 s, object
-- scans only while settling; never more than MAX_SETTLE seconds after a load.
-- (Since 2026-11-10 evening: quiet means nothing pending, see world_quiet; a set
-- unchanged for STUCK seconds also counts.)
M.QUIET=6
M.STUCK=20
M.MAX_SETTLE=60
local quiet_since,next_quiet_check,last_pending,settle_started=nil,0,nil,0
-- One scan: FindAllOf('LevelStreaming') includes its subclasses (live: 1456 = 1261
-- Dynamic + 195 AlwaysLoaded), and each scan costs about 155 ms of game thread.
local STREAM_CLASSES={'LevelStreaming'}
-- Levels that stay pending for good in Junon (live 2026-11-10); they never
-- count as the world still loading.
local NEVER_DONE={['/Game/Level/Game/Field/1350-JNONT/1350-JNONT_Airport_Terrain_Strip']=true}
local function never_done(name)
    if NEVER_DONE[name] then return true end
    return name:find('Airport_Terrain_Strip',1,true)~=nil
end
-- Quiet means nothing (but the never-done levels) has been pending for QUIET
-- seconds. Live 2026-11-10: "the pending set has not changed for 6 s" was not
-- enough; one big level streaming for that long looked stable, our request
-- went out one second after Biome Randomizer's table edits, and load crash A
-- came back. A set that stays unchanged for STUCK seconds also counts (a level
-- that never finishes), and MAX_SETTLE is the last resort.
local stable_since=nil
local function world_quiet()
    local now=os.time()
    if now-settle_started>=M.MAX_SETTLE then M.quiet_reason='max_settle';return true end
    if now<next_quiet_check then
        return (quiet_since~=nil and now-quiet_since>=M.QUIET) or (stable_since~=nil and now-stable_since>=M.STUCK)
    end
    next_quiet_check=now+3
    local pending={}
    for _,class in ipairs(STREAM_CLASSES) do
        for _,s in ipairs(FindAllOf(class) or {}) do
            if valid(s) and s:IsStreamingStatePending()==true then
                local ok,name=pcall(function() return s:GetWorldAssetPackageFName():ToString() end)
                name=ok and name or '?'
                if not never_done(name) then pending[#pending+1]=name end
            end
        end
    end
    table.sort(pending)
    local signature=table.concat(pending,'|')
    M.pending=pending[1]
    if #pending==0 then quiet_since=quiet_since or now else quiet_since=nil end
    if signature~=last_pending then last_pending,stable_since=signature,now end
    if quiet_since and now-quiet_since>=M.QUIET then M.quiet_reason='nothing_pending';return true end
    if #pending>0 and now-stable_since>=M.STUCK then M.quiet_reason='stuck '..#pending;return true end
    return false
end
-- Tell us what the world is still streaming (state text only).
M.pending=nil
-- Live 2026-11-10 20:55: a ServerBuild stream we requested stayed pending
-- (not loaded, should be loaded) for minutes; toggling it did not help and the
-- board never came. A stream we requested that is not ready STREAM_STUCK
-- seconds later is unloaded and requested once more; stuck again, the arena
-- fails with that reason instead of waiting forever. Only a new request is
-- watched (fresh): a borrowed stream is not ours, and one switched back on
-- after leaving had loaded before (asking for its package again while it
-- unloads would be refused).
M.STREAM_STUCK=20
local waiting_since,retried,fresh={}, {}, {}
local function unstick(i,level)
    local s=streams[i]
    local ok,pending=pcall(function() return s:IsStreamingStatePending() end)
    local what=level.name..' pending='..tostring(ok and pending)..' after '..(os.time()-waiting_since[i])..' s'
    if retried[i] then
        note('stream_stuck_again '..what)
        return fail('Arena level stayed pending after a second request: '..level.name)
    end
    retried[i]=true
    note('stream_stuck_requesting_again '..what)
    M.stuck_retries=(M.stuck_retries or 0)+1
    pcall(deactivate,s)
    stale[key(s)]=true
    streams[i],active[i],waiting_since[i],fresh[i]=nil,false,nil,nil
    state='stream_stuck_requesting_again'
    return false,state
end
-- world: used when there is no field pawn (between the rounds of a course,
-- see foyer.course_gap); the pawn's world otherwise.
function M.update(pawn,wanted,battle,world)
    if dev_off() then return false,'disabled_for_test' end
    -- Field pawn absence and battle transitions must never unload what the
    -- native course is using. No lookup or load at the title.
    if battle or (not valid(pawn) and not valid(world)) then return false,state end
    if valid(pawn) then world=pawn:GetWorld() end
    if not valid(world) then return false,'no_field_world' end
    local id=world:GetAddress()
    if world_id~=id then
        forget_queued()
        streams,active,failed,err,state,world_id,borrowed={}, {}, false,'','not_requested',id,{}
        stale,waiting_since,retried,fresh={}, {}, {}, {}
        settle_until=os.time()+M.SETTLE
        quiet_since,next_quiet_check,last_pending,settle_started,stable_since=nil,0,nil,os.time(),nil
    end
    if not wanted then
        for i=#LEVELS,1,-1 do
            if active[i] and valid(streams[i]) and not borrowed[i] then deactivate(streams[i]) end
            active[i]=false
            waiting_since[i]=nil
        end
        return false,'inactive'
    end
    if failed then return false,state end
    -- Live 2026-11-10: leaving the foyer unloads our levels, and the game then
    -- deletes their streaming objects; the world stays the same, so the old ones
    -- were kept and the board never came back (state stream_unavailable). Forget
    -- deleted ones and request the levels again, after the usual settling.
    for i=1,#LEVELS do
        if streams[i]~=nil and not valid(streams[i]) then
            forget_queued()
            streams,active,state,borrowed={}, {}, 'not_requested',{}
            waiting_since,retried,fresh={}, {}, {}
            settle_until=os.time()+M.SETTLE
            quiet_since,next_quiet_check,last_pending,settle_started,stable_since=nil,0,nil,os.time(),nil
            break
        end
    end
    if streams[1]==nil and (os.time()<settle_until or (M.QUIET>0 and not world_quiet())) then return false,'settling_after_load '..tostring(M.pending or '') end
    for i,level in ipairs(LEVELS) do
        if streams[i]==nil then
            local ok,result,why
            if queued[i] then
                ok,result,why=pcall(collect,i,level)
                if ok and result==nil and why=='queued' then return false,'queued_for_game_thread' end
            end
            if ok~=false and result==nil then
                local found=existing(level)
                if found then
                    streams[i],active[i],borrowed[i]=found,true,true
                else
                    -- fail once; never repeatedly submit a failed native load
                    ok,result,why=pcall(request,world,level,i)
                    if ok and result==nil then
                        if why=='queued' then
                            M.queued=(M.queued or 0)+1
                            return false,'queued_for_game_thread'
                        end
                        M.deferred=(M.deferred or 0)+1
                        return false,'deferred_off_game_thread'
                    end
                end
            end
            if streams[i]==nil then
                if not ok then
                    local found=existing(level)  -- the game may have loaded it meanwhile
                    if not found then return fail(result) end
                    result=found;borrowed[i]=true
                end
                streams[i]=result;active[i]=true;fresh[i]=not borrowed[i]
            end
        end
        if not valid(streams[i]) then return false,'stream_unavailable' end
        if not active[i] then activate(streams[i]);active[i]=true end
        if not level_ready(streams[i]) then
            if fresh[i] then
                waiting_since[i]=waiting_since[i] or os.time()
                if os.time()-waiting_since[i]>M.STREAM_STUCK then return unstick(i,level) end
            end
            state=level.state;return false,state
        end
        waiting_since[i],fresh[i]=nil,nil
    end
    state='loaded_visible'
    return true,state
end
-- Between the rounds of a course. Live 2026-11-11 a course stalled before
-- round 7 with no round territory armed, and nothing of our arena could be
-- confirmed. So check that our levels are still there: a stream the game
-- deleted is reported (the next update forgets it and requests the level
-- again), and one of ours that is valid but neither loaded nor loading is
-- switched back on. Borrowed streams (the game's own) are only reported.
-- Logs each change; returns the missing levels as text ('' when none).
local course_note=''
function M.course_check()
    if dev_off() then return '' end
    local missing={}
    for i,level in ipairs(LEVELS) do
        local s=streams[i]
        local name=level.name:match('[^/]+$')
        if s==nil then missing[#missing+1]=name..'=not_held'
        elseif not valid(s) then missing[#missing+1]=name..'=deleted'
        else
            local okl,loaded=pcall(function() return s:IsLevelLoaded() end)
            if okl and loaded==false then
                local okp,pending=pcall(function() return s:IsStreamingStatePending() end)
                if okp and pending==true then missing[#missing+1]=name..'=loading'
                elseif borrowed[i] then missing[#missing+1]=name..'=unloaded_borrowed'
                else
                    missing[#missing+1]=name..'=unloaded_switched_on'
                    pcall(activate,s);active[i]=true
                end
            end
        end
    end
    local text=table.concat(missing,' ')
    if text~=course_note then
        course_note=text
        note(text=='' and 'course_levels_present' or 'course_levels_missing '..text)
    end
    M.course_missing=text
    return text
end
function M.error() return err end
function M.package() return package end
return M
