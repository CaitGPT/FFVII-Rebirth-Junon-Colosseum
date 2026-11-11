local paths = require('paths')
-- Between-round boons (owner design 2026-11-09: the player picks a buff between
-- rounds; any polished choice will do).
-- Live facts (2026-11-09): each round of a native course is its own battle, and
-- between rounds there is only a "Get Ready" loading screen, so no field
-- dialogue can show there. The game's own message window
-- (UEndMenuAPI.ShowMessageWindow, flag PauseMenu) opens from Lua at any time with
-- our text and options. So from round 1 on, shortly after the round begins, the
-- battle pauses on that window with three random boons from data/buffs.json
-- (owner 2026-11-10: round 1 too; tiered, with epics likelier after a boss round).
-- The pick applies at once and stays for the rest of the run: its statuses go on
-- the party at every later round start and once on every enemy (Arms race, a
-- rank rule, also gives every enemy one enemy boon per pick). Nothing is
-- saved: picks live in this Lua state and end with the course (run builds are
-- ephemeral; only course-clear rewards are permanent).
-- Cheap calls only: one enemy count per second during our battles; one object
-- scan when more enemies appear or a boon is picked.
local data = require('buffwheel_data')
local leash = require('leash')   -- keeps enemies inside the ring
local M = {}
local ARENA = {X=-123780, Y=28675}
local INFINITY = 64      -- EEndBattleStatusChangeTimeType: lasts until the battle ends
local SHORT = 0          -- EEndBattleStatusChangeTimeType.Short: the game's own brief time
-- Full ATB (SetATB value; the engine clamps it to the gauge) and how often a
-- lapsed special effect (Refocus, ATB regeneration) is given again.
local ATB_FULL = 3000
local REFRESH = 3
-- Accessory-style infusions approximated in Lua (owner 2026-11-10). Not yet
-- verified in game: every call is guarded and each firing is logged.
-- Limit values are fractions of the fighter's gauge (BPGetPlayerLimitMax).
local LIMIT_TICK_SECONDS = 5   -- Gotterdammerung: every 5 fight seconds...
local LIMIT_TICK_SLICE = 0.04  -- ...4% of the gauge (empty to full in about two minutes)
local EFFECT_LOG_GAP = 10      -- seconds between log lines per effect and fighter
local party_now = {}     -- this round's fighters
-- Short rest records (a rank rule; see lean_apply): per EPlayerType, the HP %
-- and stored MP each fighter ended its last round with (live: this round's
-- latest MP reading per fighter).
local function fresh_lean() return {hp = {}, mp = {}, live = {}, gap = {}, kinds = {}, caps = {}, sample_at = 0} end
local lean = fresh_lean()
-- Live 2026-11-10: a full limit gauge set as the round began was back to its
-- old value a moment later (the game's own battle set-up runs after ours), so
-- round-start actions are given again ACTION_DELAY seconds in.
local ACTION_DELAY = 3
local DRAIN_SECONDS, DRAIN_STEP = 5, 3  -- playtest boost only
-- An enemy left at 1% this long loses its protective statuses so the party can
-- land the last blow (live 2026-11-10: a boss with a Rivals Regen out-healed
-- 14-40 a hit at 1% for 17 minutes). Setting 0% HP instead failed the course
-- when done in the final round ("Challenge Failed"), so the kill stays real.
local DRAIN_FINISH = 20
-- (BSC_Reraise stays on the list as a guard: since 2026-11-11 the mod gives it
-- to no enemy; see second_wind below.)
local STRIP = {'BSC_Regeneration', 'BSC_Barrier', 'BSC_MBarrier', 'BSC_Protes', 'BSC_Shell',
               'BSC_Reflection', 'BSC_Shield', 'BSC_Reraise', 'BSC_Invincible'}
local drain_clock = 0
local at_floor = {}      -- enemy full name -> drain clock when first seen at 1%
local actions_at = nil
local refresh_at = 0
local PAUSE_MENU = 2     -- EEndMenuMessageWindowFlags.PauseMenu
local OFFER_DELAY = 1    -- whole seconds into a round before the window opens...
local OFFER_EXTRA_MS = 500 -- ...plus this (owner 2026-11-10: 0.5 s earlier than the 2 s before)
local active = false     -- in a course in our arena
local in_round = false   -- in one of its battles
local started = false    -- this battle's round start has been handled
local enemies_seen = 0   -- enemies counted at the last tick
local round_max = 0      -- the most enemies at once this round (combined rounds: both groups)
local round_territory = nil -- this round's territory as the helper names it (no prefix)
local idle_since = 0     -- when the last round's battle ended
local stalled = false    -- the stall watchdog fired in this gap (diagnostics)
local battle_since = 0   -- when this round's battle began
local spawn_stalled = false -- the spawn-stall watchdog fired in this battle (diagnostics)
local round = 0
local buffed = {}        -- enemy actors already given this run's enemy boons
local picks = {}         -- boons chosen this run, in order
local winded = {}        -- Second wind: enemy full name -> 'watch' (hardened on a course
                         -- with the rule) or 'done' (it has risen); see second_wind
local arms = {}          -- Arms race: enemy boons drawn this course, one per pick
local boons_of = {}      -- this round: enemy full name -> {status = true} for every enemy
                         -- boon or rank-rule status the mod gave it (Rally prefers new ones)
local owed = {}          -- Rally boons for enemies not hardened yet: full name -> {ids}
local offer_at = nil     -- when to open this round's window
local window, offered = nil, nil -- the open window and its three boons
local window_at = 0      -- when it opened
local candidates = {}    -- courses the enemies seen so far fit (course design order)
local from_menu = false  -- this run's course came from the menu (branding.lua)
local course = nil       -- the course in play once known: data.courses[course]
local GREATER = 3        -- EEndAiMathCmp.Greater
local LESS = 1           -- EEndAiMathCmp.Less (Equal, Less, LessEqual, Greater, GreaterEqual, NotEqual)
local HARDEN_DELAY = 2   -- seconds between first seeing an enemy and changing it
local pending = {}       -- enemies seen but not yet hardened: {actor, at}
local SWAP_CHECK = 2     -- seconds between a spec swap and checking that it took
local swaps = {}         -- spec swaps to check: {actor, clone, before (max HP), hp (factor), at, tries}
local unknown = {}       -- names logged as spec_unknown this course
local foes_now = {}      -- this round's enemies, for the leash
local function valid(o) return o ~= nil and o:IsValid() end
local function log(line)
    local f = paths.open('junon-buffwheel.tsv', 'ab')
    if f then f:write(os.date('!%H:%M:%S')..'\t'..line..'\n'); f:close() end
end
-- Stall watchdog (diagnostics; development installs only). Live 2026-11-10 two
-- courses hung on an endless "Get Ready" between rounds. The usual gap is about
-- 20 s: after STALL_SECONDS without a battle the gap is logged once and
-- junon-stall.on asks the native helper to log, once a second, what the
-- colosseum's own between-round checks wait for (junon-stall.tsv). The switch
-- goes when a battle starts or the course ends. Releases have no telemetry
-- folder: nothing is written there.
local STALL_SECONDS = 45
local function unstall()
    if stalled then stalled = false; paths.remove('junon-stall.on') end
end
-- Spawn-stall watchdog (diagnostics; development installs only). Hang 3
-- (2026-11-10): a round's battle began but its enemies never came (their
-- character packs never finished loading). Enemies normally appear 5-6 s
-- after the battle begins; after SPAWN_STALL_SECONDS without one the battle is
-- logged once (spawn_stall, the round it waits for, the seconds) and
-- junon-spawnstall.on asks the native helper to log the spawn and pack-load
-- chain once a second (junon-spawnstall.tsv) and, only with junon-spawnfix.on
-- as well, to try its experimental recovery. The switch goes when an enemy
-- appears, the battle ends or the course ends.
local SPAWN_STALL_SECONDS = 20
local function unstall_spawn()
    if spawn_stalled then spawn_stalled = false; paths.remove('junon-spawnstall.on') end
end
local function in_arena(actor)
    if not valid(actor) then return false end
    local p = actor:K2_GetActorLocation()
    local dx, dy = p.X-ARENA.X, p.Y-ARENA.Y
    return dx*dx+dy*dy < 3000*3000
end
-- A fighter's EPlayerType (PC0000 Cloud = 0 ... PC0006 Cait Sith = 6), or nil.
local function player_type(actor)
    local ok, name = pcall(function() return actor:GetFName():ToString() end)
    return ok and tonumber(name:match('^PC(%d%d%d%d)')) or nil
end
-- Infusions that are not statuses (owner 2026-11-10: accessory-style effects).
-- Special effects come from BattleSpecialStatusChange rows, as Corsair's Compass
-- gives its 3-segment ATB (PCVision is the long version: Refocus).
local function special(api, actor, id)
    return pcall(function() api:AddSpecialStatusChangeID(actor, actor, FName(id)) end)
end
local function action(api, actor, what)
    local kind = player_type(actor)
    if not kind then return false end
    if what == 'atb_full' then
        return pcall(function() api:SetATB(kind, ATB_FULL) end)
    elseif what == 'limit_full' or what == 'limit_level' then
        local bp = StaticFindObject('/Script/EndGame.Default__EndMenuBPAPI')
        if not valid(bp) then return false end
        if what == 'limit_full' then
            return pcall(function() bp:BPSetPlayerLimit(kind, bp:BPGetPlayerLimitMax(kind)) end)
        end
        return pcall(function() bp:BPSetPlayerLimitLevel(kind, bp:BPGetPlayerLimitLevelMax(kind)) end)
    end
    return false -- heal_on_kill works as enemies fall (heal_on_kills below)
end
local function apply(api, actors, buffs, target)
    local n = 0
    for _, actor in ipairs(actors) do
        for _, b in ipairs(buffs) do
            if b.target == target then
                local time = b.time == 'short' and SHORT or INFINITY
                for _, id in ipairs(b.statuses) do
                    if pcall(function() api:AddStatusChangeID(actor, FName(id), time, true, nil, false) end) then n = n + 1 end
                end
                -- Fighters only: these mean nothing on an enemy.
                if b.special and player_type(actor) and special(api, actor, b.special) then n = n + 1 end
                if b.action and action(api, actor, b.action) then n = n + 1 end
            end
        end
    end
    return n
end
local function to_party(api, actors, buffs) return apply(api, actors, buffs, 'party') end
local function to_foes(api, actors, buffs) return apply(api, actors, buffs, 'enemies') end
-- Live: GetPartyMembersIgnoreDead and GetEnemyMembersRef give UE4SS nothing
-- usable, but GetEnemyMemberCount(None) counts the enemies and GetPartyLeader
-- works. So count every second and list the arena's characters (one object
-- scan, ~100 ms) only when needed.
local function characters()
    local party, foes = {}, {}
    for _, actor in ipairs(FindAllOf('EndCharacterBase') or {}) do
        if in_arena(actor) then
            if actor:GetFName():ToString():find('^PC%d') then party[#party+1] = actor else foes[#foes+1] = actor end
        end
    end
    return party, foes
end
-- Accessory infusions (owner 2026-11-10): the skill effects of real accessory
-- rows ("accessory": "E_ACC_xxxx"), given to the party by the native helper
-- (main.cpp InfusionSkills) under its own key beside the equipped accessory;
-- nothing is equipped. The Lua writes junon-infusions.req in the mod's folder
-- whenever the picks or the battle phase change: "run <token>", "phase
-- battle|idle" and one "acc <row>" per accessory picked this run (none: the
-- helper removes everything). The helper answers in junon-infusions.ack; these
-- infusions are offered only while that answer names this run and "status
-- ready" (no helper, another game version or a fault: never offered). Most act
-- at once; materia and ailment immunities from the next round (the helper runs
-- the game's parameter rebuild only between rounds, phase idle).
-- Rank rules with a carrier (Darkside, 2026-11-11: data.courses[c].party_accessories,
-- E_ACC_7106 = the Darkside materia at its highest level, whose effect holds the
-- HP cost and potency the BSC_Dark status lacks) go in the same request, first, for
-- the whole course, so the run's picks are only ever appended after them (the
-- helper adds appended rows in battle; any other change waits for idle).
local INFUSE_REQUEST = paths.shared('junon-infusions.req')
local INFUSE_ACK = paths.shared('junon-infusions.ack')
local infuse = {run = nil, phase = 'idle', sent = nil, serial = 0, answer = nil}
local menu_course  -- the menu's course (defined below, with identify)
-- The carriers the course's rank rules give the party. Until the enemies name the
-- course, the menu's choice decides; outside a course there are none.
local function rule_accessories()
    if not active then return {} end
    local c = course or menu_course()
    local rules = c and data.courses[c]
    return rules and rules.party_accessories or {}
end
local function write_infusions(phase)
    infuse.phase = phase or infuse.phase
    if not infuse.run then return end
    local lines, seen = {'run '..infuse.run, 'phase '..infuse.phase}, {}
    local function add(id) if id and not seen[id] then seen[id] = true; lines[#lines+1] = 'acc '..id end end
    local rule = rule_accessories()
    for _, id in ipairs(rule) do add(id) end
    for _, b in ipairs(picks) do add(b.accessory) end
    local text = table.concat(lines, '\n')..'\n'
    if text == infuse.sent then return end
    local f = io.open(INFUSE_REQUEST..'.tmp', 'wb')
    if not f then return end
    f:write(text); f:close()
    os.remove(INFUSE_REQUEST); os.rename(INFUSE_REQUEST..'.tmp', INFUSE_REQUEST)
    infuse.sent = text
    log('infusions\t'..infuse.run..'\t'..infuse.phase..'\taccessories='..(#lines - 2)
        ..(#rule > 0 and '\trule='..table.concat(rule, ',') or ''))
end
-- A new run (first tick, course start, course end): the helper must answer it anew.
local function new_run(phase)
    infuse.serial = infuse.serial + 1
    infuse.run = tostring(os.time())..'-'..infuse.serial
    write_infusions(phase)
end
-- The helper has answered this run and is ready (read once per offer).
local function native_ready()
    if not infuse.run then return false end
    local f = io.open(INFUSE_ACK, 'rb')
    if not f then return false end
    local text = f:read('a') or ''
    f:close()
    local ready = text:match('^run (%S+)') == infuse.run and text:find('\nstatus ready', 1, true) ~= nil
    local status = text:match('\nstatus ([^\r\n]*)') or 'none'
    if status ~= infuse.answer then infuse.answer = status; log('infusion_helper\t'..status) end
    return ready
end
-- Owner 2026-11-10: an infusion already taken this run is never offered again;
-- ones passed over may come back. Each option draws a tier by weight first
-- (tier_weights, or after_boss in the round after a boss round; only tiers with
-- an infusion left count), then one infusion of that tier; none twice an offer.
local offer_cursor = 0   -- playtests (devtools offer_order): where the next offer starts
local function draw_one(pool, weights)
    local total, tiers = 0, {}
    for _, t in ipairs(data.tiers or {}) do
        local w = weights and weights[t] or 0
        if w > 0 then
            for _, b in ipairs(pool) do
                if b.tier == t then total = total + w; tiers[#tiers+1] = t; break end
            end
        end
    end
    local tier = nil
    if total > 0 then
        local r = math.random(total)
        for _, t in ipairs(tiers) do
            r = r - weights[t]
            if r <= 0 then tier = t; break end
        end
    end
    local choices = {}
    for i, b in ipairs(pool) do if tier == nil or b.tier == tier then choices[#choices+1] = i end end
    return table.remove(pool, choices[math.random(#choices)])
end
local function draw(n, after_boss)
    local taken, pool = {}, {}
    for _, b in ipairs(picks) do taken[b.id] = true end
    local ready = nil   -- accessory infusions only with the helper's answer
    for _, b in ipairs(data.buffs) do
        if not taken[b.id] then
            if b.accessory and ready == nil then ready = native_ready() end
            if not b.accessory or ready then pool[#pool+1] = b end
        end
    end
    local d = package.loaded['devtools']
    local order = d and d.offer_order and d.offer_order()
    if order then
        local by_id, out = {}, {}
        for _, b in ipairs(pool) do by_id[b.id] = b end
        for i = 0, #order - 1 do
            local b = by_id[order[(offer_cursor + i) % #order + 1]]
            if b then out[#out+1] = b; by_id[b.id] = nil end
            if #out == n then break end
        end
        offer_cursor = offer_cursor + 1
        if #out > 0 then return out end
    end
    local weights = after_boss and data.after_boss or data.tier_weights
    local out = {}
    while #out < n and #pool > 0 do out[#out+1] = draw_one(pool, weights) end
    return out
end
local function reset()
    active, in_round, round, buffed, picks, offer_at, window, offered = false, false, 0, {}, {}, nil, nil, nil
    arms = {}
    boons_of, owed = {}, {}
    winded = {}
    swaps, unknown = {}, {}
    candidates, course, pending, from_menu = {}, nil, {}, false
    lean = fresh_lean()
    for i = 1, #data.courses do candidates[i] = true end
end
-- Curated random rounds (owner design 2026-11-09): every slot of every course
-- has a pool of about ten rounds (data.courses[c].slots, harder slot by slot) and
-- each run draws one per slot. The draw for all courses is sent to the native
-- helper (junon-rounds.req), which writes it into the loaded colosseum rows
-- before a course starts; a new draw follows every course. The first rounds of
-- different courses are kept distinct, so the first round names the course.
-- Both files live in the mod's own folder, on any machine.
local REQUEST = paths.shared('junon-rounds.req')
local CURRENT = paths.shared('junon-round.txt')  -- written by the helper
local draws = {}          -- this run's rounds per course
-- Combined rounds (owner 2026-11-11): two existing rounds fought as one, in the
-- pools like any round (data.combined names each one's halves). Development
-- only (devtools, junon-combined.on): course 1's first rounds are forced, the
-- rounds listed in the file or, with an empty file, data.combined_test, so a
-- live test meets known combined rounds. forced_key is the switch's content
-- at the last draw; a change between courses draws again.
local forced_key = ''
local function forced_list()
    local d = package.loaded['devtools']
    local list = d and d.forced_rounds and d.forced_rounds()
    if not list then return nil, '' end
    if list == true or #list == 0 then return data.combined_test or {}, '*' end
    return list, table.concat(list, ' ')
end
local function draw_rounds()
    local first_used = {}
    local forced
    forced, forced_key = forced_list()
    for c, rules in ipairs(data.courses) do
        local rounds = {}
        for s, pool in ipairs(rules.slots) do
            local choices = {}
            for _, r in ipairs(pool) do if s > 1 or not first_used[r] then choices[#choices+1] = r end end
            if #choices == 0 then choices = pool end
            rounds[s] = choices[math.random(1, #choices)]
        end
        if c == 1 and forced then
            local used = {}
            for s, r in ipairs(forced) do
                if s > #rounds then break end
                if data.round_specs[r] and not used[r] then rounds[s], used[r] = r, true
                else log('forced_unknown\t'..s..'\t'..tostring(r)) end
            end
            log('forced\t'..table.concat(rounds, ' ', 1, math.min(#forced, #rounds)))
        end
        first_used[rounds[1]] = true
        draws[c] = rounds
    end
    local f = io.open(REQUEST..'.tmp', 'wb')
    if not f then return end
    for c, rules in ipairs(data.courses) do
        -- "@" line: the rounds the shipped table holds (data: shipped, unique
        -- per course); the helper finds the course's round list by them.
        local defaults, names = {}, {}
        for s, pool in ipairs(rules.slots) do defaults[s] = 'terVR_COL30_'..(rules.shipped and rules.shipped[s] or pool[1]) end
        for s, r in ipairs(draws[c]) do names[s] = 'terVR_COL30_'..r end
        f:write('@'..rules.row..' '..table.concat(defaults, ' ')..'\n')
        f:write(rules.row..' '..table.concat(names, ' ')..'\n')
    end
    f:close(); os.remove(REQUEST); os.rename(REQUEST..'.tmp', REQUEST)
    log('drawn\t'..table.concat(draws[1], ' ')..'\t(course 1; all 14 sent)')
end
local function current_territory()
    local f = io.open(CURRENT, 'rb')
    if not f then return nil end
    local name = (f:read('a') or ''):gsub('%s', '')
    f:close()
    return name:match('^terVR_COL30_(.+)$')
end
-- Which spec an enemy is. Actors are named <model>_C_<n> after their CharaSpec's
-- model, which is usually the spec's own name but not always: live 2026-11-11
-- the Cactuars (SU0008_*) and the Colosseum Tonberry (EN2017_00_Tonberry_Standard,
-- spec ..._VR) were never hardened, nor the Bandits with a weapon in their spec
-- name, the Griffins, the Junon Sweeper or the Gi. So the game's own CharaSpec
-- name ("CharaSpec_<id>", one per course spec; data.spec_charas where the id is
-- not the spec) decides; the model (data.spec_models) is the fallback.
local function spec_of(actor)
    return actor:GetFName():ToString():match('^(.-)_C_%d+$')
end
local function chara_of(api, actor)
    local ok, name = pcall(function() return api:GetCharaSpecName(actor) end)
    if not ok or name == nil then return nil end
    if type(name) ~= 'string' then
        ok, name = pcall(function() return name:ToString() end)
        if not ok or type(name) ~= 'string' then return nil end
    end
    name = name:gsub('^CharaSpec_', '')
    if name == '' or name == 'None' then return nil end
    return name
end
-- The spec in `specs` (a set) an enemy is, or nil and the name it showed. A model
-- several specs share is narrowed to the round's own specs (`here`, a set or nil).
local function course_spec(api, e, specs, here)
    local chara = api and chara_of(api, e)
    local s = chara and ((data.spec_charas or {})[chara] or chara)
    if s and specs[s] then return s end
    local model = spec_of(e)
    if not model then return nil, chara end
    local options = {}
    if specs[model] then options[1] = model end
    for _, x in ipairs((data.spec_models or {})[model] or {}) do
        if specs[x] then options[#options+1] = x end
    end
    if #options > 1 and here then
        local narrowed = {}
        for _, x in ipairs(options) do if here[x] then narrowed[#narrowed+1] = x end end
        if #narrowed > 0 then options = narrowed end
    end
    if #options == 1 then return options[1] end
    if specs[model] then return model end  -- still several: its own name, as before
    return nil, chara or model
end
-- Whether an enemy showing these names may be one of the specs in `set`.
local function could_be(chara, model, set)
    local s = chara and ((data.spec_charas or {})[chara] or chara)
    if (s and set[s]) or (model and set[model]) then return true end
    for _, x in ipairs(model and (data.spec_models or {})[model] or {}) do
        if set[x] then return true end
    end
    return false
end
local function set_of(list)
    if not list then return nil end
    local set = {}
    for _, s in ipairs(list) do set[s] = true end
    return set
end
-- The current round's specs: the territory the helper names, else this run's draw.
local function round_set()
    local r = current_territory() or (course and draws[course] and draws[course][round])
    return set_of(r and data.round_specs[r])
end
-- The course chosen in the menu (branding.lua), when it names one of ours.
function menu_course()  -- the local declared above write_infusions
    local ok, branding = pcall(require, 'branding')
    local pick = ok and branding.selected_course and branding.selected_course()
    if not pick or os.time() - pick.at > 1800 then return nil end
    for c, info in ipairs(data.courses) do if info.title == pick.title then return c end end
    return nil
end
-- Which course is running. The helper names the current round's territory; the
-- run's draw maps it to a course. Without the helper the enemies decide: a course
-- stays a candidate while each round's enemies fit its drawn round (the lowest
-- candidate rules meanwhile).
local function identify(foes, api)
    local best = nil
    local territory = current_territory()
    if round == 1 and not from_menu then
        local c = menu_course()
        if c then
            from_menu, course = true, c
            for i = 1, #data.courses do candidates[i] = (i == c) or nil end
            log('course	'..c..'	'..data.courses[c].title..'	menu	'..tostring(territory))
        end
    end
    if from_menu then
        -- Known for certain; only note a draw the game has not caught up with.
        if territory and draws[course] and draws[course][round] ~= territory then
            log('draw_mismatch	'..round..'	'..tostring(draws[course][round])..'	'..territory)
        end
        return
    end
    if territory then
        for c, rounds in ipairs(draws) do
            if candidates[c] and rounds[round] == territory then best = best or c else candidates[c] = nil end
        end
    end
    if not territory or not best then
        local seen = {}
        for _, e in ipairs(foes) do
            local chara, model = api and chara_of(api, e), spec_of(e)
            if chara or model then seen[#seen+1] = {chara = chara, model = model} end
        end
        best = nil
        for c = 1, #data.courses do
            if candidates[c] then
                local drawn = draws[c] and draws[c][round]
                local set = set_of(drawn and data.round_specs[drawn])
                local fits = set ~= nil
                if fits then
                    for _, n in ipairs(seen) do
                        if not could_be(n.chara, n.model, set) then fits = false end
                    end
                end
                candidates[c] = fits or nil
                if fits and not best then best = c end
            end
        end
    end
    if best ~= course then
        course = best
        log('course\t'..tostring(course)..'\t'..(course and data.courses[course].title or 'unknown')..'\t'..tostring(territory))
    end
end
-- Every enemy spec a course can meet (its clones exist for these).
local course_specs = {}
local function specs_of(c)
    if not course_specs[c] then
        local set = {}
        for _, pool in ipairs(data.courses[c].slots) do
            for _, r in ipairs(pool) do for _, s in ipairs(data.round_specs[r] or {}) do set[s] = true end end
        end
        course_specs[c] = set
    end
    return course_specs[c]
end
local function draw_from(list, n)
    local pool = {}
    for i = 1, #list do pool[i] = list[i] end
    local out = {}
    for i = 1, math.min(n, #pool) do
        local j = math.random(i, #pool)
        pool[i], pool[j] = pool[j], pool[i]
        out[i] = pool[i]
    end
    return out
end
-- Notes a status the mod gave an enemy this round (Rally's draw prefers ones it lacks).
local function mark(key, id)
    boons_of[key] = boons_of[key] or {}
    boons_of[key][id] = true
end
-- Rally's draw for one enemy: a boon from data.enemy_boons it was not given yet,
-- else any (see rally below).
local function rally_draw(key)
    local had, fresh = boons_of[key] or {}, {}
    for _, id in ipairs(data.enemy_boons or {}) do if not had[id] then fresh[#fresh+1] = id end end
    local from = #fresh > 0 and fresh or data.enemy_boons or {}
    return #from > 0 and from[math.random(#from)] or nil
end
-- Arms race (a rank rule, owner 2026-11-11; it replaced Mirror match, whose
-- materia, accessory, ability and action infusions meant nothing on an enemy):
-- for every infusion taken (a refusal is no pick), the enemies gain one random
-- boon from data.enemy_boons (the Rivals pool) for the rest of the course. A new
-- one avoids the boons this rule already drew and the course's fixed enemy
-- statuses (Riot rush's Haste); then any not yet drawn; once the pool is used
-- up, any. The list is kept for the course (reset with the picks), every enemy
-- gets all of it when hardened, and a pick mid-round gives the new boon to the
-- enemies already standing. Each draw is logged (arms_race).
local function arms_racing()
    local rules = course and data.courses[course]
    return rules and rules.arms_race and rules or nil
end
local function arms_draw(rules)
    local drawn, fixed = {}, {}
    for _, id in ipairs(arms) do drawn[id] = true end
    for _, id in ipairs(rules.enemy_status or {}) do fixed[id] = true end
    local fresh, unused = {}, {}
    for _, id in ipairs(data.enemy_boons or {}) do
        if not drawn[id] then
            unused[#unused+1] = id
            if not fixed[id] then fresh[#fresh+1] = id end
        end
    end
    local from = #fresh > 0 and fresh or #unused > 0 and unused or data.enemy_boons or {}
    return #from > 0 and from[math.random(#from)] or nil
end
-- Draws until there is one boon per pick (the course may be recognised only
-- after a pick); each new one goes on the standing enemies given. Returns the
-- statuses given.
local function arms_fill(api, standing)
    local rules = arms_racing()
    if not rules then return 0 end
    local n = 0
    while #arms < #picks do
        local id = arms_draw(rules)
        if not id then break end
        arms[#arms+1] = id
        local given = 0
        for _, e in ipairs(standing or {}) do
            if valid(e) and pcall(function() api:AddStatusChangeID(e, FName(id), INFINITY, true, nil, false) end) then
                given = given + 1
                mark(e:GetFullName(), id)
            end
        end
        n = n + given
        log('arms_race\t'..round..'\t'..id..'\ttotal='..#arms..'\tstanding='..given)
    end
    return n
end
-- Each new enemy once: the course's stronger spec, random enemy boons and
-- statuses (bypassing resistance, like the player's boons; owner: riotous fun).
-- This round's timed rank rules (hazards_start/hazards_tick below).
local hazard = nil
-- Spec swaps are checked SWAP_CHECK seconds later: the swap rebuilds the enemy's
-- HP, so a max HP short of the course's factor means it did not take (live
-- 2026-11-11 a few enemies kept their HP although the swap was accepted). Such a
-- swap is tried once more, and logged either way (spec_retry, spec_missed).
-- Enemies of no course spec (bosses' summons and spawned young) are logged once
-- a course by the name they showed (spec_unknown).
local function hp_max(api, e)
    local ok, v = pcall(function() return api:GetHPMax(e) end)
    return ok and type(v) == 'number' and v > 0 and v or nil
end
local function check_swaps(api)
    if #swaps == 0 then return end
    local keep = {}
    for _, w in ipairs(swaps) do
        if not valid(w.actor) then -- gone: nothing to check
        elseif os.time() - w.at < SWAP_CHECK then keep[#keep+1] = w
        else
            local now = hp_max(api, w.actor)
            if now and now < w.before * (1 + (w.hp - 1) / 2) then
                local what = round..'\t'..w.actor:GetFName():ToString()..'\t'..w.clone..'\t'..w.before..'>'..now
                if w.tries < 2 and pcall(function() api:SetOverrideBattleCharaSpec(w.actor, FName(w.clone)) end) then
                    w.tries, w.at = w.tries + 1, os.time()
                    keep[#keep+1] = w
                    log('spec_retry\t'..what)
                else
                    log('spec_missed\t'..what)
                end
            end
        end
    end
    swaps = keep
end
-- Returns the changes made and how many Arms race boons each enemy was given.
local function harden(api, foes)
    local rules = course and data.courses[course]
    if not rules then return 0, 0 end
    arms_fill(api, nil)
    local raced = rules.arms_race and #arms or 0
    local n = 0
    local specs = specs_of(course)
    local here = rules.spec and rules.clone and round_set()
    for _, e in ipairs(foes) do
        if rules.spec and rules.clone then
            local s, shown = course_spec(api, e, specs, here)
            if s then
                local clone = s..'_'..rules.clone  -- courses with equal stat rules share clones
                local before = (rules.hp or 1) > 1 and hp_max(api, e)
                if pcall(function() api:SetOverrideBattleCharaSpec(e, FName(clone)) end) then
                    n = n + 1
                    if before then
                        swaps[#swaps+1] = {actor = e, clone = clone, before = before, hp = rules.hp, at = os.time(), tries = 1}
                    end
                end
            else
                local name = shown or e:GetFName():ToString()
                if not unknown[name] then
                    unknown[name] = true
                    log('spec_unknown\t'..round..'\t'..name)
                end
            end
        end
        local statuses = draw_from(data.enemy_boons, rules.enemy_boons)
        for _, st in ipairs(rules.enemy_status) do statuses[#statuses+1] = st end
        for i = 1, raced do statuses[#statuses+1] = arms[i] end
        if rules.enemy_start and hazard and not hazard.foes_done and hazard.clock < rules.enemy_start.seconds then
            statuses[#statuses+1] = rules.enemy_start.status
            hazard.foes[#hazard.foes+1] = e
        end
        local key = e:GetFullName()
        for _, id in ipairs(statuses) do
            if pcall(function() api:AddStatusChangeID(e, FName(id), INFINITY, true, nil, false) end) then n = n + 1 end
            mark(key, id)
        end
        -- Rally boons owed while it waited to be hardened, drawn now so they
        -- prefer what this enemy was not just given.
        if owed[key] then
            local late = {}
            for _ = 1, owed[key] do
                local id = rally_draw(key)
                if id then
                    mark(key, id)
                    if pcall(function() api:AddStatusChangeID(e, FName(id), INFINITY, true, nil, false) end) then
                        n = n + 1
                        late[#late+1] = id
                    end
                end
            end
            owed[key] = nil
            log('rally_owed\t'..round..'\t'..e:GetFName():ToString()..'\t'..(#late > 0 and table.concat(late, ',') or 'none'))
        end
        if rules.second_wind then
            winded[key] = winded[key] or 'watch'
        end
    end
    return n, raced
end
-- Live: the window's PauseMenu flag does not stop the battle (HP kept falling
-- behind it), so pause the game while it is open, as the tutorial tips do.
local paused = false
local function pause(on, context)
    local statics = StaticFindObject('/Script/Engine.Default__GameplayStatics')
    if not valid(statics) then return end
    local ok, err = pcall(function() statics:SetGamePaused(context, on) end)
    paused = on and ok
    log((on and 'pause' or 'unpause')..'\t'..tostring(ok)..'\t'..tostring(err))
end
-- Owner 2026-11-10: like other roguelites, a boon can be refused (useful under
-- Arms race, where every pick also arms the enemy). Always the last option.
local SKIP = 'Refuse the infusion'
-- A boss round of the course in play (course-design.json 'bosses'); before the
-- course is known, a round every course has as a boss round.
local function boss_round(r)
    local lists = data.boss_rounds or {}
    local function listed(list)
        for _, x in ipairs(list or {}) do if x == r then return true end end
        return false
    end
    if course then return listed(lists[course]) end
    for c = 1, #lists do if not listed(lists[c]) then return false end end
    return #lists > 0
end
-- The option text: the tier's label ("[Rare] ", "[Epic] ") and the infusion's.
local function label(b) return ((data.tier_labels or {})[b.tier] or '')..b.label end
local function open_window(menu, api)
    local after_boss = round > 1 and boss_round(round - 1)
    offered = draw((course and data.courses[course].offer_size) or data.per_offer, after_boss)
    local labels = {}
    for i, b in ipairs(offered) do labels[i] = label(b) end
    labels[#labels+1] = SKIP
    local context = api:GetPartyLeader()
    local ok, w = pcall(function() return menu:ShowMessageWindow(context, data.prompt, labels, PAUSE_MENU) end)
    window = ok and valid(w) and w or nil
    log('offer\t'..round..'\t'..table.concat(labels, ' | ')..'\t'..tostring(window ~= nil)..(after_boss and '\tafter_boss' or ''))
    if window then pause(true, context); window_at = os.time() end
end
-- Development builds only: devtools.lua can pick for an unattended test run.
local function dev() return package.loaded['devtools'] end
local function read_window(menu, api)
    local index = nil
    local d = dev()
    local auto = d and d.autoboon and os.time() - (window_at or 0) >= 1 and d.autoboon(#offered + 1)
    if auto then
        pcall(function() menu:HideMessageWindow(window) end)
        index = auto - 1
        log('autoboon\t'..round..'\t'..auto)
    else
        local okc, closed = pcall(function() return menu:IsMessageWindowClosed(window) end)
        if not okc then window = nil; if paused then pause(false, api:GetPartyLeader()) end; return end
        if closed ~= true then
            if os.time() % 10 == 0 then log('waiting\t'..round) end -- shows the tick runs while paused
            return
        end
        local oks, chosen = pcall(function() return menu:GetMessageWindowSelectedIndex(window) end)
        index = oks and type(chosen) == 'number' and chosen or nil
    end
    window = nil
    if paused then pause(false, api:GetPartyLeader()) end
    if index == #offered then log('skip\t'..round); return end
    local pick = index and offered[index + 1] or nil
    if not pick then log('pick_unknown\t'..round..'\t'..tostring(index)); return end
    picks[#picks+1] = pick
    if pick.accessory then write_infusions('battle') end  -- the helper adds it at once
    -- On everyone now; enemies still being set up get all picks when hardened.
    local party, foes = characters()
    local n = to_party(api, party, {pick}) + to_foes(api, foes, {pick})
    log('pick\t'..round..'\t'..pick.id..'\tstatuses='..n..'\tpicks='..#picks)
    if arms_racing() then
        -- Arms race: the new enemy boon on the enemies already hardened; those
        -- still waiting get the whole list when hardened.
        local waiting, standing = {}, {}
        for _, p in ipairs(pending) do if valid(p.actor) then waiting[p.actor:GetFullName()] = true end end
        for _, e in ipairs(foes) do if not waiting[e:GetFullName()] then standing[#standing+1] = e end end
        arms_fill(api, standing)
    end
end
-- Timed rank rules (party_start, enemy_start, Time trap). Their clock counts
-- fight seconds only: the infusion window pauses the game, so its seconds are skipped.
local function hazards_start(api, party)
    local rules = course and data.courses[course]
    hazard = {clock = 0, party = party, foes = {}}
    -- Bloodlust and Darkside: given at every round's start. Darkside's HP cost and
    -- potency come from the Darkside materia (the rule's carrier, write_infusions);
    -- BSC_Dark turns it on. The materia also gives the Darkside command, and owner
    -- 2026-11-11: a fighter may use it to switch Darkside off; it comes back here at
    -- the next round's start (no mid-round re-apply).
    for _, id in ipairs(rules and rules.party_status or {}) do
        for _, c in ipairs(party) do
            pcall(function() api:AddStatusChangeID(c, FName(id), INFINITY, true, nil, false) end)
        end
    end
    local start = rules and rules.party_start
    if start then
        local n = 0
        for _, c in ipairs(party) do
            if pcall(function() api:AddStatusChangeID(c, FName(start.status), INFINITY, true, nil, false) end) then n = n + 1 end
        end
        hazard.until_clock, hazard.status = start.seconds, start.status
        log('hazard_start\t'..round..'\t'..start.status..'\t'..n)
    end
end
local function hazards_tick(api)
    if not hazard or paused or not started then return end
    hazard.clock = hazard.clock + 1
    if hazard.until_clock and hazard.clock >= hazard.until_clock then
        for _, c in ipairs(hazard.party) do
            if valid(c) then pcall(function() api:RemoveStatusChangeID(c, FName(hazard.status), false) end) end
        end
        log('hazard_end\t'..round..'\t'..hazard.status..'\t'..hazard.clock)
        hazard.until_clock = nil
    end
    local foes_start = course and data.courses[course] and data.courses[course].enemy_start
    if foes_start and not hazard.foes_done and hazard.clock >= foes_start.seconds then
        for _, e in ipairs(hazard.foes) do
            if valid(e) then
                pcall(function() api:RemoveStatusChangeID(e, FName(foes_start.status), false) end)
                local had = boons_of[e:GetFullName()]
                if had then had[foes_start.status] = nil end  -- Rally may give it again
            end
        end
        log('hazard_end\t'..round..'\t'..foes_start.status..'\t'..#hazard.foes)
        hazard.foes_done = true
    end
    local every = course and data.courses[course] and data.courses[course].party_every
    if every and hazard.clock % every.seconds == 0 then
        local alive = {}
        for _, c in ipairs(hazard.party) do if valid(c) then alive[#alive+1] = c end end
        if #alive > 0 then
            local c = alive[math.random(#alive)]
            local ok = pcall(function() api:AddStatusChangeID(c, FName(every.status), SHORT, true, nil, false) end)
            log('hazard_every\t'..round..'\t'..every.status..'\t'..c:GetFName():ToString()..'\t'..tostring(ok))
        end
    end
end
-- One tick per second, from the gate's loop. A battle ending is a round ending;
-- the course is over once the leader is seen outside the arena, or no round
-- starts for two minutes.
-- A lapsed special effect is given again, so the infusion lasts the run
-- (unless it is a once-a-round one, like the 40 seconds of free spells). A
-- once-a-round one with 'seconds' is given again until that many fight seconds
-- into the round (the hazard clock), then left to lapse (owner 2026-11-11:
-- Turbulent Spirit for 60 s, three of its natural 20 s).
local function refresh(api)
    if paused or not started or os.time() < refresh_at then return end
    refresh_at = os.time() + REFRESH
    local clock = hazard and hazard.clock or 0
    for _, b in ipairs(picks) do
        if b.special and (not b.each_round or (b.seconds and clock < b.seconds)) then
            for _, c in ipairs(party_now) do
                if valid(c) then
                    local ok, has = pcall(function() return api:HasSpecialStatusChangeID(c, FName(b.special)) end)
                    if ok and has == false and special(api, c, b.special) then
                        log('refresh	'..round..'	'..b.special..'	'..c:GetFName():ToString())
                    end
                end
            end
        end
    end
end
-- Reclaimant Choker as an infusion: each fallen enemy gives every standing
-- fighter 10% of their HP back. The game gives Lua no HP reading, only "above
-- N%" tests, so the current percentage is found by halving (7 tests).
local function hp_percent(api, c)
    local lo, hi = 0, 100
    while lo < hi do
        local mid = (lo + hi) // 2
        local ok, above = pcall(function() return api:IsHPPercent(c, mid, GREATER) end)
        if not ok then return nil end
        if above == true then lo = mid + 1 else hi = mid end
    end
    return lo
end
-- Short rest (a rank rule, owner 2026-11-11; it replaced Wounded's 75% HP cap).
-- Vanilla colosseum rounds restore 50% HP and 30% MP between rounds; under this
-- rule a fighter starts a round with at most what it ended its last round with
-- plus rules.hp % of its max HP and rules.mp % of its max MP. Records are per
-- fighter (EPlayerType), so a team sitting a round out keeps its own record; a
-- fighter's first round of the course (round 1, or the second team's first) is
-- untouched. A fallen fighter's record is 0: if the game brings it back, it
-- starts on at most rules.hp %; one still down is left alone.
-- HP: the battle API on the actor (hp_percent's halving over IsHPPercent, then
--   SetHPPercent), sampled every LEAN_SAMPLE fight seconds and once more when
--   the last enemy falls, so the record is the HP the round ended with.
-- MP: UEndBattleAPI has no MP call at all (CXX header dump: no MP getter or
--   setter, no IsMPPercent). The menu's player API (UEndMenuBPAPI BPGetPlayerMP
--   / BPGetPlayerMaxMP / BPSetPlayerMP, by EPlayerType) is the fighter's live
--   battle MP, not a copy: BPGetPlayerMP returns the party data block's +0x3ac,
--   beside the live HP at +0x3a8, and both matched the harness's last combat
--   tick in the 2026-11-11 dump (Tifa 5745 HP / 85 MP...); the harness and the
--   live course-10 log (2026-11-11) show it falling as spells are cast.
--   BPSetPlayerMP writes that field and the second per-character MP record,
--   then notifies (disassembly, 0x14187cd50). So MP is sampled with HP while
--   enemies stand and at the last blow (the record starts from the round's last
--   reading) and read each second between rounds (the lowest reading wins); at
--   round start, and again ACTION_DELAY seconds in, it is cut to the cap. Every
--   reading that changes between rounds (lean_mp_seen) and every cut (lean,
--   before > after, and the reading after the set) is logged.
local LEAN_SAMPLE = 2
local function recovery() return course and data.courses[course] and data.courses[course].party_recovery end
local function lean_wanted() return course == nil or recovery() ~= nil end
-- The stored MP and max MP of a fighter (EPlayerType), or nil.
local function stored_mp(kind)
    local bp = StaticFindObject('/Script/EndGame.Default__EndMenuBPAPI')
    if not valid(bp) then return nil end
    local ok, mp, max = pcall(function() return bp:BPGetPlayerMP(kind), bp:BPGetPlayerMaxMP(kind) end)
    if ok and type(mp) == 'number' and type(max) == 'number' and max > 0 then return mp, max, bp end
    return nil
end
local function lean_sample(api)
    for _, c in ipairs(party_now) do
        local kind = valid(c) and player_type(c)
        local p = kind and hp_percent(api, c)
        if p then lean.hp[kind] = p end
        local mp, max = nil, nil
        if kind then mp, max = stored_mp(kind) end
        if mp then lean.live[kind] = {mp = mp, max = max} end
    end
end
-- Each second between rounds: the last round's fighters' stored MP; the lowest is the record.
local function lean_gap()
    for kind, last in pairs(lean.gap) do
        local mp, max = stored_mp(kind)
        if mp then
            if last ~= mp then
                lean.gap[kind] = mp
                log('lean_mp_seen\t'..round..'\t'..kind..'\t'..mp..'/'..max)
            end
            local rec = lean.mp[kind]
            if not rec or mp < rec.mp then lean.mp[kind] = {mp = mp, max = max} end
        end
    end
end
local function lean_round_end()
    lean.gap = {}
    if not recovery() then return end
    for _, kind in ipairs(lean.kinds) do
        lean.gap[kind] = false
        lean.mp[kind] = lean.live[kind]  -- a fresh record: the round's last reading, then this gap's
    end
    lean_gap()
end
-- Cuts this round's fighters to their caps; returns how many it cut (HP or MP).
-- The start pass keeps the records it used (lean.caps): from then on this
-- round's own HP samples replace lean.hp, for the next round.
local function lean_apply(api, party, pass)
    local rules = recovery()
    if not rules then return 0 end
    local n = 0
    for _, c in ipairs(party) do
        local kind = valid(c) and player_type(c)
        local rec = {}
        if kind and pass == 'start' then
            rec = {hp = lean.hp[kind], mp = lean.mp[kind]}
            lean.caps[kind] = rec
        elseif kind then
            rec = lean.caps[kind] or {}
        end
        local hp_rec, mp_rec = rec.hp, rec.mp
        local parts, cut = {}, false
        if hp_rec then
            local to = math.min(100, hp_rec + rules.hp)
            local ok, above = pcall(function() return api:IsHPPercent(c, to, GREATER) end)
            if ok and above == true then
                local from = hp_percent(api, c)
                if pcall(function() api:SetHPPercent(c, to) end) then
                    cut = true
                    parts[#parts+1] = 'hp='..hp_rec..'+'..rules.hp..':'..tostring(from)..'>'..to
                end
            end
        end
        if mp_rec then
            local mp, max, bp = stored_mp(kind)
            if not mp then
                parts[#parts+1] = 'mp=unread'
            else
                -- The record scaled to today's max MP (an MP Up pick changes it), plus the allowance.
                local base = math.floor(mp_rec.mp * max / mp_rec.max + 0.5)
                local to = math.min(max, base + math.floor(max * rules.mp / 100 + 0.5))
                if mp > to then
                    local ok = pcall(function() bp:BPSetPlayerMP(kind, to) end)
                    local after = stored_mp(kind)
                    cut = cut or ok
                    parts[#parts+1] = 'mp='..mp_rec.mp..'/'..mp_rec.max..'+'..rules.mp..'%:'..mp..'>'..to..
                        (ok and '' or ':set_failed')..':read='..tostring(after)
                elseif pass == 'start' then
                    parts[#parts+1] = 'mp='..mp_rec.mp..'/'..mp_rec.max..'+'..rules.mp..'%:'..mp..'<='..to
                end
            end
        end
        if cut then n = n + 1 end
        if #parts > 0 then log('lean\t'..round..'\t'..pass..'\t'..c:GetFName():ToString()..'\t'..table.concat(parts, '\t')) end
    end
    return n
end
local function heal_on_kills(api, fallen)
    local wanted = false
    for _, b in ipairs(picks) do if b.action == 'heal_on_kill' then wanted = true end end
    if not wanted or fallen < 1 then return end
    for _, c in ipairs(party_now) do
        local p = valid(c) and hp_percent(api, c)
        if p and p > 0 and p < 100 then  -- standing and hurt (never revives anyone)
            local to = math.min(100, p + 10 * fallen)
            if pcall(function() api:SetHPPercent(c, to) end) then
                log('reclaim\t'..round..'\t'..c:GetFName():ToString()..'\t'..p..'\t'..to)
            end
        end
    end
end
-- Accessory infusions that feed the limit gauge (owner 2026-11-10), through the
-- menu's player API (UEndMenuBPAPI; EPlayerType from the actor name):
--   limit_over_time (Gotterdammerung): a slice every few fight seconds;
--     (UEndBattleAPI.GetSpendATBBarTotal counts the battle's spent bars);
--     (BPGetPlayerMP falling; a rise, as from Ether, only moves the baseline).
-- Speed Demon Keychain (ATB back for abilities) has no Lua version (the API sets
-- ATB but has no getter); the native helper gives the real accessory row instead.
-- These three stay in Lua: they work without the helper.
-- Fight seconds only, as for the hazards; baselines start afresh each round.
local accessory = {clock = 0, atb = {}, mp = {}, logged = {}}
local function wants(what)
    for _, b in ipairs(picks) do if b.action == what then return true end end
    return false
end
local function note(what, kind, line)
    local key = what..kind
    if (accessory.logged[key] or 0) > os.time() then return end
    accessory.logged[key] = os.time() + EFFECT_LOG_GAP
    log(what..'\t'..round..'\t'..kind..'\t'..line)
end
-- Adds this fraction of the gauge (at least 1) up to the maximum; returns the
-- old and new values, or nil when nothing changed.
local function add_limit(bp, kind, fraction)
    local ok, now, max = pcall(function() return bp:BPGetPlayerLimit(kind), bp:BPGetPlayerLimitMax(kind) end)
    if not ok or type(now) ~= 'number' or type(max) ~= 'number' or max <= 0 or now >= max then return nil end
    local to = math.min(max, now + math.max(1, math.floor(max * fraction + 0.5)))
    if not pcall(function() bp:BPSetPlayerLimit(kind, to) end) then return nil end
    return now, to
end
local function standing(api, c)
    local ok, above = pcall(function() return api:IsHPPercent(c, 0, GREATER) end)
    return ok and above == true
end
-- Second wind (a rank rule, owner design 2026-11-10: every enemy rises again
-- once). Live 2026-11-11 (build 0.9.19, course 12): giving enemies BSC_Reraise
-- left them dead on the floor, never risen, and the battle never ended (no
-- victory, no round end), so courses 12-14 could not be cleared. The rule now
-- gives enemies no status at all: this watcher, once a second in fight time,
-- restores each enemy of the round once to rule.to % HP the first time the tick
-- sees it standing below rule.below % (IsHPPercent Less, then above 0%). Only
-- hardened enemies are watched (the course's spec swap rebuilds HP, so a rise
-- before it would be lost). The tick samples once a second, so the threshold
-- is wide (20%, not 5%): an enemy taken from above it to 0 between two ticks,
-- in one big hit or a fast combo, simply dies (never seen low and alive); that
-- is accepted. A rise is logged: second_wind <round> <enemy> <pct before>><to>.
-- Playtest boost: the drain takes the enemy under the threshold, it rises once,
-- and the drain carries on from rule.to % down to 1% and its finisher as before.
local function second_wind(api)
    local rule = course and data.courses[course] and data.courses[course].second_wind
    if not rule or paused or not started then return end
    for _, e in ipairs(foes_now) do
        local key = valid(e) and e:GetFullName()
        if key and winded[key] == 'watch' then
            local ok, low = pcall(function() return api:IsHPPercent(e, rule.below, LESS) end)
            if ok and low == true and standing(api, e) then
                local before = hp_percent(api, e)
                if pcall(function() api:SetHPPercent(e, rule.to) end) then
                    winded[key] = 'done'
                    at_floor[key] = nil  -- playtest drain: its finisher clock starts over
                    log('second_wind\t'..round..'\t'..e:GetFName():ToString()..'\t'..tostring(before)..'>'..rule.to)
                end
            end
        end
    end
end
-- Rally (a rank rule, owner 2026-11-11; it replaced Tough hides on course 3,
-- whose 25% more HP the hidden per-course HP factor now carries): whenever an
-- enemy falls during a round, every enemy still standing gains one random boon
-- from data.enemy_boons (the Rivals and Arms race pool) for the rest of the
-- round, one per fall. A survivor's boon is one the mod has not given it yet
-- where possible (Rivals, Riot rush, Arms race, Hall of mirrors while it lasts,
-- earlier rallies); opposite statuses may cancel (Haste and Slow; owner: fine).
-- Falls come from the tick's enemy count (as heal_on_kills): a drop of n is n
-- falls. So Second wind is no fall (the enemy never leaves the count), and a
-- wave, a split or a summon arriving raises the count and is none. The last
-- enemy's fall (count 0) rallies nobody. Survivors are this round's enemies
-- still above 0% HP; one seen but not yet hardened (HARDEN_DELAY) is owed its
-- boon, drawn and given with the hardening (after its Rivals boon, so the draw
-- can avoid it; the game's own set-up cannot wipe it then). A fall in the same
-- tick as an arrival can hide in the count; that is accepted.
-- Each fall is logged: rally <round> <fallen> <boons given> standing=<n>, with
-- "owed" for each boon an unhardened survivor gets later (rally_owed <round>
-- <enemy> <boons>).
local function rally(api, fallen, count)
    local rules = course and data.courses[course]
    if not (rules and rules.rally) or fallen < 1 or count < 1 then return end
    local survivors = {}
    for _, e in ipairs(foes_now) do
        if valid(e) and standing(api, e) then survivors[#survivors+1] = e end
    end
    if #survivors == 0 then return end
    local waiting = {}
    for _, p in ipairs(pending) do if valid(p.actor) then waiting[p.actor:GetFullName()] = true end end
    local given = {}
    for _ = 1, fallen do
        for _, e in ipairs(survivors) do
            local key = e:GetFullName()
            if waiting[key] then
                owed[key] = (owed[key] or 0) + 1
                given[#given+1] = 'owed'
            else
                local id = rally_draw(key)
                if id then
                    mark(key, id)
                    if pcall(function() api:AddStatusChangeID(e, FName(id), INFINITY, true, nil, false) end) then
                        given[#given+1] = id
                    end
                end
            end
        end
    end
    log('rally\t'..round..'\t'..fallen..'\t'..(#given > 0 and table.concat(given, ',') or 'none')..
        '\tstanding='..#survivors)
end
local function accessories(api)
    if paused or not started then return end
    -- (Transference Module is the real accessory row now: UEndBattleAPI's
    -- GetSpendATBBarTotal stayed 0 in battle, live 2026-11-10.)
    -- (Spectral Cogwheel too: the menu's MP reading never fell in battle.)
    local timed = wants('limit_over_time')
    if not timed then return end
    local bp = StaticFindObject('/Script/EndGame.Default__EndMenuBPAPI')
    if not valid(bp) then return end
    accessory.clock = accessory.clock + 1
    local pulse = timed and accessory.clock % LIMIT_TICK_SECONDS == 0
    for _, c in ipairs(party_now) do
        local kind = valid(c) and player_type(c)
        if kind then
            if pulse and standing(api, c) then
                local from, to = add_limit(bp, kind, LIMIT_TICK_SLICE)
                if from then note('limit_over_time', kind, from..'>'..to) end
            end
        end
    end
end
function M.tick(db, battle)
    if #draws == 0 then
        math.randomseed(os.time()); draw_rounds()
        new_run('idle')  -- no accessory infusions left from an earlier session
        paths.remove('junon-stall.on')  -- nor a stall switch from an earlier session
        paths.remove('junon-spawnstall.on')
    end
    local api = StaticFindObject('/Script/EndGame.Default__EndBattleAPI')
    local menu = StaticFindObject('/Script/EndGame.Default__EndMenuAPI')
    if not valid(api) or not valid(menu) then return end
    if not battle then
        if paused then pause(false, api:GetPartyLeader()) end -- never leave the game paused
        if in_round then
            in_round, idle_since, offer_at, window = false, os.time(), nil, nil
            hazard = nil
            unstall_spawn()
            log('round_end\t'..round)
            -- The most enemies at once against the round's own count (a combined
            -- round's both groups; wave enemies can add more).
            local combo = round_territory and data.combined and data.combined[round_territory]
            log('round_enemies\t'..round..'\tmax='..round_max..'\t'..tostring(round_territory)..
                (combo and '\texpected='..combo.enemies or ''))
            write_infusions('idle')  -- between rounds: the helper may rebuild now
            lean_round_end()         -- Short rest: the round's MP record
        elseif active then
            -- Live 2026-11-09: in two-team courses the next team's leader waits
            -- outside the arena between rounds, and the field has a player pawn
            -- during that gap too, so neither marks the end. The colosseum's
            -- result screen does (branding.lua keeps that widget); two idle
            -- minutes are the fallback.
            if next(lean.gap) then lean_gap() end
            local ok, branding = pcall(require, 'branding')
            local result = ok and branding.result_visible and branding.result_visible()
            local idle = os.time() - idle_since
            if not stalled and not result and idle > STALL_SECONDS then
                stalled = true
                log('stall\t'..round..'\t'..idle)
                local f = paths.open('junon-stall.on', 'wb')
                if f then f:write(os.date('!%H:%M:%S')..'\t'..round..'\n'); f:close() end
            end
            if result or idle > 120 then
                log('course_end\trounds='..round..'\tpicks='..#picks); reset(); unstall(); unstall_spawn()
                new_run('idle')  -- no accessories: the helper removes them all
                draw_rounds() -- a fresh draw for the next run
            end
        else
            -- Between courses: a test switch set or changed since the draw.
            local _, key = forced_list()
            if key ~= forced_key then draw_rounds() end
        end
        return
    end
    if not in_round then
        if not in_arena(api:GetPartyLeader()) then return end
        if not active then
            reset(); active = true
            log('course_start')
            new_run('battle')
        end
        in_round, started, enemies_seen = true, false, 0
        round_max, round_territory = 0, nil
        battle_since = os.time()
        lean.gap = {}
        unstall()
        write_infusions('battle')
    end
    if window then read_window(menu, api) end
    hazards_tick(api)
    refresh(api)
    if actions_at and not paused and os.time() >= actions_at then
        actions_at = nil
        local n = 0
        for _, b in ipairs(picks) do
            if b.action == 'atb_full' or b.action == 'limit_full' or b.action == 'limit_level' then
                for _, c in ipairs(party_now) do if valid(c) and action(api, c, b.action) then n = n + 1 end end
            end
        end
        if n > 0 then log('actions_again\t'..round..'\t'..n) end
        local cut = lean_apply(api, party_now, 'again')  -- the game's own set-up may have restored more
        if cut > 0 then log('lean_again\t'..round..'\t'..cut) end
    end
    accessories(api)
    second_wind(api)
    if started and not paused then pcall(leash.tick, api, foes_now, api:GetPartyLeader(), os.time()) end
    -- Playtests (devtools boostNN): enemies also lose DRAIN_STEP% HP every
    -- DRAIN_SECONDS fight seconds, down to 1%, so a round ends within a minute or
    -- two even against damage-resistant forms (live 2026-11-10: a Hecteyes took
    -- 15 per hit for ten minutes). Never in releases (no devtools there).
    if started and not paused then
        local d = dev()
        local mode = d and d.testmode and d.testmode()
        if mode == 'boost' then
            drain_clock = drain_clock + 1
            if drain_clock % DRAIN_SECONDS == 0 then
                for _, e in ipairs(foes_now) do
                    local p = valid(e) and hp_percent(api, e)
                    if p and p > 1 then
                        pcall(function() api:SetHPPercent(e, math.max(1, p - DRAIN_STEP)) end)
                    elseif p == 1 then
                        local key = e:GetFullName()
                        at_floor[key] = at_floor[key] or drain_clock
                        if drain_clock - at_floor[key] >= DRAIN_FINISH then
                            at_floor[key] = drain_clock  -- again after another DRAIN_FINISH
                            for _, id in ipairs(STRIP) do pcall(function() api:RemoveStatusChangeID(e, FName(id), false) end) end
                            for _, id in ipairs({'BSC_DeProtes', 'BSC_DeShell'}) do
                                pcall(function() api:AddStatusChangeID(e, FName(id), INFINITY, true, nil, false) end)
                            end
                            log('drain_strip	'..round..'	'..e:GetFName():ToString())
                        end
                    end
                end
            end
        end
    end
    local count = api:GetEnemyMemberCount(FName('None'))
    if type(count) ~= 'number' then count = 0 end
    if not started and count == 0 then
        local waited = os.time() - battle_since
        if not spawn_stalled and waited > SPAWN_STALL_SECONDS then
            spawn_stalled = true
            log('spawn_stall\t'..(round + 1)..'\t'..waited)
            local f = paths.open('junon-spawnstall.on', 'wb')
            if f then f:write(os.date('!%H:%M:%S')..'\t'..(round + 1)..'\n'); f:close() end
        end
    end
    if count > enemies_seen then
        local party, foes = characters()
        local first = not started
        if first then started, round = true, round + 1; unstall_spawn() end
        identify(foes, api)
        round_max = math.max(round_max, count)
        if first then
            round_territory = current_territory()
            local combo = round_territory and data.combined and data.combined[round_territory]
            if combo then
                log('combined\t'..round..'\t'..round_territory..'\t'..combo.parts[1]..'+'..combo.parts[2]..
                    '\texpected='..combo.enemies)
            end
        end
        write_infusions()  -- a rank rule's carrier once the course is known (unchanged: no write)
        if first then
            party_now, foes_now = party, {}
            boons_of, owed = {}, {}  -- a new battle: new enemies
            actions_at = os.time() + ACTION_DELAY
            accessory = {clock = 0, atb = {}, mp = {}, logged = accessory.logged}
            leash.reset()
            local n = to_party(api, party, picks)
            hazards_start(api, party)
            lean.kinds, lean.caps, lean.live, lean.sample_at = {}, {}, {}, 0
            for _, c in ipairs(party) do lean.kinds[#lean.kinds+1] = player_type(c) end
            local capped = lean_apply(api, party, 'start')
            local d = dev()
            local mode = d and d.testmode and d.testmode()
            if mode then
                -- "immortal" (for filming): the fighters only cannot die; no buffs.
                for _, c in ipairs(party) do
                    if mode == true then
                        for _, id in ipairs(d.test_party) do
                            pcall(function() api:AddStatusChangeID(c, FName(id), INFINITY, true, nil, false) end)
                        end
                    end
                    pcall(function() api:SetImmotality(c, true) end)
                end
                log('testmode\t'..round..'\tparty='..#party..'\tmode='..tostring(mode))
            end
            offer_at = os.time() + OFFER_DELAY  -- owner 2026-11-10: round 1 too
            log('round_start\t'..round..'\tenemies='..count..'\tparty='..#party..'\tpicks='..#picks..'\tparty_statuses='..n..'\tcourse='..tostring(course)..'\tlean='..capped)
        end
        -- Enemies can arrive in waves: each new one is queued once.
        for _, e in ipairs(foes) do
            local key = e:GetFullName()
            if not buffed[key] then
                buffed[key] = true
                pending[#pending+1] = {actor = e, at = os.time()}
                foes_now[#foes_now+1] = e
            end
        end
    end
    if started and count < enemies_seen then
        heal_on_kills(api, enemies_seen - count)
        rally(api, enemies_seen - count, count)
        if count == 0 and lean_wanted() then lean_sample(api) end  -- the round's last blow
    end
    enemies_seen = count
    if started and not paused and count > 0 and lean_wanted() and os.time() >= lean.sample_at then
        lean.sample_at = os.time() + LEAN_SAMPLE
        lean_sample(api)
    end
    -- Live 2026-11-09: the object scan sees enemies the game is still spawning,
    -- and their own set-up then overwrites a spec or statuses given too early
    -- (one enemy per round kept its bonus, the other lost it). So each new enemy
    -- is hardened, and given the player's enemy boons, HARDEN_DELAY seconds later.
    if #pending > 0 then
        local ready, waiting = {}, {}
        for _, p in ipairs(pending) do
            if not valid(p.actor) then -- gone: drop it
            elseif os.time() - p.at >= HARDEN_DELAY then ready[#ready+1] = p.actor
            else waiting[#waiting+1] = p end
        end
        pending = waiting
        if #ready > 0 then
            local hard, raced = harden(api, ready)
            local d = dev()
            local mode, pct = nil, nil
            if d and d.testmode then mode, pct = d.testmode() end
            if mode == true or mode == 'boost' then
                pct = mode == 'boost' and pct or 10
                for _, e in ipairs(ready) do pcall(function() api:SetHPPercent(e, pct) end) end
            end
            local n = #picks > 0 and to_foes(api, ready, picks) or 0
            if n + hard > 0 then
                log('enemy_statuses\t'..round..'\t'..#ready..'\t'..n..'\thardened='..hard..
                    (arms_racing() and '\tarms_race='..raced or ''))
            end
        end
    end
    check_swaps(api)
    if offer_at and os.time() >= offer_at and count > 0 then
        offer_at = nil
        -- The tick runs once a second, so the last half second is a timer
        -- (ExecuteWithDelay, back on the game thread); tests and old UE4SS
        -- builds without it open straight away.
        if type(ExecuteWithDelay) == 'function' and type(ExecuteInGameThread) == 'function' then
            local opened_round = round
            ExecuteWithDelay(OFFER_EXTRA_MS, function()
                ExecuteInGameThread(function()
                    if in_round and round == opened_round and not window then pcall(open_window, menu, api) end
                end)
            end)
        else
            open_window(menu, api)
        end
    end
end
-- This run's draw (for tests and devtools).
function M.draws() return draws end
-- True from a course's first round until its end (result screen or two idle
-- minutes): the arena levels must stay loaded all that time (foyer.lua).
function M.course_active() return active end
-- One offer's infusions as the window would draw them (for tests).
function M.draw_offer(n, after_boss) return draw(n, after_boss) end
-- The run token the helper must echo (for tests).
function M.infusion_run() return infuse.run end
return M
