"""LLM highlight selection pipeline retained for API mode."""
import json
import re
from . import muapi
CONTENT_TYPE_PROMPT='Analyze this video transcript sample and classify the content type. Respond with JSON only.'
VIRALITY_CRITERIA='HOOK MOMENTS, emotional peaks, revelations, conflict, quotables, story peaks, practical value.'
HIGHLIGHT_SYSTEM_PROMPT='You are an elite short-form video editor. Identify complete viral-worthy highlights. Return ONLY valid JSON.'
CHUNK_SIZE_SECONDS=1200
LONG_VIDEO_THRESHOLD=1800
CHUNK_OVERLAP_SECONDS=60
GPT_CALL_TIMEOUT_SECONDS=300
MAX_HIGHLIGHT_API_ATTEMPTS=3
def _parse_json_loose(raw):
    text=raw.strip(); text=re.sub(r'^```(?:json)?\s*','',text); text=re.sub(r'\s*```$','',text)
    try:return json.loads(text)
    except json.JSONDecodeError:
        start=text.find('{'); end=text.rfind('}')
        if start!=-1 and end!=-1:return json.loads(text[start:end+1])
        raise
def build_transcript_text(transcript): return '\n'.join(f"[{s['start']:.1f}s] {s['text'].strip()}" for s in transcript.get('segments',[]))
def call_muapi_llm(prompt):
    result=muapi.run('gpt-5-mini',{'prompt':prompt},label='gpt-5-mini',timeout=GPT_CALL_TIMEOUT_SECONDS)
    outputs=result.get('outputs')
    if isinstance(outputs,list) and outputs and isinstance(outputs[0],str):return outputs[0]
    for key in ('output','text','response','result','content'):
        v=result.get(key)
        if isinstance(v,str) and v.strip():return v
        if isinstance(v,dict) and isinstance(v.get('text') or v.get('content'),str):return v.get('text') or v.get('content')
    raise RuntimeError(f'Could not extract gpt text: {result}')
def _sanitize_highlights(raw,duration):
    out=[]
    for item in raw if isinstance(raw,list) else []:
        if not isinstance(item,dict):continue
        try:start=float(item.get('start_time')); end=float(item.get('end_time'))
        except (TypeError,ValueError):continue
        if start<0 or end<=start:continue
        end=min(end,duration) if duration>0 else end
        if end<=start:continue
        out.append({'title':str(item.get('title') or 'Untitled Highlight').strip(),'start_time':start,'end_time':end,'score':max(0,min(100,int(float(item.get('score',0))))),'hook_sentence':str(item.get('hook_sentence') or '').strip(),'virality_reason':str(item.get('virality_reason') or '').strip()})
    return out
def detect_content_type(transcript,llm_fn=call_muapi_llm):
    sample=' '.join(s['text'] for s in transcript.get('segments',[])[:25])[:3000]
    try:return _parse_json_loose(llm_fn(f'{CONTENT_TYPE_PROMPT}\nTranscript sample:\n{sample}'))
    except Exception:return {'content_type':'other','density':'medium'}
def chunk_transcript(transcript):
    segs=transcript.get('segments',[]); duration=transcript.get('duration',segs[-1]['end'] if segs else 0); chunks=[]; start=0
    while start<duration:
        end=min(start+CHUNK_SIZE_SECONDS,duration); ss=[s for s in segs if s['start']>=start and s['end']<=end+CHUNK_OVERLAP_SECONDS]
        if ss:
            chunk=dict(transcript); chunk['segments']=ss; chunk['duration']=end-start; chunk['_offset']=start; chunks.append(chunk)
        start+=CHUNK_SIZE_SECONDS-CHUNK_OVERLAP_SECONDS
    return chunks
def call_highlight_api(transcript_text,content_info,duration,num_clips,is_chunk=False,llm_fn=call_muapi_llm):
    system=HIGHLIGHT_SYSTEM_PROMPT+f"\nContent type: {content_info.get('content_type','other')} | Density: {content_info.get('density','medium')}\nGenerate complete clips."
    prompt=f'{system}\n\n{transcript_text}'
    for attempt in range(MAX_HIGHLIGHT_API_ATTEMPTS):
        raw=llm_fn(prompt)
        try:
            parsed=_parse_json_loose(raw); highlights=_sanitize_highlights(parsed.get('highlights'),duration)
            if highlights:return {'highlights':highlights}
        except Exception:pass
        prompt+= '\nIMPORTANT: valid JSON only with highlights array.'
    raise RuntimeError('Highlight generator produced invalid output')
def dedupe_highlights(highlights):
    kept=[]
    for h in sorted(highlights,key=lambda x:int(x.get('score',0)),reverse=True):
        hs,he=float(h['start_time']),float(h['end_time']); hd=he-hs
        if not any((min(he,float(k['end_time']))-max(hs,float(k['start_time'])))>0.5*hd for k in kept):kept.append(h)
    return kept
def get_highlights(transcript,num_clips=3,llm_fn=None):
    llm_fn=llm_fn or call_muapi_llm; duration=transcript.get('duration',0); info=detect_content_type(transcript,llm_fn)
    if duration>=LONG_VIDEO_THRESHOLD:
        all_h=[]
        for chunk in chunk_transcript(transcript):
            off=chunk.get('_offset',0); result=call_highlight_api(build_transcript_text(chunk),info,chunk['duration'],num_clips,True,llm_fn)
            for h in result.get('highlights',[]):h['start_time']+=off;h['end_time']+=off;all_h.append(h)
        return {'highlights':dedupe_highlights(all_h)}
    return {'highlights':dedupe_highlights(call_highlight_api(build_transcript_text(transcript),info,duration,num_clips,False,llm_fn).get('highlights',[]))}
