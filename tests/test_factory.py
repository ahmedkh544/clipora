from studio.factory import classify_source, make_metadata, select_video_urls


def test_classify_youtube_sources():
    assert classify_source("https://www.youtube.com/watch?v=abc") == "video"
    assert classify_source("https://www.youtube.com/playlist?list=xyz") == "playlist"
    assert classify_source("https://www.youtube.com/@creator") == "channel"


def test_metadata_is_deterministic_and_has_short_form_fields():
    m = make_metadata("Nobody knows this secret changed everything!", "tiktok")
    assert m["title"].endswith("#Shorts")
    assert len(m["title"]) <= 100
    assert "hashtags" in m and len(m["hashtags"]) >= 3
    assert m["privacy_status"] == "private"


def test_select_video_urls_caps_channel_items():
    entries = [{"url": f"https://youtube.com/watch?v={i}", "title": str(i)} for i in range(5)]
    assert len(select_video_urls(entries, 3)) == 3


def test_build_listing_command_is_flat_and_capped():
    from studio.factory import build_listing_command
    cmd=build_listing_command("https://www.youtube.com/@demo", 5)
    assert "--flat-playlist" in cmd
    assert "--playlist-end" in cmd and "5" in cmd
    assert "--dump-single-json" in cmd
