# Ava – Voice-Controlled Robot Assistant

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

```mermaid
graph TD
    subgraph Raspberry Pi
        USB_Mic --> AudioStream
        AudioStream --> TCP_Client[TCP Client (8888)]
        TCP_Server[TCP Server (8890)] --> CommandExecutor
        CommandExecutor --> Motors & Ultrasonic
        CameraStream --> TCP_Client_Cam[TCP Client (8891)]
    end
    subgraph Mac
        TCP_Server_Stt[TCP Server (8888)] --> AudioReceiver
        AudioReceiver --> STT[Google Speech‑to‑Text]
        STT --> Brain
        Brain --> Planner & AI_Router
        AI_Router --> TTS[Google Text‑to‑Speech]
        TTS --> AudioSender --> TCP_Client_TTS[TCP Client (8889)]
        TCP_Server_Cam[TCP Server (8891)] --> Vision
        Vision --> Face/Emotion Recognition
        Vision --> Object Detection (YOLO)
        Vision --> Depth Estimation
        Vision --> SceneState
        SceneState --> Brain
        Planner --> CommandClient[TCP Client (8890)] --> TCP_Server_Pi[TCP Server (8890) on Pi]
    end
