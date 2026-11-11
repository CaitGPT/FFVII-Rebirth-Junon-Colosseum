"""Lua stand-ins shared by the tests."""

# paths.lua as in a development install, built on whatever io.open/os.remove the
# test has faked at call time (the tests read the receipts the modules write).
PATHS_STUB = '''
package.preload.paths = function()
    local M = {dev = 'telemetry/', mod = 'mod/'}
    function M.telemetry(name) return M.dev .. name end
    function M.open(name, mode) return io.open(M.dev .. name, mode) end
    function M.remove(name) os.remove(M.dev .. name) end
    function M.shared(name) return M.mod .. name end
    return M
end
'''
