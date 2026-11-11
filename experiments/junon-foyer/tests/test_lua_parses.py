from pathlib import Path

from lupa import LuaRuntime

SCRIPTS = Path(__file__).resolve().parents[1] / 'ue4ss/JunonColosseum/Scripts'


def test_every_shipped_script_parses():
    check = LuaRuntime().eval('function(s) local f, e = load(s); return e or "ok" end')
    for script in sorted(SCRIPTS.glob('*.lua')):
        assert check(script.read_text(encoding='utf-8')) == 'ok', script.name
