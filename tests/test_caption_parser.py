from publisher.caption_parser import parse_caption_text
from publisher.platforms.base import Caption

FIXTURE = """\
Episodio 142: Elea 9003 - Il primo calcolatore elettronico commerciale italiano

Titolo del soundbite

Testo completo della trascrizione del soundbite.

Ascolta l'episodio completo: https://example.com/episodes/142/

#podcast #storia-dellinformatica #informatica-vintage
"""


def test_title():
    c = parse_caption_text(FIXTURE)
    assert c.title == "Episodio 142: Elea 9003 - Il primo calcolatore elettronico commerciale italiano"


def test_soundbite_title():
    c = parse_caption_text(FIXTURE)
    assert c.soundbite_title == "Titolo del soundbite"


def test_body_is_full_text():
    c = parse_caption_text(FIXTURE)
    assert "Testo completo" in c.body
    assert "Episodio 142" in c.body


def test_tags_extracted():
    c = parse_caption_text(FIXTURE)
    assert c.tags == ["podcast", "storia-dellinformatica", "informatica-vintage"]


def test_tags_extracted_when_transcript_follows_hashtag_line():
    c = parse_caption_text(
        """\
Episodio 150

Titolo del soundbite

Ascolta l'episodio completo: https://example.com/episodes/150/

#podcast #pensieri-in-codice

Questa e' la trascrizione del soundbite, aggiunta in fondo al caption.
"""
    )

    assert c.tags == ["podcast", "pensieri-in-codice"]


def test_tags_ignore_inline_hashtags_without_dedicated_hashtag_line():
    c = parse_caption_text("Titolo\n\nCorpo con un #hashtag citato nella frase.")

    assert c.tags == []


def test_tags_use_first_dedicated_hashtag_line():
    c = parse_caption_text(
        """\
Titolo

#primo #tag

Corpo

#secondo
"""
    )

    assert c.tags == ["primo", "tag"]


def test_episode_url():
    c = parse_caption_text(FIXTURE)
    assert c.episode_url == "https://example.com/episodes/142/"


def test_empty_caption():
    c = parse_caption_text("")
    assert c.title == ""
    assert c.tags == []
    assert c.episode_url is None


def test_no_url():
    c = parse_caption_text("Solo un titolo\n\n#tag1")
    assert c.episode_url is None
    assert c.tags == ["tag1"]


def test_no_hashtags():
    c = parse_caption_text("Titolo\n\nCorpo senza hashtag")
    assert c.tags == []


def test_title_truncation_not_applied_in_parser():
    long_title = "A" * 150
    c = parse_caption_text(long_title)
    assert c.title == long_title  # parser does not truncate; platforms do
