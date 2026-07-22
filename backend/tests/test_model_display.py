from app.model_display import display_name_for


class TestDisplayNameFor:
    def test_known_alias_maps_to_friendly_name(self):
        assert display_name_for("gemma4:e12b") == "Gemma 4 12B"

    def test_case_insensitive(self):
        assert display_name_for("GEMMA4:E12B") == "Gemma 4 12B"

    def test_weights_file_path_matches_on_model_family(self):
        # llama.cpp's /v1/models reports the full GGUF path, not the alias.
        path = "/models/gemma-4-12b-it-Q4_K_M.gguf"
        assert display_name_for(path) == "Gemma 4 12B"

    def test_unknown_model_falls_back_to_raw_identifier(self):
        assert display_name_for("some-other-model-v3") == "some-other-model-v3"

    def test_empty_string_stays_empty(self):
        assert display_name_for("") == ""
