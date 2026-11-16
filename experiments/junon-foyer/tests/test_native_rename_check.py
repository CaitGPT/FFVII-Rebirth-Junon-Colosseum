"""The helper acknowledges every request by renaming its marker (main.cpp RenameMarker).

Live 2026-11-15: under the 1.005 UE4SS build from RE-UE4SS FF7R's Files tab, whose VTableLayout.ini puts the extra
UObject virtual before ProcessEvent, UE4SS's Rename lands one slot early, returns true and leaves the name unchanged,
so every level request looked refused and the noticeboard never got its Check point. The helper now trusts the name,
not the return value, and says what to change.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = (ROOT / 'native/src/main.cpp').read_text()


def rename_marker():
    match = re.search(r'bool RenameMarker\(.*?\n    \}\n', MAIN, re.S)
    assert match, 'RenameMarker not found'
    return match.group(0)


def test_rename_is_checked_by_the_name_not_the_return_value():
    body = rename_marker()
    assert 'object->GetName()==name' in body
    assert 'return renamed;' in body


def test_only_a_silent_rename_is_reported():
    body = rename_marker()
    # An honest false (a name clash) stays a plain refusal; only "returned true, name unchanged" is the fault.
    assert 'if(returned && !renamed && !told.exchange(true))' in body


def test_the_report_names_the_setting_to_change():
    body = rename_marker()
    assert 'Fault("JC-UE4SS"' in body
    assert 'unk_FF7R_1005_ExtraVirtual' in body
    assert 'FinishDestroy' in body
    assert 'mod 2521' in body
