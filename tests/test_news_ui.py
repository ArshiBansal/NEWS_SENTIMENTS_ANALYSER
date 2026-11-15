from streamlit.testing.v1 import AppTest

# Expected UI element counts
EXPECTED_SELECTBOXES_MIN: int = 3
EXPECTED_TEXT_INPUTS_MIN: int = 1
EXPECTED_METRICS: int = 4
EXPECTED_DOWNLOAD_BUTTONS_MIN: int = 1
EXPECTED_MULTISELECTS_MIN: int = 3
EXPECTED_SLIDERS_MIN: int = 1


def test_news_app_loads_without_errors():
    """Test that the Streamlit app loads and renders without errors."""
    at = AppTest.from_file("news.py").run(timeout=30)

    assert not at.exception
    # Check main title is rendered
    markdowns = at.get("markdown")
    assert any("News Pulse" in m.value for m in markdowns)

    # Check sidebar elements exist
    selectboxes = at.get("selectbox")
    assert len(selectboxes) >= EXPECTED_SELECTBOXES_MIN  # News type, Sort by, Published

    text_inputs = at.get("text_input")
    assert len(text_inputs) >= EXPECTED_TEXT_INPUTS_MIN  # Search

    # Check feed status expander exists
    expanders = at.get("expander")
    assert any("Feed status" in e.label for e in expanders)


def test_news_app_has_expected_ui_elements():
    """Test that key UI elements are present."""
    at = AppTest.from_file("news.py").run(timeout=15)

    assert not at.exception

    # Check metrics row
    metrics = at.get("metric")
    assert len(metrics) == EXPECTED_METRICS

    # Check download button
    download_buttons = at.get("download_button")
    assert len(download_buttons) >= EXPECTED_DOWNLOAD_BUTTONS_MIN

    # Check category filters in sidebar
    multiselects = at.get("multiselect")
    assert len(multiselects) >= EXPECTED_MULTISELECTS_MIN  # Categories, Sentiment, Sources

    # Check slider
    sliders = at.get("slider")
    assert len(sliders) >= EXPECTED_SLIDERS_MIN  # Articles per category


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
