"""Tests for the translation layer.

The point of these tests is that the application must keep working when a
catalog is missing or broken - it then simply shows the English source strings.
"""

from audiflix import i18n


def teardown_function():
    # Leave the process in the untranslated state for the other tests.
    i18n.install("en")


def test_unknown_language_falls_back_to_the_source_string():
    i18n.install("zz")
    assert i18n._("Settings") == "Settings"


def test_ngettext_falls_back_to_english_plural_rules():
    i18n.install("zz")
    assert i18n.ngettext("%d hour", "%d hours", 1) % 1 == "1 hour"
    assert i18n.ngettext("%d hour", "%d hours", 3) % 3 == "3 hours"


def test_n_marker_returns_the_string_unchanged():
    assert i18n.N_("Play / Pause") == "Play / Pause"


def test_english_is_always_offered():
    assert i18n.SOURCE_LANGUAGE in i18n.available_languages()


def test_available_languages_has_no_duplicates():
    languages = i18n.available_languages()
    assert len(languages) == len(set(languages))


def test_install_returns_the_active_language():
    assert i18n.install("en") == "en"
    assert i18n.active_language() == "en"


def test_locale_dir_is_inside_the_package():
    assert i18n.locale_dir().name == "locale"
