from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from role_guesser.bot import Role, filter_roles_for_intro_quiz, find_intro_quiz_metadata, load_intro_quiz_metadata


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
