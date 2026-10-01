from studio.youtube_upload import build_video_body


def test_build_video_body_uses_private_by_default():
    body=build_video_body({"title":"Test #Shorts","description":"desc","hashtags":["#Shorts","#AI"]})
    assert body["snippet"]["title"] == "Test #Shorts"
    assert body["snippet"]["tags"] == ["Shorts","AI"]
    assert body["status"]["privacyStatus"] == "private"
