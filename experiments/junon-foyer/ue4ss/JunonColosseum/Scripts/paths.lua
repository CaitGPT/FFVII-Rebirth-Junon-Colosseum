-- Where this mod keeps its files, on any machine.
-- M.mod: the mod's own folder (…/ue4ss/Mods/<this mod>/), from where this
-- script was loaded. The files the mod and its native helper exchange live there.
-- Development installs carry dev.txt in that folder, naming a telemetry folder;
-- release packages do not, and then no telemetry is written and no diagnostic
-- switch file is read (every telemetry path below is nil).
local M = {}
local source = (debug.getinfo(1, 'S').source or ''):gsub('^@', '')
M.mod = source:gsub('[/\\][Ss]cripts[/\\][^/\\]+$', '')..'/'
local f = io.open(M.mod..'dev.txt', 'rb')
if f then
    local dir = (f:read('a') or ''):gsub('%s+$', '')
    f:close()
    if dir ~= '' then M.dev = dir:gsub('[/\\]?$', '/') end
end
-- A telemetry file's path, or nil in a release.
function M.telemetry(name) return M.dev and (M.dev..name) or nil end
function M.open(name, mode)
    local path = M.telemetry(name)
    return path and io.open(path, mode) or nil
end
function M.remove(name)
    local path = M.telemetry(name)
    if path then os.remove(path) end
end
-- Write a whole telemetry file atomically (temporary file, then rename).
function M.replace(name, text)
    local path = M.telemetry(name)
    if not path then return end
    local out = io.open(path..'.tmp', 'wb')
    if not out then return end
    out:write(text); out:close()
    os.remove(path); os.rename(path..'.tmp', path)
end
-- A file in the mod's own folder (the mod and helper exchange these).
function M.shared(name) return M.mod..name end
return M
