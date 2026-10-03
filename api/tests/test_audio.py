import io
import math
import wave
import struct
import pytest
import numpy as np

from api.modules.audio import (
    load_audio,
    compute_mel_spectrogram,
    analyze_audio_forensics,
    process_audio_pipeline
)

def create_synthetic_wav(
    duration: float = 2.0,
    sr: int = 16000,
    inject_hum: bool = False,
    inject_splice: bool = False
) -> bytes:
    buf = io.BytesIO()
    total_samples = int(sr * duration)
    with wave.open(buf, 'wb') as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sr)
        
        samples = []
        for i in range(total_samples):
            t = i / sr
            # Base 440 Hz tone
            val = 0.3 * math.sin(2.0 * math.pi * 440.0 * t)
            
            # Inject 50 Hz electrical hum
            if inject_hum:
                val += 0.4 * math.sin(2.0 * math.pi * 50.0 * t)
            
            # Inject abrupt splice jump at t = 1.0s
            if inject_splice and 0.98 <= t <= 1.02:
                val = 0.95
                
            sample_int = int(np.clip(val, -1.0, 1.0) * 32767.0)
            samples.append(sample_int)

        for s in samples:
            wav.writeframes(struct.pack('<h', s))
            
    return buf.getvalue()

def test_hum_detection_and_measurements():
    wav_bytes = create_synthetic_wav(duration=2.0, inject_hum=True)
    y, sr, duration = load_audio(wav_bytes)
    mel_spec_db, _, _ = compute_mel_spectrogram(y, sr=sr)
    
    findings, cal, stats = analyze_audio_forensics(y, sr, mel_spec_db, duration)

    assert stats["hum_detected"] is True
    assert 48.0 <= stats["hum_frequency_hz"] <= 52.0

    hum_findings = [f for f in findings if "hum" in f.label]
    assert len(hum_findings) == 1
    hf = hum_findings[0]
    assert hf.measurements["center_frequency_hz"] >= 48.0
    assert hf.risk_level in ("medium", "high")
    assert cal.kind == "spectrogram"

def test_splice_detection():
    wav_bytes = create_synthetic_wav(duration=2.0, inject_splice=True)
    y, sr, duration = load_audio(wav_bytes)
    mel_spec_db, _, _ = compute_mel_spectrogram(y, sr=sr)
    
    findings, cal, stats = analyze_audio_forensics(y, sr, mel_spec_db, duration)
    
    splice_findings = [f for f in findings if "splice" in f.label]
    assert len(splice_findings) >= 1
    # Check that splice timestamp is near 1.0s
    sf = splice_findings[0]
    assert abs(sf.measurements["timestamp_s"] - 1.0) <= 0.15

def test_audio_pipeline_end_to_end():
    wav_bytes = create_synthetic_wav(duration=1.5, inject_hum=True)
    findings, cal, vision_img, human_spec, waveform, stats, prov = process_audio_pipeline(wav_bytes)

    assert len(findings) >= 1
    assert vision_img.size[0] > 0
    assert human_spec.size[0] > 0
    assert waveform.size[0] > 0
    assert prov.pipeline_version == "1.0.0"
    assert findings[0].vision is not None
