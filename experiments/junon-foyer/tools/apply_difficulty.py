"""Course difficulty modifiers (owner design 2026-11-09): each course adds one and
keeps every earlier one, so the last course has them all.

Two halves:
- Data: for every course whose enemies change, a clone of each enemy spec its
  rounds use, named <spec>_JC<NN>: HP times the course's hidden hp_factor (the
  balance ladder, make_round_pools.py; no rank rule names it since owner
  2026-11-11) and the stat rank rules (enemy_spec: Twisted weaknesses turns
  weaknesses into absorption; attack and stagger are supported), cumulative.
- Lua (buffwheel_data.lua via apply_buff_wheel.lua): per course, its slot pools
  (each run draws one round per slot; round_specs gives each round's enemy specs,
  to recognise the course when the helper cannot say), how many random
  boons each enemy gets, enemy statuses, the party's between-round recovery
  (Short rest), Arms race (an enemy boon for every infusion taken), Rally (an
  enemy boon for every survivor whenever an enemy falls), Second wind (each enemy
  restored once when first seen low) and the offer size.
- Rank-rule carriers: a party_status modifier may name a materia and its carrier
  Equipment row ('materia', 'accessory'; apply_buff_wheel.carrier_for), which the
  whole party gets for the course through the native helper, as accessory
  infusions are given (Darkside, 2026-11-11: the status alone has no HP cost).
Live 2026-11-09: UEndBattleAPI.SetOverrideBattleCharaSpec swaps a spec mid-battle
and rebuilds HP from it; an enemy whose own AI swaps specs (Elfadunk's guard) may
replace ours. Enemy actors are named <model>_C_<n>, after their CharaSpec's model,
which is usually but not always the spec's own name (live 2026-11-11: the
Cactuars are SU0008_*, the Colosseum Tonberry EN2017_00_Tonberry_Standard, so
they kept their HP). spec_names gives buffwheel.lua the other names.
"""
import apply_buff_wheel

SPEC = 'DataObject/Resident/BattleCharaSpec.uasset'
WEAK, ABSORB = '1', '5'  # EEndBattleAttributeResistType


def course_rules(design, number):
    """The cumulative modifiers in force on course number (1-based)."""
    rules = {'enemy_boons': 0, 'enemy_status': [], 'hp': 1.0, 'attack': 1.0, 'absorb': False,
             'stagger': 1.0, 'party_recovery': None, 'offer_size': None, 'texts': [],
             'party_start': None, 'party_every': None, 'arms_race': False,
             'party_status': [], 'enemy_start': None, 'second_wind': None,
             'party_accessories': [], 'carriers': [], 'rally': False, 'ability_cost': None}
    for m in design['modifiers']:
        if m['from'] > number:
            continue
        rules['texts'].append(m['text'])
        kind = m['kind']
        if kind == 'enemy_boons':
            rules['enemy_boons'] += m['count']
        elif kind == 'enemy_status':
            rules['enemy_status'].append(m['status'])
        elif kind == 'enemy_spec':
            # Owner 2026-11-11: enemy HP is the course's hidden hp_factor only (it
            # replaced Tough hides' 25% with Rally); a rank rule may not add more.
            if 'hp' in m:
                raise ValueError("enemy_spec: enemy HP is the course's hidden hp_factor, not a rank rule")
            rules['attack'] *= m.get('attack', 1.0)
            rules['stagger'] *= m.get('stagger', 1.0)
            rules['absorb'] = rules['absorb'] or m.get('weakness') == 'absorb'
        elif kind == 'party_recovery':
            # Short rest (owner 2026-11-11): at most this % of max HP and MP back between rounds.
            if not all(isinstance(m.get(k), int) and 0 <= m[k] <= 100 for k in ('hp', 'mp')):
                raise ValueError('party_recovery: hp and mp are whole percentages, 0 to 100')
            rules['party_recovery'] = {'hp': m['hp'], 'mp': m['mp']}
        elif kind == 'offer_size':
            rules['offer_size'] = m['size']
        elif kind == 'party_status_start':
            rules['party_start'] = {'status': m['status'], 'seconds': m['seconds']}
        elif kind == 'party_status_every':
            rules['party_every'] = {'status': m['status'], 'seconds': m['seconds']}
        elif kind == 'party_status':
            rules['party_status'].append(m['status'])
            # Darkside (2026-11-11): the BSC_Dark status only turns Darkside on; its HP
            # cost (5% per ability) and potency (+20% at Lv 5) are effects of the
            # Darkside materia M_COM_106 (EffectType 16, UseAbilityDarkness). With
            # 'materia' and 'accessory' the party also gets that materia at its
            # highest level through a carrier row (apply_buff_wheel.carrier_for).
            if ('materia' in m) != ('accessory' in m):
                raise ValueError('party_status: materia and accessory go together (a carrier row)')
            if 'materia' in m:
                if m['accessory'] != apply_buff_wheel.carrier_for(m['materia']):
                    raise ValueError(f"party_status: the carrier for {m['materia']} is "
                                     f"{apply_buff_wheel.carrier_for(m['materia'])}")
                rules['party_accessories'].append(m['accessory'])
                rules['carriers'].append((m['accessory'], m['materia']))
            # Live 2026-11-11: neither BSC_Dark nor the carrier cost any HP, so
            # 'hp_cost' makes buffwheel.lua charge it: that % of max HP per use of
            # an ability in data/darkside-abilities.json while the status's state
            # is on (tools/extract_darkside_abilities.py).
            if 'hp_cost' in m:
                cost = m['hp_cost']
                if not (isinstance(cost, int) and 1 <= cost <= 50):
                    raise ValueError('party_status: hp_cost is a whole percentage of max HP, 1 to 50')
                if 'materia' not in m:
                    raise ValueError('party_status: hp_cost needs the materia whose command toggles it')
                if rules['ability_cost']:
                    raise ValueError('party_status: only one rule may cost HP per ability')
                rules['ability_cost'] = {'status': m['status'], 'percent': cost}
        elif kind == 'enemy_status_start':
            rules['enemy_start'] = {'status': m['status'], 'seconds': m['seconds']}
        elif kind == 'arms_race':
            # Arms race (owner 2026-11-11, replaced Mirror match): for every infusion the
            # player takes, every enemy gains one random enemy boon for the rest of the course.
            if set(m) - {'from', 'kind', 'text'}:
                raise ValueError('arms_race takes no settings: one enemy boon per infusion taken')
            if not design.get('enemy_boons'):
                raise ValueError('arms_race draws from enemy_boons (the Rivals pool), which is empty')
            rules['arms_race'] = True
        elif kind == 'rally':
            # Rally (owner 2026-11-11, replaced Tough hides on course 3): whenever an
            # enemy falls, every enemy still standing gains one random enemy boon
            # (the Rivals pool) for the rest of the round (buffwheel.lua).
            if set(m) - {'from', 'kind', 'text'}:
                raise ValueError('rally takes no settings: one enemy boon per survivor per fall')
            if not design.get('enemy_boons'):
                raise ValueError('rally draws from enemy_boons (the Rivals pool), which is empty')
            rules['rally'] = True
        elif kind == 'second_wind':
            # Second wind (owner: every enemy rises again once). Live 2026-11-11 an enemy
            # given BSC_Reraise lay dead and the battle never ended, so no status is used:
            # buffwheel.lua restores each enemy once to 'to' % HP the first time it is
            # seen standing below 'below' %.
            if set(m) - {'from', 'kind', 'text', 'below', 'to'}:
                raise ValueError('second_wind takes only below and to (whole HP percentages)')
            below, to = m.get('below'), m.get('to')
            if not (isinstance(below, int) and isinstance(to, int) and 0 < below < to <= 100):
                raise ValueError('second_wind: below and to are whole percentages, 0 < below < to <= 100')
            rules['second_wind'] = {'below': below, 'to': to}
        elif kind == 'encore':
            pass  # the extra round is in the course's own rounds
        else:
            raise ValueError(f'unknown modifier kind {kind}')
    # Balance (owner 2026-11-11): the course's whole hidden HP factor
    # (make_round_pools.py sets it so course totals ramp to 1.3x vanilla's
    # hardest). It is the only HP change: no rank rule names it.
    course = design['courses'][number - 1] if number <= len(design['courses']) else {}
    if 'hp_scale' in course:
        raise ValueError(f'course {number}: hp_scale is now hp_factor, the whole HP factor')
    factor = course.get('hp_factor', 1.0)
    if not 1.0 <= factor <= 3.0:
        raise ValueError(f'course {number}: hp_factor {factor} must be 1 to 3')
    rules['hp'] = round(rules['hp'] * factor, 4)
    rules['spec'] = rules['hp'] != 1.0 or rules['attack'] != 1.0 or rules['absorb'] or rules['stagger'] != 1.0
    return rules


def rule_carriers(design):
    """Every (accessory, materia) carrier a rank rule names, once each, in course order
    (apply_buff_wheel.add_carriers adds their Equipment rows)."""
    out = []
    for number in range(1, len(design['courses']) + 1):
        for pair in course_rules(design, number)['carriers']:
            if pair not in out:
                out.append(pair)
    return out


def clone_name(spec, number):
    return f'{spec}_JC{number:02}'


def signature(rules):
    return (rules['hp'], rules['attack'], rules['absorb'], rules['stagger'])


def clone_courses(design):
    """Course number -> the course whose clones it uses: courses with the same stat
    rules share one set (named after the first of them)."""
    first, out = {}, {}
    for number in range(1, len(design['courses']) + 1):
        rules = course_rules(design, number)
        if rules['spec']:
            out[number] = first.setdefault(signature(rules), number)
    return out


def spec_row(spec, values, number, rules):
    fields = {'HP': str(round(int(values['HP']) * rules['hp'])),
              'PhysicsAttack': str(round(int(values['PhysicsAttack']) * rules['attack'])),
              'MagicAttack': str(round(int(values['MagicAttack']) * rules['attack']))}
    if rules['absorb']:
        fields['AttributeResist_Array'] = [ABSORB if v == WEAK else v for v in values['AttributeResist_Array']]
    if rules['stagger'] != 1.0:
        fields['BreakValueEndurance'] = str(round(int(values['BreakValueEndurance']) * rules['stagger']))
        fields['KeepValue'] = str(round(int(values['KeepValue']) * rules['stagger']))
        fields['BurstTime'] = str(max(1, round(float(values['BurstTime']) / rules['stagger'])))
    return {'name': clone_name(spec, number), 'cloneFrom': spec, 'set': fields}


def apply(spec, design, round_data):
    """Add every course's spec clones to the spec's BattleCharaSpec table."""
    table = next(t for t in spec['tables'] if t['asset'] == SPEC)
    table['rows'] = [r for r in table['rows'] if '_JC' not in r['name']]
    owners = clone_courses(design)
    wanted = {}
    for number, course in enumerate(design['courses'], 1):
        if number in owners:
            wanted.setdefault(owners[number], set()).update(
                s for slot in course['slots'] for r in slot for s in round_data['rounds'][r]['specs'])
    for owner, names in sorted(wanted.items()):
        rules = course_rules(design, owner)
        table['rows'] += [spec_row(s, round_data['specs'][s], owner, rules) for s in sorted(names)]


# Specs left to their actor name. Live 2026-11-11 the Moss-Grown Adamantoise's moss
# (EN2256_00_Adamantaimai_Moss, actor FA0052_12_Dummy_AdamantaimaiMoss) showed the
# body's HP throughout, and the body's own clone already raised both by 1.25.
UNNAMED = {'EN2256_00_Adamantaimai_Moss'}


def spec_names(design, round_data):
    """How enemies of the courses' specs show themselves, where not by the spec's
    own name: (charas, models). charas: CharaSpec ID (GetCharaSpecName without
    'CharaSpec_') -> spec, one each; models: actor model -> the specs it may be."""
    used = sorted({s for c in design['courses'] for slot in c['slots'] for r in slot
                   for s in round_data['rounds'][r]['specs']} - UNNAMED)
    charas, models = {}, {}
    for s in used:
        info = round_data['specs'][s]
        chara = info.get('chara', s)
        if chara in charas or (chara != s and chara in used):
            raise ValueError(f'two course specs show the CharaSpec {chara}')
        charas[chara] = s
        if 'model' in info:
            models.setdefault(info['model'], []).append(s)
    return {k: v for k, v in charas.items() if k != v}, models


def lua_courses(design, round_data, shipped=None):
    """Lua source for the per-course table in buffwheel_data.lua. shipped: each
    course's round list as the table ships it (apply_course_design.shipped_rounds);
    the Lua names it to the native helper, which finds the list by it."""
    import json
    s = json.dumps
    lines = ['  courses = {']

    def recovery(rule):
        return f"{{hp = {rule['hp']}, mp = {rule['mp']}}}" if rule else 'nil'
    for number, course in enumerate(design['courses'], 1):
        rules = course_rules(design, number)
        slots = ', '.join('{' + ', '.join(s(r) for r in slot) + '}' for slot in course['slots'])
        status = ', '.join(s(x) for x in rules['enemy_status'])
        lines.append(f"    {{title = {s(course['title'])}, spec = {str(rules['spec']).lower()}, "
                     f"enemy_boons = {rules['enemy_boons']}, enemy_status = {{{status}}}, "
                     f"party_recovery = {recovery(rules['party_recovery'])}, offer_size = {rules['offer_size'] or 'nil'}, hp = {rules['hp']},")
        clone = clone_courses(design).get(number)
        def timed(rule):
            return f"{{status = {s(rule['status'])}, seconds = {rule['seconds']}}}" if rule else 'nil'
        wind = rules['second_wind']
        wind = f"{{below = {wind['below']}, to = {wind['to']}}}" if wind else 'nil'
        lines.append(f"      party_start = {timed(rules['party_start'])}, party_every = {timed(rules['party_every'])}, "
                     f"arms_race = {str(rules['arms_race']).lower()}, rally = {str(rules['rally']).lower()}, enemy_start = {timed(rules['enemy_start'])}, "
                     f"party_status = {{{', '.join(s(x) for x in rules['party_status'])}}}, second_wind = {wind},")
        cost = rules['ability_cost']
        cost = f"{{status = {s(cost['status'])}, percent = {cost['percent']}}}" if cost else 'nil'
        lines.append(f"      party_accessories = {{{', '.join(s(x) for x in rules['party_accessories'])}}}, ability_cost = {cost},")
        ships = shipped[number - 1] if shipped else [slot[0] for slot in course['slots']]
        lines.append(f"      shipped = {{{', '.join(s(r) for r in ships)}}},")
        lines.append(f"      row = {s(f'COL30_JUNON_{number:02}_Free_Col')}, clone = {s(f'JC{clone:02}') if clone else 'nil'}, slots = {{{slots}}}}},")
    lines.append('  },')
    used = sorted({r for c in design['courses'] for slot in c['slots'] for r in slot})
    lines.append('  round_specs = {')
    for r in used:
        lines.append(f"    [{s(r)}] = {{{', '.join(s(x) for x in round_data['rounds'][r]['specs'])}}},")
    lines.append('  },')
    charas, models = spec_names(design, round_data)
    lines.append('  spec_charas = {')
    for k in sorted(charas):
        lines.append(f"    [{s(k)}] = {s(charas[k])},")
    lines.append('  },')
    lines.append('  spec_models = {')
    for k in sorted(models):
        lines.append(f"    [{s(k)}] = {{{', '.join(s(x) for x in models[k])}}},")
    lines.append('  },')
    lines.append('  enemy_boons = {' + ', '.join(s(x) for x in design['enemy_boons']) + '},')
    return lines
