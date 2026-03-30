import wave

BEEP_PATH = "assets/sounds/listen_beep.wav"


def play_beep(audio_sender):
    """
    Sends a very short beep through existing TTS TCP channel.
    Pads audio to full frames and resets sender so audio is not dropped.
    """
    try:
        with wave.open(BEEP_PATH, "rb") as wf:
            data = wf.readframes(wf.getnframes())

        # ✅ IMPORTANT: reset sender after any stop()
        audio_sender.reset()

        # ✅ FRAME ALIGNMENT
        frame_bytes = audio_sender.FRAME_BYTES
        remainder = len(data) % frame_bytes

        if remainder != 0:
            padding = frame_bytes - remainder
            data += b"\x00" * padding

        audio_sender.stream_paced(data)

    except Exception as e:
        print(f"[BEEP] Failed: {e}")
