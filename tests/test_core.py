from studio.core import score_segment, select_highlights, select_narrative_sequence, build_keep_ranges, map_time

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


def test_narrative_sequence_does_not_make_last_part_cover_entire_remainder():
    transcript = {"segments": [
        {"start": i, "end": i + 10, "text": f"story part {i}"}
        for i in range(0, 600, 10)
    ]}
    clips = select_narrative_sequence(transcript, count=5, target_duration=55)
    assert len(clips) == 5
    assert all(c["end_time"] - c["start_time"] <= 70 for c in clips)
    for prev, cur in zip(clips, clips[1:]):
        assert cur["start_time"] == prev["end_time"]


def test_narrative_sequence_starts_at_first_speech_segment():
    transcript = {"segments": [
        {"start": 18, "end": 28, "text": "the story begins here"},
        {"start": 28, "end": 38, "text": "then this happened"},
        {"start": 38, "end": 48, "text": "and then the result"},
    ]}
    clips = select_narrative_sequence(transcript, count=2, target_duration=20)
    assert clips[0]["start_time"] == 18
