import io
import math
import numpy as np
from PIL import Image
import soundfile as sf
import scipy.signal as signal
import matplotlib
matplotlib.use('Agg')
import matplotlib.cm as cm
import matplotlib.pyplot as plt
from typing import Tuple, List, Dict, Any, Optional

from api.core.schema import Calibration, CalibrationAxis, Finding, Provenance, GenerativeStep
from api.core.calibration import hz_to_mel, mel_to_hz, physical_to_pixel, pixel_to_physical
from api.core.vision import run_vision
from api.modules.registry import MODULES

def load_audio(raw_bytes: bytes, target_sr: int = 16000) -> Tuple[np.ndarray, int, float]:
    """
    Loads raw WAV/audio bytes into a mono float32 array normalized to [-1.0, 1.0].
    Returns (signal, sample_rate, duration_seconds).
    """
    with io.BytesIO(raw_bytes) as buf:
        data, sr = sf.read(buf, dtype='float32')

    # Convert to mono if stereo
    if data.ndim > 1:
        data = np.mean(data, axis=1)

    # Resample if sample rate doesn't match target
    if sr != target_sr:
        num_target_samples = int(len(data) * target_sr / sr)
        data = signal.resample(data, num_target_samples)
        sr = target_sr

    duration = float(len(data) / sr)
    return data, sr, duration

def compute_mel_spectrogram(
    y: np.ndarray,
    sr: int = 16000,
    n_fft: int = 1024,
    hop_length: int = 256,
    n_mels: int = 128,
    fmin: float = 0.0,
    fmax: float = 8000.0
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Computes log-mel spectrogram using scipy & numpy.
    Returns: (mel_spec_db, times, mel_freqs)
    """
    # 1. Compute Short-Time Fourier Transform (STFT)
    f, t, Zxx = signal.stft(
        y,
        fs=sr,
        window='hann',
        nperseg=n_fft,
        noverlap=n_fft - hop_length,
        boundary=None
    )
    power_spec = np.abs(Zxx) ** 2

    # 2. Build Mel Filterbank
    mel_min = hz_to_mel(fmin)
    mel_max = hz_to_mel(fmax)
    mel_points = np.linspace(mel_min, mel_max, n_mels + 2)
    hz_points = mel_to_hz(mel_points)

    bin_points = np.floor((n_fft + 1) * hz_points / sr).astype(int)
    fbank = np.zeros((n_mels, int(np.floor(n_fft / 2 + 1))))

    for m in range(1, n_mels + 1):
        f_m_minus = bin_points[m - 1]
        f_m = bin_points[m]
        f_m_plus = bin_points[m + 1]

        for k in range(f_m_minus, f_m):
            if f_m != f_m_minus:
                fbank[m - 1, k] = (k - bin_points[m - 1]) / (f_m - f_m_minus)
        for k in range(f_m, f_m_plus):
            if f_m_plus != f_m:
                fbank[m - 1, k] = (bin_points[m + 1] - k) / (f_m_plus - f_m)

    # 3. Apply Mel Filterbank
    mel_spec = np.dot(fbank, power_spec)
    
    # 4. Convert to Log-scale (dB) relative to max
    ref_val = np.max(mel_spec) if np.max(mel_spec) > 0 else 1.0
    mel_spec_db = 10.0 * np.log10(np.maximum(mel_spec, 1e-10) / ref_val)
    mel_spec_db = np.clip(mel_spec_db, -80.0, 0.0)

    # Invert rows so highest frequency is row 0 (image top)
    mel_spec_db_flipped = np.flipud(mel_spec_db)

    return mel_spec_db_flipped, t, hz_points[1:-1]

def render_spectrogram_image(mel_spec_db: np.ndarray, colormap: str = "magma") -> Image.Image:
    """
    Renders pure axis-free vision render from log-mel spectrogram.
    """
    norm = np.clip((mel_spec_db + 80.0) / 80.0, 0.0, 1.0)
    cmap = plt.get_cmap(colormap)
    rgba = cmap(norm)
    rgb = (rgba[:, :, :3] * 255).astype(np.uint8)
    return Image.fromarray(rgb)

def render_human_spectrogram(
    mel_spec_db: np.ndarray,
    duration: float,
    fmax: float = 8000.0,
    width_px: int = 800,
    height_px: int = 400
) -> Image.Image:
    """
    Renders human-readable spectrogram with labeled time and frequency axes.
    """
    fig, ax = plt.subplots(figsize=(width_px / 100, height_px / 100), dpi=100)
    extent = [0, duration, 0, fmax]
    im = ax.imshow(
        mel_spec_db,
        aspect='auto',
        origin='upper',
        extent=extent,
        cmap='magma',
        vmin=-80,
        vmax=0
    )
    ax.set_xlabel("Time (s)", fontsize=10)
    ax.set_ylabel("Frequency (Hz)", fontsize=10)
    ax.set_title("Mel Spectrogram Analysis (0 - 8000 Hz)", fontsize=11, fontweight='bold')
    plt.colorbar(im, ax=ax, label="dB (relative to peak)")
    plt.tight_layout()

    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=100)
    plt.close(fig)
    buf.seek(0)
    return Image.open(buf)

def render_waveform_image(y: np.ndarray, sr: int, width_px: int = 800, height_px: int = 150) -> Image.Image:
    """
    Renders audio waveform envelope PNG (quicklook companion).
    """
    fig, ax = plt.subplots(figsize=(width_px / 100, height_px / 100), dpi=100)
    times = np.linspace(0, len(y) / sr, len(y))
    ax.plot(times, y, color="#2563eb", linewidth=0.6)
    ax.set_xlim(0, len(y) / sr)
    ax.set_ylim(-1.05, 1.05)
    ax.set_ylabel("Amplitude", fontsize=9)
    ax.set_xlabel("Time (s)", fontsize=9)
    ax.grid(True, linestyle="--", alpha=0.4)
    plt.tight_layout()

    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=100)
    plt.close(fig)
    buf.seek(0)
    return Image.open(buf)

def analyze_audio_forensics(
    y: np.ndarray,
    sr: int,
    mel_spec_db: np.ndarray,
    duration: float
) -> Tuple[List[Finding], Calibration, Dict[str, Any]]:
    """
    Classical DSP Audio Forensics Pipeline:
    1. 50/60 Hz power grid hum detection & harmonic check
    2. Spectral flux outlier discontinuity detection (splice candidates)
    3. Noise floor & SNR estimation
    4. Clipping ratio check
    """
    img_h, img_w = mel_spec_db.shape

    # Calibration Contract
    cal = Calibration(
        kind="spectrogram",
        width_px=img_w,
        height_px=img_h,
        axes={
            "x": CalibrationAxis(unit="s", min=0.0, max=round(duration, 3), scale="linear"),
            "y": CalibrationAxis(unit="Hz", min=0.0, max=8000.0, scale="mel")
        },
        encoding={"sr": sr, "n_fft": 1024, "hop": 256, "db_range": [-80, 0], "colormap": "magma"},
        provenance={"pipeline": "dsp_spectral_flux_hum_v1"}
    )

    findings: List[Finding] = []

    # 1. 50 / 60 Hz Hum Detection
    # Perform high-resolution FFT over entire signal to isolate narrowband hum
    n_hum_fft = 8192
    f_hum, pxx = signal.welch(y, fs=sr, nperseg=min(n_hum_fft, len(y)))
    
    # Check 50Hz band (48-52 Hz) and 60Hz band (58-62 Hz)
    idx_50 = np.where((f_hum >= 48.0) & (f_hum <= 52.0))[0]
    idx_60 = np.where((f_hum >= 58.0) & (f_hum <= 62.0))[0]
    idx_surround = np.where((f_hum >= 30.0) & (f_hum <= 80.0))[0]

    hum_found = False
    hum_freq = 0.0
    hum_prominence_db = 0.0

    if len(idx_surround) > 0:
        local_baseline = float(np.median(pxx[idx_surround])) + 1e-12

        if len(idx_50) > 0 and np.max(pxx[idx_50]) / local_baseline > 6.0:
            hum_found = True
            hum_freq = float(f_hum[idx_50[np.argmax(pxx[idx_50])]])
            hum_prominence_db = float(10.0 * np.log10(np.max(pxx[idx_50]) / local_baseline))
        elif len(idx_60) > 0 and np.max(pxx[idx_60]) / local_baseline > 6.0:
            hum_found = True
            hum_freq = float(f_hum[idx_60[np.argmax(pxx[idx_60])]])
            hum_prominence_db = float(10.0 * np.log10(np.max(pxx[idx_60]) / local_baseline))

    if hum_found:
        # Bounding box spans time [0.0, duration] and freq [hum_freq - 15, hum_freq + 15]
        phys_x = (0.0, float(duration))
        phys_y = (float(max(0.0, hum_freq - 15.0)), float(hum_freq + 15.0))
        px_box = tuple(int(v) for v in physical_to_pixel(cal, physical_x=phys_x, physical_y=phys_y))

        f_hum_finding = Finding(
            id="audio_hum_1",
            label="stationary_hum_anomaly",
            short_label=f"{int(hum_freq)}Hz Hum",
            region_px=px_box,
            region_physical={"x": list(phys_x), "y": list(phys_y), "x_unit": "s", "y_unit": "Hz"},
            measurements={
                "center_frequency_hz": round(float(hum_freq), 1),
                "prominence_db": round(float(hum_prominence_db), 2),
                "grid_type": "50Hz (EU/Asia)" if hum_freq < 55 else "60Hz (US)"
            },
            source="dsp",
            severity=0.75,
            risk_level="high" if hum_prominence_db > 12.0 else "medium"
        )
        findings.append(f_hum_finding)

    # 2. Spectral Flux & Discontinuity Detection (Splice Candidates)
    # Spectral flux across consecutive spectrogram time frames
    # Difference between flipped spectrogram columns
    spec_power = 10.0 ** (mel_spec_db / 10.0)
    flux = np.sum(np.maximum(0, np.diff(spec_power, axis=1)) ** 2, axis=0)

    if len(flux) > 5:
        flux_mean = float(np.mean(flux))
        flux_std = float(np.std(flux))
        flux_thresh = flux_mean + 3.5 * max(flux_std, 1e-6)

        # Detect isolated outlier frames
        peaks, props = signal.find_peaks(flux, height=flux_thresh, distance=int(sr / (256 * 2)))

        for idx, p in enumerate(peaks[:5]):  # Keep top 5 splice candidates
            # Convert frame index to seconds
            t_center = float(p * 256 / sr)
            t_start = max(0.0, t_center - 0.15)
            t_end = min(duration, t_center + 0.15)
            
            phys_x = (float(t_start), float(t_end))
            phys_y = (0.0, 8000.0)  # Broadband vertical slice
            px_box = tuple(int(v) for v in physical_to_pixel(cal, physical_x=phys_x, physical_y=phys_y))

            peak_val = float(props["peak_heights"][idx])
            z_score = round(float((peak_val - flux_mean) / max(flux_std, 1e-6)), 2)

            f_splice = Finding(
                id=f"audio_splice_{idx + 1}",
                label="abrupt_splice_discontinuity",
                short_label=f"Splice @ {t_center:.2f}s",
                region_px=px_box,
                region_physical={"x": [float(phys_x[0]), float(phys_x[1])], "y": [float(phys_y[0]), float(phys_y[1])], "x_unit": "s", "y_unit": "Hz"},
                measurements={
                    "timestamp_s": round(float(t_center), 3),
                    "flux_z_score": float(z_score),
                    "flux_amplitude": round(float(peak_val), 4)
                },
                source="dsp",
                severity=0.8 if z_score > 5.0 else 0.5,
                risk_level="high" if z_score > 5.0 else "medium"
            )
            findings.append(f_splice)

    # 3. Audio Quality Metrics
    # SNR and noise floor estimate from 10th percentile energy
    frame_len = 1024
    num_frames = len(y) // frame_len
    if num_frames > 0:
        frames = y[:num_frames * frame_len].reshape((num_frames, frame_len))
        frame_powers = np.mean(frames ** 2, axis=1)
        noise_p = float(np.percentile(frame_powers, 10)) + 1e-12
        sig_p = float(np.mean(frame_powers)) + 1e-12
        snr_db = round(float(10.0 * np.log10(sig_p / noise_p)), 2)
        noise_floor_db = round(float(10.0 * np.log10(noise_p)), 2)
    else:
        snr_db = 0.0
        noise_floor_db = -80.0

    # Clipping detection
    clip_count = int(np.sum(np.abs(y) >= 0.99))
    clipping_ratio = round(float(clip_count / max(len(y), 1)), 5)

    stats = {
        "duration_s": float(round(duration, 3)),
        "sample_rate": int(sr),
        "snr_db": float(snr_db),
        "noise_floor_db": float(noise_floor_db),
        "clipping_ratio": float(clipping_ratio),
        "hum_detected": bool(hum_found),
        "hum_frequency_hz": float(round(hum_freq, 1)) if hum_found else None,
        "splice_candidates": int(len([f for f in findings if "splice" in f.label]))
    }

    return findings, cal, stats

def process_audio_pipeline(
    raw_bytes: bytes,
    image_url_for_vision: str = ""
) -> Tuple[List[Finding], Calibration, Image.Image, Image.Image, Image.Image, Dict[str, Any], Provenance]:
    """
    End-to-End Pipeline for Module D (Audio Diagnostics):
    1. Loads audio and resamples to 16 kHz
    2. Computes log-mel spectrogram & waveforms
    3. Executes classical DSP: hum isolation, spectral flux splice analysis, noise floor
    4. Vision classification & explanation for detected anomalies
    """
    y, sr, duration = load_audio(raw_bytes, target_sr=16000)
    mel_spec_db, times, freqs = compute_mel_spectrogram(y, sr=sr)

    # Renders
    vision_img = render_spectrogram_image(mel_spec_db)
    human_spec_img = render_human_spectrogram(mel_spec_db, duration=duration)
    waveform_img = render_waveform_image(y, sr=sr)

    # DSP Measurements
    findings, cal, stats = analyze_audio_forensics(y, sr, mel_spec_db, duration)

    # Classify via Vision Provider
    prompt = MODULES["audio"].vision_prompt
    findings = run_vision(image_url_for_vision, findings, prompt)

    # Provenance
    provenance = Provenance(
        pipeline_version="1.0.0",
        deterministic_steps=["welch_hum_isolation", "log_mel_stft", "spectral_flux_peak_detection"],
        generative_steps=[GenerativeStep(step="e_gen_replace", purpose="display only")],
        vision={"provider": "heuristic_fallback", "model": "rule_based_v1", "prompt_version": "audio-v1"}
    )

    return findings, cal, vision_img, human_spec_img, waveform_img, stats, provenance
