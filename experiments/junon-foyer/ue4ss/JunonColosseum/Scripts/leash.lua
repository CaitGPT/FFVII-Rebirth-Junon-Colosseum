-- Arena leash: puts an enemy that stays outside the ring back inside.
-- Live (2026-11-10): a Mindflayer teleported past the arena wall and got stuck
-- there, so neither side could reach the other and the round never ended.
-- buffwheel.lua calls leash.tick once per second during a round and
-- leash.reset at the start of each new round.
-- Flying enemies and knockback can briefly cross the edge, so an enemy must be
-- out for OUT_SECONDS ticks in a row before it is moved.
-- Only cheap, known members are used (a failed member lookup in UE4SS can
-- unwind the Lua state even inside pcall): IsValid, GetFullName, GetFName,
-- K2_GetActorLocation and K2_SetActorLocation.
local M = {}
local ARENA = {X=-123780, Y=28675}
local LEASH = 2300       -- farther than this from the centre (XY) counts as out
local RETURN = 1200      -- how far from the centre an enemy is put back
local OUT_SECONDS = 3    -- ticks out in a row before acting
local COOLDOWN = 5       -- seconds after a move before it can be counted again
local MAX_MOVES = 10     -- moves per enemy per round; then stop (no loops)
local LEADER_LIFT = 100  -- above the leader's Z when an enemy was never seen inside
local state = {}         -- per enemy, by full name: {out, inside_z, moved_at, moves, capped}
local log = nil          -- optional log function, set by set_log
local function valid(o) return o ~= nil and o:IsValid() end
local function say(...)
    if log then log(table.concat({...}, '\t')) end
end
local function int(n) return string.format('%d', math.floor(n + 0.5)) end
-- Forget every enemy (new round).
function M.reset() state = {} end
-- Optional: fn(line) receives one tab-separated line per move.
function M.set_log(fn) log = fn end
-- Where to put an enemy back: RETURN from the centre along its own bearing.
local function target(p, dist)
    local dx, dy = 1, 0  -- exactly at the centre: no bearing, use +X
    if dist > 0 then dx, dy = (p.X-ARENA.X)/dist, (p.Y-ARENA.Y)/dist end
    return ARENA.X + dx*RETURN, ARENA.Y + dy*RETURN
end
-- The height to put it back at: its last height inside the ring, else just
-- above the leader, else where it is now.
local function height(s, p, leader)
    if s.inside_z then return s.inside_z end
    if valid(leader) then return leader:K2_GetActorLocation().Z + LEADER_LIFT end
    return p.Z
end
-- Called once per second during a round. api is unused for now (kept so the
-- call matches the other modules); foes is an array of enemy actors; leader is
-- the party leader (may be nil); now is os.time().
function M.tick(api, foes, leader, now)
    local moved = 0
    for _, foe in ipairs(foes or {}) do
        if valid(foe) then
            local key = foe:GetFullName()
            local s = state[key]
            if not s then s = {out=0, moves=0}; state[key] = s end
            local p = foe:K2_GetActorLocation()
            local dx, dy = p.X-ARENA.X, p.Y-ARENA.Y
            local dist = math.sqrt(dx*dx+dy*dy)
            if dist <= LEASH then
                s.out = 0
                s.inside_z = p.Z
            elseif s.capped or (s.moved_at and now < s.moved_at + COOLDOWN) then
                s.out = 0  -- given up on, or just moved: not counted
            else
                s.out = s.out + 1
                if s.out >= OUT_SECONDS then
                    local name = foe:GetFName():ToString()
                    if s.moves >= MAX_MOVES then
                        s.capped = true
                        say('leash', name, int(dist), 'cap', tostring(s.moves))
                    else
                        local x, y = target(p, dist)
                        local z = height(s, p, leader)
                        local ok = pcall(function()
                            foe:K2_SetActorLocation({X=x, Y=y, Z=z}, false, {}, true)
                        end)
                        -- A failed move still counts, so a stuck enemy cannot loop.
                        s.out, s.moved_at, s.moves = 0, now, s.moves + 1
                        if ok then
                            moved = moved + 1
                            say('leash', name, int(dist), int(x), int(y), int(z), tostring(s.moves))
                        else
                            say('leash', name, int(dist), 'failed', tostring(s.moves))
                        end
                    end
                end
            end
        end
    end
    return moved
end
return M
