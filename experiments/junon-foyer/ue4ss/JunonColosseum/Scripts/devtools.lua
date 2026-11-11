-- Development tools, each switched on by a one-shot flag file in
-- the telemetry folder named by dev.txt and writing its own .tsv there. They cost one
-- file check per second when off. None runs in a normal session.
local M = {}
local T = require('paths').dev  -- nil outside development installs: every tool is off
local ARENA = {X=-123780, Y=28675}
local function valid(o) return o ~= nil and o:IsValid() end
local function take(name)
    local f = io.open(T..name, 'rb')
    if not f then return nil end
    local lines = {}
    for line in f:lines() do local l = line:gsub('[\r\n]', ''); if l ~= '' then lines[#lines+1] = l end end
    f:close(); os.remove(T..name)
    return lines
end
local function out(name)
    return io.open(T..name, 'ab')
end
local function arena_characters()
    local party, foes = {}, {}
    for _, a in ipairs(FindAllOf('EndCharacterBase') or {}) do
        if valid(a) then
            local p = a:K2_GetActorLocation()
            local dx, dy = p.X-ARENA.X, p.Y-ARENA.Y
            if dx*dx+dy*dy < 3000*3000 then
                if a:GetFName():ToString():find('^PC%d') then party[#party+1] = a else foes[#foes+1] = a end
            end
        end
    end
    return party, foes
end

-- junon-text.on: one text ID per line -> junon-text.tsv "id<TAB>English text"
-- (UEndMenuAPI.GetString). Our exports hold no English text.
local function text_dump()
    local ids = take('junon-text.on')
    if not ids then return end
    local api = StaticFindObject('/Script/EndGame.Default__EndMenuAPI')
    local f = io.open(T..'junon-text.tsv', 'wb')
    if not valid(api) or not f then if f then f:close() end return end
    for _, id in ipairs(ids) do
        local ok, text = pcall(function() return api:GetString(id) end)
        if ok and text ~= nil and type(text) ~= 'string' then ok, text = pcall(function() return text:ToString() end) end
        f:write(id..'\t'..(ok and tostring(text):gsub('[\r\n\t]', ' ') or 'ERR '..tostring(text))..'\n')
    end
    f:close()
end

-- junon-widgets.on (with a colosseum menu or result screen open): the full widget
-- tree of each open EndColosseumMenu / EndColosseumResultMenu (or the classes
-- named in the file, one per line): class, name, visibility, texture or text,
-- colour -> junon-widgets.tsv, indented by depth. For the Junon branding.
local function widget_dump()
    local roots = take('junon-widgets.on')
    if not roots then return end
    if #roots == 0 then roots = {'EndColosseumMenu', 'EndColosseumResultMenu'} end
    local f = io.open(T..'junon-widgets.tsv', 'wb')
    if not f then return end
    -- FLinearColor (images, borders, image sets, billboards)
    local function color(c) return string.format('%.2f,%.2f,%.2f,%.2f', c.R, c.G, c.B, c.A) end
    -- FSlateColor (text blocks)
    local function slate(c) return color(c.SpecifiedColor) end
    -- UE4SS pitfall: a failed member lookup leaks the Lua C stack even inside
    -- pcall (it killed this mod's Lua on 2026-11-09). Touch a member only on a
    -- widget whose class is known to have it.
    local classes = {}
    for key, path in pairs({image = '/Script/UMG.Image', border = '/Script/UMG.Border', text = '/Script/UMG.TextBlock',
                            rich = '/Script/UMG.RichTextBlock', user = '/Script/UMG.UserWidget', panel = '/Script/UMG.PanelWidget',
                            eimage = '/Script/EndGame.EndImage', etext = '/Script/EndGame.EndTextBlock',
                            eset = '/Script/EndGame.EndImageSet', ebill = '/Script/EndGame.EndBillboard',
                            eborder = '/Script/EndGame.EndBorder'}) do
        local c = StaticFindObject(path)
        if valid(c) then classes[key] = c end
    end
    local function is(w, key) return classes[key] ~= nil and w:IsA(classes[key]) end
    local lines = 0
    local function walk(w, depth)
        if lines > 4000 or depth > 30 or not valid(w) then return end
        lines = lines + 1
        local class = w:GetClass():GetFName():ToString()
        local name = w:GetFName():ToString()
        local extra = ''
        if is(w, 'image') then
            local r = w.Brush.ResourceObject
            extra = 'brush '..(valid(r) and r:GetFullName() or 'none')..' '..color(w.ColorAndOpacity)
        elseif is(w, 'border') then
            local r = w.Background.ResourceObject
            extra = 'background '..(valid(r) and r:GetFullName() or 'none')..' '..color(w.BrushColor)
        elseif is(w, 'text') or is(w, 'rich') then
            extra = 'text "'..w:GetText():ToString():gsub('[\r\n\t]', ' ')..'" '..(is(w, 'text') and slate(w.ColorAndOpacity) or '')
        elseif is(w, 'eimage') then
            local r = w.Brush.ResourceObject
            extra = 'brush '..(valid(r) and r:GetFullName() or 'none')..' '..color(w.ColorAndOpacity)
        elseif is(w, 'eborder') then
            local r = w.Background.ResourceObject
            extra = 'background '..(valid(r) and r:GetFullName() or 'none')..' '..color(w.BrushColor)
        elseif is(w, 'etext') then
            extra = 'text "'..w.Text:ToString():gsub('[\r\n\t]', ' ')..'" '..slate(w.ColorAndOpacity)
        elseif is(w, 'ebill') then
            extra = 'billboard '..color(w.ColorAndOpacity)
        elseif is(w, 'eset') then
            local names = {}
            w.Images:ForEach(function(_, element)
                local r = element:get().Brush.ResourceObject
                names[#names+1] = valid(r) and r:GetFullName() or 'none'
            end)
            extra = 'images '..table.concat(names, ' | ')..' '..color(w.ColorAndOpacity)
        end
        f:write(string.rep('  ', depth)..class..'\t'..name..'\t'..tostring(w:GetVisibility())..'\t'..extra..'\n')
        if is(w, 'user') then
            local tree = w.WidgetTree
            if valid(tree) then walk(tree.RootWidget, depth + 1) end
        end
        if is(w, 'panel') then
            for i = 0, w:GetChildrenCount() - 1 do walk(w:GetChildAt(i), depth + 1) end
        end
    end
    for _, class in ipairs(roots) do
        for _, root in ipairs(FindAllOf(class) or {}) do
            f:write('== '..class..' '..root:GetFullName()..'\n')
            pcall(walk, root, 0)
        end
    end
    f:close()
end

-- junon-enemies.on (in battle): each arena enemy's actor name, class, and the
-- territory the game reports for it (UEndFieldAPI.GetTerritoryIdFromActorName)
-- -> junon-enemies.tsv. Tells the difficulty code how to find spec and course.
local function enemy_dump()
    if not take('junon-enemies.on') then return end
    local field = StaticFindObject('/Script/EndGame.Default__EndFieldAPI')
    local f = out('junon-enemies.tsv')
    if not f then return end
    local _, foes = arena_characters()
    for _, e in ipairs(foes) do
        local name = e:GetFName():ToString()
        local okc, class = pcall(function() return e:GetClass():GetFName():ToString() end)
        local okt, tid = pcall(function() return field:GetTerritoryIdFromActorName(e:GetFName()):ToString() end)
        f:write(os.date('!%H:%M:%S')..'\t'..name..'\t'..tostring(okc and class)..'\t'..tostring(okt and tid or ('ERR '..tostring(tid)))..'\n')
    end
    f:close()
end

-- junon-spec.on (in battle): line 1 a BattleCharaSpec ID; apply it to every arena
-- enemy with UEndBattleAPI.SetOverrideBattleCharaSpec -> junon-spec.tsv.
local function spec_test()
    local lines = take('junon-spec.on')
    if not lines then return end
    local api = StaticFindObject('/Script/EndGame.Default__EndBattleAPI')
    local f = out('junon-spec.tsv')
    if not f then return end
    local _, foes = arena_characters()
    for _, e in ipairs(foes) do
        local ok, err = pcall(function() api:SetOverrideBattleCharaSpec(e, FName(lines[1])) end)
        f:write(os.date('!%H:%M:%S')..'\t'..e:GetFName():ToString()..'\t'..lines[1]..'\t'..tostring(ok)..'\t'..tostring(err)..'\n')
    end
    f:close()
end

-- junon-hp.on (in battle): line 1 a percent; for each fighter, test
-- IsHPPercent(above) for each comparison type 0..5, then SetHPPercent -> junon-hp.tsv.
local function hp_test()
    local lines = take('junon-hp.on')
    if not lines then return end
    local api = StaticFindObject('/Script/EndGame.Default__EndBattleAPI')
    local f = out('junon-hp.tsv')
    if not f then return end
    local pct = tonumber(lines[1]) or 75
    local party = arena_characters()
    for _, c in ipairs(party) do
        local cmp = {}
        for k = 0, 5 do
            local ok, v = pcall(function() return api:IsHPPercent(c, pct, k) end)
            cmp[#cmp+1] = k..'='..tostring(ok and v)
        end
        local ok, err = pcall(function() api:SetHPPercent(c, pct) end)
        f:write(os.date('!%H:%M:%S')..'\t'..c:GetFName():ToString()..'\t'..table.concat(cmp, ' ')..'\tset '..tostring(ok)..' '..tostring(err)..'\n')
    end
    f:close()
end

-- junon-party.on: one command per line, run in order -> junon-party.tsv, with
-- the battle slots and all-party list before and after.
--   change <type>:<mode> ...   UEndBattleAPI.ChangePartyMember (EPlayerType 0 Cloud
--                              .. 6 Cait Sith; EEndMenuJoinMode 0 NewJoin 1 ReJoin
--                              2 LeftOut 3 Reserve), showUI false
--   slot <type> <slot>         UEndPartyAPI.SetBattleSlotIndex
--   away <type> <0|1>          UEndPartyAPI.SetBattleAway
--   leader <type>              UEndPartyAPI.SetPartyLeaderType(type, false, true)
local function party_state(party)
    local out = {}
    for s = 0, 2 do
        local ok, t = pcall(function() return party:GetBattleMemberType(s) end)
        out[#out+1] = 'slot'..s..'='..tostring(ok and t)
    end
    local okc, n = pcall(function() return party:GetAllPartyMemberCount() end)
    out[#out+1] = 'all='..tostring(okc and n)
    for i = 0, (okc and n or 0) - 1 do
        local ok, t = pcall(function() return party:GetAllPartyMemberType(i) end)
        local okb, b = pcall(function() return party:IsBattleMember(t) end)
        out[#out+1] = tostring(ok and t)..(okb and b and '*' or '')
    end
    return table.concat(out, ' ')
end
local function party_test()
    local lines = take('junon-party.on')
    if not lines then return end
    local battle = StaticFindObject('/Script/EndGame.Default__EndBattleAPI')
    local party = StaticFindObject('/Script/EndGame.Default__EndPartyAPI')
    local f = out('junon-party.tsv')
    if not f or not valid(party) then if f then f:close() end return end
    f:write(os.date('!%H:%M:%S')..'\tbefore\t'..party_state(party)..'\n')
    for _, line in ipairs(lines) do
        local words = {}
        for w in line:gmatch('%S+') do words[#words+1] = w end
        local ok, err = false, 'unknown command'
        if words[1] == 'change' then
            local joins = {}
            for i = 2, #words do
                local t, m = words[i]:match('^(%d+):(%d+)$')
                joins[#joins+1] = {member = tonumber(t), Mode = tonumber(m)}
            end
            ok, err = pcall(function() battle:ChangePartyMember(joins, false) end)
        elseif words[1] == 'slot' then
            ok, err = pcall(function() party:SetBattleSlotIndex(tonumber(words[2]), tonumber(words[3])) end)
        elseif words[1] == 'away' then
            ok, err = pcall(function() party:SetBattleAway(tonumber(words[2]), words[3] == '1') end)
        elseif words[1] == 'leader' then
            ok, err = pcall(function() party:SetPartyLeaderType(tonumber(words[2]), false, true) end)
        end
        f:write(os.date('!%H:%M:%S')..'\t'..line..'\t'..tostring(ok)..'\t'..tostring(err)..'\t'..party_state(party)..'\n')
    end
    f:close()
end

-- junon-assets.on: lines "<class> <text>" -> every loaded object of that class
-- whose path contains text, to junon-assets.tsv (one object scan per line).
local function asset_find()
    local lines = take('junon-assets.on')
    if not lines then return end
    local f = out('junon-assets.tsv')
    if not f then return end
    for _, line in ipairs(lines) do
        local class, text = line:match('^(%S+)%s+(%S+)$')
        if class then
            local n = 0
            for _, o in ipairs(FindAllOf(class) or {}) do
                local name = o:GetFullName()
                if name:lower():find(text:lower(), 1, true) and n < 200 then n = n + 1; f:write(class..'\t'..name..'\n') end
            end
            f:write('-- '..line..': '..n..'\n')
        end
    end
    f:close()
end

-- junon-load.on: one full asset path per line ("/Game/Dir/Name.Name") -> whether
-- it loads (UE4SS LoadAsset), to junon-load.tsv. Finds assets that are not loaded yet.
local function load_test()
    local lines = take('junon-load.on')
    if not lines then return end
    local f = out('junon-load.tsv')
    if not f then return end
    for _, path in ipairs(lines) do
        local ok, obj = pcall(function() return LoadAsset(path) end)
        f:write(path..'\t'..tostring(ok and valid(obj) and obj:GetFullName() or ('missing '..tostring(obj)))..'\n')
    end
    f:close()
end

-- junon-eval.on (development builds only; devtools.lua is not shipped): run the
-- file as a Lua chunk on the game thread; `say(...)` writes to junon-eval.tsv.
-- Beware the UE4SS member-lookup pitfall in what you run.
local function eval()
    local f = io.open(T..'junon-eval.on', 'rb')
    if not f then return end
    local code = f:read('a') or ''
    f:close(); os.remove(T..'junon-eval.on')
    -- Output is kept in memory and written once at the end, to a new file
    -- (junon-eval-<n>.tsv): an engine error can unwind past pcall and would
    -- otherwise leave the file open.
    eval_runs = (eval_runs or 0) + 1
    local lines = {}
    local env = setmetatable({say = function(...)
        local parts = {}
        for i = 1, select('#', ...) do parts[#parts+1] = tostring((select(i, ...))) end
        lines[#lines+1] = table.concat(parts, '\t')
    end}, {__index = _G})
    local chunk, err = load(code, 'junon-eval', 't', env)
    if not chunk then lines[#lines+1] = 'LOAD '..tostring(err) else
        local ok, e = pcall(chunk)
        lines[#lines+1] = ok and 'OK' or ('ERR '..tostring(e))
    end
    local o = io.open(T..'junon-eval-'..eval_runs..'.tsv', 'wb')
    if o then o:write(table.concat(lines, '\n')..'\n'); o:close() end
end

-- Test aids for clearing courses unattended (the harness cannot press menu
-- buttons in gameplay). Both are switch files that stay until removed:
--   junon-autoboon.on   the boon window picks by itself: the option number in
--                       the file (default 1), "random", or "wait" (no pick
--                       until a number replaces it)
--   junon-testmode.on   fighters get Brave, Faith, Haste and Critical Up and
--                       cannot die; enemies drop to 10% HP once set up.
--                       Containing "immortal": they only cannot die (filming)
--                       "boostNN" (e.g. boost30): they cannot die and enemies
--                       start at NN% HP, with no buffs, so the infusions and
--                       rank rules under test are not masked (playtests)
-- junon-offer.on: infusion IDs (data/buffs.json), whitespace-separated; offers
-- walk this list in order instead of drawing at random (playtests: every
-- infusion gets its turn as option 1).
function M.offer_order()
    if not T then return nil end
    local f = io.open(T..'junon-offer.on', 'rb')
    if not f then return nil end
    local ids = {}
    for id in (f:read('a') or ''):gmatch('%S+') do ids[#ids+1] = id end
    f:close()
    return #ids > 0 and ids or nil
end
-- junon-combined.on (stays until removed): course 1's first rounds are forced,
-- for a deterministic combined-round test. Round IDs (no terVR_COL30_ prefix),
-- whitespace-separated, for rounds 1, 2, ...; an empty file means the build's
-- own test rounds (buffwheel_data.lua combined_test). Read at every draw and,
-- between courses, once a second (a change draws again).
function M.forced_rounds()
    if not T then return nil end
    local f = io.open(T..'junon-combined.on', 'rb')
    if not f then return nil end
    local ids = {}
    for id in (f:read('a') or ''):gmatch('%S+') do ids[#ids+1] = id end
    f:close()
    return #ids > 0 and ids or true
end
function M.autoboon(count)
    if not T then return nil end
    local f = io.open(T..'junon-autoboon.on', 'rb')
    if not f then return nil end
    local text = (f:read('a') or ''):gsub('%s', '')
    f:close()
    if text == 'random' then return math.random(1, count) end
    -- "wait": leave the window open until the agent, having read the offer line
    -- in junon-buffwheel.tsv, writes its chosen option number here.
    if text == 'wait' then return nil end
    return math.min(math.max(tonumber(text) or 1, 1), count)
end
function M.testmode()
    if not T then return false end
    local f = io.open(T..'junon-testmode.on', 'rb')
    if not f then return false end
    local text = (f:read('a') or ''):gsub('%s', '')
    f:close()
    if text == 'immortal' then return 'immortal' end
    local pct = tonumber(text:match('^boost(%d+)$'))
    if pct then return 'boost', math.max(1, math.min(100, pct)) end
    return true
end
M.test_party = {'BSC_Brave', 'BSC_Faith', 'BSC_Haste', 'BSC_CriticalUp'}

-- junon-unlock.on with a course number N (playtests): marks courses 1..N-1
-- cleared in memory, so courses up to N can be started without replaying the
-- earlier ones after a restart. Nothing is saved by this; a save made later
-- would keep the flags (use the test slot only). Consumed when read.
local function unlock()
    local f = io.open(T..'junon-unlock.on', 'rb')
    if not f then return end
    local n = tonumber(((f:read('a') or ''):gsub('%s', '')))
    f:close(); os.remove(T..'junon-unlock.on')
    local db = StaticFindObject('/Script/EndGame.Default__EndDataBaseAPI')
    if not n or not db or not db:IsValid() then return end
    local set = 0
    for c = 1, math.min(14, n) - 1 do
        local flag = FName(string.format('stfMod_JunonColosseum_%02d_Clear', c))
        if pcall(function() db:SetStoryFlagBP(flag, true) end) then set = set + 1 end
    end
    local o = io.open(T..'junon-unlock.tsv', 'wb')
    if o then o:write('unlocked\t'..set..'\tthrough\t'..n..'\n'); o:close() end
end
function M.tick()
    if not T then return end
    pcall(unlock)
    for _, tool in ipairs({text_dump, widget_dump, enemy_dump, spec_test, hp_test, party_test, asset_find, load_test, eval}) do pcall(tool) end
end
return M
