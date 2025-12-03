import os
import subprocess
import json
import io

# import mido
from litellm import completion
from flask import Flask, render_template, request, jsonify, send_file
from midiutil import MIDIFile

app = Flask(__name__)

# --- CONFIGURATION ---
# Optional: Set a default API key via environment variable (can be overridden by client)
example_1 = open("jazz.json", "r").read()


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/generate_midi", methods=["POST"])
def generate_midi():
    data = request.json
    user_prompt = data.get("prompt")
    loop_mode = data.get("loop", False)
    variation_seed = data.get("variation_seed", 0)
    llm_settings = data.get("llm_settings", {})

    # Get LLM configuration from client or fallback to server env
    api_key = llm_settings.get("apiKey")
    model_name = llm_settings.get("modelName")
    provider = llm_settings.get("provider", "gemini")
    base_url = llm_settings.get("baseUrl", "").strip()

    if not api_key:
        return (
            jsonify({"error": "API key not provided. Please configure in settings."}),
            400,
        )

    # Construct full model name with provider prefix
    if provider == "gemini":
        model_name = f"gemini/{model_name}"
    elif provider == "openai":
        model_name = f"openai/{model_name}"
    elif provider == "anthropic":
        model_name = f"anthropic/{model_name}"
    else:
        model_name = "openai/" + model_name

    # Build loop instruction if enabled
    loop_instruction = ""
    if loop_mode:
        loop_instruction = """
    - IMPORTANT: Make this a seamless loop that can repeat smoothly.
    - The last notes should transition naturally back to the first notes.
    - Consider ending on the same chord/notes as the beginning.
    """

    # Add variation instruction for diversity
    variation_instruction = f"""
    - Variation #{variation_seed + 1}: Be creative and make this unique!
    - Try different rhythms, instruments, or note patterns each time.
    """

    # 1. Construct the Prompt
    # We ask Gemini to act as a MIDI composer.
    prompt = (
        f"""
    You are a confident composer for music generation.
    You specialize in creating musical compositions and melodies using MIDI.
    Return as JSON object of tracks, each representing a MIDI track for this description: "{user_prompt}".

    Rules:
    - Each object has 'instrument': Integer 0-127 (General MIDI). 
    - 'volume': Integer 0-127 (loudness of the track). Balance track volumes accordingly (not all maxed out. For example, use 100 for leads, 80 for pads, and 70 for bass).
    - 'notes': Array of objects.
    - 'pitch': Integer 0-127 (60 is Middle C).
    - 'duration': Float (length in beats).
    - 'time': Float (start time in beats).
    - Create engaging musical pieces (8-16 bars).
    - 'tempo': Integer (BPM), set on the first track.
    {loop_instruction}
    {variation_instruction}

***"""
        + """
## 🎶 General MIDI Instrument List (0-127)

### **1. Piano (0-7)**
| Patch # | Instrument Name |
| :---: | :--- |
| **0** | **Acoustic Grand Piano** |
| **1** | **Bright Acoustic Piano** |
| **2** | **Electric Grand Piano** |
| **3** | **Honky-tonk Piano** |
| **4** | **Electric Piano 1** (Rhodes) |
| **5** | **Electric Piano 2** (Chorus Organ) |
| **6** | **Harpsichord** |
| **7** | **Clavinet** |

---

### **2. Chromatic Percussion (8-15)**
| Patch # | Instrument Name |
| :---: | :--- |
| **8** | **Celesta** |
| **9** | **Glockenspiel** |
| **10** | **Music Box** |
| **11** | **Vibraphone** |
| **12** | **Marimba** |
| **13** | **Xylophone** |
| **14** | **Tubular Bells** |
| **15** | **Dulcimer** (Cimbalom) |

---

### **3. Organ (16-23)**
| Patch # | Instrument Name |
| :---: | :--- |
| **16** | **Drawbar Organ** (Hammond) |
| **17** | **Percussive Organ** |
| **18** | **Rock Organ** |
| **19** | **Church Organ** |
| **20** | **Reed Organ** |
| **21** | **Accordion** (French) |
| **22** | **Harmonica** |
| **23** | **Tango Accordion** (Bandoneón) |

---

### **4. Guitar (24-31)**
| Patch # | Instrument Name |
| :---: | :--- |
| **24** | **Acoustic Guitar (Nylon)** |
| **25** | **Acoustic Guitar (Steel)** |
| **26** | **Electric Guitar (Jazz)** |
| **27** | **Electric Guitar (Clean)** |
| **28** | **Electric Guitar (Muted)** |
| **29** | **Overdriven Guitar** |
| **30** | **Distortion Guitar** |
| **31** | **Guitar Harmonics** |

---

### **5. Bass (32-39)**
| Patch # | Instrument Name |
| :---: | :--- |
| **32** | **Acoustic Bass** |
| **33** | **Electric Bass (Finger)** |
| **34** | **Electric Bass (Pick)** |
| **35** | **Fretless Bass** |
| **36** | **Slap Bass 1** |
| **37** | **Slap Bass 2** |
| **38** | **Synth Bass 1** |
| **39** | **Synth Bass 2** |

---

### **6. Strings (40-47)**
| Patch # | Instrument Name |
| :---: | :--- |
| **40** | **Violin** |
| **41** | **Viola** |
| **42** | **Cello** |
| **43** | **Contrabass** |
| **44** | **Tremolo Strings** |
| **45** | **Pizzicato Strings** |
| **46** | **Orchestral Harp** |
| **47** | **Timpani** |

---

### **7. Ensemble (48-55)**
| Patch # | Instrument Name |
| :---: | :--- |
| **48** | **String Ensemble 1** (Slow) |
| **49** | **String Ensemble 2** (Fast) |
| **50** | **Synth Strings 1** |
| **51** | **Synth Strings 2** |
| **52** | **Choir Aahs** |
| **53** | **Voice Oohs** |
| **54** | **Synth Voice** |
| **55** | **Orchestra Hit** |

---

### **8. Brass (56-63)**
| Patch # | Instrument Name |
| :---: | :--- |
| **56** | **Trumpet** |
| **57** | **Trombone** |
| **58** | **Tuba** |
| **59** | **Muted Trumpet** |
| **60** | **French Horn** |
| **61** | **Brass Section** |
| **62** | **Synth Brass 1** |
| **63** | **Synth Brass 2** |

---

### **9. Reed (64-71)**
| Patch # | Instrument Name |
| :---: | :--- |
| **64** | **Soprano Sax** |
| **65** | **Alto Sax** |
| **66** | **Tenor Sax** |
| **67** | **Baritone Sax** |
| **68** | **Oboe** |
| **69** | **English Horn** |
| **70** | **Bassoon** |
| **71** | **Clarinet** |

---

### **10. Pipe (72-79)**
| Patch # | Instrument Name |
| :---: | :--- |
| **72** | **Piccolo** |
| **73** | **Flute** |
| **74** | **Recorder** |
| **75** | **Pan Flute** |
| **76** | **Blown Bottle** |
| **77** | **Shakuhachi** |
| **78** | **Whistle** |
| **79** | **Ocarina** |

---

### **11. Synth Lead (80-87)**
| Patch # | Instrument Name |
| :---: | :--- |
| **80** | **Lead 1 (Square)** |
| **81** | **Lead 2 (Sawtooth)** |
| **82** | **Lead 3 (Calliope)** |
| **83** | **Lead 4 (Chiff)** |
| **84** | **Lead 5 (Charang)** |
| **85** | **Lead 6 (Voice)** |
| **86** | **Lead 7 (5th)** |
| **87** | **Lead 8 (Bass + Lead)** |

---

### **12. Synth Pad (88-95)**
| Patch # | Instrument Name |
| :---: | :--- |
| **88** | **Pad 1 (New Age)** |
| **89** | **Pad 2 (Warm)** |
| **90** | **Pad 3 (Polysynth)** |
| **91** | **Pad 4 (Choir)** |
| **92** | **Pad 5 (Bowed)** |
| **93** | **Pad 6 (Metallic)** |
| **94** | **Pad 7 (Halo)** |
| **95** | **Pad 8 (Sweep)** |

---

### **13. Synth SFX (96-103)**
| Patch # | Instrument Name |
| :---: | :--- |
| **96** | **FX 1 (Rain)** |
| **97** | **FX 2 (Soundtrack)** |
| **98** | **FX 3 (Crystal)** |
| **99** | **FX 4 (Atmosphere)** |
| **100** | **FX 5 (Brightness)** |
| **101** | **FX 6 (Goblins)** |
| **102** | **FX 7 (Echoes)** |
| **103** | **FX 8 (Sci-Fi)** |

---

### **14. Ethnic (104-111)**
| Patch # | Instrument Name |
| :---: | :--- |
| **104** | **Sitar** |
| **105** | **Banjo** |
| **106** | **Shamisen** |
| **107** | **Koto** |
| **108** | **Kalimba** |
| **109** | **Bagpipe** |
| **110** | **Fiddle** |
| **111** | **Shanai** |

---

### **15. Percussive (112-119)**
| Patch # | Instrument Name |
| :---: | :--- |
| **112** | **Tinkle Bell** |
| **113** | **Agogo** |
| **114** | **Steel Drums** |
| **115** | **Woodblock** |
| **116** | **Taiko Drum** |
| **117** | **Melodic Tom** |
| **118** | **Synth Drum** |
| **119** | **Reverse Cymbal** |

---

### **16. Sound Effects (120-127)**
| Patch # | Instrument Name |
| :---: | :--- |
| **120** | **Guitar Fret Noise** |
| **121** | **Breath Noise** |
| **122** | **Seashore** |
| **123** | **Bird Tweet** |
| **124** | **Telephone Ring** |
| **125** | **Helicopter** |
| **126** | **Applause** |
| **127** | **Gunshot** |

***


    JSON Schema:
    {
        "tracks": [
            {
                "tempo": 120,
                "instrument": 0,
                "volume": 127,
                "notes": [
                    {"pitch": 60, "duration": 1.0, "time": 0.0},
                    ...
                ]
            },
            ...
        ]
    }
    """
        # + "\n***\n"
        # + "### Example Output for 'jazz music':\n"
        # + example_1
        # + "\n***\n"
    )

    try:
        # Prepare completion parameters
        completion_params = {
            "model": model_name,
            "messages": [{"role": "user", "content": prompt}],
            "api_key": api_key,
        }

        # Add base_url if provided
        if base_url:
            completion_params["api_base"] = base_url

        response = completion(**completion_params)
        raw = (
            response.choices[0]
            .message.content.replace("\\n", "\n")
            .replace("\\", "")
            .strip()
        )

        try:
            midi_data = json.loads(raw)
        except Exception as e:
            midi_data = json.loads(raw[raw.index("```json") + 7 : raw.rindex("```")])

        # Ensure midi_data is a list
        if not isinstance(midi_data, list):
            midi_data = midi_data.get("tracks", [])

        # 4. Create MIDI File using MidiUtil
        num_tracks = len(midi_data)
        MyMIDI = MIDIFile(num_tracks)

        for track_idx, track_data in enumerate(midi_data):
            channel = track_idx
            time = 0  # In beats
            tempo = track_data.get("tempo", 120)
            program = track_data.get("instrument", 0)
            volume = track_data.get("volume", 100)

            # Sanitize program number (must be 0-127)
            program = max(0, min(127, int(program)))

            # Set tempo only on the first track
            if track_idx == 0:
                MyMIDI.addTempo(track_idx, time, tempo)
            MyMIDI.addProgramChange(track_idx, channel, time, program)

            for note in track_data.get("notes", []):
                p = int(note.get("pitch", 60))
                d = float(note.get("duration", 1))
                t = float(note.get("time", 0))
                # Sanitize pitch (0-127)
                p = max(0, min(127, p))

                MyMIDI.addNote(track_idx, channel, p, t, d, volume)

        # 5. Save to memory buffer
        mem_file = io.BytesIO()
        MyMIDI.writeFile(mem_file)
        mem_file.seek(0)

        return send_file(
            mem_file,
            mimetype="audio/midi",
            as_attachment=True,
            download_name="gemini_music.mid",
        )

    except Exception as e:
        print(f"Error: {e}")
        return jsonify({"error": str(e)}), 500


def separate_channels_and_render(input_midi, soundfont, output_wav):

    # mid = mido.MidiFile(input_midi)
    # cleaned_mid = mido.MidiFile()
    # cleaned_mid.ticks_per_beat = mid.ticks_per_beat

    # print("Remapping channels to fix collision...")

    # # We skip Channel 9 (Index 9 is Channel 10 in MIDI speak)
    # # because that is reserved for DRUMS only.
    # available_channels = [ch for ch in range(16) if ch != 9]

    # current_channel_index = 0

    # for i, track in enumerate(mid.tracks):
    #     new_track = mido.MidiTrack()

    #     # Check if track has notes (ignore empty metadata tracks)
    #     has_notes = any(msg.type == "note_on" for msg in track)

    #     # Assign a unique channel to this track if it has notes
    #     # If it's a metadata track, we don't assign a channel (remains 0 but unused)
    #     track_channel = 0
    #     if has_notes:
    #         if current_channel_index < len(available_channels):
    #             track_channel = available_channels[current_channel_index]
    #             current_channel_index += 1
    #         else:
    #             print(f"Warning: Too many tracks! Track {i} sharing channel.")
    #             track_channel = 0  # Fallback

    #     for msg in track:
    #         # COPY the message so we don't modify the original object in memory
    #         new_msg = msg.copy()

    #         # If it is a channel message, Force the new channel
    #         if not new_msg.is_meta:
    #             if hasattr(new_msg, "channel"):
    #                 new_msg.channel = track_channel

    #         # Still filter out Bank Selects (CC 0/32) just in case
    #         if new_msg.type == "control_change" and new_msg.control in [0, 32]:
    #             continue

    #         new_track.append(new_msg)

    #     cleaned_mid.tracks.append(new_track)

    # # Save the repaired MIDI
    # temp_midi = tmpfile(suffix=".mid", delete=False).name
    # cleaned_mid.save(temp_midi)
    # print(
    #     f"Channels remapped. Track 1->Ch{available_channels[0]}, Track 2->Ch{available_channels[1]}, etc."
    # )

    # Render
    command = [
        "fluidsynth",
        "-ni",
        soundfont,
        input_midi,
        "-F",
        output_wav,
        "-r",
        "44100",
        "-g",
        "1.0",
        "-o",
        "synth.polyphony=512",
    ]

    try:
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode == 0:
            print(f"Success! Saved to {output_wav}")
        else:
            print("FluidSynth Error:", result.stderr)
    finally:
        if os.path.exists(input_midi):
            os.remove(input_midi)


@app.route("/convert_midi_to_wav", methods=["POST"])
def convert_midi_to_wav():

    try:
        # Get the MIDI file from the request
        midi_file = request.files["midi_file"]
        midi_data = midi_file.read()

        open("/tmp/test.mid", "wb").write(midi_data)

        # Convert MIDI to WAV
        separate_channels_and_render(
            input_midi="/tmp/test.mid",
            soundfont="GeneralUserGS.sf3",
            output_wav="/tmp/test.wav",
        )

        # Return the WAV file
        return send_file(
            "/tmp/test.wav",
            mimetype="audio/wav",
            as_attachment=True,
            download_name="output.wav",
        )

    except Exception as e:
        print(f"Error: {e}")
        return jsonify({"error": str(e)}), 500
