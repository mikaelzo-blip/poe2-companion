import importlib.util
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location(
    "gen_pob_base_types", Path(__file__).resolve().parents[2] / "scripts" / "gen_pob_base_types.py"
)
gen = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gen)


def _fork(tmp_path: Path, lua: str) -> Path:
    bases = tmp_path / "src" / "Data" / "Bases"
    bases.mkdir(parents=True)
    (bases / "x.lua").write_text(lua, encoding="utf-8")
    return tmp_path


def test_collect_reads_types_and_tolerates_repeated_bases(tmp_path):
    fork = _fork(tmp_path, (
        'itemBases["Dull Hatchet"] = {\n\ttype = "One Hand Axe",\n}\n'
        'itemBases["Chain"] = {\n\ttype = "Amulet",\n\thidden = true,\n}\n'
        'itemBases["Chain"] = {\n\ttype = "Amulet",\n}\n'
    ))
    assert gen.collect(fork) == {"Dull Hatchet": "One Hand Axe", "Chain": "Amulet"}


@pytest.mark.parametrize("lua", [
    'itemBases["Chain"] = {\n\ttype = "Amulet",\n}\nitemBases["Chain"] = {\n\ttype = "Ring",\n}\n',
    'itemBases["Odd"] = {\n\tquality = 20,\n\ttype = "Ring",\n}\n',
])
def test_collect_refuses_type_clash_or_unparsed_base(tmp_path, lua):
    with pytest.raises(SystemExit):
        gen.collect(_fork(tmp_path, lua))
