import studio_app

def test_studio_ui_exposes_story_first_workflow():
    html = studio_app.HTML
    assert "Turn one long video into a" in html
    assert "storyMode" in html
    assert "dropzone" in html
    assert "processingSteps" in html
    assert "Download clip" in html

def test_studio_ui_is_mobile_first_and_accessible():
    html = studio_app.HTML
    assert "min-width:320px" in html
    assert "aria-label" in html
    assert "prefers-reduced-motion" in html
