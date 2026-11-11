"""The native helper's off-thread request queue (main.cpp) and the Lua waits that
depend on it stay coherent. Live 2026-11-10 20:55 (0.9.12): a queued level served
at an arbitrary game-thread call stayed pending for good."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = (ROOT / 'native/src/main.cpp').read_text()
SCRIPTS = ROOT / 'ue4ss/JunonColosseum/Scripts'


def lua_number(name, key):
    return int(re.search(rf'^M\.{key}=(\d+)', (SCRIPTS / name).read_text(), re.M).group(1))


def body(name, indent=4):
    start = MAIN.index(name)
    return MAIN[start:MAIN.index('\n' + ' ' * indent + '}\n', start)]


def test_queued_requests_are_served_only_at_a_safe_point_one_at_a_time():
    serve_calls = [m.start() for m in re.finditer(r'\bServeEntry\(e,', MAIN)]
    assert len(serve_calls) == 1
    serve = body('bool ServeOneQueued(')
    assert serve.index('Queue::TakeOne(e,') < serve.index('ServeEntry(e,')
    at = body('void AtGameThreadCall(')
    assert at.index('SafePoint::Kind(function)') < at.index('SafePoint::Open(object,function)') < at.index('ServeOneQueued(kind,')
    assert 'if(kind && Queue::any' in at  # the no-safe-point fallback never loads
    assert 'SafePoint::Close(object,function)' in at
    assert MAIN.count('ServeOneQueued(') == 2  # defined once, called once
    assert 'ServeQueued()' not in MAIN and 'ServeQueuedAt(' not in MAIN  # the old serve paths are gone
    assert 'STR("ReceiveTick")' in MAIN
    assert 'STR("BlueprintModifyCamera")' in MAIN


def test_lua_gives_up_only_after_the_helper_has_answered_deferred():
    expiry_ms = int(re.search(r'constexpr ULONGLONG Expiry=(\d+);', MAIN).group(1))
    assert expiry_ms <= 3000
    take = body('bool TakeOne(', 8)
    assert 'now-it->at>Expiry' in take  # never served after Expiry
    assert 'ModJunonDeferred_' in body('void ExpireQueued(')
    for name, key in (('battle_plan.lua', 'QUEUE_TIMEOUT'), ('foyer.lua', 'MESH_QUEUE_TIMEOUT')):
        assert lua_number(name, key) * 1000 >= expiry_ms + 2000, key


def test_a_level_loaded_moments_ago_is_not_loaded_twice():
    window_ms = int(re.search(r'constexpr ULONGLONG Window=(\d+);', MAIN).group(1))
    assert window_ms < lua_number('battle_plan.lua', 'STREAM_STUCK') * 1000  # the stuck retry still loads
    assert MAIN.count('Recent::Duplicate(') == 1  # every request is served from the queue
    assert MAIN.count('Recent::Loaded(') == 1
    assert 'entries.erase(std::remove_if' in body('bool Add(', 8)  # a newer request replaces a queued one
