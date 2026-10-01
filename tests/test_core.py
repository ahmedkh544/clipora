from studio.core import score_segment, select_highlights, select_narrative_sequence, build_keep_ranges, map_time, choose_scene_aware_boundary, detect_visual_scene_boundaries
from studio.toolbox import detect_with_transnetv2, refine_boundary_with_waveform, refine_narrative_boundaries, run_frameshift, run_autocaption, video_conveyor_available, openshorts_available, steezy_available, broll_search_available

def test_hook_language_scores_above_plain_text():
    assert score_segment("Nobody knows the secret mistake that changed everything!") > score_segment("Today we discuss the weather.")

def test_highlights_are_ranked_and_non_overlapping():
    transcript={"segments":[
        {"start":0,"end":10,"text":"plain discussion"},
        {"start":55,"end":68,"text":"Nobody knows this secret and it changed everything!"},
        {"start":90,"end":103,"text":"another ordinary discussion"},
    ]}
    out=select_highlights(transcript,2)
    assert len(out)==2
    assert out[0]["score"] >= out[1]["score"]
    assert out[0]["end_time"] <= out[1]["start_time"] or out[1]["end_time"] <= out[0]["start_time"]

def test_short_transcript_segments_are_grouped_into_highlight_windows():
    transcript={"segments":[
        {"start":0,"end":4.5,"text":"This is a real speech test."},
        {"start":4.5,"end":10,"text":"The system should detect this spoken hook."},
        {"start":10,"end":12,"text":"Saving time is the goal."},
    ]}
    out=select_highlights(transcript,1)
    assert len(out)==1
    assert out[0]["end_time"] >= 12

def test_narrative_sequence_is_contiguous_and_ordered():
    transcript={"segments":[
        {"start":0,"end":5,"text":"Beginning of the story."},
        {"start":5,"end":12,"text":"Then the first event happens."},
        {"start":12,"end":20,"text":"After that the second event happens."},
        {"start":20,"end":29,"text":"Finally the consequence is revealed."},
    ]}
    out=select_narrative_sequence(transcript,3,target_duration=10)
    assert len(out)==3
    assert out[0]["start_time"] == 0
    assert out[0]["end_time"] <= out[1]["start_time"]
    assert out[1]["end_time"] <= out[2]["start_time"]

def test_keep_ranges_remove_long_silence_and_map_time():
    tr={"segments":[
        {"start":0,"end":4,"text":"one"},
        {"start":4.3,"end":6,"text":"two"},
        {"start":8,"end":10,"text":"three"},
    ]}
    ranges=build_keep_ranges(tr,0,12,min_gap=0.7)
    assert ranges == [(0.0,6.0),(8.0,10.0)]
    assert map_time(8,ranges)==6.0
    assert map_time(9,ranges)==7.0

def test_narrative_sequence_prefers_arabic_sentence_boundary_without_english_word_rules():
    transcript={"segments":[
        {"start":0,"end":24,"text":"في البداية نعرض المشكلة التي حدثت."},
        {"start":24,"end":31,"text":"ثم نصل إلى النقطة المهمة،"},
        {"start":31,"end":39,"text":"وهنا تبدأ القصة الحقيقية بعد ذلك."},
        {"start":39,"end":48,"text":"وفي النهاية تظهر النتيجة."},
    ]}
    clips=select_narrative_sequence(transcript,count=2,target_duration=30,total_duration=48)
    assert clips[0]["end_time"] == 24


def test_full_video_narrative_uses_speech_structure_but_preserves_exact_coverage():
    transcript={"segments":[
        {"start":0,"end":21,"text":"هذه بداية القصة وفيها تفاصيل كثيرة."},
        {"start":21,"end":31,"text":"ثم ننتقل إلى حدث جديد بعد صمت واضح."},
        {"start":31,"end":43,"text":"وتستمر الأحداث حتى نصل إلى النهاية."},
        {"start":43,"end":50,"text":"وهنا تظهر الخلاصة."},
    ]}
    clips=select_narrative_sequence(transcript,count=2,target_duration=None,total_duration=50)
    assert len(clips)==2
    assert clips[0]["start_time"] == 0
    assert clips[0]["end_time"] == clips[1]["start_time"]
    assert clips[-1]["end_time"] == 50
    assert clips[0]["end_time"] == 21


def test_narrative_sequence_partitions_the_entire_story_into_requested_count():
    transcript={"segments":[
        {"start":i,"end":i+10,"text":f"story part {i}"}
        for i in range(0,1500,10)
    ]}
    clips=select_narrative_sequence(transcript,count=8,target_duration=None)
    assert len(clips)==8
    assert clips[0]["start_time"] == 0
    assert clips[-1]["end_time"] == 1500
    for prev,cur in zip(clips,clips[1:]):
        assert cur["start_time"] == prev["end_time"]
    durations=[c["end_time"]-c["start_time"] for c in clips]
    assert max(durations)-min(durations) <= 30

def test_narrative_sequence_with_source_duration_covers_leading_and_trailing_non_speech():
    transcript={"segments":[
        {"start":20,"end":30,"text":"the story begins"},
        {"start":60,"end":70,"text":"the story continues"},
        {"start":110,"end":120,"text":"the story ends"},
    ]}
    clips=select_narrative_sequence(transcript,count=4,target_duration=None,total_duration=120)
    assert len(clips)==4
    assert clips[0]["start_time"] == 0
    assert clips[-1]["end_time"] == 120
    for prev,cur in zip(clips,clips[1:]):
        assert cur["start_time"] == prev["end_time"]

def test_narrative_sequence_starts_at_first_speech_segment():
    transcript={"segments":[
        {"start":18,"end":28,"text":"the story begins here"},
        {"start":28,"end":38,"text":"then this happened"},
        {"start":38,"end":48,"text":"and then the result"},
    ]}
    clips=select_narrative_sequence(transcript,count=2,target_duration=20)
    assert clips[0]["start_time"] == 18

def test_narrative_sequence_prefers_a_nearby_scene_break_over_an_early_sentence_end():
    transcript={"segments":[
        {"start":0,"end":30,"text":"The setup explains what happened."},
        {"start":30,"end":48,"text":"The investigation reaches a turning point."},
        {"start":50,"end":56,"text":"The next scene begins after a clear pause"},
        {"start":56,"end":65,"text":"and the story continues from there."},
    ]}
    clips=select_narrative_sequence(transcript,count=2,target_duration=55)
    assert clips[0]["end_time"] == 56

def test_narrative_sequence_avoids_boundary_before_a_continuation_clause():
    transcript={"segments":[
        {"start":0,"end":20,"text":"The decision looked simple on paper."},
        {"start":20,"end":30,"text":"But the result was different because."},
        {"start":30,"end":42,"text":"because the market changed overnight."},
        {"start":42,"end":55,"text":"That forced the team to change direction."},
    ]}
    clips=select_narrative_sequence(transcript,count=2,target_duration=32)
    assert clips[0]["end_time"] == 42

def test_scene_aware_boundary_prefers_nearby_visual_scene_change():
    scene_boundaries=[48.0,56.0,74.0]
    boundary=choose_scene_aware_boundary(50.0,scene_boundaries,45.0,70.0)
    assert boundary == 56.0

def test_visual_scene_detector_returns_ordered_boundaries_for_real_video():
    from pathlib import Path
    boundaries=detect_visual_scene_boundaries(str(Path(__file__).parents[1]/"studio_test.mp4"))
    assert boundaries == sorted(boundaries)
    assert all(x >= 0 for x in boundaries)

def test_optional_transnetv2_integration_is_safe_when_not_installed():
    assert detect_with_transnetv2("missing.mp4") == []

def test_waveform_refinement_returns_a_real_boundary():
    from pathlib import Path
    desired=refine_boundary_with_waveform(str(Path(__file__).parents[1]/"studio_test.mp4"), 3.0)
    assert 1.5 <= desired <= 4.5

def test_frameshift_adapter_is_safe_when_cli_is_absent():
    ok,_=run_frameshift("missing.mp4","out.mp4")
    assert ok is False

def test_autocaption_adapter_is_safe_when_cli_is_absent():
    ok,_=run_autocaption("missing.mp4","out.mp4")
    assert ok is False

def test_open_source_pipeline_adapters_are_safe_without_vendor_checkouts():
    assert video_conveyor_available() is False
    assert openshorts_available() is False
    assert steezy_available() is False
    assert broll_search_available() is False

def test_waveform_refinement_preserves_narrative_continuity():
    clips=[{"start_time":0.0,"end_time":3.0},{"start_time":3.0,"end_time":6.0},{"start_time":6.0,"end_time":9.0}]
    out=refine_narrative_boundaries("missing.mp4",clips)
    assert out[1]["start_time"] == out[0]["end_time"]
    assert out[2]["start_time"] == out[1]["end_time"]
