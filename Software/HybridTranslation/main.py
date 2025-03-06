import sys
import os
import random
import json
import asyncio
import difflib
import pyttsx3  # For text-to-speech

from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QListWidget, QListWidgetItem,
    QSlider, QTextEdit, QSpinBox, QFileDialog, QComboBox, QTabWidget,
    QCheckBox, QFrame, QMessageBox
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QObject

# Import googletrans (ensure version 4.0.0-rc1 is installed)
from googletrans import Translator, LANGUAGES

# --- Helper: Parse language input (accepts code, full name, or unique prefix) ---
def parse_language(input_str):
    s = input_str.strip().lower()
    if not s:
        return None
    # Direct code match.
    if s in LANGUAGES:
        return s
    # Full language name match.
    for code, name in LANGUAGES.items():
        if s == name.lower():
            return code
    # Check if s is a unique prefix.
    matches = [code for code, name in LANGUAGES.items() if name.lower().startswith(s)]
    if len(matches) == 1:
        return matches[0]
    # Allow common abbreviations.
    mapping = {
        "eng": "en",
        "hindi": "hi",
        "hin": "hi",
        "urdu": "ur",
        "bangla": "bn",
        "ben": "bn"
    }
    if s in mapping:
        return mapping[s]
    return None

# --- Worker for asynchronous translation chain ---
class TranslationWorker(QObject):
    # Each chain element: (round_number, language_code, translated_text, pronunciation)
    finished = pyqtSignal(list, str)   # Emits (chain_list, final_output)
    progress = pyqtSignal(list)          # Emits current chain list (live update)
    error = pyqtSignal(str)

    def __init__(self, original_text, language_chain, num_rounds, freq_value):
        """
        original_text: the text to translate.
        language_chain: ordered list of language codes from fixed slots.
        num_rounds: total rounds (if > len(language_chain), extra rounds use random languages).
        freq_value: 0-100; determines final output selection based on similarity.
                   0 = most similar (minimal change), 100 = most different.
        """
        super().__init__()
        self.original_text = original_text
        self.language_chain = language_chain
        self.num_rounds = num_rounds
        self.freq_value = freq_value

    def run(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            chain, final_output = loop.run_until_complete(self.async_translate_chain())
            self.finished.emit(chain, final_output)
        except Exception as ex:
            self.error.emit(str(ex))
        finally:
            loop.close()

    async def async_translate_chain(self):
        translator = Translator()
        chain = []  # Each element: (round_number, language_code, translated_text, pronunciation)
        current_text = self.original_text

        # Round 0: Original text (no pronunciation available; shown as N/A)
        chain.append((0, "auto", current_text, "N/A"))
        total_rounds = self.num_rounds

        for i in range(1, total_rounds + 1):
            # Use fixed slot language if available; otherwise, choose a random language.
            if i <= len(self.language_chain):
                target_lang = self.language_chain[i - 1]
            else:
                target_lang = random.choice(list(LANGUAGES.keys()))
            try:
                result = await translator.translate(current_text, dest=target_lang)
                current_text = result.text
                # Use the pronunciation provided by the result if available.
                pron = result.pronunciation if result.pronunciation else "N/A"
                chain.append((i, target_lang, current_text, pron))
            except Exception as e:
                chain.append((i, target_lang, f"Error: {e}", "N/A"))
                break
            self.progress.emit(chain.copy())

        # Compute similarity ratios between original text and each round's translated text.
        similarities = []
        for round_num, lang, text, _ in chain:
            ratio = difflib.SequenceMatcher(None, self.original_text, text).ratio()
            similarities.append(ratio)
        max_sim = max(similarities)
        min_sim = min(similarities)
        # Map freq_value (0 means most similar, 100 means least similar).
        desired = max_sim - (self.freq_value / 100) * (max_sim - min_sim)
        # Find the round whose similarity is closest to desired.
        best_index = min(range(len(similarities)), key=lambda i: abs(similarities[i] - desired))
        final_output = chain[best_index][2]
        return chain, final_output

# --- Worker for Text-to-Speech in a Separate Thread ---
class SpeechWorker(QThread):
    def __init__(self, text, parent=None):
        super().__init__(parent)
        self.text = text

    def run(self):
        engine = pyttsx3.init()
        engine.say(self.text)
        engine.runAndWait()

# --- Main Application Window ---
class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Dynamic Translation Chain")
        self.history = []  # List to store previous runs.
        self.language_slots = []  # List of tuples: (slot_number, language_code)
        self.final_output_text = ""
        self.setup_ui()
        self.worker_thread = None
        self.speech_thread = None

    def setup_ui(self):
        # --- Overall Color & Style Setup via Stylesheet ---
        self.setStyleSheet("""
            QWidget { background-color: #f5f5f5; font-family: Arial; font-size: 14px; color: #333; }
            QLineEdit, QTextEdit, QSpinBox, QComboBox { background-color: #fff; border: 1px solid #ccc; padding: 6px; }
            QPushButton { background-color: #4285f4; color: #fff; border: none; padding: 8px 12px; border-radius: 4px; }
            QPushButton:hover { background-color: #357ae8; }
            QTabWidget::pane { border: 1px solid #ccc; }
            QTabBar::tab { background: #ddd; padding: 10px; margin: 2px; border-radius: 4px; }
            QTabBar::tab:selected { background: #4285f4; color: #fff; }
            QCheckBox { padding: 4px; }
            QListWidget { background-color: #fff; }
        """)

        # --- Create Main Tabs ---
        self.tabs = QTabWidget()
        self.translation_tab = QWidget()
        self.history_tab = QWidget()
        self.tabs.addTab(self.translation_tab, "Translation")
        self.tabs.addTab(self.history_tab, "History")

        # ---- Translation Tab Layout ----
        trans_layout = QVBoxLayout(self.translation_tab)

        # Input Text Section
        input_layout = QHBoxLayout()
        self.input_label = QLabel("Input Text:")
        self.input_text = QLineEdit()
        input_layout.addWidget(self.input_label)
        input_layout.addWidget(self.input_text)
        trans_layout.addLayout(input_layout)

        # Language Slot Input Section
        lang_input_layout = QHBoxLayout()
        self.lang_code_input = QLineEdit()
        self.lang_code_input.setPlaceholderText("Language (code/full/prefix, e.g., en, english, hin)")
        self.slot_input = QLineEdit()
        self.slot_input.setPlaceholderText("Slot (optional integer)")
        self.add_lang_button = QPushButton("Add/Update Slot")
        self.add_lang_button.clicked.connect(self.add_language_slot)
        self.edit_lang_button = QPushButton("Edit Selected Slot")
        self.edit_lang_button.clicked.connect(self.edit_language_slot)
        self.remove_lang_button = QPushButton("Remove Selected Slot")
        self.remove_lang_button.clicked.connect(self.remove_language_slot)
        lang_input_layout.addWidget(self.lang_code_input)
        lang_input_layout.addWidget(self.slot_input)
        lang_input_layout.addWidget(self.add_lang_button)
        lang_input_layout.addWidget(self.edit_lang_button)
        lang_input_layout.addWidget(self.remove_lang_button)
        trans_layout.addLayout(lang_input_layout)

        # Fixed Language Slots List
        self.chain_list_widget = QListWidget()
        trans_layout.addWidget(QLabel("Fixed Language Slots (ordered by slot):"))
        trans_layout.addWidget(self.chain_list_widget)

        # Rounds and Frequency Settings
        rounds_layout = QHBoxLayout()
        self.rounds_label = QLabel("Total Rounds:")
        self.rounds_spin = QSpinBox()
        self.rounds_spin.setMinimum(1)
        self.rounds_spin.setMaximum(500)
        self.rounds_spin.setValue(5)
        rounds_layout.addWidget(self.rounds_label)
        rounds_layout.addWidget(self.rounds_spin)
        trans_layout.addLayout(rounds_layout)

        freq_layout = QHBoxLayout()
        self.freq_label = QLabel("Frequency (0=most similar, 100=most different): 100")
        self.freq_slider = QSlider(Qt.Orientation.Horizontal)
        self.freq_slider.setMinimum(0)
        self.freq_slider.setMaximum(100)
        self.freq_slider.setValue(100)
        self.freq_slider.valueChanged.connect(lambda value: self.freq_label.setText(f"Frequency (0=most similar, 100=most different): {value}"))
        freq_layout.addWidget(self.freq_label)
        freq_layout.addWidget(self.freq_slider)
        trans_layout.addLayout(freq_layout)

        # Run Translation Chain Button
        self.run_button = QPushButton("Run Translation Chain")
        self.run_button.clicked.connect(self.run_translation_chain)
        trans_layout.addWidget(self.run_button)

        # Live Translation Chain Display
        self.chain_display = QTextEdit()
        self.chain_display.setReadOnly(True)
        trans_layout.addWidget(QLabel("Translation Chain (Live Progress):"))
        trans_layout.addWidget(self.chain_display)

        # Final Output Section with Speak and Final Layer Translation
        final_layout = QHBoxLayout()
        self.final_output_label = QLabel("Final Output: ")
        final_layout.addWidget(self.final_output_label)

        self.speak_button = QPushButton("Speak Final Output")
        self.speak_button.clicked.connect(self.speak_final_output)
        final_layout.addWidget(self.speak_button)
        trans_layout.addLayout(final_layout)

        # Final Layer Translation Checkbox and Input (initially hidden)
        self.final_layer_checkbox = QCheckBox("Final Layer Translation")
        self.final_layer_checkbox.toggled.connect(self.toggle_final_layer)
        trans_layout.addWidget(self.final_layer_checkbox)

        self.final_layer_widget = QFrame()
        self.final_layer_widget.setFrameShape(QFrame.Shape.StyledPanel)
        final_layer_layout = QHBoxLayout(self.final_layer_widget)
        self.final_layer_input = QLineEdit()
        self.final_layer_input.setPlaceholderText("Enter language for final translation (e.g., en, english)")
        self.final_layer_button = QPushButton("Apply Final Translation")
        self.final_layer_button.clicked.connect(self.final_layer_retranslate)
        final_layer_layout.addWidget(self.final_layer_input)
        final_layer_layout.addWidget(self.final_layer_button)
        self.final_layer_widget.setVisible(False)
        trans_layout.addWidget(self.final_layer_widget)

        # Export Options Section
        export_layout = QHBoxLayout()
        self.export_format_combo = QComboBox()
        self.export_format_combo.addItems(["Plain Text", "JSON"])
        self.export_button = QPushButton("Export Chain")
        self.export_button.clicked.connect(self.export_chain)
        export_layout.addWidget(QLabel("Export Format:"))
        export_layout.addWidget(self.export_format_combo)
        export_layout.addWidget(self.export_button)
        trans_layout.addLayout(export_layout)

        # ---- History Tab Layout ----
        hist_layout = QVBoxLayout(self.history_tab)
        self.history_list = QListWidget()
        self.history_list.itemClicked.connect(self.load_history_item)
        hist_layout.addWidget(QLabel("Previous Translation Runs:"))
        hist_layout.addWidget(self.history_list)
        self.history_details = QTextEdit()
        self.history_details.setReadOnly(True)
        hist_layout.addWidget(QLabel("History Details:"))
        hist_layout.addWidget(self.history_details)

        # Overall Layout
        main_layout = QVBoxLayout(self)
        main_layout.addWidget(self.tabs)
        self.setLayout(main_layout)

    def toggle_final_layer(self, checked):
        self.final_layer_widget.setVisible(checked)

    def add_language_slot(self):
        lang_input = self.lang_code_input.text()
        lang_code = parse_language(lang_input)
        if not lang_code:
            self.lang_code_input.clear()
            self.lang_code_input.setPlaceholderText("Invalid language! Try again.")
            return
        slot_text = self.slot_input.text().strip()
        try:
            slot_num = int(slot_text) if slot_text else None
        except ValueError:
            slot_num = None
        # If no slot number provided, assign next available.
        if slot_num is None:
            slot_num = max([slot for slot, _ in self.language_slots], default=0) + 1
        # Update if slot exists; otherwise, add new.
        updated = False
        for idx, (snum, _) in enumerate(self.language_slots):
            if snum == slot_num:
                self.language_slots[idx] = (slot_num, lang_code)
                updated = True
                break
        if not updated:
            self.language_slots.append((slot_num, lang_code))
        self.language_slots.sort(key=lambda x: x[0])
        self.refresh_chain_list()
        self.lang_code_input.clear()
        self.slot_input.clear()

    def edit_language_slot(self):
        selected = self.chain_list_widget.currentRow()
        if selected >= 0 and selected < len(self.language_slots):
            slot_num, lang_code = self.language_slots[selected]
            self.lang_code_input.setText(lang_code)
            self.slot_input.setText(str(slot_num))
            # Do not remove the slot; let add/update handle modifications.

    def remove_language_slot(self):
        selected = self.chain_list_widget.currentRow()
        if selected >= 0 and selected < len(self.language_slots):
            del self.language_slots[selected]
            self.refresh_chain_list()

    def refresh_chain_list(self):
        self.chain_list_widget.clear()
        for slot, code in self.language_slots:
            name = LANGUAGES.get(code, "Unknown")
            item = QListWidgetItem(f"Slot {slot}: {code} - {name}")
            self.chain_list_widget.addItem(item)

    def run_translation_chain(self):
        original_text = self.input_text.text().strip()
        if not original_text:
            self.chain_display.setPlainText("Please enter input text.")
            return
        sorted_chain = [code for _, code in sorted(self.language_slots, key=lambda x: x[0])]
        num_rounds = self.rounds_spin.value()
        freq_value = self.freq_slider.value()

        self.run_button.setEnabled(False)
        self.chain_display.setPlainText("Processing translation chain...")

        self.worker_thread = QThread()
        self.worker = TranslationWorker(original_text, sorted_chain, num_rounds, freq_value)
        self.worker.moveToThread(self.worker_thread)
        self.worker_thread.started.connect(self.worker.run)
        self.worker.progress.connect(self.update_live_progress)
        self.worker.finished.connect(self.handle_worker_finished)
        self.worker.error.connect(self.handle_worker_error)
        self.worker.finished.connect(lambda: self.worker_thread.quit())
        self.worker.finished.connect(self.worker.deleteLater)
        self.worker_thread.finished.connect(self.worker_thread.deleteLater)
        self.worker_thread.start()

    def update_live_progress(self, chain):
        lines = []
        for round_num, lang, text, pron in chain:
            lang_name = LANGUAGES.get(lang, "auto-detected") if lang != "auto" else "auto-detected"
            lines.append(f"---({round_num})> [{lang} - {lang_name}]: {text}")
            lines.append(f"   Pronunciation: {pron}")
        self.chain_display.setPlainText("\n".join(lines))

    def handle_worker_finished(self, chain, final_output):
        lines = []
        for round_num, lang, text, pron in chain:
            lang_name = LANGUAGES.get(lang, "auto-detected") if lang != "auto" else "auto-detected"
            lines.append(f"---({round_num})> [{lang} - {lang_name}]: {text}")
            lines.append(f"   Pronunciation: {pron}")
        chain_text = "\n".join(lines)
        self.chain_display.setPlainText(chain_text)
        self.final_output_label.setText(f"Final Output: {final_output}")
        self.final_output_text = final_output  # Save for TTS and final layer translation
        self.run_button.setEnabled(True)
        # Save to history.
        history_item = {"chain": chain, "final_output": final_output, "input": self.input_text.text()}
        self.history.append(history_item)
        self.refresh_history_list()

    def handle_worker_error(self, error_msg):
        self.chain_display.setPlainText(f"Error: {error_msg}")
        self.run_button.setEnabled(True)

    def speak_final_output(self):
        # Use SpeechWorker to speak final_output_text in a separate thread.
        if self.final_output_text:
            self.speech_thread = SpeechWorker(self.final_output_text)
            self.speech_thread.start()
        else:
            self.chain_display.append("\nNo final output available to speak.")

    def final_layer_retranslate(self):
        # Final layer translation: retranslate final_output_text using the language from final_layer_input.
        target_input = self.final_layer_input.text().strip()
        if not self.final_output_text:
            QMessageBox.warning(self, "No Final Output", "No final output available to re-translate.")
            return
        target_lang = parse_language(target_input)
        if not target_lang:
            self.final_layer_input.clear()
            self.final_layer_input.setPlaceholderText("Invalid target language! Try again.")
            return
        try:
            translator = Translator()
            result = translator.translate(self.final_output_text, dest=target_lang)
            retranslated_text = result.text
            # Update final output label to reflect re-translated final layer.
            self.final_output_label.setText(f"Final Output (Re-Translated to {target_lang}): {retranslated_text}")
            self.final_output_text = retranslated_text
        except Exception as e:
            QMessageBox.critical(self, "Translation Error", f"Error during final layer translation: {e}")

    def export_chain(self):
        if not hasattr(self, "final_output_text") or not self.final_output_text:
            self.chain_display.setPlainText("No translation chain to export.")
            return
        fmt = self.export_format_combo.currentText()
        filename, _ = QFileDialog.getSaveFileName(self, "Export Translation Chain", os.getcwd(), "Text Files (*.txt);;JSON Files (*.json)")
        if filename:
            try:
                if fmt == "Plain Text":
                    with open(filename, "w", encoding="utf-8") as f:
                        f.write(self.chain_display.toPlainText())
                elif fmt == "JSON":
                    chain_data = []
                    # Use the last history item.
                    for round_num, lang, text, pron in self.history[-1]["chain"]:
                        chain_data.append({
                            "round": round_num,
                            "language_code": lang,
                            "language": LANGUAGES.get(lang, "auto-detected") if lang != "auto" else "auto-detected",
                            "text": text,
                            "pronunciation": pron
                        })
                    data = {
                        "input": self.history[-1]["input"],
                        "final_output": self.history[-1]["final_output"],
                        "chain": chain_data
                    }
                    with open(filename, "w", encoding="utf-8") as f:
                        json.dump(data, f, ensure_ascii=False, indent=2)
                self.chain_display.append(f"\nExported chain to {filename}")
            except Exception as e:
                self.chain_display.append(f"\nError exporting file: {e}")

    def refresh_history_list(self):
        self.history_list.clear()
        for idx, item in enumerate(self.history, start=1):
            summary = f"Run {idx}: Input='{item['input'][:15]}...', Final='{item['final_output'][:15]}...'"
            list_item = QListWidgetItem(summary)
            self.history_list.addItem(list_item)

    def load_history_item(self, item):
        idx = self.history_list.row(item)
        if idx < len(self.history):
            history_item = self.history[idx]
            lines = [f"Input: {history_item['input']}"]
            for round_num, lang, text, pron in history_item["chain"]:
                lang_name = LANGUAGES.get(lang, "auto-detected") if lang != "auto" else "auto-detected"
                lines.append(f"---({round_num})> [{lang} - {lang_name}]: {text}")
                lines.append(f"   Pronunciation: {pron}")
            lines.append(f"Final Output: {history_item['final_output']}")
            self.history_details.setPlainText("\n".join(lines))

# --- Run the Application ---
if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.resize(900, 800)
    window.show()
    sys.exit(app.exec())
