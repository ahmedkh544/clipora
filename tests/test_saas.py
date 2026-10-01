import os
from pathlib import Path

def test_vertical_crop_x_returns_valid_crop_for_real_video():
    from studio.toolbox import vertical_crop_x
    p=Path(__file__).parents[1]/"studio_test.mp4"
    x=vertical_crop_x(str(p),720,1280)
    assert isinstance(x,int) and x>=0

def test_visual_filter_is_vertical_and_contains_subtle_zoom():
    from studio.toolbox import visual_filter
    f=visual_filter(100,1920,1080,720,1280,0.02)
    assert "720:1280" in f
    assert "scale=" in f and "crop=" in f

def test_persistence_password_and_session(tmp_path,monkeypatch):
    monkeypatch.setenv("CLIPORA_DB_PATH",str(tmp_path/"clipora.db"))
    import importlib
    import studio.persistence as p
    p.DB_PATH=tmp_path/"clipora.db"; p.init_db()
    uid=p.create_user("test@example.com","password123")
    user=p.authenticate("test@example.com","password123")
    assert user and user["id"]==uid and user["plan"]=="free"
    token=p.create_session(uid)
    assert p.get_user_by_session(token)["email"]=="test@example.com"

def test_make_ass_contains_arabic_karaoke_tags(tmp_path):
    import studio_app
    tr={"segments":[{"start":0,"end":2,"text":"مرحبا بالعالم","words":[{"start":0,"end":1,"word":"مرحبا"},{"start":1,"end":2,"word":"بالعالم"}]}]}
    out=tmp_path/"a.ass"; studio_app.make_ass(tr,0,2,out,"karaoke")
    text=out.read_text(encoding="utf-8")
    assert "مرحبا" in text and "\\k100" in text
