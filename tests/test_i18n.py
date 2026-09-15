"""Tests for mylib/i18n.py: catalog completeness (every message key has
every supported language) and that t() never raises on a missing key or
missing interpolation kwargs (both degrade to a readable placeholder,
since a translation lookup failing must never crash the GUI)."""
import mylib.i18n as i18n


class TestCatalogCompleteness:
    def test_every_key_has_every_supported_language(self):
        missing = {
            key: [lang for lang in i18n.SUPPORTED_LANGS if lang not in entry]
            for key, entry in i18n.MESSAGES.items()
        }
        missing = {k: v for k, v in missing.items() if v}
        assert missing == {}, f"catalog entries missing languages: {missing}"

    def test_every_translation_is_a_non_empty_string(self):
        bad = [
            (key, lang)
            for key, entry in i18n.MESSAGES.items()
            for lang in i18n.SUPPORTED_LANGS
            if lang in entry and (not isinstance(entry[lang], str) or entry[lang] == "")
        ]
        assert bad == []


class TestTranslateFunction:
    def test_switches_active_language(self):
        original = i18n.get_language()
        try:
            i18n.set_language("en")
            en_text = i18n.t("plot.gui.quit")
            i18n.set_language("ja")
            ja_text = i18n.t("plot.gui.quit")
            assert en_text != ja_text
        finally:
            i18n.set_language(original)

    def test_unknown_key_degrades_to_the_key_itself_not_a_crash(self):
        assert i18n.t("this.key.does.not.exist") == "this.key.does.not.exist"

    def test_missing_interpolation_kwarg_does_not_raise(self):
        # comm.additional_init needs {init}; omitting it must not crash --
        # a missing/malformed kwarg degrades to the raw template.
        result = i18n.t("comm.additional_init")
        assert isinstance(result, str)

    def test_format_kwargs_are_interpolated(self):
        result = i18n.t("comm.additional_init", init="DPG_X95840Wpeak.ini")
        assert "DPG_X95840Wpeak.ini" in result
