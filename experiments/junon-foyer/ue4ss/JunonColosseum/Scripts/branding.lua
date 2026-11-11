local paths = require('paths')
-- Junon Colosseum branding on the colosseum menus (owner 2026-11-09: no
-- Musclehead branding; our own title and palette).
-- Live facts (widget dump 2026-11-09): every colosseum menu is one widget,
-- VR_Top_C (EndColosseumMenu), with four themes picked by index: 0 Combat
-- Simulator, 1 Gold Saucer (Musclehead), 2 Corneo, 3 Shinra Manor. LogoSet and
-- ListBgSet* hold each theme's logo and panel art; Pnl_GS_Deco* the Gold Saucer
-- flames; Pnl_TitleColiseum / Txt_TitleColiseum a text title the Corneo theme
-- uses. Our menu opens on the Gold Saucer theme (menu argument 5), and changing
-- that argument would mix our courses into another colosseum's list, so the
-- look is changed here, only in Junon, on widgets found by name.
-- UE4SS pitfall: a failed member lookup leaks the Lua C stack even in pcall, so
-- members are touched only on widgets whose class is checked first.
local M = {}
local TITLE = 'JUNON COLOSSEUM'
-- Palette from the Junon arena itself (owner 2026-11-09): dark teal-green steel
-- walls, red-and-white hazard stripes, stencilled codes ("ACY-312"), red "B" and
-- green "A" sector boards.
local STEEL = {R = 0.30, G = 0.78, B = 0.70, A = 1.0}  -- teal steel for the Gold Saucer's orange frames
local SKY = {R = 0.45, G = 0.75, B = 0.72, A = 1.0}    -- backdrop tint: towards the arena's teal
local THEME = 3                                       -- panel art set: 0 simulator, 1 Gold Saucer, 2 Corneo, 3 Shinra Manor (owner 2026-11-10)
-- The Gold Saucer backdrop (U_Com_GoldSaucerArena_Bg1_Sprite) has the Musclehead
-- logo and flames painted in; the pause menu's own backdrop is plain (live
-- 2026-11-09: no other colosseum backdrop exists under that naming).
-- Ours since 2026-11-10: the owner's photo of the arena floor (the Shinra emblem),
-- blurred and vignetted, packed as a texture in our archive (TexturePack.cs).
local BACKDROP = 'U_Com_JunonArena_Bg1'
local JUNON = {X = -123780, Y = 28675}                -- the arena; the foyer board is beside it
local RADIUS = 15000
local menus = {}                                      -- full name -> {widget, targets}
local classes = nil
local function valid(o) return o ~= nil and o:IsValid() end
local function log(line)
    local f = paths.open('junon-branding.tsv', 'ab')
    if f then f:write(os.date('!%H:%M:%S')..'\t'..line..'\n'); f:close() end
end
local function load_classes()
    if classes then return classes end
    classes = {}
    for key, path in pairs({user = '/Script/UMG.UserWidget', panel = '/Script/UMG.PanelWidget',
                            image = '/Script/EndGame.EndImage', text = '/Script/EndGame.EndTextBlock',
                            set = '/Script/EndGame.EndImageSet', bill = '/Script/EndGame.EndBillboard'}) do
        local c = StaticFindObject(path)
        if valid(c) then classes[key] = c end
    end
    return classes
end
local function is_class(w, key) local c = load_classes()[key]; return c ~= nil and w:IsA(c) end
local is = is_class
-- Live: while a menu is open the game has no player pawn, so the answer from
-- the last moment one existed is kept (set every second by M.tick).
local last_junon = false
local function in_junon()
    local helpers = require('UEHelpers')
    local pawn = helpers.GetPlayer()
    if valid(pawn) then
        local p = pawn:K2_GetActorLocation()
        local dx, dy = p.X - JUNON.X, p.Y - JUNON.Y
        last_junon = dx * dx + dy * dy < RADIUS * RADIUS
    end
    return last_junon
end
-- Walk once and remember what to change.
local function collect(root)
    local t = {title_panel = {}, title_text = {}, hide = {}, sets = {}, tint = {}, bills = {}, named = {}}
    local function walk(w, depth)
        if depth > 30 or not valid(w) then return end
        local name = w:GetFName():ToString()
        if name == 'Pnl_TitleColiseum' then t.title_panel[#t.title_panel+1] = w end
        if name == 'Txt_TitleColiseum' and is(w, 'text') then t.title_text[#t.title_text+1] = w end
        if name == 'LogoSet' or name:find('^Pnl_GS_Deco') then t.hide[#t.hide+1] = w end
        if is(w, 'set') and name:find('^ListBgSet') then t.sets[#t.sets+1] = w end
        if is(w, 'image') then
            local c = w.ColorAndOpacity
            if c.R > 0.9 and c.G > 0.4 and c.G < 0.6 and c.B < 0.1 then t.tint[#t.tint+1] = w end -- Gold Saucer orange
        end
        if is(w, 'bill') and name == 'Billboard_Bg' then t.bills[#t.bills+1] = w end
        if is(w, 'image') or is(w, 'text') or is(w, 'set') or is(w, 'panel') then
            t.named[name] = t.named[name] or {}
            table.insert(t.named[name], w)
        end
        if is(w, 'user') then
            local tree = w.WidgetTree
            if valid(tree) then walk(tree.RootWidget, depth + 1) end
        end
        if is(w, 'panel') then
            for i = 0, w:GetChildrenCount() - 1 do walk(w:GetChildAt(i), depth + 1) end
        end
    end
    walk(root, 0)
    -- The course rows live in a virtual scroll box, outside this tree: find them
    -- by class (one object scan per menu opening) so they can be styled too.
    for _, item in ipairs(FindAllOf('VR_ListItem_C') or {}) do
        if valid(item) then walk(item, 1) end -- rows still hidden by the intro animation too
    end
    return t
end
local function brand(entry)
    local t = entry.targets
    for _, w in ipairs(t.title_panel) do if valid(w) then w:SetVisibility(4) end end   -- SelfHitTestInvisible
    for _, w in ipairs(t.title_text) do if valid(w) then w:SetText(TITLE) end end
    for _, w in ipairs(t.hide) do if valid(w) then w:SetVisibility(1) end end          -- Collapsed
    for _, w in ipairs(t.sets) do if valid(w) then w:SetSelectedIndex(THEME) end end
    for _, w in ipairs(t.tint) do if valid(w) then w:SetColorAndOpacity(STEEL) end end
    for _, w in ipairs(t.bills) do if valid(w) then w:SetColorAndOpacity(SKY) end end
end
-- Development only: junon-style.txt in the dev.txt telemetry folder restyles the
-- open menu without a restart (read each time a menu opens). One rule per line:
--   theme N                 panel art set (0 simulator, 1 Gold Saucer, 2 Corneo, 3 Shinra Manor)
--   sky R G B A             backdrop tint
--   tint NAME R G B A       every image or text widget named NAME
--   hide NAME | show NAME   visibility
--   opacity NAME A          render opacity
--   text NAME words...      text
--   gradient NAME R G B A   text fades from its colour to this one, top to bottom
--   outline NAME R G B A    text outline
--   shadow NAME DX DY R G B A  text drop shadow
--   hidefrom NAME R0 G0 B0 A0  hide images at colour R0..A0 (visibility is not animated)
--   opacityfrom NAME R0 G0 B0 A0 A  render opacity for images at colour R0..A0; unlike a
--                           tint, the game's highlight animations never reset it
--   tintfrom NAME R0 G0 B0 A0 R G B A  tint only widgets still at colour R0..A0 (to tell
--                           apart same-named widgets, e.g. a row's Base from a badge's)
-- (EndTextBlock's own members: its Font is an EndFont object, not FSlateFontInfo,
-- so reading w.Font as a struct failed and unwound the Lua state, 2026-11-10.)
-- Releases have no telemetry folder, so the file never applies for players; the
-- built-in rules below always do, and a dev file's rules follow them.
-- Row backgrounds fade (opacityfrom) rather than tint (owner preferred it to hiding them): the game's highlight animation
-- reset a tinted row to white for a frame when the cursor left it (owner, 2026-11-10).
-- The look the owner approved on 2026-11-10: Shinra Manor panels (THEME), no glow
-- behind the title, the course name in light teal-steel, and dark steel course rows
-- with light text (the game animates the title text's colour, so it is left alone).
-- The result screen's simulator blues (title streak, difficulty, round count,
-- advice and prize headings) in the same teal-steel (owner approved, 2026-11-10).
local BUILTIN = [[
hide Light1
tint Txt_CourseTitle 0.70 0.88 0.88 1
opacityfrom Base 0.90 0.90 0.90 0.90 0.12
tintfrom Txt_Name 0.08 0.08 0.08 1 0.86 0.90 0.92 1
tintfrom Icon_Lock 0.10 0.10 0.10 1 0.62 0.68 0.70 1
tint TitleLight 0.60 0.80 0.80 0.30
tint TtileLine 0.75 0.85 0.85 1
tint IconLineRight 0.70 0.88 0.88 0.6
tint IconLineLeft 0.70 0.88 0.88 0.6
tint Txt_DifficultyTitle 0.62 0.72 0.76 1
tint Txt_Turn 0.60 0.86 0.86 1
tint Txt_FailedInfo 0.60 0.86 0.86 1
tint Txt_TitlePrize 0.60 0.86 0.86 1
]]
local style = nil
local function parse(text, into)
    for line in (text or ''):gmatch('[^\r\n]+') do
        local words = {}
        for w in line:gmatch('%S+') do words[#words+1] = w end
        if #words > 0 and words[1]:sub(1, 1) ~= '#' then into[#into+1] = {line = line, words = words} end
    end
end
local function read_style()
    style = {}
    parse(BUILTIN, style)
    local path = paths.telemetry('junon-style.txt')
    local f = path and io.open(path, 'rb')
    if not f then return end
    parse(f:read('a'), style)
    f:close()
end
local function rgba(words, from)
    return {R = tonumber(words[from]) or 1, G = tonumber(words[from+1]) or 1,
            B = tonumber(words[from+2]) or 1, A = tonumber(words[from+3]) or 1}
end
-- Rules the game's own highlight animations can undo, so they are checked again
-- on row changes; the rest stick once applied at opening (owner 2026-11-11: moving
-- between course rows lagged while every rule ran on every hook and every 50 ms).
local DYNAMIC = {tint = true, opacityfrom = true, tintfrom = true, hidefrom = true, opacity = true}
local function near(c, want)
    return c ~= nil and math.abs(c.R - want.R) < 0.02 and math.abs(c.G - want.G) < 0.02
       and math.abs(c.B - want.B) < 0.02 and math.abs(c.A - want.A) < 0.02
end
local function apply_style(t, light)
    if not style then return end
    local once = not t.fonts_done
    t.fonts_done = true
    -- Class checks cached per widget for this walk of the menu (IsA is a call each time).
    t.kinds = t.kinds or {}
    local function is(w, key)
        local m = t.kinds[w]
        if not m then m = {}; t.kinds[w] = m end
        local v = m[key]
        if v == nil then v = is_class(w, key); m[key] = v end
        return v
    end
    for _, s in ipairs(style) do
        local op, name, words = s.words[1], s.words[2], s.words
        if light and not DYNAMIC[op] then
            -- static rule: applied when the menu opened
        elseif op == 'theme' then
            for _, w in ipairs(t.sets) do if valid(w) then w:SetSelectedIndex(tonumber(name) or THEME) end end
        elseif op == 'sky' then
            for _, w in ipairs(t.bills) do if valid(w) then w:SetColorAndOpacity(rgba(words, 2)) end end
        else
            for _, w in ipairs(t.named[name or ''] or {}) do
                if valid(w) then
                    -- A tint is set only when the widget is not already that colour:
                    -- reading a property is cheap, a set re-lays the widget out.
                    if op == 'tint' and is(w, 'text') then
                        local want = rgba(words, 3)
                        if not near(w.ColorAndOpacity.SpecifiedColor, want) then
                            w:SetColorAndOpacity({SpecifiedColor = want, ColorUseRule = 0})
                        end
                    elseif op == 'tint' and is(w, 'image') then
                        local want = rgba(words, 3)
                        if not near(w.ColorAndOpacity, want) then w:SetColorAndOpacity(want) end
                    elseif op == 'hide' then w:SetVisibility(1)
                    elseif op == 'show' then w:SetVisibility(4)
                    elseif op == 'opacity' then w:SetRenderOpacity(tonumber(words[3]) or 1)
                    elseif op == 'text' and is(w, 'text') then w:SetText(s.line:match('^%s*text%s+%S+%s+(.*)$') or '')
                    elseif op == 'hidefrom' and is(w, 'image') then
                        local want, c = rgba(words, 3), w.ColorAndOpacity
                        if math.abs(c.R - want.R) < 0.02 and math.abs(c.G - want.G) < 0.02
                           and math.abs(c.B - want.B) < 0.02 and math.abs(c.A - want.A) < 0.02 then
                            w:SetVisibility(2) -- Hidden: keeps the layout, and no colour animation shows it
                        end
                    elseif op == 'opacityfrom' and is(w, 'image') then
                        local want, c = rgba(words, 3), w.ColorAndOpacity
                        if math.abs(c.R - want.R) < 0.02 and math.abs(c.G - want.G) < 0.02
                           and math.abs(c.B - want.B) < 0.02 and math.abs(c.A - want.A) < 0.02 then
                            w:SetRenderOpacity(tonumber(words[7]) or 1)
                        end
                    elseif op == 'tintfrom' then
                        local want = rgba(words, 3)
                        local c = is(w, 'text') and w.ColorAndOpacity.SpecifiedColor or (is(w, 'image') and w.ColorAndOpacity)
                        if c and math.abs(c.R - want.R) < 0.02 and math.abs(c.G - want.G) < 0.02
                           and math.abs(c.B - want.B) < 0.02 and math.abs(c.A - want.A) < 0.02 then
                            if is(w, 'text') then w:SetColorAndOpacity({SpecifiedColor = rgba(words, 7), ColorUseRule = 0})
                            else w:SetColorAndOpacity(rgba(words, 7)) end
                        end
                    elseif op == 'gradient' and once and is(w, 'text') then
                        w.Gradient = true
                        w.BottomColorAndOpacity = {SpecifiedColor = rgba(words, 3), ColorUseRule = 0}
                    elseif op == 'outline' and once and is(w, 'text') then
                        w.Outline = true
                        w.OutlineColorAndOpacity = rgba(words, 3)
                    elseif op == 'shadow' and once and is(w, 'text') then
                        w.ShadowOffset = {X = tonumber(words[3]) or 0, Y = tonumber(words[4]) or 0}
                        w.ShadowColorAndOpacity = rgba(words, 5)
                    end
                end
            end
        end
    end
end
local backdrop_asset = nil                            -- keeps our backdrop loaded
local backdrop_tried = false                          -- asked once per game session
local result_menu = nil                               -- the colosseum result screen, once created
-- True while the colosseum's result screen shows: a course has just ended
-- (buffwheel.lua's end-of-course signal).
function M.result_visible()
    return valid(result_menu) and result_menu:IsVisible()
end
-- Returns true once the menu's widgets are known (its tree is built).
local function adopt(menu)
    if not valid(menu) then return false end
    local result_class = StaticFindObject('/Script/EndGame.EndColosseumResultMenu')
    if valid(result_class) and menu:IsA(result_class) then result_menu = menu end
    local key = menu:GetFullName()
    if menus[key] then return true end
    local ok, targets = pcall(collect, menu)
    if not ok then log('collect_failed\t'..tostring(targets)); return false end
    if #targets.title_text + #targets.bills + #targets.hide == 0 then return false end -- not built yet
    menus[key] = {widget = menu, targets = targets}
    for _, b in ipairs(targets.bills) do
        local ok2, path = pcall(function() return b.ImagePath.AssetPathName:ToString() end)
        log('backdrop\t'..tostring(ok2 and path))
    end
    log(string.format('adopted\t%s\ttitle=%d hide=%d sets=%d tint=%d bills=%d', key, #targets.title_text,
        #targets.hide, #targets.sets, #targets.tint, #targets.bills))
    return true
end
-- Dev switch (junon-backdrop.on, one shot): line 1 an asset name for the menu
-- backdrop (EndBillboard.SetImageAssetNameString); also logs where the game
-- resolves that name. Live: ours is U_Com_GoldSaucerArena_Bg1_Sprite in
-- /Game/Menu/Billboard/Common.
local function backdrop_test()
    local path = paths.telemetry('junon-backdrop.on')
    local f = io.open(path, 'rb')
    if not f then return end
    local name = (f:read('a') or ''):gsub('%s', '')
    f:close(); os.remove(path)
    local cdo = StaticFindObject('/Script/EndGame.Default__EndBillboard')
    local okp, soft = pcall(function() return cdo:MakeImagePathFromAssetNameString(name).AssetPathName:ToString() end)
    log('backdrop_path\t'..name..'\t'..tostring(okp and soft or ('ERR '..tostring(soft))))
    for _, entry in pairs(menus) do
        for _, b in ipairs(entry.targets.bills) do
            if valid(b) then
                local ok, err = pcall(function() b:SetImageAssetNameString(name, true, true) end)
                log('backdrop_set\t'..name..'\t'..tostring(ok)..'\t'..tostring(err))
            end
        end
    end
end
-- Brand every cached menu that is showing. Runs every 50 ms (owner 2026-11-10:
-- at one-second steps the result screen showed Musclehead for a second or two
-- before ours). Only cached widgets are touched and Junon is the answer kept by
-- the one-second tick, so this costs a few calls per run, no object scans.
-- Live 2026-11-10: a menu adopted as it was created was still half-built (two of
-- five decorations, no frames), so the widgets are walked again each time a menu
-- opens, and once more a second later.
local function refresh(entry)
    local ok, targets = pcall(collect, entry.widget)
    if ok and targets then entry.targets = targets end
end
-- light: a row change or the backup loop, on a menu already branded this opening:
-- only the rules the game's animations can undo (see DYNAMIC).
local function show(entry, light)
    if light and entry.open and not (entry.again and os.time() >= entry.again) then
        -- The frame and backdrop tints too, in case an animation fades them: read first, set only if changed.
        pcall(function()
            for _, w in ipairs(entry.targets.tint) do
                if valid(w) and not near(w.ColorAndOpacity, STEEL) then w:SetColorAndOpacity(STEEL) end
            end
            for _, w in ipairs(entry.targets.bills) do
                if valid(w) and not near(w.ColorAndOpacity, SKY) then w:SetColorAndOpacity(SKY) end
            end
        end)
        if style then pcall(apply_style, entry.targets, true) end
        return
    end
    if not entry.open then
        entry.open = true
        entry.again_count = 0
        refresh(entry)
        read_style()
        entry.targets.fonts_done = false
        entry.again = os.time() + 1
        -- The backdrop once per opening: setting it reloads the image.
        for _, b in ipairs(entry.targets.bills) do
            if valid(b) then pcall(function() b:SetImageAssetNameString(BACKDROP, true, true) end) end
        end
    elseif entry.again and os.time() >= entry.again then
        -- Again 1 s and 3 s after opening: the last course rows appear late.
        entry.again = (entry.again_count or 0) < 1 and os.time() + 2 or nil
        entry.again_count = (entry.again_count or 0) + 1
        refresh(entry)
    end
    local ok, err = pcall(brand, entry)
    if ok and style then pcall(apply_style, entry.targets) end
    if not ok and not entry.failed then entry.failed = true; log('brand_failed\t'..tostring(err)) end
end
local function show_all(light)
    for key, entry in pairs(menus) do
        if not valid(entry.widget) then menus[key] = nil
        elseif last_junon and entry.widget:IsVisible() then show(entry, light)
        else entry.open = false end
    end
end
-- From hooks on the menus' own functions: brand in the same frame as the game
-- sets the menu up, so its Gold Saucer look never reaches the screen.
local menu_classes = nil
-- The course the player has highlighted, from the menu's course title: the one
-- they start is the last one shown. buffwheel.lua takes the course from it (live
-- 2026-11-10: guessing the course from the round draw applied course 3's rules
-- to course 2 when a course was started straight after the last one ended).
local selected = nil
local function note_course(entry)
    for _, w in ipairs(entry.targets.named['Txt_CourseTitle'] or {}) do
        if valid(w) then
            local ok, text = pcall(function() return w:GetText():ToString() end)
            if ok and type(text) == 'string' and text ~= '' then selected = {title = text, at = os.time()} end
        end
    end
end
function M.selected_course() return selected end
local function on_menu(obj, light)
    if not last_junon or not valid(obj) then return end
    if not menu_classes then
        menu_classes = {}
        for _, path in ipairs({'/Script/EndGame.EndColosseumMenu', '/Script/EndGame.EndColosseumResultMenu'}) do
            local c = StaticFindObject(path)
            if valid(c) then menu_classes[#menu_classes+1] = c end
        end
    end
    local ours = false
    for _, c in ipairs(menu_classes) do if obj:IsA(c) then ours = true end end
    if not ours then return end
    local entry = menus[obj:GetFullName()]
    if not entry and adopt(obj) then entry = menus[obj:GetFullName()] end
    if entry then show(entry, light); pcall(note_course, entry) end
end
-- Once a second from the gate loop: refresh the Junon answer, dev switches.
function M.tick()
    -- Keep our backdrop loaded so the swap does not wait for it: loaded the first
    -- time the player is in Junon, never while the game is still starting up
    -- (a startup hang on 2026-11-10 made a load at mod start a needless risk).
    if last_junon and not backdrop_tried then
        backdrop_tried = true
        pcall(function() backdrop_asset = LoadAsset('/Game/Menu/Billboard/Common/'..BACKDROP..'.'..BACKDROP) end)
    end
    pcall(backdrop_test)
    in_junon()
    show_all()
end
-- The menus are created when first opened and then reused: adopt each as soon
-- as its widget tree exists (retried every 50 ms for up to three seconds), and
-- brand it straight away.
function M.register()
    local function attempt(obj, n)
        local ok, done = pcall(adopt, obj)
        if ok and done then pcall(show_all)
        elseif n < 60 then
            ExecuteWithDelay(50, function() ExecuteInGameThread(function() attempt(obj, n + 1) end) end)
        end
    end
    for _, class in ipairs({'/Script/EndGame.EndColosseumMenu', '/Script/EndGame.EndColosseumResultMenu'}) do
        pcall(NotifyOnNewObject, class, function(obj)
            ExecuteInGameThread(function() attempt(obj, 0) end)
        end)
    end
    -- The game's own set-up calls (course list items, selection changes, and
    -- every End menu's show and animation calls), after they run.
    -- Setting up and showing a menu brand it fully; a row change and the
    -- highlight animations it plays (several per move) only re-check the rules
    -- those animations can undo.
    for fn, light in pairs({['/Script/EndGame.EndColosseumMenu:OnCourseMenuSetupItem'] = false,
                            ['/Script/EndGame.EndColosseumMenu:OnCourseMenuSelectedIndexChanged'] = true,
                            ['/Script/EndGame.EndUserWidget:AddToViewportEx'] = false,
                            ['/Script/EndGame.EndUserWidget:PlayAnimationEx'] = true}) do
        local ok, err = pcall(RegisterHook, fn, function() end, function(self)
            pcall(on_menu, self:get(), light)
        end)
        if not ok then log('hook_failed\t'..fn..'\t'..tostring(err)) end
    end
    -- Backup loop: notices a menu opening (or its 1 s and 3 s passes) within
    -- 50 ms; on an open menu it re-checks the animated rules every fourth pass.
    local loops = 0
    LoopAsync(50, function()
        loops = loops + 1
        local recheck = loops % 4 == 0
        ExecuteInGameThread(function()
            local due = recheck
            if not due then
                for _, entry in pairs(menus) do
                    if not entry.open or (entry.again and os.time() >= entry.again) then due = true; break end
                end
            end
            if due then pcall(show_all, true) end
        end)
        return false
    end)
end
return M
