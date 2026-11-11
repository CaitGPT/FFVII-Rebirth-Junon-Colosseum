from pathlib import Path

from lupa import LuaRuntime


def test_invitation_guard_and_discovery_are_separate_and_current_chapter_gated():
    source = Path(__file__).resolve().parents[1] / 'ue4ss/JunonColosseum/Scripts/gate.lua'
    policy = LuaRuntime(unpack_returned_tuples=True).execute(source.read_text()).policy
    for progress in (2140, 4000, 4500, 11805, 11999):
        p = policy(progress, True, 1, True)
        assert p.roche_defeated is True
        assert p.guard_enabled is False
        assert p.access_enabled is False
        assert p.board_enabled is False
        assert p.exit_enabled is False
    before = policy(12000, False, 1, False)
    assert before.guard_enabled is True
    assert before.access_enabled is False
    assert before.board_enabled is False
    after = policy(12000, False, 1, True)
    assert after.guard_enabled is True
    assert after.access_enabled is True
    assert after.board_enabled is True
    # Discovery survives replay and does not depend on retaining the key item.
    replay = policy(4500, True, 0, True)
    assert replay.discovered is True
    assert replay.access_enabled is False
    returned = policy(13000, True, 0, True)
    assert returned.access_enabled is True
    assert returned.guard_enabled is False
    assert returned.grant_invitation is True
    missing_item = policy(12980, True, 0, False)
    assert missing_item.guard_enabled is False
    assert missing_item.access_enabled is False
    assert missing_item.grant_invitation is True
    for count, discovered in ((None, False), (-1, False), (0.5, False), (1, None)):
        assert policy(12980, True, count, discovered) == (None, 'invitation_or_discovery_unobserved')
