"""data/round-data.json: what the difficulty code needs to know about each round.

For every simulator round in the lore pool (and any a course names): its level,
enemy count and enemy specs (EnemyTerritory ->
mob template -> BattleCharaSpec) and their numbers; for each of those specs the
values the course modifiers scale (HP, attack, element resistances, stagger)
and how an enemy of that spec shows itself in game, where that is not the
spec's own name: 'chara', its CharaSpec row (UEndBattleAPI.GetCharaSpecName
reports "CharaSpec_<chara>"), and 'model', the CharaSpec's ContentsModel, which
names the actor (<model>_C_<n>). Live 2026-11-11 the Cactuars (chara and model
SU0008_*) and the Colosseum Tonberry (model EN2017_00_Tonberry_Standard) were
never hardened: buffwheel.lua knew enemies only by their actor names.

Inputs are DataBuilder exports ("export <table>.uasset <out>") of the vanilla
EnemyTerritory, EnemyTerritoryMob, BattleCharaSpec and CharaSpec tables:
    python tools/extract_round_data.py <EnemyTerritory.csv> <EnemyTerritoryMob.csv> <BattleCharaSpec.csv> <CharaSpec.csv>
To add only the chara and model names to the current file (the Resident tables
in either layout: DataBuilder's Name,Property,Value or one row per name):
    python tools/extract_round_data.py --identities <BattleCharaSpec.csv> <CharaSpec.csv>
Only names and numbers are kept, no game assets.
"""
import csv
import json
import sys
from collections import OrderedDict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'data/round-data.json'
FIELDS = ('HP', 'PhysicsAttack', 'MagicAttack', 'AttributeResist_Array', 'BreakValueEndurance', 'BurstTime', 'KeepValue')


def load(path):
    """Rows by name: DataBuilder's long layout (Name, Property, Value) or a wide
    one (a row per name, a column per property; array columns are not kept)."""
    rows = OrderedDict()
    with open(path, encoding='utf-8') as f:
        reader = csv.DictReader(f)
        long = 'Property' in reader.fieldnames
        for r in reader:
            if long:
                rows.setdefault(r['Name'], {})[r['Property']] = r['Value']
            else:
                rows[r['Name']] = r
    return rows


def identity(name, spec, chara_spec):
    """How an enemy of spec `name` shows itself, where that differs from the name."""
    chara = spec[name].get('CharaSpecID') or name
    model = chara_spec.get(chara, {}).get('ContentsModel') or chara
    out = {}
    if chara != name:
        out['chara'] = chara
    if model != name:
        out['model'] = model
    return out


def split(value):
    return [x for x in value.split('|') if x != ''] if value else []


def main(territory_csv, mob_csv, spec_csv, chara_csv):
    design = json.loads((ROOT / 'data/course-design.json').read_text(encoding='utf-8'))
    territory, mob, spec, chara = load(territory_csv), load(mob_csv), load(spec_csv), load(chara_csv)
    pool = json.loads((ROOT / 'data/enemy-pool.json').read_text(encoding='utf-8'))['pool_rows']
    wanted = {t[len('terVR_COL30_'):] for t in pool if t.startswith('terVR_COL30_')}
    for course in design['courses']:
        for slot in course.get('slots', []):
            wanted.update(slot)
        wanted.update(course.get('rounds', []))
    rounds, specs = {}, {}
    for r in sorted(wanted):
        row = territory[f'terVR_COL30_{r}']
        templates = split(row['MobTemplateList_Array'])
        counts = [int(x) for x in split(row['MinPopList_Array'])]
        levels = [int(x) for x in split(row['MobLevelList_Array'])]
        names = [mob[t]['BattleCharaSpecID'] for t in templates]
        # level 0: the enemies fight at the party's level (RecommendedLevel -2)
        rounds[r] = {'specs': sorted(set(names)), 'enemies': sum(counts), 'level': max(levels or [0])}
        for name in names:
            specs[name] = {k: (split(spec[name][k]) if k.endswith('_Array') else spec[name][k]) for k in FIELDS}
            specs[name].update(identity(name, spec, chara))
    out = {'_about': __doc__.strip().splitlines()[0], 'rounds': dict(sorted(rounds.items())),
           'specs': dict(sorted(specs.items()))}
    OUT.write_text(json.dumps(out, indent=1) + '\n', encoding='utf-8')
    print(len(rounds), 'rounds,', len(specs), 'specs ->', OUT)


def add_identities(spec_csv, chara_csv):
    """Only the chara and model names, into the current data/round-data.json."""
    spec, chara = load(spec_csv), load(chara_csv)
    out = json.loads(OUT.read_text(encoding='utf-8'))
    for name, values in out['specs'].items():
        for k in ('chara', 'model'):
            values.pop(k, None)
        values.update(identity(name, spec, chara))
    OUT.write_text(json.dumps(out, indent=1) + '\n', encoding='utf-8')
    print(sum(1 for v in out['specs'].values() if 'chara' in v or 'model' in v), 'specs show other names ->', OUT)


if __name__ == '__main__':
    if sys.argv[1] == '--identities':
        add_identities(*sys.argv[2:4])
    else:
        main(*sys.argv[1:5])
