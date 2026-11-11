"""Compose Training Dummy's data changes with this venue's.

Both mods replace the Colosseum tables, and our archive loads over Training
Dummy's, so ours carries its rows too. With --show-base-courses-with FLAG, the
base spec's courses are shown only through FLAG, which compat.lua sets when
Training Dummy is installed; without it they stay hidden.
"""
import argparse
import json
import re
from pathlib import Path

COLOSSEUM = 'DataObject/Resident/Colosseum.uasset'
STORY = 'DataObject/Resident/StoryFlag.uasset'


def load(source):
    return json.loads(re.sub(r'^\s*//.*$', '', Path(source).read_text(encoding='utf-8-sig'), flags=re.M))


def merge(base, own, flag=None):
    tables = {}
    for data, gated in ((base, flag), (own, None)):
        for table in data['tables']:
            target = tables.setdefault(table['asset'], {'asset': table['asset'], 'rows': []})
            for row in table['rows']:
                if any(existing['name'] == row['name'] for existing in target['rows']):
                    raise ValueError(f"conflicting row: {table['asset']}:{row['name']}")
                if gated and table['asset'] == COLOSSEUM:
                    row = json.loads(json.dumps(row))
                    row.setdefault('set', {})['DisplayFlagID_Array'] = [gated]
                target['rows'].append(row)
    if flag and not any(r['name'] == flag for r in tables.get(STORY, {'rows': []})['rows']):
        raise ValueError(f'{flag} must be a StoryFlag row in our spec')
    return {'tables': list(tables.values())}


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('base')
    p.add_argument('own')
    p.add_argument('output')
    p.add_argument('--show-base-courses-with')
    a = p.parse_args()
    merged = merge(load(a.base), load(a.own), a.show_base_courses_with)
    Path(a.output).write_text(json.dumps(merged, indent=2), encoding='utf-8')
