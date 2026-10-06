"""Announcements reach speech and braille independently, without real hardware."""

from unittest.mock import Mock

import pytest

from audiflix import speech


@pytest.fixture
def output(monkeypatch):
    backend = Mock()
    monkeypatch.setattr(speech, "_get_speaker", lambda: backend)
    speech.reset_dedupe()
    yield backend
    speech.reset_dedupe()


def test_status_is_sent_to_speech_and_braille(output):
    speech.announce("Speed 1.5x", interrupt=True)
    output.speak.assert_called_once_with("Speed 1.5x", interrupt=True)
    output.braille.assert_called_once_with("Speed 1.5x")


def test_braille_can_use_compact_digits(output):
    speech.announce("Position one minute", braille_text="Position 01:00")
    output.speak.assert_called_once_with("Position one minute", interrupt=False)
    output.braille.assert_called_once_with("Position 01:00")


@pytest.mark.parametrize("failed_channel", ["speak", "braille"])
def test_output_failure_does_not_disable_the_other_channel(output, failed_channel):
    getattr(output, failed_channel).side_effect = RuntimeError("unavailable")
    speech.announce("Paused")
    output.speak.assert_called_once()
    output.braille.assert_called_once()


def test_deduplication_and_explicit_repeat_apply_to_both_channels(output, monkeypatch):
    monkeypatch.setattr(speech.time, "monotonic", lambda: 100.0)
    speech.announce("Paused")
    speech.announce("Paused")
    assert output.speak.call_count == output.braille.call_count == 1
    speech.announce("Paused", force=True)
    assert output.speak.call_count == output.braille.call_count == 2


def test_changed_braille_time_is_not_suppressed_when_spoken_minutes_match(output):
    speech.announce("One minute", braille_text="01:01")
    speech.announce("One minute", braille_text="01:02")
    assert output.braille.call_count == 2
    output.braille.assert_called_with("01:02")


def test_no_screen_reader_is_harmless(monkeypatch):
    monkeypatch.setattr(speech, "_get_speaker", lambda: None)
    speech.announce("Playing", force=True)
    speech.reset_dedupe()
