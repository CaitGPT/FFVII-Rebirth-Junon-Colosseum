import shutil
from pathlib import Path

from lupa import LuaRuntime

SCRIPT = Path(__file__).resolve().parents[1] / 'ue4ss/JunonColosseum/Scripts/paths.lua'


def load(mod_dir):
    scripts = mod_dir / 'Scripts'
    scripts.mkdir(parents=True, exist_ok=True)
    shutil.copy(SCRIPT, scripts / 'paths.lua')
    lua = LuaRuntime(unpack_returned_tuples=True)
    return lua.execute(f"return dofile([[{(scripts / 'paths.lua').as_posix()}]])")


def test_a_release_writes_no_telemetry_and_shares_files_in_the_mod_folder(tmp_path):
    mod = tmp_path / 'Mods' / 'JunonColosseum'
    paths = load(mod)
    assert paths.dev is None and paths.telemetry('x.tsv') is None and paths.open('x.tsv', 'ab') is None
    assert Path(paths.shared('junon-rounds.req')) == mod / 'junon-rounds.req'


def test_a_development_install_names_its_telemetry_folder_in_dev_txt(tmp_path):
    mod = tmp_path / 'Mods' / 'JunonColosseum'
    telemetry = tmp_path / 'Telemetry'
    telemetry.mkdir()
    mod.mkdir(parents=True)
    (mod / 'dev.txt').write_text(str(telemetry) + '\n')
    paths = load(mod)
    paths.replace('probe.tsv', 'ok')
    assert (telemetry / 'probe.tsv').read_text() == 'ok'
