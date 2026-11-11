"""data/territory-rows.json: the vanilla EnemyTerritory and EnemyTerritoryLevel rows
that combined rounds are built from (tools/make_combined_rounds.py).

For every round a course pool can draw (data/course-design.json slots), every
endgame round the pool generator may choose from (make_round_pools.endgame, in
data/round-data.json), and the spare simulator territories no vanilla course
uses (candidates for repurposing): the EnemyTerritory and EnemyTerritoryLevel
rows (fields the game leaves empty are left out), the size class
(PhysiqueSize), movement type and base HP of each enemy spec, the per-level HP
factor (EnemyParameter Enemy_<level>.HPMax / 100: an enemy's HP is its spec HP
times the factor at its level, verified live 2026-11-11), and every UniqueIndex
the EnemyTerritory table already uses (a new row needs its own). Only names and
numbers are kept, no game assets.

Input: the DataTableIndex wide CSV exports of the vanilla Resident tables (one
column per array element, the array's own column empty; "0    | " is an empty
array), e.g. <DataTableIndex>/Input/Resident:
    python tools/extract_territory_rows.py <Resident CSV folder>
"""
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import make_round_pools  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'data/territory-rows.json'
DESIGN = ROOT / 'data/course-design.json'


def load(path):
    """Rows of a wide CSV export: name -> {field: value or [values]}."""
    with open(path, newline='', encoding='utf-8') as f:
        reader = csv.reader(f)
        header = next(reader)
        rows = list(reader)
    groups, i = [], 0
    while i < len(header):
        j = i + 1
        if header[i].endswith('_Array'):
            while j < len(header) and header[j].isdigit():
                j += 1
        groups.append((header[i], i, j))
        i = j
    out = {}
    for row in rows:
        fields = {}
        for name, a, b in groups:
            if name in ('Index', 'Name'):
                continue
            if name.endswith('_Array'):
                if b == a + 1:  # no element columns: the array is empty in every row
                    fields[name] = []
                    continue
                values = row[a + 1:b]
                while values and values[-1] == '':
                    values.pop()
                fields[name] = values
            else:
                fields[name] = row[a]
        out[row[1]] = fields
    return out


def sparse(row):
    """A row without its empty fields (an empty string or array is the default)."""
    return {k: v for k, v in row.items() if v not in ('', [])} if row is not None else None


def main(folder):
    folder = Path(folder)
    territory = load(folder / 'EnemyTerritory.csv')
    level = load(folder / 'EnemyTerritoryLevel.csv')
    mob = load(folder / 'EnemyTerritoryMob.csv')
    chara = load(folder / 'CharaSpec.csv')
    battle = load(folder / 'BattleCharaSpec.csv')
    colosseum = load(folder / 'Colosseum.csv')
    parameter = load(folder / 'EnemyParameter.csv')
    design = json.loads(DESIGN.read_text(encoding='utf-8'))
    rounds = {r for c in design['courses'] for slot in c['slots'] for r in slot}
    known = json.loads((ROOT / 'data/round-data.json').read_text(encoding='utf-8'))['rounds']
    rounds |= {r for r in known if make_round_pools.endgame(r) and f'terVR_COL30_{r}' in territory}
    used = {t for c in colosseum.values() for t in c['EnemyTerritoryID_Array']}
    spares = sorted(k for k in territory if k.startswith('terVR_COL30_') and k not in used)
    wanted = sorted(f'terVR_COL30_{r}' for r in rounds) + spares
    rows, templates, specs = {}, {}, {}
    for name in wanted:
        row = territory[name]
        rows[name] = {'territory': sparse(row), 'level': sparse(level.get(name))}
        for t in row['MobTemplateList_Array'] + [w for w in row['WaveMobTemplateList_Array'] if w]:
            spec = mob[t]['BattleCharaSpecID']
            templates[t] = spec
            chara_id = battle[spec]['CharaSpecID'] if spec in battle else spec
            c = chara.get(chara_id, {})
            specs[spec] = {'chara': chara_id, 'size': int(c.get('PhysiqueSize') or 0), 'move': int(c.get('MoveType') or 0),
                           'hp': int(battle.get(spec, {}).get('HP') or 0)}
    out = {'_about': __doc__.strip().split('\n\n')[0].replace('\n', ' '),
           'rows': rows, 'spares': spares, 'templates': dict(sorted(templates.items())),
           'specs': dict(sorted(specs.items())),
           'level_hp': {int(k.split('_')[1]): int(v['HPMax']) / 100
                        for k, v in sorted(parameter.items(), key=lambda kv: kv[0])
                        if k.startswith('Enemy_') and k.split('_')[1].isdigit()},
           'unique_indices': sorted({int(r['UniqueIndex']) for r in territory.values()})}
    OUT.write_text(json.dumps(out, indent=1, ensure_ascii=True) + '\n', encoding='utf-8')
    print(len(rows), 'rows,', len(spares), 'spares,', len(specs), 'specs ->', OUT)


if __name__ == '__main__':
    main(sys.argv[1])
