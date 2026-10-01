import os
import sys
import json
import sqlite3
import subprocess
import tempfile
import wave
import webbrowser
import threading
import time
import base64
from io import BytesIO
from datetime import datetime
import requests
import sounddevice as sd
import speech_recognition as sr
import numpy as np
from duckduckgo_search import DDGS
import customtkinter as ctk
import psutil
from PIL import ImageGrab
import pyautogui
from kokoro_onnx import Kokoro

# Configure PyAutoGUI safety thresholds
pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.5

# Configure CustomTkinter dark theme
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

# --- 1. LOCAL MEMORY SYSTEM ---
DB_PATH = "sakura_memory.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_facts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fact TEXT UNIQUE
        )
    ''')
    conn.commit()
    conn.close()

def save_fact(fact):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT OR IGNORE INTO user_facts (fact) VALUES (?)", (fact,))
        conn.commit()
    finally:
        conn.close()

def get_memories():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT fact FROM user_facts")
    facts = [row[0] for row in cursor.fetchall()]
    conn.close()
    
    if facts:
        return "\nUser Facts:\n" + "\n".join(f"- {f}" for f in facts)
    return ""

# --- 2. KOKORO-82M ONNX NEURAL VOICE ENGINE ---
print("[TTS Engine]: Initializing Kokoro-82M ONNX Voice Engine...")
KOKORO_AVAILABLE = False
kokoro = None

if os.path.exists("kokoro-v0_19.onnx") and os.path.exists("voices.json"):
    try:
        kokoro = Kokoro("kokoro-v0_19.onnx", "voices.json")
        KOKORO_AVAILABLE = True
        print("[TTS Engine]: Kokoro-82M ONNX loaded successfully!")
    except Exception as e:
        print(f"[Kokoro Load Error: {e}] - Falling back to native system speech.")
else:
    print("[TTS Engine]: Kokoro ONNX files not found locally. Falling back to native system speech.")

VOICE_NAME = "af_heart"  # Flagship female voice preset

def speak_neural_stream(gui_instance, text):
    """
    Generates high-fidelity neural audio using Kokoro ONNX and plays it via sounddevice.
    Monitors mic input to allow live user voice interruptions.
    """
    gui_instance.is_speaking = True
    gui_instance.update_status("SPEAKING (Kokoro Neural)...", "#FF007F")
    gui_instance.log_chat("Sakura", text)

    if KOKORO_AVAILABLE and kokoro:
        try:
            samples, sample_rate = kokoro.create(text, voice=VOICE_NAME, speed=1.0, lang="en-us")
            audio_data = (samples * 32767).astype(np.int16)
            sd.play(audio_data, samplerate=sample_rate)
            
            while sd.get_stream().active:
                if not gui_instance.is_speaking:
                    sd.stop()
                    print("[Speech Output Halted by Interruption]")
                    break
                time.sleep(0.05)
        except Exception as e:
            print(f"[Kokoro Playback Error: {e}]")
            gui_instance.fallback_speak(text)
    else:
        gui_instance.fallback_speak(text)

    time.sleep(0.2)
    gui_instance.is_speaking = False

# --- 3. WEB SEARCH, NEWS & SYSTEM DIAGNOSTICS ---
def web_search(query):
    try:
        results = DDGS().text(query, max_results=3)
        if results:
            formatted_results = []
            for i, r in enumerate(results, 1):
                formatted_results.append(f"Source {i}: {r.get('title', '')}\nSummary: {r.get('body', '')}")
            return "\n\n".join(formatted_results)
    except Exception as e:
        print(f"[Web Search Error: {e}]")
    return None

def get_briefing_weather():
    try:
        results = DDGS().text("current weather in Greater Noida Delhi India", max_results=1)
        if results:
            return results[0].get("body", "Weather data currently unavailable.")
    except Exception as e:
        print(f"[Weather Error: {e}]")
    return "Could not retrieve live weather information."

def get_briefing_news():
    try:
        results = DDGS().text("top news headlines India", max_results=3)
        if results:
            headlines = [f"- {r.get('title')}" for r in results]
            return "\n".join(headlines)
    except Exception:
        pass
    return "No live news available."

def get_system_stats():
    cpu = psutil.cpu_percent(interval=0.3)
    ram = psutil.virtual_memory().percent
    battery = psutil.sensors_battery()
    battery_str = f"{battery.percent}%" if battery else "Desktop (N/A)"
    return f"CPU Usage: {cpu}%, RAM Usage: {ram}%, Battery: {battery_str}"

# --- 4. VISION & COMPUTER USE ENGINE ---
def capture_screen_base64():
    try:
        screenshot = ImageGrab.grab()
        screenshot.thumbnail((1024, 1024))
        buffered = BytesIO()
        screenshot.save(buffered, format="JPEG", quality=80)
        return base64.b64encode(buffered.getvalue()).decode('utf-8')
    except Exception as e:
        print(f"[Screen Capture Error: {e}]")
        return None

def analyze_screen_with_llava(prompt="Describe what is currently visible on this screen in 2 brief sentences."):
    img_b64 = capture_screen_base64()
    if not img_b64:
        return "Failed to capture screen image."

    url = "http://localhost:11434/api/generate"
    payload = {
        "model": "llava",
        "prompt": prompt,
        "images": [img_b64],
        "stream": False
    }

    try:
        res = requests.post(url, json=payload, timeout=45)
        if res.status_code == 200:
            return res.json().get("response", "").strip()
    except Exception as e:
        print(f"[LLaVA Error: {e}]")
        return "Unable to reach local LLaVA vision engine."
    return "Failed to analyze screen."

def execute_computer_action(action_type, target_description=None, text_to_type=None):
    screen_width, screen_height = pyautogui.size()
    
    if action_type == "click":
        target_lower = target_description.lower() if target_description else ""
        if "search" in target_lower or "address bar" in target_lower:
            pyautogui.hotkey("ctrl", "l")
            time.sleep(0.3)
            if text_to_type:
                pyautogui.write(text_to_type, interval=0.05)
                pyautogui.press("enter")
            return "Focused search bar."

        try:
            screenshot = ImageGrab.grab()
            buffered = BytesIO()
            screenshot.save(buffered, format="JPEG", quality=90)
            img_b64 = base64.b64encode(buffered.getvalue()).decode('utf-8')
        except Exception:
            return "Failed to capture screen image."

        prompt = (
            f"Locate UI element '{target_description}'. "
            f"Return ONLY JSON containing estimated percentage position: {{\"x_pct\": integer, \"y_pct\": integer}}. "
            f"Scale 0 to 100 where top-left is 0,0."
        )
        
        url = "http://localhost:11434/api/generate"
        payload = {"model": "llava", "prompt": prompt, "images": [img_b64], "stream": False}
        
        try:
            res = requests.post(url, json=payload, timeout=30)
            if res.status_code == 200:
                raw_out = res.json().get("response", "").strip()
                if "{" in raw_out and "}" in raw_out:
                    json_str = raw_out[raw_out.find("{"):raw_out.rfind("}")+1]
                    coords = json.loads(json_str)
                    
                    x_pixel = int((coords.get("x_pct", 50) / 100.0) * screen_width)
                    y_pixel = int((coords.get("y_pct", 50) / 100.0) * screen_height)
                    
                    pyautogui.moveTo(x_pixel, y_pixel, duration=0.8)
                    pyautogui.click()
                    return f"Clicked on {target_description}."
        except Exception as e:
            print(f"[Computer Action Error: {e}]")
            return f"Could not determine coordinates for {target_description}."

    elif action_type == "type":
        if text_to_type:
            time.sleep(0.3)  # Short pause to ensure UI field focus
            pyautogui.write(text_to_type, interval=0.05)
            pyautogui.press("enter")
            return f"Typed: {text_to_type}"

    elif action_type == "scroll_down":
        pyautogui.scroll(-600)
        return "Scrolled down."

    elif action_type == "scroll_up":
        pyautogui.scroll(600)
        return "Scrolled up."

    return "Action unverified."

# --- 5. ROBUST APP LAUNCHERS ---
def open_chrome():
    possible_paths = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
    ]
    for path in possible_paths:
        if os.path.exists(path):
            subprocess.Popen([path])
            return True
    webbrowser.open("https://www.google.com")
    return True

def open_edge():
    try:
        os.system("start msedge")
        return True
    except Exception:
        webbrowser.open("https://www.bing.com")
        return True

def open_spotify():
    spotify_path = os.path.expandvars(r"%AppData%\Spotify\spotify.exe")
    if os.path.exists(spotify_path):
        subprocess.Popen([spotify_path])
        return True
    try:
        os.system("start spotify:")
        return True
    except Exception as e:
        print(f"[Spotify Launch Error: {e}]")
        return False

def open_whatsapp():
    try:
        os.system("start whatsapp:")
        return True
    except Exception as e:
        print(f"[WhatsApp Launch Error: {e}]")
        return False

def open_notepad():
    subprocess.Popen(["notepad.exe"])
    return True

def open_calculator():
    subprocess.Popen(["calc.exe"])
    return True

def open_vscode():
    try:
        os.system("start code")
        return True
    except Exception as e:
        print(f"[VS Code Launch Error: {e}]")
        return False

def open_gmail():
    webbrowser.open("https://mail.google.com")
    return True

# --- 6. GUI APPLICATION CLASS ---
class SakuraGUI(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.is_speaking = False

        self.title("SAKURA AI - Dashboard")
        self.geometry("700x550")
        self.resizable(False, False)

        # Header Title
        self.title_label = ctk.CTkLabel(
            self, text="SAKURA AI AGENT", font=ctk.CTkFont(size=24, weight="bold"), text_color="#1f538d"
        )
        self.title_label.pack(pady=(15, 5))

        # Status Indicator Box
        self.status_box = ctk.CTkFrame(self, fg_color="#1A1A1A", border_width=2, border_color="#00D2FF")
        self.status_box.pack(fill="x", padx=20, pady=10)

        self.status_label = ctk.CTkLabel(
            self.status_box, text="STANDBY (Say 'Wake Up' or 'Sakura')", font=ctk.CTkFont(size=14, weight="bold"), text_color="#00D2FF"
        )
        self.status_label.pack(pady=10)

        # Scrollable Chat Transcript Window
        self.chat_box = ctk.CTkTextbox(self, width=660, height=360, font=ctk.CTkFont(size=13))
        self.chat_box.pack(padx=20, pady=10)
        self.chat_box.configure(state="disabled")

        # Memory Facts Window Trigger
        self.memory_btn = ctk.CTkButton(self, text="View Saved Memory", command=self.show_memory_popup)
        self.memory_btn.pack(pady=(0, 10))

        # Start Agent Runtime Thread
        init_db()
        threading.Thread(target=self.run_agent_loop, daemon=True).start()

    def update_status(self, text, color):
        """Thread-safe UI status updater."""
        self.status_label.configure(text=text, text_color=color)
        self.status_box.configure(border_color=color)

    def log_chat(self, sender, message):
        """Thread-safe chat transcript logger."""
        self.chat_box.configure(state="normal")
        self.chat_box.insert("end", f"{sender}: {message}\n\n")
        self.chat_box.see("end")
        self.chat_box.configure(state="disabled")

    def show_memory_popup(self):
        memories = get_memories() or "No saved memories found."
        popup = ctk.CTkToplevel(self)
        popup.title("Saved Memory Facts")
        popup.geometry("400x300")
        popup.attributes("-topmost", True)

        txt = ctk.CTkTextbox(popup, width=380, height=260)
        txt.pack(padx=10, pady=10)
        txt.insert("end", memories)
        txt.configure(state="disabled")

    def fallback_speak(self, text):
        """Safe fallback using PowerShell to prevent C-level pyttsx3 thread crashes."""
        try:
            clean_text = text.replace('"', '\\"')
            ps_script = f'Add-Type –AssemblyName System.Speech; $speak = New-Object System.Speech.Synthesis.SpeechSynthesizer; $speak.SelectVoiceByHints([System.Speech.Synthesis.VoiceGender]::Female); $speak.Speak("{clean_text}");'
            subprocess.run(["powershell", "-Command", ps_script], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as e:
            print(f"[Fallback Speech Error: {e}]")

    def speak(self, text):
        """Primary voice dispatcher utilizing Kokoro ONNX streaming."""
        speak_neural_stream(self, text)

    def listen_continuous(self, timeout_sec=10):
        """Continuous mic energy monitor with live interrupt detection."""
        sample_rate = 16000
        chunk_samples = int(sample_rate * 0.5)
        energy_threshold = 300
        audio_frames = []
        talking = False
        silent_chunks = 0
        start_time = time.time()

        with sd.InputStream(samplerate=sample_rate, channels=1, dtype='int16') as stream:
            while True:
                data, _ = stream.read(chunk_samples)
                rms = np.sqrt(np.mean(data.astype(np.float32)**2))

                # --- LIVE USER VOICE INTERRUPTION CHECK ---
                if self.is_speaking:
                    if rms > energy_threshold + 150:
                        print("[Interrupt Triggered! Halting Speech Stream...]")
                        self.is_speaking = False
                    time.sleep(0.05)
                    continue

                if not talking and (time.time() - start_time > timeout_sec):
                    return None

                if rms > energy_threshold:
                    if not talking:
                        self.update_status("LISTENING TO VOICE...", "#00FF66")
                        talking = True
                    audio_frames.append(data)
                    silent_chunks = 0
                elif talking:
                    audio_frames.append(data)
                    silent_chunks += 1
                    if silent_chunks > 2:
                        break

        if not audio_frames:
            return None

        recording = np.concatenate(audio_frames, axis=0)
        fd, temp_wav_path = tempfile.mkstemp(suffix=".wav")
        os.close(fd)

        try:
            with wave.open(temp_wav_path, 'wb') as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(sample_rate)
                wf.writeframes(recording.tobytes())

            recognizer = sr.Recognizer()
            with sr.AudioFile(temp_wav_path) as source:
                audio_data = recognizer.record(source)
                recognized_text = recognizer.recognize_google(audio_data)
                print(f"[Recognized Speech]: {recognized_text}")
                return recognized_text
        except Exception:
            return None
        finally:
            if os.path.exists(temp_wav_path):
                try:
                    os.remove(temp_wav_path)
                except OSError:
                    pass

    def ask_ollama(self, prompt, web_context=None):
        now = datetime.now().strftime("%A, %B %d, %Y at %I:%M %p")
        memories = get_memories()

        system_prompt = (
            f"You are Sakura (Synthetic Autonomous Kernel for User Resource Automation), "
            f"an AI assistant created for Ujjwal.\nLive Date/Time: {now}\n{memories}\n"
        )
        if web_context:
            system_prompt += f"\nLIVE CONTEXT:\n{web_context}\n"
        system_prompt += "\nKeep responses concise and direct."

        url = "http://localhost:11434/api/generate"
        payload = {"model": "llama3.2", "prompt": f"System: {system_prompt}\nUser: {prompt}\nSakura:", "stream": False}

        try:
            res = requests.post(url, json=payload, timeout=30)
            if res.status_code == 200:
                return res.json().get("response", "").strip()
        except Exception:
            return "Unable to reach local Ollama engine."
        return "Couldn't process request."

    def run_agent_loop(self):
        while True:
            self.update_status("STANDBY (Say 'Wake Up' or 'Sakura')...", "#00D2FF")
            
            audio_text = self.listen_continuous(timeout_sec=99999)

            if audio_text:
                text_lower = audio_text.lower()

                if "wake up" in text_lower or "wakeup" in text_lower or "wake" in text_lower or "sakura" in text_lower:
                    self.speak("I am Sakura, awake and online. How can I help you, sir?")
                    
                    session_start = time.time()
                    session_timeout = 180  # 3 minutes

                    while time.time() - session_start < session_timeout:
                        remaining_time = int(session_timeout - (time.time() - session_start))
                        self.update_status(f"ACTIVE SESSION ({remaining_time}s remaining)...", "#00FF66")
                        
                        command = self.listen_continuous(timeout_sec=12)

                        if command:
                            session_start = time.time()
                            self.log_chat("You", command)
                            cmd_lower = command.lower()

                            if "exit" in cmd_lower or "sleep" in cmd_lower or "bye" in cmd_lower or "stop" in cmd_lower:
                                self.speak("Going to standby mode.")
                                break

                            # --- COMPLETE SHUTDOWN HANDLER ---
                            if "shutdown sakura" in cmd_lower or "terminate" in cmd_lower or "close sakura" in cmd_lower or "shutdown" in cmd_lower:
                                self.speak("Shutting down Sakura completely. Goodbye, sir!")
                                self.destroy()
                                sys.exit()

                            # --- ROBUST TYPING HANDLER ---
                            elif cmd_lower.startswith("type ") or "type text" in cmd_lower or "type saying" in cmd_lower:
                                text_to_write = command
                                for prefix in ["type text", "type saying", "type"]:
                                    if text_to_write.lower().startswith(prefix):
                                        text_to_write = text_to_write[len(prefix):].strip()
                                        break
                                
                                for suffix in ["and press enter", "and enter", "press enter"]:
                                    if text_to_write.lower().endswith(suffix):
                                        text_to_write = text_to_write[:-len(suffix)].strip()
                                        break

                                if text_to_write:
                                    self.update_status(f"TYPING: {text_to_write}", "#FFCC00")
                                    result = execute_computer_action("type", text_to_type=text_to_write)
                                    self.speak(result)
                                else:
                                    self.speak("Please specify what you would like me to type.")

                            # --- CLICKING & NAVIGATION HANDLERS ---
                            elif "click on" in cmd_lower or "click the" in cmd_lower:
                                target = command.lower().replace("click on", "").replace("click the", "").strip()
                                self.update_status(f"LOCATING & CLICKING: {target}", "#FFCC00")
                                self.speak(f"Locating {target} on screen.")
                                result = execute_computer_action("click", target_description=target)
                                self.speak(result)

                            elif "scroll down" in cmd_lower or "page down" in cmd_lower:
                                self.speak("Scrolling down.")
                                execute_computer_action("scroll_down")

                            elif "scroll up" in cmd_lower or "page up" in cmd_lower:
                                self.speak("Scrolling up.")
                                execute_computer_action("scroll_up")

                            # --- VISION / SCREEN ANALYSIS HANDLER ---
                            elif "analyze my screen" in cmd_lower or "what is on my screen" in cmd_lower or "look at my screen" in cmd_lower or "read screen" in cmd_lower:
                                self.update_status("ANALYZING SCREEN (LLaVA)...", "#FFCC00")
                                self.speak("Capturing screen and analyzing visually.")
                                
                                user_prompt = "Describe what is currently visible on this screen in 2 brief sentences."
                                if "read" in cmd_lower or "explain" in cmd_lower:
                                    user_prompt = f"Analyze this screen capture image and answer: {command}"

                                vision_summary = analyze_screen_with_llava(prompt=user_prompt)
                                self.speak(vision_summary)

                            # --- DAILY BRIEFING COMMAND (WITH LIVE NEWS INTEGRATION) ---
                            elif "good morning" in cmd_lower or "morning briefing" in cmd_lower or "daily briefing" in cmd_lower:
                                self.update_status("GENERATING DAILY BRIEFING...", "#FFCC00")
                                
                                now_str = datetime.now().strftime("%A, %B %d, %Y at %I:%M %p")
                                stats = get_system_stats()
                                weather = get_briefing_weather()
                                news = get_briefing_news()
                                memories = get_memories() or "No saved memory items."

                                prompt = (
                                    f"Prepare a concise 3-4 sentence morning briefing for Ujjwal.\n"
                                    f"Current Date/Time: {now_str}\n"
                                    f"System Diagnostics: {stats}\n"
                                    f"Local Weather: {weather}\n"
                                    f"Top News Headlines: {news}\n"
                                    f"Saved User Memories: {memories}\n\n"
                                    f"Greet Ujjwal as sir, highlight current weather, report system health, summarize 1 top news headline naturally, and mention a stored fact if available."
                                )

                                briefing_response = self.ask_ollama("Give me my morning briefing", web_context=prompt)
                                self.speak(briefing_response)

                            # --- APP COMMAND HANDLERS ---
                            elif "chrome" in cmd_lower:
                                self.speak("Opening Google Chrome.")
                                open_chrome()

                            elif "edge" in cmd_lower:
                                self.speak("Opening Microsoft Edge.")
                                open_edge()

                            elif "spotify" in cmd_lower:
                                self.speak("Opening Spotify.")
                                open_spotify()

                            elif "whatsapp" in cmd_lower or "whats app" in cmd_lower:
                                self.speak("Opening WhatsApp.")
                                open_whatsapp()

                            elif "notepad" in cmd_lower:
                                self.speak("Opening Notepad.")
                                open_notepad()

                            elif "calculator" in cmd_lower or "calc" in cmd_lower:
                                self.speak("Opening Calculator.")
                                open_calculator()

                            elif "vs code" in cmd_lower or "vscode" in cmd_lower or "code" in cmd_lower:
                                self.speak("Opening Visual Studio Code.")
                                open_vscode()

                            elif "gmail" in cmd_lower or "mail" in cmd_lower:
                                self.speak("Opening Gmail.")
                                open_gmail()

                            # --- MEMORY HANDLER ---
                            elif "remember that" in cmd_lower:
                                fact = command.lower().replace("remember that", "").strip()
                                save_fact(fact)
                                self.speak(f"Saved to permanent memory: {fact}")

                            # --- WEB & AI HANDLER ---
                            else:
                                self.update_status("THINKING / SEARCHING...", "#FFCC00")
                                search_keywords = ["search", "who is", "what is", "latest", "news", "today", "weather"]
                                needs_search = any(kw in cmd_lower for kw in search_keywords)

                                web_context = None
                                if needs_search:
                                    web_context = web_search(command)

                                response = self.ask_ollama(command, web_context=web_context)
                                self.speak(response)

                    self.speak("Inactivity detected. Going to standby mode.")

if __name__ == "__main__":
    app = SakuraGUI()
    app.mainloop()