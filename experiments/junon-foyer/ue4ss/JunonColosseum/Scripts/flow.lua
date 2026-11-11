local paths = require('paths')
-- Permanent discovery follows a requested guard entry and live arena arrival.
-- A dialogue registration or a requested transition alone is insufficient.
local M={}
local started=nil
local settled=0
local pending_flag='stfMod_JunonColosseum_EntryPending'
local discovered_flag='stfMod_JunonColosseum_Discovered'
local ROOT = paths.telemetry('junon-colosseum-entry.json')
local function write(state,p)
    if not ROOT then return end
    local f=io.open(ROOT..'.tmp','wb')
    if not f then return end
    f:write('{"state":"'..state..'","timestamp_utc":"'..os.date('!%Y-%m-%dT%H:%M:%SZ')..'","x":'..p.X..',"y":'..p.Y..',"z":'..p.Z..'}')
    f:close();os.remove(ROOT);os.rename(ROOT..'.tmp',ROOT)
end
function M.tick(db,pawn,progress,count)
    if type(progress)~='number' or type(count)~='number' then return end
    if db:IsStoryFlag(FName(pending_flag))~=true then started=nil;settled=0;return end
    local p=pawn:K2_GetActorLocation()
    if progress<12000 or count<1 then
        db:SetStoryFlagBP(FName(pending_flag),false)
        started=nil;settled=0;write('entry_ineligible_discovery_unchanged',p);return
    end
    started=started or os.time()
    local dx,dy,dz=p.X+122488.4375,p.Y-32968.976562,p.Z-6257.788574
    local movement=pawn:GetMovementComponent()
    local grounded=movement~=nil and movement:IsValid() and movement:IsMovingOnGround()==true
    local velocity=pawn:GetVelocity()
    local still=velocity.X*velocity.X+velocity.Y*velocity.Y+velocity.Z*velocity.Z<25
    local yaw=pawn:K2_GetActorRotation().Yaw
    local yaw_error=math.abs((yaw+127.451088+180)%360-180)
    -- Guard landings settle 1.0-1.6 m from the pose (party collision), and a
    -- player may turn before settling: 3 m and 45 degrees still means the foyer.
    local at_arrival=dx*dx+dy*dy<=300*300 and math.abs(dz)<=160 and yaw_error<=45
    if at_arrival and grounded and still then settled=settled+1 else settled=0 end
    -- LocationJump can reach coordinates while the destination geometry is
    -- absent. Never earn discovery from that void/ungrounded state (S trial).
    if settled>=3 then
        db:SetStoryFlagBP(FName(discovered_flag),true)
        if db:IsStoryFlag(FName(discovered_flag)) then
            db:SetStoryFlagBP(FName(pending_flag),false)
            started=nil;settled=0;write('guard_entry_grounded_arrival_verified_discovery_unlocked',p)
        end
    elseif os.time()-started>=120 then
        db:SetStoryFlagBP(FName(pending_flag),false)
        started=nil;settled=0;write('entry_arrival_not_verified_discovery_unchanged',p)
    else
        write('entry_pending_grounded_arrival_not_yet_verified',p)
    end
end
return M
