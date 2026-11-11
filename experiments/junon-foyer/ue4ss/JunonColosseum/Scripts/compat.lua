-- Compatibility with our other mods.
-- Training Dummy adds three Combat Simulator courses to the same Colosseum
-- tables our archive replaces, and our archive loads over Training Dummy's
-- (its _999_P name mounts later). So our archive carries those three courses
-- too, shown only through FLAG: this sets it when Training Dummy is installed
-- and enabled and the Grasslands simulator is open (the course's own
-- condition). Without Training Dummy they stay hidden. Biome Randomizer and
-- Battle Meters ship no table changes and need nothing here.
local paths = require('paths')
local M = {}
local FLAG = 'stfMod_JunonColosseum_TrainingDummyShown'
local VR_OPEN = 'stf1210_CHOFA_VROpen_Gras'

local function read(path)
    local f = io.open(path, 'rb')
    if not f then return nil end
    local text = f:read('a') or ''
    f:close()
    return text
end

-- UE4SS starts a mod when mods.txt lists it with 1 or its folder has enabled.txt.
function M.mod_enabled(name)
    local mods = paths.mod..'../'
    if not read(mods..name..'/Scripts/main.lua') then return false end
    if read(mods..name..'/enabled.txt') then return true end
    for line in (read(mods..'mods.txt') or ''):gmatch('[^\r\n]+') do
        local key, value = line:match('^%s*([%w_%-]+)%s*:%s*(%d+)')
        if key == name then return value == '1' end
    end
    return false
end

-- mods.txt and the folders are read once: UE4SS reads them only at start-up.
M.training_dummy = M.mod_enabled('TrainingDummy')

function M.tick(db)
    local want = M.training_dummy and db:IsStoryFlag(FName(VR_OPEN)) == true
    if db:IsStoryFlag(FName(FLAG)) ~= want then db:SetStoryFlagBP(FName(FLAG), want) end
end

return M
