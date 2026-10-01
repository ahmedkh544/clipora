from studio_app import rtl_ass_text


def test_rtl_ass_text_wraps_arabic_in_bidi_controls():
    text = rtl_ass_text("مرحبا بالعالم")
    assert text.startswith(chr(0x202b))
    assert text.endswith(chr(0x202c))
