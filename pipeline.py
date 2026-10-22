"""Cautious, explainable candidate indicators; not automatic moderation decisions.
Optional local Whisper ASR requires ENABLE_ASR=true and downloads a model at first use.
"""
import os, re
from functools import lru_cache

RULES = {
    'possible_threat': [r'\b(kill you|hurt you|maar dunga|mar dunga|jaan se maar|tujhe marunga)\b',r'جان سے مار',r'قتل کر'],
    'possible_private_information': [r'\b(?:\+?92[- ]?)?0?3\d{2}[- ]?\d{7}\b',r'\b\+?1[- .]?\(?\d{3}\)?[- .]?\d{3}[- .]?\d{4}\b'],
    'possible_targeted_abuse': [r'\b(teri family|tumhari family|tuhadi family|your family|tuhaday ghar)\b',r'تمہاری فیملی',r'تہاڈی فیملی'],
}
def redact(text):
    for pattern in RULES['possible_private_information']:
        text=re.sub(pattern,'[REDACTED CONTACT]',text,flags=re.I)
    return text

def classify(text):
    indicators=[]
    for tag, patterns in RULES.items():
        for pattern in patterns:
            match=re.search(pattern,text,flags=re.I)
            if match:
                indicators.append({'category':tag,'excerpt':redact(text[max(0,match.start()-45):match.end()+45]),'start_char':match.start()})
                break
    return {'tags':list(dict.fromkeys(i['category'] for i in indicators)), 'indicators':indicators,
            'notes':'Heuristic candidates only. A keyword alone is not proof of harassment. Review intent, target, consent, context and counter-speech.'}

@lru_cache(maxsize=1)
def get_asr():
    from faster_whisper import WhisperModel
    return WhisperModel(os.getenv('ASR_MODEL','tiny'),device='cpu',compute_type='int8')

def transcribe_media(path):
    if os.getenv('ENABLE_ASR','false').lower() != 'true':
        return '', 'not_enabled', 'ASR disabled. Set ENABLE_ASR=true to transcribe uploaded audio/video.'
    try:
        segments,info=get_asr().transcribe(path,beam_size=3,vad_filter=True)
        return ' '.join(s.text.strip() for s in segments),info.language,'Transcription produced by multilingual Whisper; verify dialect, slang, Urdu/Punjabi code-switching.'
    except Exception as exc:
        return '', 'error', f'ASR unavailable: {type(exc).__name__}. Check audio format, ffmpeg and model download.'
