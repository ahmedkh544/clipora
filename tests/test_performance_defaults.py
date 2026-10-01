from shorts_generator.config import LOCAL_WHISPER_MODEL, LOCAL_WHISPER_DEVICE


def test_fast_local_defaults_are_cpu_friendly():
    assert LOCAL_WHISPER_MODEL in {"tiny", "base"}
    assert LOCAL_WHISPER_DEVICE in {"auto", "cpu", "cuda"}


def test_fast_render_profile_is_vertical():
    from studio_app import RENDER_WIDTH, RENDER_HEIGHT, RENDER_PRESET

    assert (RENDER_WIDTH, RENDER_HEIGHT) == (720, 1280)
    assert RENDER_PRESET == "ultrafast"
