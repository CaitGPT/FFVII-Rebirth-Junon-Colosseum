"""Scripts/buffwheel_data.lua from data/buffs.json: the boons buffwheel.lua offers.

History (2026-11-09): a first version added story flags, triggers, states and
Moogle-style dialogue rows so the mod's flow object could show a dialogue wheel
between rounds. Live, a native course has no field moment between rounds (each
round is its own battle, with only a loading screen between), and Lua's
SendStateTrigger never reached the flow object. The game's own message window
(UEndMenuAPI.ShowMessageWindow) opens from Lua inside a battle instead, so the
boons need no table rows at all.

Tiers (owner 2026-11-10): every infusion is common, rare or epic; offers draw a
tier by weight first (tier_weights, or after_boss_weights in the round after a
boss round), and the option text carries the tier's label.

Accessory infusions (owner 2026-11-10): 'accessory' names an Equipment row
(E_ACC_xxxx); the native helper gives the party that accessory's skill effects
and immunities (buffwheel.lua writes junon-infusions.req). Labels must stay
short: the message window is narrow.

Labels (owner 2026-11-11) may use Latin-1 letters, for "Party equips
Götterdämmerung" as the game's own UI spells it. The emitter writes them as raw
UTF-8 in buffwheel_data.lua (valid in a Lua source), and UE4SS passes Lua strings
to the game as UTF-8. Check the ö and ä visually in game: the message window's
font has to show them.
"""
import json
import re

LABEL_MAX = 48  # characters (not bytes), tier prefix included (the window is narrow)
# Materia carriers (owner 2026-11-11: an infusion for every stat-up materia). The
# game's materia earrings are Equipment rows with one skill of type 100 naming a
# materia (SkillEffectName_Array), which the game applies at that materia's
# highest level ("Allows use of the highest level of HP Up materia, increasing
# maximum HP by 30%"); the row carries no value of its own. Vanilla has them for
# HP Up (E_ACC_0238), MP Up (0248) and Luck Up (0249) but not for Strength,
# Magic, Vitality, Spirit or Speed Up. An infusion with 'materia' next to its
# 'accessory' names a carrier row this mod adds: a clone of HP Up Materia
# Earrings with only the materia changed, in our own range E_ACC_8xxx (vanilla
# rows go up to 0274, 1002, 9201 and 9202). The rows have no Item row, so they
# can never be owned, sold or shown; the native helper reads them by name like
# any accessory. The clone keeps HP Up's menu text label, which nothing shows.
# A carrier's number follows its materia, so ids never clash: E_ACC_8nnn for an
# independent materia M_IND_nnn, E_ACC_7nnn for a command materia M_COM_nnn
# (2026-11-11: the Darkside rank rule's carrier, E_ACC_7106 for M_COM_106, which
# Strength Up's E_ACC_8106 would otherwise collide with). The game's own command
# materia earrings (Chakra E_ACC_0246 = M_COM_004, Prayer E_ACC_0247 = M_COM_005)
# use the same skill type 100 as HP Up's, so one template serves both kinds.
# Rank rules may name carriers too (course-design.json: a modifier with 'materia'
# and 'accessory'; apply_difficulty.rule_carriers); their rows are added here.
EQUIPMENT = 'DataObject/Resident/Equipment.uasset'
CARRIER_TEMPLATE = 'E_ACC_0238'
CARRIER_ID = r'E_ACC_[78]\d{3}'
MATERIA_ID = r'M_[A-Z]{3}_\d{3}'
CARRIER_PREFIX = {'IND': '8', 'COM': '7'}


def carrier_for(materia):
    """Our carrier row's id for a materia (M_IND_106 -> E_ACC_8106, M_COM_106 -> E_ACC_7106)."""
    m = re.fullmatch(r'M_([A-Z]{3})_(\d{3})', materia or '')
    if not m or m.group(1) not in CARRIER_PREFIX:
        raise ValueError(f'{materia}: carriers exist for independent (M_IND_) and command (M_COM_) materia only')
    return f'E_ACC_{CARRIER_PREFIX[m.group(1)]}{m.group(2)}'


ACTIONS = ('atb_full', 'limit_full', 'limit_level', 'heal_on_kill',
           # Accessory effects buffwheel.lua approximates while a round runs.
           'limit_over_time')


def validate(design, boss_rounds=()):
    ids = [b['id'] for b in design['buffs']]
    if len(set(ids)) != len(ids):
        raise ValueError('duplicate boon id')
    if not 1 <= design['per_offer'] <= min(4, len(ids)):
        raise ValueError('per_offer must be 1 to 4 and no more than the boons')
    tiers = list(design['tier_weights'])
    for table in ('tier_weights', 'after_boss_weights'):
        weights = design[table]
        if list(weights) != tiers:
            raise ValueError(f'{table} must name the same tiers, in the same order, as tier_weights')
        if any(not isinstance(w, int) or w < 0 for w in weights.values()) or sum(weights.values()) <= 0:
            raise ValueError(f'{table}: whole, non-negative weights with a positive total')
    if set(design['tier_labels']) != set(tiers):
        raise ValueError('tier_labels must name every tier')
    for b in design['buffs']:
        if b['target'] not in ('party', 'enemies') or not b['label']:
            raise ValueError(f"{b['id']}: target party|enemies and a label")
        if b.get('tier') not in tiers:
            raise ValueError(f"{b['id']}: tier must be one of {tiers}")
        # Owner 2026-11-10: one effect per infusion, never a bundle like Protect + Shell.
        effects = len(b.get('statuses', [])) + ('special' in b) + ('action' in b) + ('accessory' in b)
        if effects != 1:
            raise ValueError(f"{b['id']}: exactly one effect (one status, a special, an action or an accessory)")
        if 'accessory' in b and not re.fullmatch(r'E_ACC_\d{4}', b['accessory']):
            raise ValueError(f"{b['id']}: accessory is an Equipment row E_ACC_ and four digits")
        ours = 'accessory' in b and re.fullmatch(CARRIER_ID, b['accessory'])
        if bool(ours) != ('materia' in b):
            raise ValueError(f"{b['id']}: 'materia' goes with an accessory of our own carrier range {CARRIER_ID}, and only there")
        if 'materia' in b and not re.fullmatch(MATERIA_ID, b['materia']):
            raise ValueError(f"{b['id']}: materia is a Materia row such as M_IND_106")
        if 'materia' in b and b['accessory'] != carrier_for(b['materia']):
            raise ValueError(f"{b['id']}: the carrier for {b['materia']} is {carrier_for(b['materia'])}")
        label = design['tier_labels'][b['tier']] + b['label']
        # Latin-1 only (the game's font); printable, so json.dumps never writes a \u escape Lua can't read.
        if not all(ord(c) < 256 and c.isprintable() for c in label):
            raise ValueError(f"{b['id']}: label in printable Latin-1 (the game's font)")
        if 'accessory' in b and len(label) > LABEL_MAX:
            raise ValueError(f"{b['id']}: accessory label of at most {LABEL_MAX} characters with its tier")
        if b.get('action') not in (None, *ACTIONS):
            raise ValueError(f"{b['id']}: unknown action")
        if b.get('time') not in (None, 'short'):
            raise ValueError(f"{b['id']}: time is short or absent")
        # A once-a-round special given again as it lapses until this many fight
        # seconds into the round (owner 2026-11-11: Turbulent Spirit for 60 s).
        if 'seconds' in b and not (b.get('special') and b.get('each_round')
                                   and isinstance(b['seconds'], int) and b['seconds'] > 0):
            raise ValueError(f"{b['id']}: seconds is a positive whole number, only on an each_round special")
        if ('special' in b or 'action' in b or 'accessory' in b) and b['target'] != 'party':
            raise ValueError(f"{b['id']}: specials, actions and accessories are for the party")
    accessories = [b['accessory'] for b in design['buffs'] if 'accessory' in b]
    if len(set(accessories)) != len(accessories):
        raise ValueError('an accessory is offered twice')
    materia = [b['materia'] for b in design['buffs'] if 'materia' in b]
    if len(set(materia)) != len(materia):
        raise ValueError('a materia has two carriers')
    for rounds in boss_rounds:
        if any(not isinstance(r, int) or r < 1 for r in rounds):
            raise ValueError('boss rounds are round numbers from 1')


def carrier_rows(design, rule_carriers=()):
    """Our Equipment rows: one per infusion that names a 'materia' (see CARRIER_ID),
    then one per rank-rule carrier ((accessory, materia) pairs, apply_difficulty.rule_carriers)."""
    validate(design)
    pairs = [(b['accessory'], b['materia']) for b in design['buffs'] if 'materia' in b]
    for accessory, materia in rule_carriers:
        if accessory != carrier_for(materia):
            raise ValueError(f'rank rule carrier {accessory}: the carrier for {materia} is {carrier_for(materia)}')
        if (accessory, materia) not in pairs:
            pairs.append((accessory, materia))
    if len({a for a, _ in pairs}) != len(pairs):
        raise ValueError('a carrier row is named twice with different materia')
    return [{'name': accessory, 'cloneFrom': CARRIER_TEMPLATE, 'set': {'SkillEffectName_Array': [materia]}}
            for accessory, materia in pairs]


def add_carriers(spec, design, rule_carriers=()):
    """Replace the spec's Equipment table with the carrier rows (none: no table)."""
    rows = carrier_rows(design, rule_carriers)
    spec['tables'] = [t for t in spec['tables'] if t['asset'] != EQUIPMENT]
    if rows:
        spec['tables'].append({'asset': EQUIPMENT, 'rows': rows})
    return spec


def lua(design, course_lines=(), boss_rounds=()):
    """The Lua table buffwheel.lua requires; course_lines adds the per-course
    difficulty table (apply_difficulty.lua_courses) and boss_rounds each
    course's boss rounds (course-design.json 'bosses', in course order)."""
    validate(design, boss_rounds)
    # A JSON string of printable Latin-1, written as raw UTF-8, is a valid Lua string.
    def s(x): return json.dumps(x, ensure_ascii=False)

    def weights(table):
        return '{' + ', '.join(f'[{s(t)}] = {w}' for t, w in design[table].items()) + '}'
    lines = ['-- Generated from data/buffs.json by tools/apply_course_design.py; do not edit.',
             'return {', f"  per_offer = {design['per_offer']},", f"  prompt = {s(design['prompt'])},",
             f"  tiers = {{{', '.join(s(t) for t in design['tier_weights'])}}},",
             f"  tier_weights = {weights('tier_weights')},",
             f"  after_boss = {weights('after_boss_weights')},",
             '  tier_labels = {' + ', '.join(f'[{s(t)}] = {s(x)}' for t, x in design['tier_labels'].items()) + '},',
             '  boss_rounds = {' + ', '.join('{' + ', '.join(str(r) for r in rounds) + '}' for rounds in boss_rounds) + '},',
             '  buffs = {']
    for b in design['buffs']:
        statuses = ', '.join(s(x) for x in b.get('statuses', []))
        extra = ''
        if b.get('time'): extra += f", time = {s(b['time'])}"
        if b.get('special'): extra += f", special = {s(b['special'])}"
        if b.get('each_round'): extra += ', each_round = true'
        if b.get('seconds'): extra += f", seconds = {b['seconds']}"
        if b.get('action'): extra += f", action = {s(b['action'])}"
        if b.get('accessory'): extra += f", accessory = {s(b['accessory'])}"
        lines.append(f"    {{id = {s(b['id'])}, tier = {s(b['tier'])}, label = {s(b['label'])}, target = {s(b['target'])}, statuses = {{{statuses}}}{extra}}},")
    lines += ['  },', *course_lines, '}', '']
    return '\n'.join(lines)
