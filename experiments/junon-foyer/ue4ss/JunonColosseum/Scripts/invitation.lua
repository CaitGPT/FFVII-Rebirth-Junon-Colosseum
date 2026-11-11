local paths = require('paths')
-- Observe the native guard's missing-Invitation reward. No inventory edits,
-- debug action calls or unobserved broadcast receivers are used here.
local M={}
local started,verified=nil,false
local ROOT = paths.telemetry('junon-colosseum-invitation.json')
local function write(state,count)
    if not ROOT then return end
    local f=io.open(ROOT..'.tmp','wb')
    if not f then return end
    f:write('{"state":"'..state..'","count":'..tostring(count)..',"timestamp_utc":"'..os.date('!%Y-%m-%dT%H:%M:%SZ')..'","native_receipt_verified":'..tostring(state=='verified_native_inventory')..'}')
    f:close();os.remove(ROOT);os.rename(ROOT..'.tmp',ROOT)
end
function M.tick(db,pawn,policy)
    local count=db:GetItemNumBP(3902)
    if count>0 then
        if not verified then write('verified_native_inventory',count);verified=true end
        return
    end
    verified=false
    if not policy.grant_invitation then started=nil;return end
    local p=pawn:K2_GetActorLocation()
    local dx,dy=p.X+63836.7,p.Y-97102.6
    if dx*dx+dy*dy>5000*5000 then
        started=nil;write('awaiting_loaded_junon_guard_context',count);return
    end
    started=started or os.time()
    write(os.time()-started>=10 and 'guard_reward_not_verified_no_retry' or 'native_guard_reward_pending_readback',count)
end
return M
