"""All of the native helper's engine work runs at a safe point (main.cpp, 2026-11-11).

Hang 3 (2026-11-10): the engine lost two enemy pack loads while its async loader
sat idle, in a session where the helper did engine work from arbitrary
game-thread ProcessEvent calls. These tests keep that work behind FrameWork,
the loader wait bounded, the in-battle spawn-stall logger read-only and its
experimental recovery behind every check."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = (ROOT / 'native/src/main.cpp').read_text()

JOBS = ('ArenaReady::Tick', 'RoundShuffle::Tick', 'InfusionSkills::Tick', 'Stall::Tick', 'SpawnStall::Tick')


def body(name, indent=4):
    start = MAIN.index(name)
    return MAIN[start:MAIN.index('\n' + ' ' * indent + '}\n', start)]


def namespace(name):
    start = MAIN.index('    namespace ' + name + '\n    {')
    return MAIN[start:MAIN.index('\n    }\n', start)]


def callback():
    start = MAIN.rindex('RegisterProcessEventPreCallback(')  # the call, not the declaration
    return MAIN[start:MAIN.index('});', start)]


def test_the_processevent_callback_does_no_engine_work_itself():
    cb = callback()
    for job in JOBS:
        assert job not in cb, job
    for call in ('StaticFindObject', 'ForEachUObject', 'LoadOwnedLevel', 'LoadBoardMesh', 'LoadAssetPath', 'ServeEntry'):
        assert call not in cb, call
    assert 'AtGameThreadCall(object,function)' in cb
    assert cb.index('const bool game=OnGameThread();') < cb.index('AtGameThreadCall(object,function)')


def test_every_periodic_job_runs_only_from_the_frame_scheduler():
    jobs = namespace('FrameWork')
    for job in JOBS:
        assert len(re.findall(r'(?<![A-Za-z])' + job, MAIN)) == 1, job  # its one reference is the job table
        assert job in jobs
    # FrameWork schedules them: no job keeps its own clock any more.
    for match in re.finditer(r'\n        void Tick\(\)\n        \{\n(.*?)\n        \}\n', MAIN, re.S):
        assert 'now-last<' not in match.group(1)


def test_one_unit_of_work_per_frame_and_a_bounded_wait_for_the_loader():
    at = body('void AtGameThreadCall(')
    assert at.index('Loader::Busy()') < at.index('ServeOneQueued(kind,') < at.index('FrameWork::Next(now,loading)')
    assert 'if(!worked)' in at  # a served request is the frame's only work
    assert 'thread_local bool busy' in at  # our own loads re-enter ProcessEvent
    max_defer = int(re.search(r'constexpr ULONGLONG MaxDefer=(\d+)', MAIN).group(1))
    expiry = int(re.search(r'constexpr ULONGLONG Expiry=(\d+);', MAIN).group(1))
    assert max_defer < expiry  # a queued request can still be served before it expires
    nxt = body('        Job* Next(', 8)
    assert 'now-j.next<MaxDefer' in nxt
    assert 'loading?FrameWork::MaxDefer:0' in body('bool ServeOneQueued(')


def test_without_safe_points_only_the_periodic_jobs_run_and_it_is_logged():
    at = body('void AtGameThreadCall(')
    assert 'now-FrameWork::lastSafe<FrameWork::FallbackAfter' in at
    assert '"fallback_no_safe_point"' in at and '"safe_point_back"' in at
    assert '(++calls&255)!=0' in at


def test_every_request_is_queued_even_on_the_game_thread():
    for name in ('void RequestOwnedLevel(', 'void RequestBoardMesh('):
        b = body(name)
        assert 'QueueRequest(object,' in b and 'OnGameThread()' in b
        assert 'LoadOwnedLevel(' not in b and 'LoadBoardMesh(' not in b
    assert MAIN.count('LoadOwnedLevel(marker') == 1 and MAIN.count('LoadBoardMesh()') == 2  # ServeEntry only


def test_the_loader_check_is_verified_against_the_executable_first():
    loader = namespace('Loader')
    verify = body('        bool Verify()', 8)
    assert '33 D2 33 C0 F0 0F B1 91 08 02 00 00 75 0C 33 C0 F0 0F B1 91 0C 02 00 00 74 02 B2 01 8A C2 C3' in verify
    assert 'slot==Code::At(IsLoadingPackages)' in verify
    assert 'vtable!=Code::At(Vtable)' in loader  # the global must hold the verified loader
    assert 'return p && CallBusy(p,busy) && busy;' in loader  # unverified: never "busy"
    assert '__except' in body('        bool CallBusy(', 8)


def test_the_spawn_stall_logger_only_reads_and_calls_the_checked_pending_test():
    spawn = namespace('SpawnStall')
    tick = spawn[spawn.index('        void Tick()'):]
    assert 'junon-spawnstall.on' in tick and 'junon-spawnstall.tsv' in tick
    writes = re.findall(r'\*reinterpret_cast<[^>]*>\([^)]*\)=', spawn)
    assert writes and all('0x44' in w or '0x48' in w for w in writes)
    assert spawn.count('WriteLoaded(') == 2  # defined, and called once by Fix
    assert 'Fix(out,' in tick and tick.index('DevFlag("junon-spawnfix.on")') < tick.index('Fix(out,')
    assert 'if(state!=1 || id<0) return "?";' in spawn  # IsLoading only after Verify


def test_the_recovery_writes_what_the_poller_writes_and_only_after_every_check():
    spawn = namespace('SpawnStall')
    # The poller's own bytes: or dword [rbx+44],-1; mov dword [rbx+48],3.
    assert '83 4B 44 FF C7 43 48 03 00 00 00' in spawn
    write = body('        bool WriteLoaded(', 8)
    assert '(entry+0x44)=-1' in write and '(entry+0x48)=3' in write
    fix = body('        void Fix(', 8)
    order = ['w.tried=true', 'code_checks_unverified', 'sequence_not_waiting_for_spawns', 'engine_loader_not_idle',
             'entry_changed"', 'not_a_charaspec_pack', 'handle_not_pending', 'request_not_found',
             'engine_request_not_pending', 'no_asset_paths_listed', 'load_failed', 'not_found_after_load',
             'entry_changed_during_load', 'WriteLoaded(entry)', 'fix_marked_loaded']
    at = [fix.index(step) for step in order]
    assert at == sorted(at), order
    assert 'now-w.since<FixAfter' in fix
    assert re.search(r'constexpr ULONGLONG FixAfter=(\d+)', MAIN).group(1) == '20000'


def test_stall_diagnostics_do_not_look_objects_up_by_package_path():
    stall = namespace('Stall')
    assert 'StaticFindObject' not in stall  # unreliable here (2026-11-11)
    assert 'ColosseumScan::Sequence()' in stall  # the sequence is a heap object, found by its vtable
    assert 'Arena(out,stamp)' in stall and 'IsUnreachable()' in stall
    assert 'round_keys' in stall  # keys without a territory are counted, not listed


def test_arena_ready_relinks_a_lost_partner_only_while_idle():
    tick = body('        void Tick()\n        {\n            const auto now=std::chrono::steady_clock::now();\n            if(state==0){', 8)
    assert 'PartnerAlive(o)' in tick and '(phase!=0 && phase!=4)' in tick
    assert '"arena_ready_partner_lost"' in tick and '"arena_ready_relinked"' in tick
