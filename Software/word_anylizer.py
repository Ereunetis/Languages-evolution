import sys
import os
import re
from collections import defaultdict
import PyPDF2
import docx
from langdetect import detect, DetectorFactory
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QPushButton,
    QLabel, QFileDialog, QMessageBox, QTextEdit, QProgressBar
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal

DetectorFactory.seed = 0

class FileProcessor(QThread):
    progress_updated = pyqtSignal(int)
    analysis_complete = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)

    def __init__(self, file_path):
        super().__init__()
        self.file_path = file_path
        self.readers = {
            '.pdf': self.read_pdf,
            '.docx': self.read_docx,
            '.txt': self.read_txt
        }

    def run(self):
        try:
            ext = os.path.splitext(self.file_path)[1].lower()
            if ext not in self.readers:
                self.error_occurred.emit("Unsupported file format")
                return

            text = self.readers[ext]()
            if not text:
                self.error_occurred.emit("File is empty or cannot be read")
                return

            result = self.analyze_text(text)
            self.analysis_complete.emit(result)

        except Exception as e:
            self.error_occurred.emit(str(e))

    def read_pdf(self):
        text = []
        with open(self.file_path, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            total = len(reader.pages)
            for i, page in enumerate(reader.pages):
                text.append(page.extract_text() or "")
                self.progress_updated.emit(int((i+1)/total*100))
        return "\n".join(text)

    def read_docx(self):
        doc = docx.Document(self.file_path)
        return "\n".join(para.text for para in doc.paragraphs)

    def read_txt(self):
        with open(self.file_path, "r", encoding="utf-8") as f:
            return f.read()

    def analyze_text(self, text):
        stats = defaultdict(int)
        word_counts = defaultdict(int)
        detected_langs = set()
        sentences = re.split(r'[.!?]+', text)
        word_re = re.compile(r"\b\w[\w'-]*\b", re.UNICODE)

        # Single pass character analysis
        for c in text:
            if c.isalpha():
                stats['letters'] += 1
            elif c.isdigit():
                stats['digits'] += 1
            elif c.isspace():
                stats['spaces'] += 1
            elif not c.isalnum():
                stats['special'] += 1

        # Word analysis with improved regex
        words = word_re.findall(text.lower())
        stats['words'] = len(words)
        stats['unique_words'] = len(set(words))

        # Language detection with sampling
        sample_size = min(100, len(sentences))
        for sentence in sentences[:sample_size]:
            sentence = sentence.strip()
            if len(sentence) >= 3:
                try:
                    lang = detect(sentence)
                    detected_langs.add(lang)
                except Exception:
                    pass

        stats['languages'] = detected_langs
        stats['lines'] = text.count('\n') + 1

        return dict(stats)

class TextAnalyzerApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Advanced Text Analyzer")
        self.resize(1000, 800)
        self.current_file = ""
        self.init_ui()

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        # File selection
        self.file_label = QLabel("No file selected")
        self.btn_open = QPushButton("Open File")
        self.btn_open.clicked.connect(self.open_file)
        
        # Progress bar
        self.progress = QProgressBar()
        self.progress.hide()

        # Results display
        self.results = QTextEdit()
        self.results.setReadOnly(True)

        layout.addWidget(self.btn_open)
        layout.addWidget(self.file_label)
        layout.addWidget(self.progress)
        layout.addWidget(self.results)

    def open_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Open File", "",
            "Supported Files (*.pdf *.docx *.txt);;All Files (*)"
        )
        if file_path:
            self.current_file = file_path
            self.file_label.setText(f"Analyzing: {os.path.basename(file_path)}")
            self.start_analysis(file_path)

    def start_analysis(self, file_path):
        self.progress.show()
        self.btn_open.setEnabled(False)

        self.worker = FileProcessor(file_path)
        self.worker.progress_updated.connect(self.update_progress)
        self.worker.analysis_complete.connect(self.show_results)
        self.worker.error_occurred.connect(self.show_error)
        self.worker.finished.connect(self.analysis_finished)
        self.worker.start()

    def update_progress(self, value):
        self.progress.setValue(value)

    def show_results(self, results):
        text = (
            f"Total Letters: {results['letters']}\n"
            f"Total Words: {results['words']}\n"
            f"Unique Words: {results['unique_words']}\n"
            f"Total Lines: {results['lines']}\n"
            f"Total Digits: {results['digits']}\n"
            f"Whitespace Characters: {results['spaces']}\n"
            f"Special Characters: {results['special']}\n"
            f"Languages Detected: {len(results['languages'])}\n"
            f"Detected Languages: {', '.join(results['languages']) or 'None'}"
        )
        self.results.setPlainText(text)

    def show_error(self, message):
        QMessageBox.critical(self, "Error", message)

    def analysis_finished(self):
        self.progress.hide()
        self.btn_open.setEnabled(True)
        self.file_label.setText(f"Analyzed: {os.path.basename(self.current_file)}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = TextAnalyzerApp()
    window.show()
    sys.exit(app.exec())
