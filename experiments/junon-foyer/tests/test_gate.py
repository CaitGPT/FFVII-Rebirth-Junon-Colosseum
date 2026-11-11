from pathlib import Path

from lupa import LuaRuntime


def test_completion_gate_survives_chapter_selection_and_rejects_unknown_state():
    source = Path(__file__).resolve().parents[1] / 'ue4ss/JunonColosseum/Scripts/gate.lua'
    lua = LuaRuntime(unpack_returned_tuples=True)
    gate = lua.execute(source.read_text())
    assert gate.unlocked(2140, False) is False  # owner's chapter 2 save
    assert gate.unlocked(11804, False) is False  # before the Chapter 11 Roche victory
    assert gate.unlocked(11805, False) is True  # Chapter.csv's post-Roche milestone
    assert gate.unlocked(11810, False) is True
    assert gate.unlocked(2140, True) is True  # cleared save selecting an earlier chapter
    assert gate.unlocked(12980, True) is True
    for progress in (4000, 4010, 4500, 4999):
        p = gate.policy(progress, True, 1, True)
        assert p.roche_defeated is True
        assert p.chapter4 is True
        assert p.access_enabled is False
    assert gate.policy(3999, True, 1, True).access_enabled is False
    assert gate.policy(5000, True, 1, True).access_enabled is False
    assert gate.policy(11804, False, 1, True).access_enabled is False
    assert gate.policy(11805, False, 1, True).access_enabled is False
    assert gate.policy(12000, False, 1, True).access_enabled is True
    for unknown in (None, True, -1, 11805.5, float('nan'), float('inf')):
        assert gate.unlocked(unknown, False) == (None, 'completion_state_unobserved')
