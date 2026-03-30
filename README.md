# Aiva – Voice-Controlled Robot Assistant

Ava is a voice‑controlled robot that combines natural language processing on a Mac with motor, sensor, and camera control on a Raspberry Pi.  
The system understands commands, answers questions, navigates autonomously, and recognises faces and emotions.

## Overview

The project is split into two independent parts:

- **Mac Side** – Handles AI, speech recognition, text‑to‑speech, and decision making.  
- **Raspberry Pi Side** – Controls motors, reads ultrasonic sensors, streams camera, and executes commands.

Communication between the two is over TCP/IP using raw PCM audio, JSON commands, and JPEG video frames.

## Features

- **Voice control** – Wake word (“Ava”), continuous speech, and interruption.
- **AI conversation** – Uses Ollama (local) or Gemini for natural responses.
- **Intent classification** – Distinguishes chat, questions, commands.
- **Autonomous navigation** – Obstacle avoidance, random exploration.
- **Real‑time safety** – Emergency stop on obstacle detection.
- **Camera streaming** – Live video to the Mac for face recognition and object detection.
- **Face & emotion recognition** – Recognises known faces and emotions using YOLO, ArcFace, and Mini‑Xception.
- **Remote command execution** – Send movement commands from the Mac to the Pi.

## Architecture

The system is built on two independent machines communicating over a local network.

### Mac Side
- `start_brain.py` – Main orchestrator. Starts TCP servers for audio (STT), TTS, and camera; runs the voice loop.
- `audio_receiver.py` – Wraps `TCPServer` to receive PCM audio from Pi.
- `audio_sender.py` – Sends PCM audio to Pi (for TTS) with pacing.
- `google_stt_client.py` – Google Streaming STT – yields final transcripts.
- `google_tts_client.py` – Google TTS – returns PCM audio.
- `intent_classifier.py` – Rule‑based intent detection (command, question, chat).
- `ai_router.py` – Routes to Ollama or Gemini, cleans responses.
- `planner.py` – Decides mode (CASUAL, MENTOR, GUIDE, etc.) based on intent.
- `context_manager.py` – Maintains conversation history.
- `guide_controller.py` – Step‑by‑step guidance state machine.
- `command_client.py` – Sends structured commands (intents) to Pi.
- `vision/` – Camera receiver, YOLO detection, face recognition, emotion detection, depth estimation.

### Raspberry Pi Side
- `start_pi.py` – Main robot controller. Starts command server, executor, safety loop.
- `start_audio.py` – Microphone capture (USB) and speaker playback (ALSA).
- `start_camera.py` – Camera streaming using `rpicam-vid`.
- `command_server.py` – TCP server receiving JSON commands from Mac.
- `command_executor.py` – Executes MOVE/TURN/STOP commands with safety checks.
- `movement_controller.py` – High‑level motor control (forward/backward/turn).
- `motor_driver.py` – Low‑level GPIO motor control (gpiozero or RPi.GPIO).
- `ultrasonic.py` – Distance readings from HC‑SR04 sensors.
- `adxl345.py` – Accelerometer readings (ADXL345).
- `camera_stream.py` – Captures JPEG frames with `rpicam-vid`.
- `speaker_player.py` – Plays PCM audio using `sounddevice`.
- `usb_mic_stream.py` – Captures PCM from USB microphone.

### Network Communication

| Service      | Port | Direction                |
|--------------|------|--------------------------|
| Audio STT    | 8888 | Pi → Mac (PCM)           |
| Audio TTS    | 8889 | Mac → Pi (PCM)           |
| Commands     | 8890 | Mac ↔ Pi (JSON commands) |
| Camera       | 8891 | Pi → Mac (JPEG frames)   |

## Prerequisites

### Mac
- Python 3.7+
- Google Cloud account with Speech‑to‑Text and Text‑to‑Speech APIs enabled.
- [Ollama](https://ollama.ai/) installed and running (for local LLM).
- (Optional) Gemini API key.

### Raspberry Pi
- Raspberry Pi 4B (or 3B+)
- Raspberry Pi OS (Debian Bookworm) with Python 3.7+
- Hardware:
  - USB microphone
  - USB or CSI camera
  - 2x DC motors + motor driver (e.g. L298N)
  - 3x HC‑SR04 ultrasonic sensors (front, left, right)
  - ADXL345 accelerometer (optional)
- Wi‑Fi or Ethernet connection

## Installation

### 1. Clone the repository
```bash
git clone https://github.com/yourusername/ava-robot.git
cd ava-robot
Mac side setup
```
2. Mac side setup
```bash
cd mac
python -m venv venv
source venv/bin/activate
pip install -r requirements-mac.txt
```
Set environment variables for Google APIs:
```bash
export GOOGLE_APPLICATION_CREDENTIALS="/path/to/your/service-account-key.json"
```
If using Gemini, also:
```bash
export GOOGLE_API_KEY="your-gemini-api-key"
```
3. Raspberry Pi side setup
```bash
cd pi
python -m venv venv
source venv/bin/activate
pip install -r requirements-pi.txt
```
Install system dependencies:

```bash
sudo apt update
sudo apt install -y python3-gpiozero python3-rpi.gpio portaudio19-dev python3-pyaudio
```
For camera:

```bash
sudo apt install -y libcamera-apps
```
For YOLO (on Pi, optional):

```bash
pip install ultralytics
```
For face recognition models (download and place in vision/models/):

arcface.onnx (rename appropriately)

emotion_mini_xception.h5 (or from a trained model)

yolov8n.pt

4. Configuration
Edit config/network_config.py on both sides to set the Mac’s IP address (replace MAC_HOST).
On the Pi, also set MAC_HOST in config/network_config.py (or in network_config.yaml).

Usage
Start the Mac brain
```bash
cd mac
python start_brain.py
```
The brain will start TCP servers and wait for connections from the Pi.

Start the Raspberry Pi subsystems
In separate terminals (or via start_all.py):

Pi controller (handles commands, motors, sensors):

```bash
cd pi
python start_pi.py
```
This starts a command server on port 8890.

Audio streaming (microphone → Mac, speaker ← Mac):

```bash
cd pi
python start_audio.py
```
This connects to Mac on port 8888 (send mic) and 8889 (receive TTS).

Camera streaming (optional):

```bash
cd pi
python start_camera.py
```
This connects to Mac on port 8891 and sends JPEG frames.

You can also use the master launcher to start all Pi subsystems at once:

```bash
cd pi
python start_all.py
```
Interacting with Ava
Once all services are running, say the wake word “Ava” followed by a command or question.
Examples:

“Ava, move forward 2 meters”

“Ava, what’s the weather like?”

“Ava, turn left”

“Ava, tell me a joke”

“Ava, stop”

“Ava, explain step by step how to bake a cake”

The system will process your request, generate a response, and speak it back through the Pi’s speaker.
If you give a movement command, the Pi will execute it with obstacle avoidance.

Safety & Obstacle Avoidance
The Pi continuously checks the front ultrasonic sensor when moving forward (or during arc turns).

If an obstacle is detected within the safe distance (40 cm in manual mode, 25 cm in autonomous), an emergency stop is triggered.

Backward movement has no safety block.

The system also has a dead‑man timeout: if no command is received for 1.5 seconds while moving, it stops.

Customising AI Responses
You can replace the system prompt for Ollama by editing ai_models/ollama/system_prompt.txt on the Mac.

To use Gemini, set GOOGLE_API_KEY and ensure google-genai is installed. The AIRouter will automatically use Gemini for QUESTION intents.

Intent classification is rule‑based; you can extend intent_classifier.py with new keywords.

Troubleshooting
No audio from speaker: Check ALSA devices (aplay -L). Ensure the speaker is connected and the correct device is set in audio_config.yaml (default hw:0,0).

Microphone not working: Run arecord -L to list devices. The USB mic is usually hw:3,0. Test with arecord -D hw:3,0 -f S16_LE -r 44100 -c 1 -t wav test.wav.

Connection refused: Make sure the Mac is reachable from the Pi (ping). Check firewall settings on Mac.

Obstacle not detected: Test the ultrasonic sensors with the ultrasonic.py script. Verify wiring.

Camera not streaming: Run rpicam-vid -t 0 --codec mjpeg -o - | dd of=/dev/null to test.

License
This project is released under the MIT License. See LICENSE for details.

Acknowledgements
Google Cloud Speech‑to‑Text and Text‑to‑Speech

Ollama for local LLM inference

Ultralytics YOLO

ArcFace and InsightFace for face embeddings

TensorFlow/Keras for emotion model

OpenCV and PyTorch

sounddevice and PyAudio

gpiozero and RPi.GPIO
