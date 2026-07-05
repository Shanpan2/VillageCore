from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from role_guesser.bot import (
    Role,
    build_intro_quiz_embed,
    filter_roles_for_intro_quiz,
    find_intro_quiz_metadata,
    load_intro_quiz_metadata,
)


def test_filter_roles_for_intro_quiz_excludes_vanilla_by_default():
    roles = [
        Role(name="Crewmate", display_name="クルーメイト", mod="Vanilla", features={}),
        Role(name="Sheriff", display_name="シェリフ", mod="TOH", features={}),
    ]

    filtered = filter_roles_for_intro_quiz(roles, "TOH")

    assert [role.mod for role in filtered] == ["TOH"]


def test_intro_quiz_metadata_can_provide_wiki_link():
    metadata = load_intro_quiz_metadata()
    role = Role(name="Sheriff", display_name="シェリフ", mod="TOH", features={})

    item = find_intro_quiz_metadata(role, metadata)

    assert item is not None
    assert item["wiki_url"].startswith("http")


def test_intro_quiz_metadata_treats_placeholder_wiki_as_missing():
    metadata = {
        "mods": {"TOH": {"wiki_url": "https://example.com/toh"}},
        "roles": {"Sheriff": {"intro_text": "インポスターを撃ち抜け", "wiki_url": "未登録"}},
    }
    role = Role(name="Sheriff", display_name="シェリフ", mod="TOH", features={})

    item = find_intro_quiz_metadata(role, metadata)

    assert item is not None
    assert item["intro_text"] == "インポスターを撃ち抜け"
    assert item["wiki_url"] is None


def test_intro_quiz_embed_falls_back_to_mod_wiki_when_role_wiki_is_placeholder(monkeypatch):
    metadata = {
        "mods": {"TOH": {"wiki_url": "https://example.com/toh"}},
        "roles": {"Sheriff": {"intro_text": "インポスターを撃ち抜け", "wiki_url": "未登録"}},
    }
    monkeypatch.setattr("role_guesser.bot.load_intro_quiz_metadata", lambda: metadata)
    role = Role(name="Sheriff", display_name="シェリフ", mod="TOH", features={})

    embed = build_intro_quiz_embed(role, [role], selected_mod="TOH")

    assert embed.title == "イントロクイズ"
    assert "https://example.com/toh" in embed.fields[0].value
