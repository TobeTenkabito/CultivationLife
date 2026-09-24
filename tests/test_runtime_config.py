from pathlib import Path

from cultivation_life.runtime_config import load_runtime_config, parse_runtime_config


def test_runtime_config_accepts_english_and_chinese_semantics() -> None:
    assert parse_runtime_config("debug=true")["debug"] is True
    assert parse_runtime_config("调试模式：开启")["debug"] is True
    assert parse_runtime_config("运行模式 = 调试")["debug"] is True
    assert parse_runtime_config("开启调试模式")["debug"] is True
    assert parse_runtime_config("mode=release")["debug"] is False
    assert parse_runtime_config("关闭调试模式")["debug"] is False


def test_runtime_config_is_safe_by_default_and_reloads_from_disk(tmp_path: Path) -> None:
    missing = load_runtime_config(tmp_path)
    assert missing["debug"] is False
    assert missing["mode"] == "release"
    assert missing["exists"] is False

    path = tmp_path / "game_config.txt"
    path.write_text("运行模式 = 调试\n", encoding="utf-8")
    assert load_runtime_config(tmp_path)["debug"] is True
    path.write_text("运行模式 = 正式\n", encoding="utf-8")
    assert load_runtime_config(tmp_path)["debug"] is False


def test_invalid_runtime_config_never_enables_debug() -> None:
    shown = parse_runtime_config("debug = maybe\n加载模式 = 随便\nprint('unsafe')")
    assert shown == {"debug": False, "mode": "release"}
