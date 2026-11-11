"""data/darkside-abilities.json: the party abilities that cost HP under the Darkside
rank rule (courses 13-14), from the vanilla BattleAbility table.

Live 2026-11-11 (owner, and a frozen-enemy test with Yuffie): the rule's BSC_Dark
status and the Darkside materia's carrier row (E_ACC_7106) give no HP cost, so
buffwheel.lua charges it: it watches each fighter's current ability
(UEndBattleAPI.GetCurrentAbilityID) and takes 5% of max HP for every use of an
ability in this set while that fighter's Darkside is on. The vanilla text: "When
active, increases the potency of abilities, but causes you to suffer damage when
they are used" (magic is not affected).

Rules (BattleAbility columns; the IDs are what GetCurrentAbilityID returns, e.g.
PC0001_AtkBurst02_ATB_1, PC0002_AtkBurst07, live 2026-11-11):
- CommandType: 0 basic attacks, unique abilities (PC0001_SAtk_MAX is Barret's
  Overcharge) and synergy skills (Chain*); 1 the Abilities command; 2 magic;
  3 limit breaks; 4 items; 5 synergy abilities. Only CommandType 1 can cost.
- Weapon and folio abilities: PC<id>_AtkBurst<nn>, _EleBurst<nn> (folio elemental
  abilities), _MAtkBurst<nn>, with any suffix (Barret's _ATB_1.._3 by the ATB
  spent, Yuffie's _UsedATB_n, Red XIII's _Revenge, Cait Sith's Moogle forms).
- Command materia abilities: M_CMD_003 (Enemy Skill), M_CMD_101 (Morph),
  M_CMD_102 (Spare Change) and M_CMD_105 (Jump): attacks the potency applies to.
  Left out as utility, so no HP for them: M_CMD_001 (Steal, and its Mug rows,
  which no materia names), M_CMD_002 (Assess), M_CMD_005/006 (Chakra, Prayer:
  heals; charging HP for a heal works against it), M_CMD_007 (ATB Boost),
  M_CMD_104 (Limit Siphon) and M_CMD_107 (Gambler: casts a random ability or spell).
  Summons (M_SMN_*, also CommandType 1) are not abilities.
- Only rows that spend ATB (ATB > 0). A row with ATB 0 is a free follow-up of an
  ability already paid for (Tifa's PC0002_AtkBurst10_B/_C, Cait Sith's _1 and
  MoogleSync rows, Aerith's MAtkBurst casts inside her ward, Red XIII's Sentinel
  Stance counter), so it never costs a second time.
- Darkside's own command (M_CMD_106_*) is the toggle, never a cost.
Each cost ID maps to its family (the ability without its variant suffix):
consecutive IDs of one family are one use (an ability that moves through its
rows, as Cait Sith's _0 then _1 or Tifa's _A then _B).

Input: the DataTableIndex wide CSV export (one column per array element), e.g.
    python tools/extract_darkside_abilities.py <Resident CSV folder>
Only ability names and the rules are kept, no game assets.
"""
import csv
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'data/darkside-abilities.json'

ABILITIES, MAGIC, LIMIT, ITEM, SYNERGY = '1', '2', '3', '4', '5'  # BattleAbility CommandType
WEAPON = re.compile(r'^(PC(?:\d{4}|Toad)_(?:Atk|Ele|MAtk)Burst\d+)')
COMMAND = re.compile(r'^(M_CMD_(\d{3})_[a-z]+\d+)')
COST_COMMANDS = {'003': 'Enemy Skill', '101': 'Morph', '102': 'Spare Change', '105': 'Jump'}
UTILITY_COMMANDS = {'001': 'Steal (and Mug)', '002': 'Assess', '005': 'Chakra', '006': 'Prayer',
                    '007': 'ATB Boost', '104': 'Limit Siphon', '107': 'Gambler'}
TOGGLE = '106'  # Darkside
RULES = [
    'CommandType 1 (the Abilities command) only: 0 basic/unique/synergy skills, 2 magic, 3 limits, 4 items, 5 synergy abilities never cost',
    'weapon and folio abilities: PC<id>_AtkBurst/EleBurst/MAtkBurst<nn> and their variant rows',
    'command materia attacks: ' + ', '.join(f'M_CMD_{k} {v}' for k, v in COST_COMMANDS.items()),
    'utility commands left out: ' + ', '.join(f'M_CMD_{k} {v}' for k, v in UTILITY_COMMANDS.items()) + '; summons M_SMN_*',
    'ATB > 0 only: ATB-free rows are follow-ups of an ability already paid for',
    'M_CMD_106 (Darkside) toggles the state and never costs',
    'consecutive IDs of one family (the ability without its variant suffix) are one use',
]


def load(path):
    """name -> {CommandType, ATB} from the wide CSV (the scalar columns follow
    'Explanation'; 'Name' appears twice, the row name is the second column)."""
    with open(path, newline='', encoding='utf-8-sig') as f:
        reader = csv.reader(f)
        header = next(reader)
        start = header.index('Explanation')
        col = {h: i for i, h in enumerate(header) if i >= start}
        out = {}
        for r in reader:
            if len(r) > col['ATB']:
                out[r[1]] = {'CommandType': r[col['CommandType']], 'ATB': r[col['ATB']]}
    return out


def classify(rows):
    """(cost: {id: family}, toggle: [ids], excluded: {reason: count or ids})."""
    cost, toggle = {}, []
    excluded = {'magic': 0, 'limit': 0, 'item': 0, 'synergy': 0, 'summon': 0,
                'atb_free': [], 'utility': []}
    by_type = {MAGIC: 'magic', LIMIT: 'limit', ITEM: 'item', SYNERGY: 'synergy'}
    for name in sorted(rows):
        row = rows[name]
        kind = row['CommandType']
        party = WEAPON.match(name) or name.startswith(('M_CMD_', 'M_MAG_', 'M_SMN_', 'PC', 'IT_', 'it_'))
        if kind in by_type:
            if party:
                excluded[by_type[kind]] += 1
            continue
        if kind != ABILITIES:
            continue
        weapon, command = WEAPON.match(name), COMMAND.match(name)
        if name.startswith('M_SMN_'):
            excluded['summon'] += 1
        elif command and command.group(2) == TOGGLE:
            toggle.append(name)
        elif not (weapon or (command and command.group(2) in COST_COMMANDS)):
            if command:
                excluded['utility'].append(name)
        elif int(row['ATB'] or 0) <= 0:
            excluded['atb_free'].append(name)
        else:
            cost[name] = (weapon or command).group(1)
    return cost, toggle, excluded


def snapshot(folder):
    path = Path(folder) / 'BattleAbility.csv'
    rows = load(path)
    cost, toggle, excluded = classify(rows)
    return {'source': 'DataTableIndex Resident BattleAbility.csv',
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'rows': len(rows), 'rules': RULES, 'toggle': toggle, 'cost': cost, 'excluded': excluded}


def lua_lines(snap):
    """The two tables buffwheel.lua reads: darkside_cost (id -> family) and darkside_toggle."""
    s = json.dumps
    lines = ['  darkside_toggle = {' + ', '.join(f'[{s(x)}] = true' for x in snap['toggle']) + '},',
             '  darkside_cost = {']
    for name in sorted(snap['cost']):
        lines.append(f"    [{s(name)}] = {s(snap['cost'][name])},")
    lines.append('  },')
    return lines


def main():
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    snap = snapshot(sys.argv[1])
    OUT.write_text(json.dumps(snap, indent=1) + '\n', encoding='utf-8', newline='\n')
    print(f"{len(snap['cost'])} cost IDs, {len(set(snap['cost'].values()))} families, toggle {snap['toggle']}")


if __name__ == '__main__':
    main()
