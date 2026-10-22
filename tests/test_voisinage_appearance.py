import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from cultivation_life.ui_preferences import load_ui_preferences, write_ui_preferences

STYLE = dict(outline='star', pattern='lotus', palette='pink', control='crystal', density=72)


@pytest.mark.parametrize('theme', ['water', 'mountain', 'wood', 'thunder', 'moon', 'void', 'time'])
def test_extended_components_mix_with_existing_components(tmp_path, theme):
    for outline, pattern in [(theme, 'lotus'), ('star', theme), (theme, theme)]:
        style = STYLE | {'outline': outline, 'pattern': pattern, 'palette': '#89abcd'}
        write_ui_preferences(tmp_path, {'voisinage_appearance': style})
        assert load_ui_preferences(tmp_path)['voisinage_appearance'] == style


def test_appearance_roundtrip_preserves_other_preferences_and_saves(tmp_path):
    save = tmp_path/'data/saves/sentinel.json'
    save.parent.mkdir(parents=True)
    save.write_text('{"unchanged":true}')
    original = write_ui_preferences(tmp_path, {'theme':'f','navigation':{'pins':['map'],'recent':[]}})
    assert write_ui_preferences(tmp_path, {'voisinage_appearance':STYLE}) == original | {'voisinage_appearance':STYLE}
    assert load_ui_preferences(tmp_path)['voisinage_appearance'] == STYLE
    write_ui_preferences(tmp_path, {'pixel_art':True})
    assert load_ui_preferences(tmp_path)['voisinage_appearance'] == STYLE
    assert save.read_text() == '{"unchanged":true}'


@pytest.mark.parametrize('color', ['#000000', '#ffffff', '#12aBCd', '#FF0000', '#330000'])
def test_custom_color_roundtrip(tmp_path, color):
    style = STYLE | {'palette': color}
    expected = style | {'palette': color.lower()}
    assert write_ui_preferences(tmp_path, {'voisinage_appearance': style})['voisinage_appearance'] == expected
    assert load_ui_preferences(tmp_path)['voisinage_appearance'] == expected


@pytest.mark.parametrize('bad', [None, [], {}, STYLE|{'power':999}, *[STYLE|{'palette':color} for color in ['#fff', '#12345678', '#zzzzzz', '#123456\n', 'red', 'url(x)', [], None]], STYLE|{'outline':[]}, STYLE|{'control':'kill'}, STYLE|{'density':True}, STYLE|{'density':19}, STYLE|{'density':101}, STYLE|{'density':65.5}])
def test_invalid_appearance_is_atomic(tmp_path,bad):
    write_ui_preferences(tmp_path, {'voisinage_appearance':STYLE})
    path=tmp_path/'data/ui_preferences.json'
    before=path.read_bytes()
    with pytest.raises(ValueError):
        write_ui_preferences(tmp_path, {'theme':'f','voisinage_appearance':bad})
    assert path.read_bytes() == before


def test_corrupt_optional_style_does_not_erase_other_preferences(tmp_path):
    path=tmp_path/'data/ui_preferences.json';path.parent.mkdir()
    path.write_text(json.dumps({'theme':'d','voisinage_appearance':{'palette':'invalid'}}))
    assert load_ui_preferences(tmp_path)['theme']=='d'
    assert 'voisinage_appearance' not in load_ui_preferences(tmp_path)


def test_parallel_partial_preferences_keep_appearance(tmp_path):
    patches=[{'voisinage_appearance':STYLE},{'theme':'f'},{'pixel_art':True},{'navigation':{'pins':['map'],'recent':[]}}]
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda patch:write_ui_preferences(tmp_path,patch),patches))
    final=load_ui_preferences(tmp_path)
    assert final['voisinage_appearance']==STYLE and final['theme']=='f' and final['pixel_art'] is True
