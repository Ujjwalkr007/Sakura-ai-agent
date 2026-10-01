# S.A.K.U.R.A. AI Agent 🌸

**Synthetic Autonomous Kernel for User Resource Automation**

S.A.K.U.R.A. is a 100% local, multimodal AI desktop assistant for Windows built with Python. It features offline neural speech synthesis, computer vision screen analysis, OS action automation, and persistent long-term memory.

---

## 🌟 Key Features

- **Local LLM & Vision:** Powered by Ollama (`llama3.2` and `llava`).
- **Neural Voice Synthesis:** Uses `kokoro-onnx` (82M) with live mic energy monitoring for mid-sentence voice interruption.
- **OS Automation:** Voice dictation, typing, scrolling, and app launching via `pyautogui`.
- **System Telemetry & Briefings:** Aggregates hardware stats (`psutil`), web search (DuckDuckGo), and local weather into dynamic daily briefings.
- **Persistent Memory:** SQLite database integration for long-term fact retention.

---

## 🛠️ Tech Stack

- **Language:** Python 3.12
- **UI Framework:** CustomTkinter
- **Local AI Engine:** Ollama (`llama3.2`, `llava`)
- **Speech Engine:** Kokoro-82M ONNX + Google Speech Recognition
- **Automation:** PyAutoGUI + Subprocess
- **Database:** SQLite3

---

## 🚀 Quickstart

1. **Clone the repository:**
   ```bash
   git clone [https://github.com/YOUR_USERNAME/sakura-ai-agent.git](https://github.com/YOUR_USERNAME/sakura-ai-agent.git)
   cd sakura-ai-agent
