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
