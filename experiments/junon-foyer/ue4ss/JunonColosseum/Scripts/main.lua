local paths = require('paths')
local helpers = require('UEHelpers')
local gate = require('gate')
local foyer = require('foyer')
local invitation = require('invitation')
local flow = require('flow')
local buffwheel = require('buffwheel')
-- Development builds only; release packages leave devtools.lua out.
local has_devtools, devtools = pcall(require, 'devtools')
if not has_devtools then devtools = {tick = function() end} end
local branding = require('branding')
local compat = require('compat')
local FLAG = 'stfMod_JunonColosseum_RocheDefeated'
local ACCESS = 'stfMod_JunonColosseum_AccessEnabled'
local DISCOVERED = 'stfMod_JunonColosseum_Discovered'
local GUARD = 'stfMod_JunonColosseum_GuardEnabled'
local EXIT = 'stfMod_JunonColosseum_ExitEnabled'
local NEEDS = 'stfMod_JunonColosseum_NeedsInvitation'
local ROOT = paths.telemetry('junon-colosseum-travel-gate.json')
local busy, halted, writes = false, false, 0
local field_seen=false
local function valid(v) return v ~= nil and v:IsValid() end
local function quote(s) return '"' .. tostring(s):gsub('\\','\\\\'):gsub('"','\\"'):gsub('[\r\n]',' ') .. '"' end
local function emit(state)
    state.source, state.timestamp_utc, state.flag, state.writes = 'JunonColosseum', os.date('!%Y-%m-%dT%H:%M:%SZ'), FLAG, writes
    local parts = {}
    for k,v in pairs(state) do
        parts[#parts+1] = quote(k) .. ':' .. (type(v)=='boolean' and tostring(v) or type(v)=='number' and tostring(v) or quote(v))
    end
    table.sort(parts)
    if not ROOT then return end
    local f=io.open(ROOT..'.tmp','wb')
    if not f then return end
    f:write('{'..table.concat(parts,',')..'}'); f:close()
    os.remove(ROOT); os.rename(ROOT..'.tmp',ROOT)
end
local wheel_error=nil
local function wheel()
    -- The buff wheel runs in and out of battle (it clears a finished run's picks).
    if not field_seen or wheel_error then return end
    local db=StaticFindObject('/Script/EndGame.Default__EndDataBaseAPI')
    local field=StaticFindObject('/Script/EndGame.Default__EndFieldAPI')
    if not valid(db) or not valid(field) then return end
    local ok,err=pcall(function()
        local battle=field:IsDuringBattle()
        buffwheel.tick(db,battle)
    end)
    if not ok then wheel_error=tostring(err) end -- stop the wheel, keep the gate
end
local function tick()
    wheel()
    devtools.tick()
    pcall(branding.tick)
    local pawn = helpers.GetPlayer()
    if not valid(pawn) then
        -- The controller has no field pawn during native colosseum battles.
        -- Hide cached props anyway, but never call battle APIs from the title.
        if field_seen then
            local field=StaticFindObject('/Script/EndGame.Default__EndFieldAPI')
            if valid(field) and field:IsDuringBattle() then
                foyer.hide_for_battle()
                emit({verified=false,reason='battle_field_gate_writes_suspended'});return
            end
            -- Between a course's rounds: keep our arena levels (foyer.course_gap).
            pcall(function() foyer.course_gap(helpers.GetWorld and helpers.GetWorld()) end)
        end
        emit({verified=false,reason='no_loaded_player'}); return
    end
    local class = pawn:GetClass():GetFName():ToString()
    if not class:match('^PC%d%d%d%d_') then emit({verified=false,reason='not_field_player'}); return end
    field_seen=true
    local db = StaticFindObject('/Script/EndGame.Default__EndDataBaseAPI')
    if not valid(db) then return end
    for _,method in ipairs({'IsStoryFlag','SetStoryFlagBP','GetChapterProgress','GetItemNumBP'}) do
        if not valid(StaticFindObject('/Script/EndDataBase.EndDataBaseDataBaseAPI:'..method)) then return end
    end
    local progress = db:GetChapterProgress()
    if type(progress) ~= 'number' or progress <= 0 then return end
    local visited = db:IsStoryFlag(FName('stfCmnChapter12_Visited'))
    local cleared = db:IsStoryFlag(FName('stfComn_Release_ChapterSelect'))
    local invitation_count=db:GetItemNumBP(3902)
    flow.tick(db,pawn,progress,invitation_count)
    pcall(compat.tick,db) -- Training Dummy's courses: a display flag only
    local discovered=db:IsStoryFlag(FName(DISCOVERED))
    local policy, reason = gate.policy(progress, cleared, invitation_count, discovered)
    if policy == nil then emit({verified=false,reason=reason}); return end
    local desired=policy.roche_defeated
    local before = db:IsStoryFlag(FName(FLAG))
    if type(before) ~= 'boolean' then emit({verified=false,reason='custom_flag_unreadable'}); return end
    if before ~= desired then
        -- Only mod-owned flags are synchronized; vanilla progress is read-only.
        db:SetStoryFlagBP(FName(FLAG), desired)
        writes = writes + 1
    end
    local after = db:IsStoryFlag(FName(FLAG))
    local access_before=db:IsStoryFlag(FName(ACCESS))
    if type(access_before)~='boolean' then emit({verified=false,reason='access_flag_unreadable'});return end
    if access_before~=policy.access_enabled then
        db:SetStoryFlagBP(FName(ACCESS),policy.access_enabled)
        writes=writes+1
    end
    local access=db:IsStoryFlag(FName(ACCESS))
    local guard_before=db:IsStoryFlag(FName(GUARD))
    if type(guard_before)~='boolean' then emit({verified=false,reason='guard_flag_unreadable'});return end
    if guard_before~=policy.guard_enabled then
        db:SetStoryFlagBP(FName(GUARD),policy.guard_enabled)
        writes=writes+1
    end
    local guard=db:IsStoryFlag(FName(GUARD))
    local exit_before=db:IsStoryFlag(FName(EXIT))
    if type(exit_before)~='boolean' then emit({verified=false,reason='exit_flag_unreadable'});return end
    if exit_before~=policy.exit_enabled then
        db:SetStoryFlagBP(FName(EXIT),policy.exit_enabled)
        writes=writes+1
    end
    local exit=db:IsStoryFlag(FName(EXIT))
    local needs_before=db:IsStoryFlag(FName(NEEDS))
    if type(needs_before)~='boolean' then emit({verified=false,reason='invitation_need_flag_unreadable'});return end
    if needs_before~=policy.grant_invitation then
        db:SetStoryFlagBP(FName(NEEDS),policy.grant_invitation)
        writes=writes+1
    end
    local needs=db:IsStoryFlag(FName(NEEDS))
    emit({wheel_error=wheel_error,verified=after==desired and access==policy.access_enabled and guard==policy.guard_enabled and exit==policy.exit_enabled and needs==policy.grant_invitation,enabled=access,guard_enabled=guard,exit_enabled=exit,invitation_needed=needs,discovered=discovered,invitation_count=invitation_count,chapter12_plus=policy.chapter12_plus,roche_defeated=after,chapter4_replay=policy.chapter4,chapter12_visited=visited,
          chapter_select_released=cleared,chapter_progress=progress,player_actor=pawn:GetFullName()})
    if after ~= desired or access~=policy.access_enabled or guard~=policy.guard_enabled or exit~=policy.exit_enabled or needs~=policy.grant_invitation then halted=true end
    if not halted then
        invitation.tick(db,pawn,policy)
        foyer.tick(db,pawn,policy)
    end
end
-- Register the game-thread callback during mod loading, never for the first
-- time while a save is playing. No hot reload or per-frame object scans.
pcall(ExecuteInGameThread,function() end)
pcall(branding.register) -- before any colosseum menu exists
pcall(buffwheel.start_poll) -- Darkside's HP cost: a 200 ms ability read, armed only in its rounds
LoopAsync(1000,function()
    if halted then return true end
    if busy then return false end
    busy=true
    ExecuteInGameThread(function()
        local ok,err=pcall(tick)
        busy=false
        if not ok then emit({verified=false,reason='gate_runtime_error',error=tostring(err)}); halted=true end
    end)
    return false
end)
