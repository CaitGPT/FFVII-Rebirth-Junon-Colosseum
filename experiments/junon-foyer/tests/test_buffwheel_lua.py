from pathlib import Path

from lupa import LuaRuntime

SCRIPTS = Path(__file__).resolve().parents[1] / 'ue4ss/JunonColosseum/Scripts'

FAKE = r'''
calls, shown, now = {}, {}, 1000
local function actor(name, x, y)
    return {name=name, IsValid=function() return true end,
            K2_GetActorLocation=function() return {X=x, Y=y, Z=0} end,
            GetFullName=function() return name end,
            GetFName=function() return {ToString=function() return name end} end}
end
party = {actor('PC0000_Cloud', -123780, 28675), actor('PC0003_Aerith', -123700, 28675)}
-- Another fighter in the ring (the second team of a two-team course).
function fighter(name) return actor(name, -123700, 28675) end
foes = {}
function spawn(name) foes[#foes+1] = actor(name, -123500, 28675) end
nextid = 0
-- An enemy of a real course spec, named as the game names actors.
function spawn_spec(spec) nextid = nextid + 1; spawn(spec..'_C_'..nextid) end
-- An enemy as the game shows it: an actor named after its model, its CharaSpec
-- name (nil: GetCharaSpecName fails) and its max HP; a swap raises max HP by the
-- clone's course HP factor unless `keeps` more swaps fail to take.
function spawn_shown(model, chara, max, keeps)
    nextid = nextid + 1; spawn(model..'_C_'..nextid)
    local a = foes[#foes]
    a.chara, a.max, a.keeps = chara, max, keeps or 0
    return a
end
function wipe() foes = {} end
-- The HP factor a clone carries: its course's (courses sharing clones share it).
function swap_factor(id)
    local jc = id:match('_(JC%d+)$')
    for _, c in ipairs(data.courses) do if c.clone == jc then return c.hp end end
    return 1.25
end
-- A round of this course whose enemies include this spec (the pools change with
-- the balance generator; tests find their rounds instead of naming them). A
-- single round, not a combined one.
function round_with(spec, c)
    for _, slot in ipairs(data.courses[c].slots) do
        for _, r in ipairs(slot) do
            if not data.combined[r] then
                for _, s in ipairs(data.round_specs[r]) do if s == spec then return r end end
            end
        end
    end
    error('course '..c..' has no round with '..spec)
end
api = {IsValid=function() return true end,
       GetPartyLeader=function() return party[1] end,
       GetEnemyMemberCount=function(_, race) assert(race == 'None'); return #foes end,
       AddStatusChangeID=function(_, a, id, time) calls[#calls+1] = a.name..':'..id..':'..time end,
       RemoveStatusChangeID=function(_, a, id) calls[#calls+1] = a.name..'-'..id end,
       SetOverrideBattleCharaSpec=function(_, a, id)
           calls[#calls+1] = a.name..'>'..id
           if a.max and (a.keeps or 0) > 0 then a.keeps = a.keeps - 1
           elseif a.max and not a.swapped then a.swapped, a.max = true, math.floor(a.max * swap_factor(id) + 0.5) end
       end,
       GetCharaSpecName=function(_, a)
           if not a.chara then error('no CharaSpec') end
           return {ToString=function() return a.chara end}
       end,
       GetHPMax=function(_, a) return a.max end,
       -- EEndAiMathCmp: 1 Less, 3 Greater (the only two the mod asks).
       IsHPPercent=function(_, a, pct, cmp)
           if cmp == 1 then return (a.hp or 100) < pct end
           return cmp == 3 and (a.hp or 100) > pct
       end,
       SetHPPercent=function(_, a, pct) a.hp = pct; calls[#calls+1] = a.name..'%'..pct end,
       SetImmotality=function(_, a, on) calls[#calls+1] = a.name..'!immortal' end,
       AddSpecialStatusChangeID=function(_, a, causer, id) specials[a.name..':'..id] = true; calls[#calls+1] = a.name..'~'..id end,
       HasSpecialStatusChangeID=function(_, a, id) return specials[a.name..':'..id] == true end,
       SetATB=function(_, kind, value) calls[#calls+1] = 'atb'..kind..'='..value end,
       -- ATB bars a fighter spent this battle (set a.spent in a test).
       GetSpendATBBarTotal=function(_, a) return a.spent or 0 end}
specials = {}
limits, mp = {}, {}   -- limit gauge and MP per EPlayerType (gauge max 1000, MP max 100)
bp = {IsValid=function() return true end,
      BPGetPlayerLimitMax=function(_, kind) return 1000 end,
      BPGetPlayerLimit=function(_, kind) return limits[kind] or 0 end,
      BPGetPlayerLimitLevelMax=function(_, kind) return 3 end,
      BPSetPlayerLimitLevel=function(_, kind, value) calls[#calls+1] = 'level'..kind..'='..value end,
      BPSetPlayerLimit=function(_, kind, value) limits[kind] = value; calls[#calls+1] = 'limit'..kind..'='..value end,
      BPGetPlayerMP=function(_, kind) return mp[kind] or 100 end,
      BPSetPlayerMP=function(_, kind, value) mp[kind] = value; calls[#calls+1] = 'mp'..kind..'='..value end,
      BPGetPlayerMaxMP=function(_, kind) return 100 end}
-- The party member has this one infusion's effect (status, special or action).
function got(b, name)
    if b.special then return has(name..'~'..b.special) end
    if b.action == 'atb_full' then return has('atb'..tonumber(name:match('^PC(%d+)'))..'=') end
    if b.action == 'limit_level' then return has('level'..tonumber(name:match('^PC(%d+)'))..'=3') end
    if b.action == 'heal_on_kill' or (b.action or ''):find('^limit_o') then return true end  -- they act later
    if b.action == 'limit_full' then return has('limit'..tonumber(name:match('^PC(%d+)'))..'=1000') end
    return has(name..':'..b.statuses[1]..':'..(b.time == 'short' and 0 or 64))
end
hidden = 0
menu_hide = function() hidden = hidden + 1 end
window = nil
menu = {IsValid=function() return true end,
        ShowMessageWindow=function(_, ctx, text, options, flags)
            window = {IsValid=function() return true end, closed=false, index=0, options=options, flags=flags, text=text}
            shown[#shown+1] = window
            return window
        end,
        IsMessageWindowClosed=function(_, w) return w.closed end,
        HideMessageWindow=function(_, w) w.closed = true; hidden = hidden + 1 end,
        GetMessageWindowSelectedIndex=function(_, w) return w.index end}
-- The player picks the option at this position (1-based); returns its label.
function choose(position)
    window.index = position - 1
    window.closed = true
    return window.options[position]
end
function FindAllOf(class)
    local all = {}
    for _, a in ipairs(party) do all[#all+1] = a end
    for _, a in ipairs(foes) do all[#all+1] = a end
    return all
end
game_paused = false
statics = {IsValid=function() return true end, SetGamePaused=function(_, ctx, on) game_paused = on end}
function StaticFindObject(path)
    if path:find('GameplayStatics') then return statics end
    if path:find('MenuBPAPI') then return bp end
    if path:find('BattleAPI') then return api end
    if path:find('MenuAPI') then return menu end
end
function FName(s) return s end
result_showing = false
menu_title = nil
package.preload.branding = function() return {result_visible = function() return result_showing end,
    selected_course = function() return menu_title and {title = menu_title, at = now} end} end
os.time = function() return now end
function tick(battle, seconds) for _ = 1, seconds or 1 do now = now + 1; wheel.tick({}, battle) end end
function has(text) return table.concat(calls, ','):find(text, 1, true) ~= nil end
data = require('buffwheel_data')
-- Test-only epics: since owner 2026-11-11 no infusion offers the limit_full and
-- limit_over_time actions (Gotterdammerung is the real accessory now), but
-- buffwheel.lua keeps them; these entries test them and keep four epics that need
-- no helper.
function add_limit_actions()
    table.insert(data.buffs, {id = 'FullLimit', tier = 'epic', label = 'Full limit gauge at the start of each round', target = 'party', statuses = {}, action = 'limit_full'})
    table.insert(data.buffs, {id = 'LimitOverTime', tier = 'epic', label = 'Limit gauge fills over time', target = 'party', statuses = {}, action = 'limit_over_time'})
end
-- An option's text without its tier label ("[Rare] ", "[Epic] ").
function plain(option) return (option:gsub('^%[%a+%] ', '')) end
function boon(label) for _, b in ipairs(data.buffs) do if b.label == plain(label) then return b end end end
-- Pick the option with this label, tier label or not (the draw is random).
function choose_label(label)
    for i, o in ipairs(window.options) do if plain(o) == label then return choose(i) end end
    error('not offered: '..label)
end
-- Refuse the open offer (the last option), so the round's clock runs on.
function refuse() if window and not window.closed then choose(#window.options) end end
function offered(label)
    for _, o in ipairs(window.options) do if plain(o) == label then return true end end
    return false
end
-- Offer only these boons, so a test can pick one it knows.
function only(...)
    local keep = {}
    for _, label in ipairs({...}) do keep[#keep+1] = boon(label) end
    data.buffs = keep
end
'''


def runtime():
    lua = LuaRuntime(unpack_returned_tuples=True)
    lua.globals().package.path = str(SCRIPTS / '?.lua').replace('\\', '/') + ';' + lua.globals().package.path
    lua.execute(FAKE)
    # No telemetry writes in tests; the helper's round report is faked by `territory`.
    lua.execute("""
        territory = nil
        requests = {}
        infusion_writes, ack = {}, nil   -- junon-infusions.req writes; the helper's answer
        io.open = function(path, mode)
            if path:find('junon%-round%.txt') and territory then
                return {read = function() return territory end, close = function() end}
            end
            if path:find('junon%-rounds%.req') then
                return {write = function(_, s) requests[#requests+1] = s end, close = function() end}
            end
            if path:find('junon%-infusions%.req') then
                return {write = function(_, s) infusion_writes[#infusion_writes+1] = s end, close = function() end}
            end
            if path:find('junon%-infusions%.ack') and ack then
                return {read = function() return ack end, close = function() end}
            end
            return nil
        end
        os.rename = function() end
        os.remove = function() end
    """)
    lua.execute("wheel = require('buffwheel')")
    lua.execute(INFUSION_HELPERS)
    return lua


INFUSION_HELPERS = r'''
-- The native helper answers the current run (status "ready" by default).
function answer(status, run)
    ack = 'run '..(run or wheel.infusion_run())..'\nstatus '..(status or 'ready')..'\nphase battle\n'
end
-- The last junon-infusions.req the Lua wrote.
function sent() return infusion_writes[#infusion_writes] or '' end
function sent_accessories()
    local out = {}
    for id in sent():gmatch('acc (%S+)') do out[#out+1] = id end
    return table.concat(out, ',')
end
'''


def test_round_one_pauses_on_three_boons_and_the_pick_lasts_the_run():
    """Owner 2026-11-10: the first offer comes in round 1 too, OFFER_DELAY seconds in."""
    lua = runtime()
    lua.execute('''
        tick(true); spawn('EN1'); tick(true)      -- round 1 begins; banner still showing
        assert(#shown == 0)
        tick(true, 2)                             -- 2 s in, the battle pauses on the window
        assert(#shown == 1 and #window.options == 4 and window.flags == 2 and game_paused)
        assert(window.options[4] == 'Refuse the infusion')
        assert(window.text == 'Choose a Mako infusion')
        local seen = {}
        for i = 1, 3 do local o = window.options[i]; assert(boon(o) and not seen[o]); seen[o] = true end
        local b = boon(choose(2)); tick(true)
        assert(not game_paused)
        tick(true, 2)                             -- enemy boons land 2 s after the enemy appeared
        local target = b.target == 'party' and 'PC0000_Cloud' or 'EN1'
        assert(got(b, target), b.id)
        wipe(); tick(true); tick(false, 15)       -- the round's battle ends; loading screen
        calls = {}
        tick(true); spawn('EN2'); tick(true, 3)   -- round 2: the boon again (enemies 2 s after they appear)
        target = b.target == 'party' and 'PC0003_Aerith' or 'EN2'
        assert(got(b, target), b.id)
        assert(#shown == 2)                       -- and another choice
    ''')


def test_enemy_boons_reach_later_enemies_once():
    lua = runtime()
    lua.execute('''
        only('Slow the enemy', 'Haste for the party', 'Shell for the party')
        tick(true); spawn('EN1'); tick(true); wipe(); tick(true); tick(false, 15)
        tick(true); spawn('EN2'); tick(true, 4)
        choose_label('Slow the enemy'); tick(true)
        assert(has('EN2:BSC_Slow:64') and not has('PC0000_Cloud:BSC_Slow'))
        local n = #calls
        spawn('EN3'); tick(true, 3)               -- a later arrival is slowed once, 2 s after it appears
        assert(#calls == n + 1 and calls[#calls] == 'EN3:BSC_Slow:64')
        tick(true, 3)
        assert(#calls == n + 1)
    ''')


def test_the_run_ends_when_no_round_follows_and_picks_do_not_carry_over():
    lua = runtime()
    lua.execute('''
        only('Slow the enemy', 'Haste for the party', 'Shell for the party')
        tick(true); spawn('EN1'); tick(true); wipe(); tick(true); tick(false, 15)
        tick(true); spawn('EN2'); tick(true, 4)
        choose_label('Haste for the party'); tick(true)
        assert(has('BSC_Haste'))
        wipe(); tick(true); tick(false, 130)      -- course over
        calls = {}
        tick(true); spawn('EN9'); tick(true, 5)   -- a new course: no Haste; its round 1 offers again
        assert(not has('BSC_Haste') and #shown == 2 and offered('Haste for the party'))
    ''')


def test_battles_outside_the_arena_are_ignored():
    lua = runtime()
    lua.execute('''
        for _, p in ipairs(party) do p.K2_GetActorLocation = function() return {X=0, Y=0, Z=0} end end
        for _ = 1, 3 do tick(true); spawn('EN1'); tick(true, 5); wipe(); tick(true); tick(false, 15) end
        assert(#shown == 0 and #calls == 0)
    ''')


def test_a_battle_ending_under_the_window_unpauses():
    lua = runtime()
    lua.execute('''
        tick(true); spawn('EN1'); tick(true); wipe(); tick(true); tick(false, 15)
        tick(true); spawn('EN2'); tick(true, 4)
        assert(game_paused)
        tick(false)
        assert(not game_paused)
    ''')


def round_specs(lua, course, rnd):
    """The enemy specs of the round this run drew for a course's slot (after a tick)."""
    return list(lua.eval(f'data.round_specs[wheel.draws()[{course}][{rnd}]]').values())


def test_course_six_is_recognised_and_its_enemies_hardened():
    """Course 6 (owner's order of 2026-11-10; Rally replaced Tough hides on
    2026-11-11): Rivals, Rally, Riot rush, Bloodlust and Hall of mirrors, with the
    course's hidden HP factor."""
    lua = runtime()
    lua.execute('tick(false); territory = "terVR_COL30_" .. wheel.draws()[6][1]')
    specs = round_specs(lua, 6, 1)
    lua.globals().first_specs = lua.table_from(specs)
    lua.execute('''
        tick(true)
        for _, s in ipairs(first_specs) do spawn_spec(s) end
        tick(true, 3)                                 -- hardened 2 s after they appear
        refuse()                                      -- round 1's offer
        local rules = data.courses[6]
        assert(rules.spec and rules.enemy_boons == 1)
        local spec = first_specs[1]
        local got = table.concat(calls, ',')
        assert(got:find(spec..'_C_1>'..spec..'_'..rules.clone, 1, true), got)  -- shared with the first course of equal stats
        local boons = 0
        for _, c in ipairs(calls) do if c:find('^'..spec..'_C_1:') then boons = boons + 1 end end
        assert(boons == 3, got)                       -- one random enemy boon, Riot rush's Haste and the opening Reflect
        assert(got:find(spec..'_C_1:BSC_Reflection:64', 1, true), got)
        tick(true, 60)                                -- Hall of mirrors ends after 60 fight seconds
        assert(table.concat(calls, ','):find(spec..'_C_1-BSC_Reflection', 1, true))
    ''')


def test_the_last_course_has_short_rest_offers_two_and_second_wind():
    lua = runtime()
    lua.execute('tick(false); territory = "terVR_COL30_" .. wheel.draws()[14][1]')
    specs = round_specs(lua, 14, 1)
    lua.globals().first_specs = lua.table_from(specs)
    lua.execute('''
        tick(true)
        for _, s in ipairs(first_specs) do spawn_spec(s) end
        tick(true, 3)                                 -- hardened 2 s after they appear
        local got = table.concat(calls, ',')
        assert(not got:find('PC0000_Cloud%', 1, true), got)  -- round 1: no cut
        assert(not got:find('BSC_Reraise', 1, true), got)    -- Second wind gives the enemy no status
        assert(data.courses[14].second_wind.below == 20 and data.courses[14].second_wind.to == 50)
        assert(data.courses[14].party_recovery.hp == 20 and data.courses[14].party_recovery.mp == 15)
        party[1].hp = 30                              -- Cloud ends round 1 on 30%
        refuse(); tick(true, 2)
        wipe(); tick(true); tick(false, 15)
        party[1].hp = 80                              -- the game's own restore between rounds
        territory = 'terVR_COL30_' .. wheel.draws()[14][2]
        tick(true)
        for _, s in ipairs(data.round_specs[wheel.draws()[14][2]]) do spawn_spec(s) end
        tick(true, 4)
        assert(#shown == 2 and #window.options == 3)  -- slim pickings: two boons and Skip (round 1 offered too)
        assert(party[1].hp == 50, party[1].hp)        -- Short rest: 30% + 20%
    ''')


def start_round(lua, course, rnd, team=None):
    """Battle begins, the round's real enemies appear, its offer is refused."""
    lua.globals().round_specs_now = lua.table_from(round_specs(lua, course, rnd))
    lua.execute(f'''
        territory = "terVR_COL30_" .. wheel.draws()[{course}][{rnd}]
        tick(true)
        for _, s in ipairs(round_specs_now) do spawn_spec(s) end
        tick(true)
        tick(true, 2); refuse(); tick(true)
    ''')


def end_round(lua):
    lua.execute('wipe(); tick(true); tick(false, 15)')


def test_short_rest_lets_each_fighter_recover_only_20_hp_and_15_mp_between_rounds():
    """Owner 2026-11-11 (course 10 on, replacing Wounded): vanilla rounds restore
    50% HP and 30% MP; under Short rest a fighter starts a round with at most what
    it ended its last round with plus 20% HP and 15% MP. Records are per fighter,
    so the team sitting a round out keeps its own; a fallen fighter the game
    brings back starts on at most 20%; round 1 and a team's first round are
    untouched."""
    lua = runtime()
    lua.execute('tick(false)')
    cloud, aerith = 'party[1]', 'party[2]'
    lua.execute('team_a = {party[1], party[2]}; team_b = {fighter("PC0001_Barret"), fighter("PC0002_Tifa")}')
    assert lua.eval('data.courses[9].party_recovery') is None
    assert lua.eval('data.courses[10].party_recovery.hp') == 20
    start_round(lua, 10, 1)
    lua.execute('''
        assert(not has('%'), table.concat(calls, ','))        -- round 1 untouched
        assert(not has('lean'))
        party[1].hp, mp[0] = 30, 40                             -- Cloud ends on 30% HP, 40 MP
        party[2].hp, mp[3] = 0, 10                              -- Aerith falls
    ''')
    lua.execute('tick(true, 2)')                                # sampled while enemies stand
    end_round(lua)
    lua.execute('''
        -- The game's restore between rounds; team B fights round 2.
        party[1].hp, party[2].hp, mp[0], mp[3] = 80, 50, 70, 40
        party = team_b
        team_b[1].hp, team_b[2].hp, mp[1], mp[2] = 80, 100, 100, 100
        calls = {}
    ''')
    start_round(lua, 10, 2)
    lua.execute('''
        assert(not has('%') and not has('mp1=') and not has('mp2='), table.concat(calls, ','))  -- team B's first round
        team_b[1].hp, mp[1] = 60, 50                            -- Barret ends on 60% HP, 50 MP
    ''')
    end_round(lua)
    lua.execute('''
        team_b[1].hp, mp[1] = 100, 80
        party = team_a
        calls = {}
    ''')
    lua.globals().round_specs_now = lua.table_from(round_specs(lua, 10, 3))
    lua.execute('''
        territory = "terVR_COL30_" .. wheel.draws()[10][3]
        tick(true)
        for _, s in ipairs(round_specs_now) do spawn_spec(s) end
        tick(true)                                              -- round 3 starts
        assert(team_a[1].hp == 50 and mp[0] == 55, team_a[1].hp..' '..mp[0])   -- 30+20, 40+15
        assert(team_a[2].hp == 20 and mp[3] == 25, team_a[2].hp..' '..mp[3])   -- fallen: 0+20, 10+15
        assert(has('PC0000_Cloud%50') and has('mp0=55') and has('mp3=25'))
        -- The game's own set-up restores again a moment later: the second pass
        -- (with the round-start actions, after the offer) cuts it back.
        team_a[1].hp, mp[0] = 90, 80
        tick(true, 2); refuse(); tick(true)
        assert(team_a[1].hp == 50 and mp[0] == 55, team_a[1].hp..' '..mp[0])
        -- A fighter below its cap is never raised.
        team_a[1].hp, team_a[2].hp, mp[0], mp[3] = 10, 0, 5, 0     -- Aerith falls again
    ''')
    end_round(lua)
    lua.execute('''
        party = team_b
        calls = {}
    ''')
    start_round(lua, 10, 4)
    lua.execute('''
        assert(team_b[1].hp == 80 and mp[1] == 65, team_b[1].hp..' '..mp[1])  -- team B kept its record: 60+20, 50+15
        assert(team_b[2].hp == 100 and mp[2] == 100)                          -- Tifa ended full: nothing to cut
    ''')
    end_round(lua)
    lua.execute('''
        party = team_a
        team_a[1].hp, mp[0] = 15, 10                            -- below the caps (30%, 20 MP)
        calls = {}
    ''')
    start_round(lua, 10, 5)
    lua.execute('''
        assert(team_a[1].hp == 15 and mp[0] == 10 and not has('PC0000_Cloud%') and not has('mp0='))
        assert(team_a[2].hp == 0 and not has('PC0003_Aerith%'))   -- still down: left alone
    ''')


def test_short_rest_logs_a_compact_count_and_a_line_per_fighter():
    lua = runtime()
    lua.execute('''
        require('paths').dev = 'telemetry/'          -- a development install
        lines = {}
        local real = io.open
        io.open = function(path, mode)
            if path:find('junon%-buffwheel%.tsv') then
                return {write = function(_, s) lines[#lines+1] = s end, close = function() end}
            end
            return real(path, mode)
        end
        tick(false)
    ''')
    start_round(lua, 10, 1)
    lua.execute('party[1].hp, mp[0] = 30, 40; tick(true, 2)')
    end_round(lua)
    lua.execute('party[1].hp, mp[0] = 80, 70')
    start_round(lua, 10, 2)
    log = ''.join(lua.eval('table.concat(lines)'))
    assert '\tlean=1' in log and '\tlean=0' in log, log                 # round_start: fighters cut
    assert 'lean_mp_seen\t1\t0\t40/100' in log, log
    assert 'lean\t2\tstart\tPC0000_Cloud\thp=30+20:80>50\tmp=40/100+15%:70>55:read=55' in log, log
    assert 'PC0003_Aerith\tmp=100/100+15%:100<=100' in log, log         # MP read, nothing to cut


def test_short_rest_takes_the_mp_record_from_the_battle_itself():
    """BPGetPlayerMP is the fighter's live battle MP (party block +0x3ac; dumps
    and the harness, 2026-11-11), so the record is the round's last reading: a
    restore the game makes before the first reading between rounds is not
    recorded."""
    lua = runtime()
    lua.execute('tick(false)')
    start_round(lua, 10, 1)
    lua.execute('mp[0] = 40; tick(true, 2)')                  # Cloud casts: 40 MP in battle
    lua.execute('wipe(); tick(true)')                         # the last blow: sampled
    lua.execute('mp[0] = 70; tick(false, 15)')                # restored before the gap's first reading
    lua.execute('calls = {}')
    start_round(lua, 10, 2)
    lua.execute("assert(mp[0] == 55 and has('mp0=55'), mp[0]..' '..table.concat(calls, ','))")  # 40 + 15


def test_courses_before_ten_leave_recovery_to_the_game():
    lua = runtime()
    lua.execute('tick(false)')
    start_round(lua, 9, 1)
    lua.execute('party[1].hp, mp[0] = 30, 40; tick(true, 2)')
    end_round(lua)
    lua.execute('party[1].hp, mp[0] = 80, 70; calls = {}')
    start_round(lua, 9, 2)
    lua.execute("assert(party[1].hp == 80 and mp[0] == 70 and not has('PC0000_Cloud%') and not has('mp0='))")


def test_course_one_has_no_modifiers():
    lua = runtime()
    lua.execute('tick(false); territory = "terVR_COL30_" .. wheel.draws()[1][1]')
    specs = round_specs(lua, 1, 1)
    lua.globals().first_specs = lua.table_from(specs)
    lua.execute('''
        tick(true)
        for _, s in ipairs(first_specs) do spawn_spec(s) end
        tick(true, 3)                                 -- hardened 2 s after they appear
        assert(#calls == 0, table.concat(calls, ','))
    ''')


def test_the_menu_title_shin_iri_names_course_one():
    """Owner 2026-11-11: course 1 is Shin'iri (新入り, newcomer), not Rookie; the
    menu's title, apostrophe and all, still picks it over a stale draw."""
    lua = runtime()
    lua.execute("""
        assert(data.courses[1].title == "Shin'iri")
        tick(false)
        menu_title = "Shin'iri"
        territory = 'terVR_COL30_' .. wheel.draws()[4][1]   -- a stale draw would say course 4
        tick(true); spawn('EN1'); tick(true, 3)
        assert(#calls == 0, table.concat(calls, ','))      -- course 1: no rule hardens EN1
    """)


def test_the_result_screen_ends_the_course_and_team_swaps_do_not():
    lua = runtime()
    lua.execute('''
        only('Haste for the party', 'Regen for the party', 'Shell for the party')
        tick(true); spawn('EN1'); tick(true, 3)
        choose_label('Haste for the party'); tick(true)
        wipe(); tick(true); tick(false, 15)
        tick(true); spawn('EN2'); tick(true, 3)      -- round 2 after a 15 s gap: same course
        assert(#shown == 2 and not offered('Haste for the party'))  -- still taken
        wipe(); tick(true); tick(false, 3)
        result_showing = true; tick(false)           -- the result screen: course over
        result_showing = false
        tick(true); spawn('EN9'); tick(true, 5)      -- a new course: no picks yet
        assert(#shown == 3 and offered('Haste for the party'))
    ''')


def test_every_run_draws_one_round_per_slot_and_sends_it_to_the_helper():
    lua = runtime()
    lua.execute('''
        tick(false)
        local d = wheel.draws()
        assert(#d == #data.courses)
        local firsts = {}
        for c, rules in ipairs(data.courses) do
            assert(#d[c] == #rules.slots)
            for s, r in ipairs(d[c]) do
                local ok = false
                for _, x in ipairs(rules.slots[s]) do if x == r then ok = true end end
                assert(ok, 'course '..c..' slot '..s..' drew '..r..' from outside its pool')
            end
            assert(not firsts[d[c][1]], 'two courses start with '..d[c][1]); firsts[d[c][1]] = true
        end
        local sent = table.concat(requests)
        assert(sent:find('COL30_JUNON_01_Free_Col terVR_COL30_'..d[1][1], 1, true), sent:sub(1, 200))
        local before = table.concat(d[14], ',')
        -- a finished course brings a fresh draw
        tick(true); spawn('EN1'); tick(true, 3); wipe(); tick(true); tick(false, 130)
        assert(#requests > 1)
    ''')


def test_development_switches_pick_boons_and_soften_rounds():
    lua = runtime()
    lua.execute('''
        package.loaded.devtools = {autoboon = function(n) return 2 end, testmode = function() return true end,
                                   test_party = {'BSC_Brave'}}
        tick(true); spawn('EN1'); tick(true, 3)
        local got = table.concat(calls, ',')
        assert(got:find('PC0000_Cloud:BSC_Brave:64', 1, true) and got:find('PC0000_Cloud!immortal', 1, true), got)
        assert(got:find('EN1%10', 1, true), got)               -- enemies at 10% once set up
        assert(#shown == 1)                                    -- round 1: window opens...
        tick(true, 2)                                          -- ...and picks option 2 by itself
        assert(hidden == 1 and not game_paused)
        wipe(); tick(true); tick(false, 15)
        tick(true); spawn('EN2'); tick(true, 5)                -- and again in round 2
        assert(#shown == 2 and hidden == 2 and not game_paused)
    ''')


def test_rank_rules_riot_rush_bloodlust_darkside_and_time_trap():
    """Owner 2026-11-10: creative rank rules. Course 13, where Darkside arrives in the
    owner's reordered ladder, also has Riot rush (enemies hasted; it replaced Toad
    drill after the playtest), Bloodlust (Berserk all course) and Time trap (Stop
    every 30 fight seconds)."""
    lua = runtime()
    lua.execute('tick(false); territory = "terVR_COL30_" .. wheel.draws()[13][1]')
    lua.globals().first_specs = lua.table_from(round_specs(lua, 13, 1))
    lua.execute('''
        tick(true)
        for _, s in ipairs(first_specs) do spawn_spec(s) end
        tick(true, 3)
        if window and not window.closed then choose(#window.options); tick(true) end  -- refuse; the fight clock runs again
        refuse()                                                   -- round 1's offer
        local got = table.concat(calls, ',')
        assert(not got:find('BSC_Toad', 1, true), got)
        assert(got:find(foes[1].name..':BSC_Haste:64', 1, true), got)
        assert(got:find('PC0000_Cloud:BSC_Berserk:64', 1, true), got)
        assert(got:find('PC0000_Cloud:BSC_Dark:64', 1, true), got)
        assert(data.courses[13].party_status[2] == 'BSC_Dark' and #data.courses[12].party_status == 1)
        assert(not got:find('BSC_Stop', 1, true))
        tick(true, 28)
        got = table.concat(calls, ',')
        assert(got:find(':BSC_Stop:0', 1, true), got)              -- the game's short Stop at 30 s
    ''')


def test_darkside_asks_the_helper_for_the_darkside_materia_for_the_whole_course():
    """Research 2026-11-11: the status alone has no HP cost. On Darkside courses the
    request names the rule's carrier (E_ACC_7106, the Darkside materia) first, once
    the enemies name the course, whatever infusions are picked; picks append after
    it, and the course's end removes it. BSC_Dark is still given at each round's
    start (owner 2026-11-11: a fighter may switch it off with the Darkside command;
    it comes back at the next round's start, with no mid-round re-apply)."""
    lua = runtime()
    lua.execute('tick(false); territory = "terVR_COL30_" .. wheel.draws()[13][1]')
    lua.globals().first_specs = lua.table_from(round_specs(lua, 13, 1))
    lua.execute(r"""
        only('Party equips Genji Gloves', 'Haste for the party')  -- Slim pickings: two per offer
        tick(true)                                           -- course start: the course is not known yet
        local run = wheel.infusion_run()
        assert(sent() == 'run '..run..'\nphase battle\n', sent())
        answer()
        for _, s in ipairs(first_specs) do spawn_spec(s) end
        tick(true)                                           -- the enemies name course 13
        assert(sent() == 'run '..run..'\nphase battle\nacc E_ACC_7106\n', sent())
        assert(not has('E_ACC'))                             -- no status call for it
        tick(true, 2)
        assert(has('PC0000_Cloud:BSC_Dark:64'))              -- the status still turns Darkside on
        choose_label('Party equips Genji Gloves'); tick(true)
        assert(sent_accessories() == 'E_ACC_7106,E_ACC_0211', sent())   -- picks append after the rule
        wipe(); tick(true); tick(false)
        assert(sent():find('phase idle', 1, true) and sent_accessories() == 'E_ACC_7106,E_ACC_0211', sent())
        -- Darkside switched off with the command in round 1: given again at round 2's start.
        local before = 0
        for _, c in ipairs(calls) do if c == 'PC0000_Cloud:BSC_Dark:64' then before = before + 1 end end
        tick(false, 10)
        territory = 'terVR_COL30_' .. wheel.draws()[13][2]
        tick(true)
        for _, s in ipairs(data.round_specs[wheel.draws()[13][2]]) do spawn_spec(s) end
        tick(true, 2)
        local after = 0
        for _, c in ipairs(calls) do if c == 'PC0000_Cloud:BSC_Dark:64' then after = after + 1 end end
        assert(after == before + 1, before..' '..after)
        wipe(); tick(true); tick(false, 130)                 -- the course ends
        assert(wheel.infusion_run() ~= run and sent_accessories() == '', sent())
    """)


def test_the_menu_names_a_darkside_course_before_its_enemies_and_others_get_no_carrier():
    lua = runtime()
    lua.execute(r"""
        tick(false)
        menu_title = data.courses[14].title
        tick(true)                                           -- course start, course 14 from the menu
        assert(sent_accessories() == 'E_ACC_7106', sent())
        wipe(); tick(true); tick(false, 130)
        assert(sent_accessories() == '', sent())
        menu_title = data.courses[12].title                  -- Second wind, no Darkside yet
        tick(true); spawn('EN1'); tick(true, 3)
        assert(sent_accessories() == '', sent())
        for c = 1, 12 do assert(#data.courses[c].party_accessories == 0, c) end
        assert(data.courses[13].party_accessories[1] == 'E_ACC_7106')
    """)


def test_second_wind_restores_each_enemy_once_from_course_twelve():
    """Live 2026-11-11 (course 12, build 0.9.19): enemies given BSC_Reraise lay
    dead without rising and the battle never ended. Second wind now gives no
    status: the first time the tick sees an enemy standing below 20% HP it is
    restored to 50%, once per enemy; an enemy already at 0% stays dead, one above
    the threshold is left alone, and each rise is logged."""
    lua = runtime()
    lua.execute(ARMS_RACE_FAKES)
    lua.execute(r'''
        assert(data.courses[11].second_wind == nil)
        for c = 12, 14 do
            assert(data.courses[c].second_wind.below == 20 and data.courses[c].second_wind.to == 50, c)
            for _, id in ipairs(data.courses[c].enemy_status) do assert(id ~= 'BSC_Reraise', c) end
        end
        tick(false); menu_title = data.courses[12].title
        tick(true); spawn('EN1'); spawn('EN2'); spawn('EN3'); spawn('EN4')
        tick(true, 3); refuse(); tick(true)                -- hardened; round 1's offer refused
        assert(not has('BSC_Reraise'), table.concat(calls, ','))
        foes[1].hp = 15                                    -- low and standing: rises
        foes[2].hp = 0                                     -- dead between two ticks: stays dead
        foes[3].hp = 25                                    -- above the threshold: left alone
        tick(true)
        assert(foes[1].hp == 50 and foes[2].hp == 0 and foes[3].hp == 25 and foes[4].hp == nil)
        local wind = lines('second_wind')
        assert(#wind == 1 and wind[1][2] == '1' and wind[1][3] == 'EN1' and wind[1][4] == '15>50',
               table.concat(wind[1] or {}, ' '))
        foes[1].hp = 5                                     -- low again: only once
        foes[3].hp = 19                                    -- its own first time
        tick(true, 2)
        assert(foes[1].hp == 5 and foes[3].hp == 50 and #lines('second_wind') == 2)
        assert(lines('second_wind')[2][3] == 'EN3' and lines('second_wind')[2][4] == '19>50')
        next_round()
        tick(true); spawn('EN5'); tick(true, 3); refuse(); tick(true)
        foes[1].hp = 1
        tick(true)
        assert(foes[1].hp == 50 and lines('second_wind')[3][2] == '2' and lines('second_wind')[3][4] == '1>50')
    ''')


def test_second_wind_waits_for_the_enemy_to_be_hardened_and_skips_earlier_courses():
    lua = runtime()
    lua.execute(ARMS_RACE_FAKES)
    lua.execute(r'''
        tick(false); menu_title = data.courses[12].title
        tick(true); spawn('EN1'); foes[1].hp = 10
        tick(true)                                         -- not hardened yet (HARDEN_DELAY)
        assert(foes[1].hp == 10 and #lines('second_wind') == 0)
        tick(true, 2); refuse(); tick(true)
        assert(foes[1].hp == 50 and #lines('second_wind') == 1)
        refuse(); tick(true); wipe(); tick(true); tick(false, 130)   -- the course ends
        menu_title = data.courses[11].title
        tick(true); spawn('EN2'); tick(true, 3); refuse(); tick(true)
        foes[1].hp = 10
        tick(true, 3)
        assert(foes[1].hp == 10 and #lines('second_wind') == 1)
    ''')


def test_second_wind_in_a_boost_playtest_rises_once_then_drains_to_the_finisher():
    """Playtest boost (devtools boostNN): the enemy starts at NN%, rises once to
    50%, then the drain takes it back to 1% and strips its wards, so test runs
    still end."""
    lua = runtime()
    lua.execute(ARMS_RACE_FAKES)
    lua.execute(r'''
        package.loaded.devtools = {testmode = function() return 'boost', 10 end}
        tick(false); menu_title = data.courses[12].title
        tick(true); spawn('EN1'); tick(true, 3); refuse(); tick(true)
        assert(foes[1].hp == 50, foes[1].hp)               -- set to 10%, then its second wind
        assert(#lines('second_wind') == 1 and lines('second_wind')[1][4] == '10>50')
        tick(true, 90)
        assert(foes[1].hp == 1, foes[1].hp)                -- drained again, never a second rise
        assert(#lines('second_wind') == 1)
        tick(true, 30)
        assert(#lines('drain_strip') >= 1 and foes[1].hp == 1)
        assert(#lines('second_wind') == 1)
    ''')


ARMS_RACE_FAKES = r"""
    require('paths').dev = 'telemetry/'          -- a development install: log lines are kept
    logged = {}
    local open = io.open
    io.open = function(path, mode)
        if path == 'telemetry/junon-buffwheel.tsv' then
            return {write = function(_, s) logged[#logged+1] = s end, close = function() end}
        end
        return open(path, mode)
    end
    -- The log lines of this kind, as lists of their tab-separated fields (time dropped).
    function lines(kind)
        local out = {}
        for _, s in ipairs(logged) do
            local fields = {}
            for f in s:gsub('\n$', ''):gmatch('[^\t]+') do fields[#fields+1] = f end
            table.remove(fields, 1)
            if fields[1] == kind then out[#out+1] = fields end
        end
        return out
    end
    -- The enemy boons drawn by Arms race so far, in order.
    function raced()
        local out = {}
        for _, f in ipairs(lines('arms_race')) do out[#out+1] = f[3] end
        return out
    end
    function in_pool(id) for _, b in ipairs(data.enemy_boons) do if b == id then return true end end return false end
    -- The statuses an enemy was given (in calls).
    function given(name)
        local out = {}
        for _, c in ipairs(calls) do
            local id = c:match('^'..name..':(BSC_[%w_]+):64$')
            if id then out[#out+1] = id end
        end
        return out
    end
    function holds(name, id) return has(name..':'..id..':64') end
    -- Infusions none of which an enemy boon matches (no status from the pool).
    only('Resist ailments', 'Full ATB at the start of each round', 'Refocus: three ATB segments')
    function next_round() wipe(); tick(true); tick(false, 15) end
"""


def test_arms_race_is_course_eights_rule_and_mirror_match_is_gone():
    """Owner 2026-11-11: Arms race replaces Mirror match on course 8; like every
    rank rule it holds on every later course."""
    lua = runtime()
    lua.execute('''
        assert(not data.courses[7].arms_race)
        for c = 8, 14 do assert(data.courses[c].arms_race, c) end
        for c = 1, 14 do assert(data.courses[c].mirror == nil, c) end
        assert(#data.enemy_boons >= 10)
    ''')


def test_arms_race_gives_the_enemy_a_boon_for_every_infusion_taken():
    """One random enemy boon per infusion taken (refusals do not count): on the
    enemies standing when it is taken, and all of them on every later enemy. The
    party's infusions themselves never reach the enemy (Mirror match is gone)."""
    lua = runtime()
    lua.execute(ARMS_RACE_FAKES)
    lua.execute(r'''
        tick(false); menu_title = data.courses[8].title
        tick(true); spawn('EN1'); tick(true, 3)          -- round 1; EN1 hardened, the offer open
        assert(holds('EN1', 'BSC_Haste'))                 -- Riot rush
        calls = {}
        choose_label('Resist ailments'); tick(true)
        local got = raced()
        assert(#got == 1 and in_pool(got[1]), table.concat(got, ','))
        assert(got[1] ~= 'BSC_Haste')                     -- the enemies are hasted already (Riot rush)
        local first = lines('arms_race')[1]
        assert(first[2] == '1' and first[4] == 'total=1' and first[5] == 'standing=1', table.concat(first, ' '))
        assert(#given('EN1') == 1 and holds('EN1', got[1]), table.concat(calls, ','))  -- standing: the new boon only
        assert(has('PC0000_Cloud:BSC_Resist:64') and not has('EN1:BSC_Resist'))
        spawn('EN2'); tick(true, 3)                       -- a later wave gets the list when hardened
        assert(holds('EN2', got[1]))
        local hard = lines('enemy_statuses')
        assert(hard[#hard][6] == 'arms_race=1', table.concat(hard[#hard], ' '))
        next_round()
        tick(true); spawn('EN3'); tick(true, 3)          -- round 2: refused, so nothing new
        refuse(); tick(true)
        assert(#raced() == 1 and holds('EN3', got[1]))
        next_round()
        tick(true); spawn('EN4'); tick(true, 3)          -- round 3: a second infusion, a second boon
        choose_label('Full ATB at the start of each round'); tick(true)
        got = raced()
        assert(#got == 2 and got[2] ~= got[1] and got[2] ~= 'BSC_Haste' and in_pool(got[2]), table.concat(got, ','))
        assert(lines('arms_race')[2][2] == '3' and lines('arms_race')[2][4] == 'total=2')
        assert(holds('EN4', got[2]))
        next_round()
        calls = {}
        tick(true); spawn('EN5'); tick(true, 3)          -- round 4: a new enemy carries both
        assert(holds('EN5', got[1]) and holds('EN5', got[2]), table.concat(calls, ','))
        hard = lines('enemy_statuses')
        assert(hard[#hard][2] == '4' and hard[#hard][6] == 'arms_race=2', table.concat(hard[#hard], ' '))
        assert(not has('EN5~') and not has('EN5:BSC_Resist'))
        refuse(); tick(true); wipe(); tick(true); tick(false, 130)   -- the course ends
        calls = {}
        menu_title = data.courses[8].title
        tick(true); spawn('EN6'); tick(true, 3)          -- a new course starts unarmed
        hard = lines('enemy_statuses')
        assert(hard[#hard][6] == 'arms_race=0', table.concat(hard[#hard], ' '))
    ''')


def test_arms_race_draws_new_boons_until_the_pool_runs_out():
    """Each new boon avoids the ones already drawn and the course's own enemy
    statuses (Haste), then any not drawn yet, then any at all."""
    lua = runtime()
    lua.execute(ARMS_RACE_FAKES)
    lua.execute(r'''
        data.enemy_boons = {'BSC_Haste', 'BSC_Protes'}
        tick(false); menu_title = data.courses[8].title
        for r = 1, 3 do
            tick(true); spawn('EN'..r); tick(true, 3)
            choose(1); tick(true)
            next_round()
        end
        local got = raced()
        assert(#got == 3 and got[1] == 'BSC_Protes' and got[2] == 'BSC_Haste' and in_pool(got[3]), table.concat(got, ','))
        calls = {}
        tick(true); spawn('EN4'); tick(true, 3)
        local hard = lines('enemy_statuses')
        assert(hard[#hard][6] == 'arms_race=3', table.concat(hard[#hard], ' '))
    ''')


def test_before_course_eight_infusions_do_not_arm_the_enemy():
    lua = runtime()
    lua.execute(ARMS_RACE_FAKES)
    lua.execute(r'''
        tick(false); menu_title = data.courses[7].title
        tick(true); spawn('EN1'); tick(true, 3)
        choose_label('Resist ailments'); tick(true)
        next_round()
        calls = {}
        tick(true); spawn('EN2'); tick(true, 3)
        assert(#raced() == 0)
        local hard = lines('enemy_statuses')
        assert(#hard[#hard] == 5, table.concat(hard[#hard], ' '))   -- no arms_race field
        local boons = 0
        for _, id in ipairs(given('EN2')) do if id ~= 'BSC_Haste' and id ~= 'BSC_Reflection' then boons = boons + 1 end end
        assert(boons <= 1, table.concat(calls, ','))                 -- Rivals' one only
    ''')


def test_a_boon_can_be_skipped():
    """Owner 2026-11-10: like other roguelites, refusing every boon is allowed."""
    lua = runtime()
    lua.execute('''
        tick(true); spawn('EN1'); tick(true, 3)
        assert(#shown == 1 and game_paused)
        local before = #calls
        assert(choose(#window.options) == 'Refuse the infusion'); tick(true)
        assert(not game_paused and #calls == before)  -- nothing applied
        wipe(); tick(true); tick(false, 15)
        calls = {}
        tick(true); spawn('EN2'); tick(true, 3)
        for _, c in ipairs(calls) do assert(not c:find('^PC'), c) end  -- no boon carried into round 2
    ''')


def test_a_taken_infusion_is_never_offered_again():
    """Owner 2026-11-10: once picked, an infusion leaves the run's offers; passed-over ones may return."""
    lua = runtime()
    lua.execute("""
        only('Haste for the party', 'Regen for the party', 'Shell for the party')
        tick(true); spawn('EN1'); tick(true); wipe(); tick(true); tick(false, 15)
        for r = 2, 4 do
            tick(true); spawn('EN'..r); tick(true, 3)
            if r == 2 then choose_label('Haste for the party') end
            if r == 3 then
                for _, o in ipairs(window.options) do assert(o ~= 'Haste for the party', o) end
                choose_label('Regen for the party')
            end
            if r == 4 then
                assert(#window.options == 2)  -- one left, plus Refuse
                for _, o in ipairs(window.options) do assert(o ~= 'Haste for the party' and o ~= 'Regen for the party', o) end
            end
            tick(true); wipe(); tick(true); tick(false, 15)
        end
    """)


def test_special_and_action_infusions():
    """Refocus lasts the run (given again when it lapses); a full limit gauge comes each round start."""
    lua = runtime()
    lua.execute("""
        add_limit_actions()
        only('Refocus: three ATB segments', 'Full ATB at the start of each round', 'Full limit gauge at the start of each round')
        tick(true); spawn('EN1'); tick(true); wipe(); tick(true); tick(false, 15)
        tick(true); spawn('EN2'); tick(true, 3)
        choose_label('Refocus: three ATB segments'); tick(true)
        assert(has('PC0000_Cloud~PCVision') and not has('EN2~PCVision'))
        calls = {}; specials = {}           -- it lapses
        tick(true, 4)
        assert(has('PC0003_Aerith~PCVision'))
        wipe(); tick(true); tick(false, 15)
        tick(true); spawn('EN3'); tick(true, 3)
        choose_label('Full limit gauge at the start of each round'); tick(true)
        assert(has('limit0=1000') and has('limit3=1000'))
        wipe(); tick(true); tick(false, 15)
        calls = {}
        tick(true); spawn('EN4'); tick(true)
        assert(has('limit0=1000') and has('PC0000_Cloud~PCVision'))
    """)


def test_turbulent_spirit_lasts_60_fight_seconds_each_round_and_mana_surge_its_own_40():
    """Owner 2026-11-11: Turbulent Spirit ('seconds': 60) is given again as it lapses
    until 60 fight seconds into the round, then left to lapse; Mana Surge (no
    'seconds') is given once a round only."""
    lua = runtime()
    lua.execute("""
        only('Turbulent Spirit for 60 s each round', 'Free spells for 40 seconds each round', 'Haste for the party')
        tick(true); spawn('EN1'); tick(true, 3)
        choose_label('Turbulent Spirit for 60 s each round'); tick(true)
        assert(has('PC0000_Cloud~ATBRegeneration'))
        wipe(); tick(true); tick(false, 15)
        tick(true); spawn('EN2'); tick(true, 3)
        choose_label('Free spells for 40 seconds each round'); tick(true)
        assert(has('PC0003_Aerith~PCMPinfinity') and has('PC0003_Aerith~ATBRegeneration'))
        calls = {}; specials = {}           -- both lapse 20 fight seconds in
        tick(true, 4)
        assert(has('PC0000_Cloud~ATBRegeneration') and has('PC0003_Aerith~ATBRegeneration'))
        assert(not has('PCMPinfinity'))     -- Mana Surge: once a round
        tick(true, 60)                      -- past 60 fight seconds
        calls = {}; specials = {}
        tick(true, 4)
        assert(not has('ATBRegeneration') and not has('PCMPinfinity'), table.concat(calls, ','))
        wipe(); tick(true); tick(false, 15)
        calls = {}
        tick(true); spawn('EN3'); tick(true, 3)   -- the next round gives both again
        assert(has('PC0000_Cloud~ATBRegeneration') and has('PC0000_Cloud~PCMPinfinity'))
    """)


def test_the_menu_names_the_course():
    """Live 2026-11-10: the round draw put course 3's rules on course 2; the menu's title decides.
    Riot rush is course 4's rule since the owner's reorder, so the stale draw is course 4's."""
    lua = runtime()
    lua.execute("""
        tick(false)
        menu_title = 'Security Officer'
        territory = 'terVR_COL30_' .. wheel.draws()[4][1]   -- a stale draw would say course 4
        tick(true); spawn('EN1'); tick(true, 3)
        local got = table.concat(calls, ',')
        assert(not got:find('BSC_Haste', 1, true), got)    -- no Riot rush (course 4)
        assert(got:find('EN1:', 1, true), got)              -- Rivals (course 2) still hardens it
    """)


def test_reclaim_heals_standing_fighters_when_an_enemy_falls():
    lua = runtime()
    lua.execute("""
        only('Party equips Reclaimant Choker', 'Haste for the party', 'Regen for the party')
        tick(true); spawn('EN1'); tick(true); wipe(); tick(true); tick(false, 15)
        tick(true); spawn('EN2'); spawn('EN3'); tick(true, 3)
        choose_label('Party equips Reclaimant Choker'); tick(true)
        party[1].hp = 42; party[2].hp = 0   -- Aerith is down
        calls = {}; table.remove(foes); tick(true)
        assert(has('PC0000_Cloud%52') and not has('PC0003_Aerith%'), table.concat(calls, ','))
    """)


def test_tier_labels_show_and_the_pick_maps_back():
    """Owner 2026-11-10: the option text shows the tier; commons carry no label."""
    lua = runtime()
    lua.execute('''
        only('Haste for the party', 'Regen for the party', 'Reraise for the party')
        tick(true); spawn('EN1'); tick(true, 3)
        local set = {}
        for _, o in ipairs(window.options) do set[o] = true end
        assert(set['[Rare] Haste for the party'] and set['Regen for the party'] and set['[Epic] Reraise for the party'],
               table.concat(window.options, ' | '))
        for i, o in ipairs(window.options) do if o == '[Epic] Reraise for the party' then choose(i) end end
        tick(true)
        assert(has('PC0000_Cloud:BSC_Reraise:64') and not has('BSC_Haste') and not has('BSC_Regeneration'))
    ''')


def test_every_infusion_has_a_tier_and_the_bosses_come_from_the_course_design():
    lua = runtime()
    lua.execute('''
        local count = {}
        for _, b in ipairs(data.buffs) do
            assert(data.tier_weights[b.tier] and data.after_boss[b.tier], b.id)
            count[b.tier] = (count[b.tier] or 0) + 1
            assert(b.id ~= 'Berserk', 'Berserk is a rank rule, not an infusion')
        end
        assert(count.common > 0 and count.rare > 0 and count.epic > 0)
        assert(data.after_boss.epic > data.tier_weights.epic * 3)
        assert(#data.boss_rounds == #data.courses)
        assert(table.concat(data.boss_rounds[1], ',') == '3,6,9' and table.concat(data.boss_rounds[14], ',') == '3,6,9,10')
    ''')


def test_the_weighted_draw_honours_tiers():
    lua = runtime()
    draws = lua.eval('''function(after_boss, n)
        math.randomseed(7)
        local counts = {common = 0, rare = 0, epic = 0}
        for _ = 1, n do
            local offer = wheel.draw_offer(3, after_boss)
            assert(#offer == 3 and offer[1] ~= offer[2] and offer[2] ~= offer[3] and offer[1] ~= offer[3])
            local t = offer[1].tier
            counts[t] = counts[t] + 1
        end
        return counts
    end''')
    n = 3000
    lua.execute('add_limit_actions()')
    base = dict(draws(False, n))
    assert abs(base['common'] / n - 0.60) < 0.04, base
    assert abs(base['rare'] / n - 0.30) < 0.04, base
    assert abs(base['epic'] / n - 0.10) < 0.03, base
    boss = dict(draws(True, n))
    assert abs(boss['epic'] / n - 0.40) < 0.04, boss
    assert boss['epic'] > 3 * base['epic'], (base, boss)
    # A tier with nothing left gives way: every drawable epic first, then the rest at random.
    lua.execute('''
        data.tier_weights = {common = 0, rare = 0, epic = 1}
        local offer = wheel.draw_offer(12, false)
        local seen, epics, after = {}, 0, false
        for _, b in ipairs(offer) do
            assert(not seen[b.id]); seen[b.id] = true
            if b.tier == 'epic' then assert(not after, b.id); epics = epics + 1 else after = true end
        end
        assert(#offer == 12 and epics >= 4 and after, epics)
    ''')


def test_the_offer_after_a_boss_round_favours_epics():
    """Rounds 3, 6 and 9 are boss rounds: the offers of rounds 4, 7 and 10 use the after-boss weights."""
    lua = runtime()
    lua.execute('''
        add_limit_actions()
        data.tier_weights = {common = 1, rare = 0, epic = 0}   -- forced, to tell the two tables apart
        data.after_boss = {common = 0, rare = 0, epic = 1}
        local tiers = {}
        for r = 1, 5 do
            tick(true); spawn('EN'..r); tick(true, 3)
            assert(#shown == r)
            local got = {}
            for i = 1, #window.options - 1 do got[i] = boon(window.options[i]).tier end
            tiers[r] = table.concat(got, ',')
            if r == 4 then for i = 1, 3 do assert(window.options[i]:find('^%[Epic%] '), window.options[i]) end end
            refuse(); tick(true); wipe(); tick(true); tick(false, 15)
        end
        for _, r in ipairs({1, 2, 3, 5}) do assert(tiers[r] == 'common,common,common', r..': '..tiers[r]) end
        assert(tiers[4] == 'epic,epic,epic', tiers[4])
    ''')


def test_taken_infusions_stay_out_of_weighted_offers():
    lua = runtime()
    lua.execute('''
        add_limit_actions()
        data.tier_weights = {common = 0, rare = 0, epic = 1}
        tick(true); spawn('EN1'); tick(true, 3)
        local first = boon(window.options[1])
        assert(first.tier == 'epic')
        choose(1); tick(true); wipe(); tick(true); tick(false, 15)
        tick(true); spawn('EN2'); tick(true, 3)
        assert(#window.options == 4)
        for i = 1, 3 do
            local b = boon(window.options[i])
            assert(b.id ~= first.id and b.tier == 'epic', window.options[i])  -- the three epics left
        end
    ''')


def test_the_dev_offer_order_bypasses_the_weights():
    lua = runtime()
    lua.execute('''
        package.loaded.devtools = {offer_order = function() return {'Resist', 'Reraise', 'Haste'} end}
        data.tier_weights = {common = 0, rare = 0, epic = 1}
        tick(true); spawn('EN1'); tick(true, 3)
        assert(window.options[1] == 'Resist ailments' and window.options[2] == '[Epic] Reraise for the party'
               and window.options[3] == '[Rare] Haste for the party', table.concat(window.options, ' | '))
    ''')


def test_the_limit_gauge_fills_over_fight_time():
    """limit_over_time (Gotterdammerung's effect): 4% of the gauge every 5 fight seconds for standing fighters, never while paused."""
    lua = runtime()
    lua.execute('''
        add_limit_actions()
        only('Limit gauge fills over time', 'Haste for the party', 'Regen for the party')
        tick(true); spawn('EN1'); tick(true, 3)
        choose_label('Limit gauge fills over time'); tick(true)
        assert(limits[0] == nil)
        tick(true, 4)
        assert(limits[0] == 40 and limits[3] == 40, tostring(limits[0]))
        party[2].hp = 0                          -- Aerith is down: nothing for her
        tick(true, 5)
        assert(limits[0] == 80 and limits[3] == 40)
        party[2].hp = 100
        wipe(); tick(true); tick(false, 15)
        tick(true); spawn('EN2'); tick(true, 3)  -- round 2: the offer pauses the battle
        tick(true, 10)
        assert(game_paused and limits[0] == 80)  -- no fight seconds while paused
        refuse(); tick(true); tick(true, 3)   -- the window now opens 1 s in, so one more fight second
        assert(limits[0] == 120 and limits[3] == 80, tostring(limits[0])..' '..tostring(limits[3]))
        limits[0] = 990; tick(true, 5)
        assert(limits[0] == 1000)                -- never past the gauge
    ''')


def test_accessory_infusions_do_nothing_until_picked():
    lua = runtime()
    lua.execute('''
        only('Haste for the party', 'Regen for the party', 'Shell for the party')
        tick(true); spawn('EN1'); tick(true, 3); choose_label('Haste for the party'); tick(true)
        party[1].spent = 4; mp[0] = 10; tick(true, 10)
        assert(next(limits) == nil)
    ''')


def test_accessory_infusions_are_offered_only_once_the_helper_answers_this_run():
    """No helper, a disabled helper or an answer for another run: no accessory infusion."""
    lua = runtime()
    lua.execute('''
        only('Party equips Genji Gloves', 'Haste for the party', 'Regen for the party')
        tick(true); spawn('EN1'); tick(true, 3)              -- no answer at all
        assert(#window.options == 3 and not offered('Party equips Genji Gloves'), table.concat(window.options, ' | '))
        refuse(); tick(true); wipe(); tick(true); tick(false, 15)
        answer('disabled signature_mismatch MapFind 0x1412eee58')
        tick(true); spawn('EN2'); tick(true, 3)
        assert(not offered('Party equips Genji Gloves'))
        refuse(); tick(true); wipe(); tick(true); tick(false, 15)
        answer('ready', 'an-earlier-run')
        tick(true); spawn('EN3'); tick(true, 3)
        assert(not offered('Party equips Genji Gloves'))
        refuse(); tick(true); wipe(); tick(true); tick(false, 15)
        answer()
        tick(true); spawn('EN4'); tick(true, 3)
        assert(#window.options == 4 and offered('Party equips Genji Gloves'), table.concat(window.options, ' | '))
    ''')


def test_an_accessory_pick_goes_to_the_helper_and_leaves_with_the_course():
    lua = runtime()
    lua.execute(r'''
        tick(false)
        assert(sent():find('^run %S+\nphase idle\n$'), sent())   -- the first tick clears any old request
        local boot = wheel.infusion_run()
        only('Party equips Genji Gloves', 'Party equips White Cape', 'Gain spells: Fire, Fira, Firaga')
        tick(true)                                           -- course start: a new run, in battle
        local run = wheel.infusion_run()
        assert(run ~= boot and sent() == 'run '..run..'\nphase battle\n', sent())
        answer()
        spawn('EN1'); tick(true, 3)
        choose_label('Party equips Genji Gloves'); tick(true)
        assert(sent() == 'run '..run..'\nphase battle\nacc E_ACC_0211\n', sent())
        assert(not has('E_ACC'))                              -- no status call for it
        wipe(); tick(true); tick(false)                       -- between rounds: the helper may rebuild
        assert(sent():find('phase idle', 1, true) and sent_accessories() == 'E_ACC_0211', sent())
        tick(false, 10)
        tick(true); spawn('EN2'); tick(true, 3)               -- round 2
        assert(sent():find('phase battle', 1, true))
        choose_label('Gain spells: Fire, Fira, Firaga'); tick(true)
        assert(sent_accessories() == 'E_ACC_0211,E_ACC_0253', sent())
        local writes = #infusion_writes
        tick(true, 5)
        assert(#infusion_writes == writes)                    -- unchanged requests are not rewritten
        wipe(); tick(true); tick(false, 130)                  -- the course ends
        assert(wheel.infusion_run() ~= run and sent_accessories() == '' and sent():find('phase idle', 1, true), sent())
    ''')


def test_every_accessory_infusion_names_one_row_and_fits_the_window():
    lua = runtime()
    lua.execute('''
        local seen, count = {}, 0
        for _, b in ipairs(data.buffs) do
            if b.accessory then
                count = count + 1
                assert(b.accessory:match('^E_ACC_%d%d%d%d$') and not seen[b.accessory], b.id)
                assert(b.accessory ~= 'E_ACC_0007', 'Fury Ring is never an infusion')
                assert(b.target == 'party' and #b.statuses == 0 and not b.special and not b.action, b.id)
                assert(utf8.len((data.tier_labels[b.tier] or '')..b.label) <= 48, b.label)  -- characters, not bytes
                seen[b.accessory] = true
            end
        end
        assert(count >= 40 and seen.E_ACC_0211 and seen.E_ACC_1002 and seen.E_ACC_0253 and seen.E_ACC_0029, count)
        assert(not seen.E_ACC_0236, 'Assess is not an infusion (owner 2026-11-11)')
    ''')


def test_the_round_request_names_each_course_by_its_own_shipped_list():
    '''The helper reads junon-rounds.req a line at a time: the first word is the
    colosseum row ("@" first: the list the row ships with, by which the helper
    finds it in the loaded table), the rest are territory names; it writes the
    row's other line (the draw) over that list. So each "@" line must be exactly
    the row's shipped EnemyTerritoryID_Array, unique, and as long as the draw.'''
    import json
    spec = json.loads((SCRIPTS.parents[2] / 'data/junon-arena.json').read_text(encoding='utf-8-sig'))
    rows = next(t['rows'] for t in spec['tables'] if t['asset'] == 'DataObject/Resident/Colosseum.uasset')
    shipped = {r['name']: r['set']['EnemyTerritoryID_Array'] for r in rows}
    lua = runtime()
    lua.execute('tick(false)')
    request = lua.eval('table.concat(requests)')
    defaults, wanted = {}, {}
    for line in request.splitlines():
        words = line.split()
        if not words:
            continue
        row = words[0]
        (defaults if row.startswith('@') else wanted)[row.lstrip('@')] = words[1:]
    assert defaults == shipped
    assert set(wanted) == set(shipped)
    assert len({tuple(v) for v in defaults.values()}) == len(defaults) == 14
    for row, names in wanted.items():
        assert len(names) == len(defaults[row]) and all(n.startswith('terVR_COL30_') for n in names)


def test_a_long_gap_between_rounds_logs_a_stall_and_raises_the_switch_until_a_battle():
    lua = runtime()
    lua.execute(r'''
        require('paths').dev = 'telemetry/'          -- a development install
        stalls, switch, removed = {}, false, 0
        local open = io.open
        io.open = function(path, mode)
            if path == 'telemetry/junon-stall.on' then
                switch = true
                return {write = function() end, close = function() end}
            end
            if path == 'telemetry/junon-buffwheel.tsv' then
                return {write = function(_, s) if s:find('\tstall\t', 1, true) then stalls[#stalls+1] = s end end,
                        close = function() end}
            end
            return open(path, mode)
        end
        os.remove = function(path)
            if path == 'telemetry/junon-stall.on' then switch = false; removed = removed + 1 end
        end
        tick(false)
        assert(removed == 1)                          -- a switch left from an earlier session goes
        tick(true); spawn('EN1'); tick(true, 3); refuse(); tick(true)
        wipe(); tick(true); tick(false, 40)            -- an ordinary gap
        assert(#stalls == 0 and not switch)
        tick(false, 10)
        assert(#stalls == 1 and switch and stalls[1]:find('stall\t1\t46', 1, true), stalls[1])
        tick(false, 20)
        assert(#stalls == 1 and switch)               -- once per gap
        tick(true); spawn('EN2'); tick(true, 3)        -- round 2 starts: the switch goes
        assert(not switch)
        refuse(); tick(true); wipe(); tick(true); tick(false, 130)
        assert(#stalls == 2 and not switch)           -- the course ended (idle fallback)
    ''')


SPAWN_STALL_FAKES = r"""
    require('paths').dev = 'telemetry/'          -- a development install
    spawnstalls, switch, removed = {}, false, 0
    local open = io.open
    io.open = function(path, mode)
        if path == 'telemetry/junon-spawnstall.on' then
            switch = true
            return {write = function() end, close = function() end}
        end
        if path == 'telemetry/junon-buffwheel.tsv' then
            return {write = function(_, s) if s:find('\tspawn_stall\t', 1, true) then spawnstalls[#spawnstalls+1] = s end end,
                    close = function() end}
        end
        return open(path, mode)
    end
    os.remove = function(path)
        if path == 'telemetry/junon-spawnstall.on' then switch = false; removed = removed + 1 end
    end
"""


def test_a_battle_without_enemies_logs_a_spawn_stall_once_and_raises_the_switch_until_they_come():
    """Hang 3 (2026-11-10): round 6's battle began and its enemies never came."""
    lua = runtime()
    lua.execute(SPAWN_STALL_FAKES)
    lua.execute(r'''
        tick(false)
        assert(removed == 1)                          -- a switch left from an earlier session goes
        tick(true); spawn('EN1'); tick(true, 3); refuse(); tick(true)
        wipe(); tick(true); tick(false, 15)           -- round 1, then the gap
        tick(true, 21)                                -- round 2's battle: 20 s without an enemy
        assert(#spawnstalls == 0 and not switch)
        tick(true)
        assert(#spawnstalls == 1 and switch and spawnstalls[1]:find('spawn_stall\t2\t21', 1, true), spawnstalls[1])
        tick(true, 10)
        assert(#spawnstalls == 1 and switch)          -- once per battle
        spawn('EN2'); tick(true)                      -- the enemies come after all
        assert(not switch)
        tick(true, 30)
        assert(#spawnstalls == 1)                     -- a running round never counts
    ''')


def test_the_spawn_stall_switch_goes_when_the_battle_or_course_ends():
    lua = runtime()
    lua.execute(SPAWN_STALL_FAKES)
    lua.execute(r'''
        tick(false)
        tick(true, 25)                                -- round 1's battle: no enemy at all
        assert(#spawnstalls == 1 and switch and spawnstalls[1]:find('spawn_stall\t1\t21', 1, true), spawnstalls[1])
        tick(false)                                   -- the player retires: the battle ends
        assert(not switch)
        tick(true, 25)                                -- the next battle stalls again: logged again
        assert(#spawnstalls == 2 and switch)
        tick(false, 130)                              -- the course ends (idle fallback)
        assert(not switch)
    ''')


def test_ordinary_rounds_never_log_a_spawn_stall():
    lua = runtime()
    lua.execute(SPAWN_STALL_FAKES)
    lua.execute(r'''
        tick(false)
        for r = 1, 4 do
            tick(true, 6); spawn('EN'..r); tick(true, 3); refuse(); tick(true, 20)
            wipe(); tick(true); tick(false, 20)
        end
        assert(#spawnstalls == 0 and not switch)
    ''')


def logging_runtime():
    """A runtime whose mod log lines are kept in `lines` (a development install)."""
    lua = runtime()
    lua.execute('''
        require('paths').dev = 'telemetry/'
        lines = {}
        local real = io.open
        io.open = function(path, mode)
            if path:find('junon%-buffwheel%.tsv') then
                return {write = function(_, s) lines[#lines+1] = s end, close = function() end}
            end
            return real(path, mode)
        end
        function logged(text) return table.concat(lines):find(text, 1, true) ~= nil end
        function swaps_of(a)
            local n = 0
            for _, c in ipairs(calls) do if c:find(a.name..'>', 1, true) then n = n + 1 end end
            return n
        end
    ''')
    return lua


def test_enemies_named_after_another_model_are_hardened():
    """Live 2026-11-11, course 14: ten Tonberries (spec EN2017_00_Tonberry_Standard_VR,
    actors EN2017_00_Tonberry_Standard_C_<n>) and a Cactuar (spec
    EN2259_05_Cactuar_JapoEnd2, actor and CharaSpec SU0008_05_Cactuar_JapoEnd2) kept
    their HP: the mod looked for the spec in the actor's name. The CharaSpec name
    decides; without it the model does."""
    lua = logging_runtime()
    lua.execute('''
        tick(false); menu_title = data.courses[14].title
        territory = 'terVR_COL30_'..round_with('EN2017_00_Tonberry_Standard_VR', 14)   -- Tonberries
        tick(true)
        local shown = spawn_shown('EN2017_00_Tonberry_Standard', 'CharaSpec_EN2017_00_Tonberry_Standard_VR', 23670)
        local plain = spawn_shown('EN2017_00_Tonberry_Standard', nil, 23670)
        local cactuar = spawn_shown('SU0008_05_Cactuar_JapoEnd2', 'CharaSpec_SU0008_05_Cactuar_JapoEnd2', 43395)
        local cactuar2 = spawn_shown('SU0008_05_Cactuar_JapoEnd2', nil, 43395)
        tick(true, 3)
        local got = table.concat(calls, ',')
        local jc, hp = data.courses[14].clone, data.courses[14].hp
        assert(jc and hp == 2.5)                            -- the course's hidden HP factor (was Tough hides x scale)
        for _, a in ipairs({shown, plain}) do
            assert(got:find(a.name..'>EN2017_00_Tonberry_Standard_VR_'..jc, 1, true), got)
        end
        for _, a in ipairs({cactuar, cactuar2}) do
            assert(got:find(a.name..'>EN2259_05_Cactuar_JapoEnd2_'..jc, 1, true), got)
        end
        assert(shown.max == math.floor(23670 * hp + 0.5) and cactuar.max == math.floor(43395 * hp + 0.5))
        tick(true, 3)                                       -- checked: they took
        assert(not logged('spec_retry') and not logged('spec_missed') and not logged('spec_unknown'), table.concat(lines))
    ''')


def test_a_model_several_specs_share_needs_the_charaspec_or_the_round():
    """The Gi (EXTRA_03_020) are all EN2244_00_GiSpector_StandardEnd2 actors with
    one spec each: the CharaSpec name tells them apart, and a model alone that fits
    more than one spec of the round is left alone and logged once."""
    lua = logging_runtime()
    lua.execute('''
        tick(false); menu_title = data.courses[14].title
        territory = 'terVR_COL30_'..round_with('EN2244_00_GiSpector_SpearEnd2', 14)
        tick(true)
        local spear = spawn_shown('EN2244_00_GiSpector_StandardEnd2', 'CharaSpec_EN2244_00_GiSpector_SpearEnd2', 12051)
        local wand = spawn_shown('EN2244_00_GiSpector_StandardEnd2', 'CharaSpec_EN2244_00_GiSpector_WandEnd2', 6026)
        local a = spawn_shown('EN2244_00_GiSpector_StandardEnd2', nil, 10043)
        local b = spawn_shown('EN2244_00_GiSpector_StandardEnd2', nil, 10043)
        tick(true, 3)
        local got = table.concat(calls, ',')
        local jc = data.courses[14].clone
        assert(got:find(spear.name..'>EN2244_00_GiSpector_SpearEnd2_'..jc, 1, true), got)
        assert(got:find(wand.name..'>EN2244_00_GiSpector_WandEnd2_'..jc, 1, true), got)
        assert(swaps_of(a) == 0 and swaps_of(b) == 0, got)
        local n = 0
        for _, l in ipairs(lines) do if l:find('spec_unknown\t1\tEN2244_00_GiSpector_StandardEnd2', 1, true) then n = n + 1 end end
        assert(n == 1, table.concat(lines))
    ''')


def test_a_model_the_round_names_once_is_that_spec():
    """EN0008_02_Vice_VariationB is a spec and also the SpikedBat spec's model: in a
    round with only the SpikedBat Bandit, that actor is the SpikedBat."""
    lua = logging_runtime()
    lua.execute('''
        tick(false)
        local course, spiked = nil, nil
        for c = #data.courses, 1, -1 do
            local specs, found = {}, nil
            for _, slot in ipairs(data.courses[c].slots) do
                for _, r in ipairs(slot) do
                    local set = {}
                    for _, s in ipairs(data.round_specs[r]) do set[s] = true end
                    if set.EN0008_02_Vice_VariationB_SpikedBat and not set.EN0008_02_Vice_VariationB then found = r end
                    for s in pairs(set) do specs[s] = true end
                end
            end
            if found and specs.EN0008_02_Vice_VariationB and data.courses[c].clone then course, spiked = c, found; break end
        end
        assert(spiked, 'a course has both Bandits, one round only the SpikedBat')
        menu_title = data.courses[course].title
        territory = 'terVR_COL30_' .. spiked
        tick(true)
        local bandit = spawn_shown('EN0008_02_Vice_VariationB', nil, 6026)
        tick(true, 3)
        assert(has(bandit.name..'>EN0008_02_Vice_VariationB_SpikedBat_'..data.courses[course].clone), table.concat(calls, ','))
    ''')


def test_a_swap_that_does_not_take_is_tried_once_more_and_logged():
    lua = logging_runtime()
    lua.execute('''
        tick(false); menu_title = data.courses[14].title
        territory = 'terVR_COL30_'..round_with('EN2017_00_Tonberry_Standard_VR', 14)
        local jc, hp = data.courses[14].clone, data.courses[14].hp
        tick(true)
        local late = spawn_shown('EN2017_00_Tonberry_Standard', nil, 23670, 1)   -- takes the second time
        local never = spawn_shown('EN2017_00_Tonberry_Standard', nil, 23670, 5)
        tick(true, 3)                                       -- hardened
        assert(swaps_of(late) == 1 and swaps_of(never) == 1)
        tick(true, 2)                                       -- SWAP_CHECK later: neither took
        assert(swaps_of(late) == 2 and swaps_of(never) == 2)
        assert(logged('spec_retry\t1\t'..late.name..'\tEN2017_00_Tonberry_Standard_VR_'..jc..'\t23670>23670'), table.concat(lines))
        tick(true, 2)
        assert(late.max == math.floor(23670 * hp + 0.5) and swaps_of(late) == 2)
        assert(swaps_of(never) == 2 and logged('spec_missed\t1\t'..never.name), table.concat(lines))
        assert(not logged('spec_missed\t1\t'..late.name))
        local n = #calls
        tick(true, 5)                                       -- nothing more
        assert(#calls == n)
    ''')


def test_the_course_is_recognised_from_enemies_named_after_another_model():
    """Without the helper's territory or the menu the enemies decide; a Tonberry
    actor (EN2017_00_Tonberry_Standard) fits only the round of its spec (..._VR)."""
    lua = runtime()
    lua.execute('''
        tick(false)
        local d = wheel.draws()
        for c = 1, #d do d[c][1] = 'COSMA_02_020' end       -- three Cactuars
        d[14][1] = round_with('EN2017_00_Tonberry_Standard_VR', 14)   -- Tonberries
        tick(true)
        spawn_shown('EN2017_00_Tonberry_Standard', nil, 23670)
        tick(true, 3)
        assert(has('>EN2017_00_Tonberry_Standard_VR_'..data.courses[14].clone), table.concat(calls, ','))
    ''')


COMBINED_FAKES = ARMS_RACE_FAKES + r"""
    forced = nil                                  -- junon-combined.on: nil absent, true empty, or a list
    package.loaded.devtools = {forced_rounds = function() return forced end}
    function sent_rounds()                        -- the last draw sent to the helper, course 1's line
        for i = #requests, 1, -1 do
            if requests[i]:find('^COL30_JUNON_01_Free_Col ') then return (requests[i]:gsub('\n$', '')) end
        end
    end
    function draws_sent() return #lines('drawn') end
"""


def test_combined_rounds_are_in_the_pools_with_their_specs():
    """Combined rounds (2026-11-11): every slot that can pair has combined rounds
    after its single ones; each knows its halves, enemy count and union of specs."""
    lua = runtime()
    lua.execute(r'''
        local n = 0
        for id, combo in pairs(data.combined) do
            n = n + 1
            -- The first half is a pooled round (its specs are listed); the second may be
            -- boss adds no course draws alone. The union itself is checked in Python.
            local got = {}
            for _, s in ipairs(data.round_specs[id]) do got[s] = true end
            for _, s in ipairs(data.round_specs[combo.parts[1]]) do assert(got[s], id..' '..s) end
            assert(#data.round_specs[id] > #data.round_specs[combo.parts[1]], id)
            assert(combo.enemies >= 2 and combo.enemies <= 6, id)
        end
        assert(n > 0)                             -- T2 (new rows) by default; T1 would cap at the 17 spares
        assert(#data.combined_test == 3)
        for s, id in ipairs(data.combined_test) do
            local found = false
            for _, r in ipairs(data.courses[1].slots[s]) do found = found or r == id end
            assert(found and data.combined[id], id)
            assert(data.courses[1].slots[s][1] ~= id)  -- singles first: the shipped round stays single
        end
    ''')


def test_the_switch_forces_course_ones_first_rounds_to_combined_rounds():
    lua = runtime()
    lua.execute(COMBINED_FAKES)
    lua.execute(r'''
        forced = true                             -- an empty switch: the build's test rounds
        tick(false)
        local d = wheel.draws()
        for s, id in ipairs(data.combined_test) do assert(d[1][s] == id, s..' '..tostring(d[1][s])) end
        local want = 'COL30_JUNON_01_Free_Col'
        for s = 1, #d[1] do want = want..' terVR_COL30_'..d[1][s] end
        assert(sent_rounds() == want, sent_rounds())
        assert(sent_rounds():find(' terVR_COL30_'..data.combined_test[1]..' terVR_COL30_'..data.combined_test[2]..
               ' terVR_COL30_'..data.combined_test[3]..' ', 1, true))
        assert(#lines('forced') == 1 and lines('forced')[1][2] == table.concat(data.combined_test, ' '))
        for c = 2, #data.courses do assert(d[c][1] ~= d[1][1]) end  -- first rounds still name their course
    ''')


def test_the_switch_names_rounds_and_a_change_between_courses_draws_again():
    lua = runtime()
    lua.execute(COMBINED_FAKES)
    lua.execute(r'''
        tick(false)                               -- no switch: an ordinary draw
        local sent = draws_sent()
        assert(sent == 1)
        tick(false, 3)
        assert(draws_sent() == sent)              -- nothing changed: no new draw
        local id = data.combined_test[3]
        forced = {id, 'NOT_A_ROUND'}              -- switch set between courses: course 1 opens on it
        tick(false)
        assert(draws_sent() == sent + 1 and wheel.draws()[1][1] == id)
        assert(#lines('forced_unknown') == 1 and lines('forced_unknown')[1][3] == 'NOT_A_ROUND')
        tick(false, 2)
        assert(draws_sent() == sent + 1)          -- the same switch: no further draw
        forced = nil                              -- removed: a fresh random draw
        tick(false)
        assert(draws_sent() == sent + 2)
    ''')


def test_a_combined_round_logs_its_halves_and_how_many_enemies_stood():
    lua = runtime()
    lua.execute(COMBINED_FAKES)
    lua.execute(r'''
        forced = true
        tick(false)
        local id = data.combined_test[1]
        local combo = data.combined[id]
        territory = 'terVR_COL30_'..id
        tick(true)
        -- Both groups: the first round's enemies, then the second's a tick later.
        local specs = data.round_specs[combo.parts[1]]
        local first = {}
        for _, s in ipairs(specs) do spawn_spec(s); first[s] = true end
        tick(true)
        for _, s in ipairs(data.round_specs[id]) do if not first[s] then spawn_spec(s) end end
        while #foes < combo.enemies do spawn_spec(specs[1]) end
        tick(true, 3); refuse(); tick(true)
        local c = lines('combined')
        assert(#c == 1 and c[1][2] == '1' and c[1][3] == id, #c)
        assert(c[1][4] == combo.parts[1]..'+'..combo.parts[2] and c[1][5] == 'expected='..combo.enemies)
        assert(lines('course')[1][2] == '1')      -- the territory names course 1
        table.remove(foes, 1); tick(true)         -- one group falls first: the battle goes on
        assert(#lines('round_end') == 0)
        wipe(); tick(true); tick(false)
        local e = lines('round_enemies')
        assert(#e == 1 and e[1][3] == 'max='..combo.enemies and e[1][4] == id and e[1][5] == 'expected='..combo.enemies,
               table.concat(e[1], ' '))
        -- A single round logs its count without an expectation.
        territory = 'terVR_COL30_'..wheel.draws()[1][2]
        tick(false, 15); tick(true); spawn_spec(data.round_specs[wheel.draws()[1][2]][1]); tick(true, 3); refuse()
        wipe(); tick(true); tick(false)
        assert(#lines('round_enemies') == 2)
    ''')


RALLY_FAKES = ARMS_RACE_FAKES + r"""
    -- An enemy falls: 0% HP and out of the game's enemy count.
    function kill(name)
        for i, a in ipairs(foes) do
            if a.name == name then a.hp = 0; table.remove(foes, i); return end
        end
        error('no enemy '..name)
    end
    function count_of(list, id) local n = 0 for _, x in ipairs(list) do if x == id then n = n + 1 end end return n end
    function split(s) local out = {} for x in s:gmatch('[^,]+') do out[#out+1] = x end return out end
"""


def test_rally_is_the_rule_of_courses_three_to_fourteen():
    """Owner 2026-11-11: Rally replaces Tough hides on course 3; like every rank
    rule it holds on every later course."""
    lua = runtime()
    lua.execute('''
        for c = 1, 2 do assert(not data.courses[c].rally, c) end
        for c = 3, 14 do assert(data.courses[c].rally, c) end
    ''')


def test_rally_gives_every_survivor_one_new_boon_per_fall():
    """Whenever an enemy falls, each enemy still standing gains one random enemy
    boon, one it lacks where possible; two falls in one tick give two each; the
    last enemy's fall gives none. One log line per fall."""
    lua = runtime()
    lua.execute(RALLY_FAKES)
    lua.execute(r'''
        data.enemy_boons = {'BSC_Haste', 'BSC_Protes', 'BSC_Shell'}
        tick(false); menu_title = data.courses[3].title
        tick(true); spawn('EN1'); spawn('EN2'); spawn('EN3'); spawn('EN4')
        tick(true, 3); refuse(); tick(true)                -- hardened: one Rivals boon each
        local before = {}
        for i = 2, 4 do before['EN'..i] = given('EN'..i); assert(#before['EN'..i] == 1) end
        calls = {}
        kill('EN1'); tick(true)
        local r = lines('rally')
        assert(#r == 1 and r[1][2] == '1' and r[1][3] == '1' and r[1][5] == 'standing=3', table.concat(r[1] or {}, ' '))
        assert(#split(r[1][4]) == 3)
        for i = 2, 4 do
            local now = given('EN'..i)
            assert(#now == 1 and in_pool(now[1]), 'EN'..i)
            assert(now[1] ~= before['EN'..i][1], 'EN'..i..' got a boon it had')   -- a new one
        end
        assert(#given('EN1') == 0)                         -- the fallen get nothing
        calls = {}
        kill('EN2'); kill('EN3'); tick(true)              -- two at once: two boons for the survivor
        r = lines('rally')
        assert(#r == 2 and r[2][3] == '2' and r[2][5] == 'standing=1', table.concat(r[2], ' '))
        local got = given('EN4')
        assert(#got == 2 and #split(r[2][4]) == 2 and in_pool(got[1]) and in_pool(got[2]))
        calls = {}
        kill('EN4'); tick(true)                            -- the last enemy: nobody to rally
        assert(#lines('rally') == 2 and #calls == 0, table.concat(calls, ','))
    ''')


def test_rally_prefers_boons_the_survivor_lacks():
    lua = runtime()
    lua.execute(RALLY_FAKES)
    lua.execute(r'''
        data.enemy_boons = {'BSC_Haste', 'BSC_Protes', 'BSC_Shell'}
        tick(false); menu_title = data.courses[3].title
        tick(true); spawn('EN1'); spawn('EN2'); spawn('EN3')
        tick(true, 3); refuse(); tick(true)
        local rivals = given('EN3')[1]
        kill('EN1'); tick(true)
        kill('EN2'); tick(true)
        local got = given('EN3')                           -- Rivals, then two rallies
        assert(#got == 3 and got[1] == rivals)
        for _, id in ipairs(data.enemy_boons) do assert(count_of(got, id) == 1, id) end   -- all three, none twice
    ''')


def test_second_wind_is_not_a_fall_and_earlier_courses_do_not_rally():
    lua = runtime()
    lua.execute(RALLY_FAKES)
    lua.execute(r'''
        tick(false); menu_title = data.courses[12].title
        tick(true); spawn('EN1'); spawn('EN2'); spawn('EN3')
        tick(true, 3); refuse(); tick(true)
        foes[1].hp = 15; tick(true)                        -- Second wind: it rises, it has not fallen
        assert(foes[1].hp == 50 and #lines('second_wind') == 1 and #lines('rally') == 0)
        foes[2].hp = 10; tick(true)
        assert(#lines('second_wind') == 2 and #lines('rally') == 0)
        kill('EN3'); tick(true)                            -- a real fall
        local r = lines('rally')
        assert(#r == 1 and r[1][5] == 'standing=2', table.concat(r[1] or {}, ' '))
        refuse(); tick(true); wipe(); tick(true); tick(false, 130)   -- the course ends
        menu_title = data.courses[2].title
        tick(true); spawn('EN4'); spawn('EN5'); tick(true, 3); refuse(); tick(true)
        calls = {}
        kill('EN4'); tick(true)
        assert(#lines('rally') == 1 and #given('EN5') == 0, table.concat(calls, ','))
    ''')


def test_a_wave_is_no_fall_and_a_survivor_not_yet_hardened_gets_its_boon_then():
    """Enemies arriving raise the count (no rally). One that has just arrived when
    another falls is rallied with its hardening, so the game's own set-up cannot
    overwrite the boon."""
    lua = runtime()
    lua.execute(RALLY_FAKES)
    lua.execute(r'''
        data.enemy_boons = {'BSC_Haste', 'BSC_Protes'}
        tick(false); menu_title = data.courses[3].title
        tick(true); spawn('EN1'); spawn('EN2')
        tick(true, 3); refuse(); tick(true)
        spawn('EN3'); spawn('EN4'); tick(true)             -- a wave: no fall
        assert(#lines('rally') == 0)
        calls = {}
        kill('EN1'); tick(true)                            -- EN3 and EN4 are still waiting to be hardened
        local r = lines('rally')
        assert(#r == 1 and r[1][5] == 'standing=3', table.concat(r[1] or {}, ' '))
        local boons = split(r[1][4])
        assert(#boons == 3 and in_pool(boons[1]) and boons[2] == 'owed' and boons[3] == 'owed', r[1][4])
        assert(#given('EN2') == 1 and #given('EN3') == 0 and #given('EN4') == 0, table.concat(calls, ','))
        tick(true)                                         -- hardened: Rivals' boon, then the owed rally
        for _, name in ipairs({'EN3', 'EN4'}) do
            local got = given(name)
            assert(#got == 2 and got[1] ~= got[2], name..' '..table.concat(got, ','))   -- a boon it lacked
        end
        local late = lines('rally_owed')
        assert(#late == 2 and late[1][2] == '1' and late[1][3] == 'EN3' and late[1][4] == given('EN3')[2],
               table.concat(late[1] or {}, ' '))
        local n = #calls
        tick(true, 3)
        assert(#calls == n)                                -- given once
    ''')


# Darkside's HP cost (live 2026-11-11: neither BSC_Dark nor the Darkside materia's
# carrier cost any HP, so buffwheel.lua charges it from the current ability).
DARKSIDE_FAKES = ARMS_RACE_FAKES + r"""
    -- The current ability as the game returns it: an FName-like object ('None' when idle).
    function fname(s) return {ToString = function() return s end} end
    api.GetCurrentAbilityID = function(_, a) return fname(a.ability or 'None') end
    api.GetCharaHP = function(_, a) return a.hpv end
    api.HasStatusChangeID = function(_, a, id) return has(a.name..':'..id..':64') end
    local set = api.SetHPPercent
    api.SetHPPercent = function(self, a, pct)
        set(self, a, pct)
        if a.hpv and a.max then a.hpv = math.floor(a.max * pct / 100) end
    end
    cloud = party[1]
    cloud.max, cloud.hpv = 6000, 6000
    party[2].max, party[2].hpv = 4000, 4000
    function poll(n) for _ = 1, n or 1 do wheel.darkside_poll() end end
    -- Cloud acts: the ability shows for a few polls, then idle.
    function use(id, polls) cloud.ability = id; poll(polls or 3); cloud.ability = nil; poll() end
    -- A round of this course has begun and its offer is refused (the fight runs).
    function darkside_round(c)
        tick(false); menu_title = data.courses[c].title
        tick(true); spawn('EN1'); tick(true, 3); refuse(); tick(true)
    end
    function costs() return lines('darkside_cost') end
    function set_hp()
        local n = 0
        for _, c in ipairs(calls) do if c:find('PC0000_Cloud%', 1, true) == 1 then n = n + 1 end end
        return n
    end
"""


def test_darkside_costs_five_percent_of_max_hp_per_ability_use():
    """One charge per use: an ability held over several polls is one use, a
    repeat after idle (or after another action) is another, idle costs nothing,
    and rows of one ability in a row (Barret's _ATB_1 then _ATB_2) are one use."""
    lua = runtime()
    lua.execute(DARKSIDE_FAKES)
    lua.execute(r'''
        darkside_round(13)
        assert(data.courses[13].ability_cost.percent == 5 and data.courses[13].ability_cost.status == 'BSC_Dark')
        poll(5)                                                   -- idle: nothing
        assert(#costs() == 0 and set_hp() == 0)
        use('PC0000_AtkBurst01', 4)                               -- Braver, held over four polls
        local c = costs()
        assert(#c == 1 and c[1][2] == '1' and c[1][3] == 'PC0000_Cloud' and c[1][4] == 'PC0000_AtkBurst01'
               and c[1][5] == '6000>5700' and c[1][6] == 'pct=95' and c[1][7] == 'read=exact'
               and c[1][8] == 'status=true', table.concat(c[1] or {}, ' '))
        use('PC0000_AtkBurst01')                                  -- the same ability again after idle
        assert(#costs() == 2 and costs()[2][5] == '5700>5400', table.concat(costs()[2], ' '))
        cloud.ability = 'PC0000_AtkBurst01'; poll(2)
        cloud.ability = 'PC0000_NAtk_1'; poll(2)                  -- a basic attack in between...
        cloud.ability = 'PC0000_AtkBurst01'; poll(2)              -- ...so this is another use
        cloud.ability = nil; poll()
        assert(#costs() == 4 and cloud.hpv == 4800, tostring(cloud.hpv))
        cloud.ability = 'PC0001_AtkBurst02_ATB_1'; poll(2)
        cloud.ability = 'PC0001_AtkBurst02_ATB_2'; poll(2)        -- the same ability's next row: one use
        cloud.ability = nil; poll(10)
        assert(#costs() == 5 and cloud.hpv == 4500, tostring(cloud.hpv))
        local probes = lines('darkside_probe')
        assert(#probes == 3, #probes)                             -- Cloud's first idle and busy readings, Aerith's idle one
        assert(probes[1][4] == 'table' and probes[1][5] == 'None', table.concat(probes[1], ' '))
        local seen = {}
        for _, f in ipairs(lines('darkside_seen')) do seen[f[4]] = f[5] end
        assert(seen['PC0000_AtkBurst01'] == 'cost' and seen['PC0000_NAtk_1'] == 'free')
        assert(party[2].hpv == 4000)                              -- Aerith did nothing
    ''')


def test_darkside_never_charges_magic_items_limits_or_other_actions():
    lua = runtime()
    lua.execute(DARKSIDE_FAKES)
    lua.execute(r'''
        darkside_round(14)
        for _, id in ipairs({'M_MAG_001_heal001_01', 'M_MAG_004_atk002_01_SP', 'it_potion', 'IT_hpotion',
                             'PC0000_Limit001', 'PC0001_PC0002_BurstChain01_B', 'PC0001_SAtk_MAX', 'PC0000_NAtk_101',
                             'PC0003_ChainGuard1_UC', 'M_SMN_004_atk001_01', 'M_CMD_002_atk001_01', 'M_CMD_001_atk001_01',
                             'M_CMD_005_heal001_01', 'M_CMD_104_atk001_01', 'M_CMD_107_atk001_01', 'PC0002_AtkBurst10_B'}) do
            assert(not data.darkside_cost[id], id)
            use(id)
        end
        assert(#costs() == 0 and set_hp() == 0 and cloud.hpv == 6000)
        for _, id in ipairs({'PC0002_AtkBurst07', 'PC0001_AtkBurst02_ATB_1', 'PC0005_EleBurst01',
                             'M_CMD_003_atk000_01', 'M_CMD_105_atk001_01', 'M_CMD_102_atk001_01'}) do
            assert(data.darkside_cost[id], id)
        end
        use('M_CMD_105_atk001_01')                                -- Jump: a command materia attack
        assert(#costs() == 1)
    ''')


def test_the_darkside_command_switches_the_cost_off_and_on_until_the_next_round():
    """Owner 2026-11-11: a fighter may switch Darkside off with its command; it
    stays off for the round and is on again at the next round's start."""
    lua = runtime()
    lua.execute(DARKSIDE_FAKES)
    lua.execute(r'''
        darkside_round(13)
        use('M_CMD_106_atk001_01')                                -- off
        local t = lines('darkside_toggle')
        assert(#t == 1 and t[1][2] == '1' and t[1][3] == 'PC0000_Cloud' and t[1][4] == 'off', table.concat(t[1] or {}, ' '))
        use('PC0000_AtkBurst01'); use('PC0000_AtkBurst02')
        assert(#costs() == 0 and cloud.hpv == 6000)
        local free = lines('darkside_free')
        assert(#free == 2 and free[1][4] == 'PC0000_AtkBurst01' and free[1][5] == 'off')
        cloud.ability = 'M_CMD_106_atk001_01'; poll(3)            -- held: one toggle, not three
        cloud.ability = nil; poll()
        assert(#lines('darkside_toggle') == 2 and lines('darkside_toggle')[2][4] == 'on')
        use('PC0000_AtkBurst01')
        assert(#costs() == 1 and cloud.hpv == 5700)
        use('M_CMD_106_atk001_01')                                -- off again at the round's end
        wipe(); tick(true); tick(false, 15)
        tick(true); spawn('EN2'); tick(true, 3); refuse(); tick(true)   -- round 2: on for everyone
        use('PC0000_AtkBurst01')
        assert(#costs() == 2 and costs()[2][2] == '2', table.concat(costs()[2] or {}, ' '))
    ''')


def test_darkside_never_takes_a_fighter_below_one_hp():
    lua = runtime()
    lua.execute(DARKSIDE_FAKES)
    lua.execute(r'''
        darkside_round(13)
        cloud.hpv = 200                                           -- 3% of 6000: the cost would kill
        use('PC0000_AtkBurst01')
        assert(cloud.hpv == 60 and has('PC0000_Cloud%1'), tostring(cloud.hpv))   -- the lowest whole percent
        use('PC0000_AtkBurst01')                                  -- 1%: no whole percent below it but 0
        assert(cloud.hpv == 60 and costs()[2][5] == '60>60' and costs()[2][6] == 'floor', table.concat(costs()[2], ' '))
        cloud.hpv = 1
        use('PC0000_AtkBurst01')
        assert(cloud.hpv == 1 and costs()[3][6] == 'floor')
        for _, c in ipairs(calls) do assert(c ~= 'PC0000_Cloud%0', c) end
        cloud.hpv = 5730                                          -- 95.5%: the nearest whole percent of 5430
        use('PC0000_AtkBurst01')
        assert(cloud.hpv == 5460, tostring(cloud.hpv))            -- 91%
    ''')


def test_courses_before_thirteen_and_paused_windows_cost_nothing():
    """Courses 1-12 have no ability cost and the fast loop never reads; while the
    infusion window pauses the battle, nothing is read either."""
    lua = runtime()
    lua.execute(DARKSIDE_FAKES)
    lua.execute(r'''
        for c = 1, 12 do assert(data.courses[c].ability_cost == nil, c) end
        assert(data.courses[14].ability_cost.percent == 5)
        queued = 0
        ExecuteInGameThread = function(f) queued = queued + 1; f() end
        LoopAsync = function(ms, f) loop_ms, loop = ms, f end
        assert(wheel.start_poll() and loop_ms == 200 and not wheel.start_poll())   -- one loop only
        darkside_round(12)
        cloud.ability = 'PC0000_AtkBurst01'
        loop(); poll(3)
        assert(queued == 0 and #costs() == 0 and set_hp() == 0)
        cloud.ability = nil
        wipe(); tick(true); tick(false, 130)                      -- course 12 ends
        menu_title = data.courses[13].title
        tick(true); spawn('EN1'); tick(true, 2)                   -- the window is open: paused
        assert(window and not window.closed and game_paused)
        cloud.ability = 'PC0000_AtkBurst01'
        loop(); poll(3)
        assert(queued == 0 and #costs() == 0, #costs())
        refuse(); tick(true)                                      -- the fight runs again
        loop()                                                    -- Braver is still under way: one use
        assert(queued == 1 and #costs() == 1, #costs())
        loop(); poll(2)
        assert(#costs() == 1 and queued == 2)
        wipe(); tick(true); tick(false)                           -- the round's battle ends: the loop rests
        loop()
        assert(queued == 2)
    ''')
