import sys
import threading
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QWidget, QLineEdit, QPushButton,
    QListWidget, QLabel, QSlider, QHBoxLayout, QProgressBar, QSizePolicy,
    QSpacerItem
)
from PyQt6.QtCore import Qt, pyqtSignal, QObject, QThread
from PyQt6.QtGui import QColor, QFont
import nltk
from nltk.corpus import cmudict
from fuzzywuzzy import fuzz
from wordfreq import zipf_frequency
from collections import defaultdict
nltk.download('cmudict', quiet=True)

class PhonemeMapBuilder(QObject):
    progress = pyqtSignal(int)
    finished = pyqtSignal(dict)
    
    def run(self):
        cmu_dict = cmudict.dict()
        phoneme_map = defaultdict(list)
        total = len(cmu_dict)
        for i, (word, prons) in enumerate(cmu_dict.items()):
            self.progress.emit(int((i/total)*100))
            for pron in prons:
                clean = tuple(p[:-1] if p[-1].isdigit() else p for p in pron)
                phoneme_map[clean].append(word.lower())
        self.finished.emit(phoneme_map)

class HomophoneWorker(QObject):
    finished = pyqtSignal(list)
    
    def __init__(self, word, phoneme_map, accuracy=90, min_zipf=2.0, max_results=10, use_freq_filter=True):
        super().__init__()
        self.word = word.lower()
        self.phoneme_map = phoneme_map
        self.accuracy = accuracy
        self.min_zipf = min_zipf
        self.max_results = max_results
        self.use_freq_filter = use_freq_filter
        
    def process(self):
        cmu_dict = cmudict.dict()
        target_prons = cmu_dict.get(self.word, [])
        if not target_prons:
            self.finished.emit([])
            return
        target_sequences = []
        for pron in target_prons:
            clean = tuple(p[:-1] if p[-1].isdigit() else p for p in pron)
            target_sequences.append(clean)
            
        candidates = set()
        for seq in target_sequences:
            for candidate_seq in self.phoneme_map:
                score = fuzz.ratio(' '.join(seq), ' '.join(candidate_seq))
                if score >= self.accuracy:
                    candidates.update(self.phoneme_map[candidate_seq])
        
        valid = []
        for word in candidates:
            if word == self.word:
                continue
            if self.use_freq_filter:
                if zipf_frequency(word, 'en') >= self.min_zipf:
                    valid.append(word)
            else:
                valid.append(word)
        
        unique = list(set(valid))
        sorted_words = sorted(unique, key=lambda w: (-zipf_frequency(w, 'en'), w))
        limited = sorted_words[:self.max_results] if self.max_results > 0 else sorted_words
        self.finished.emit(limited)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Homophone Pro")
        self.setGeometry(100, 100, 800, 600)
        self.setStyleSheet("""
            QMainWindow { background-color: #f5f5f5; }
            QLabel { font-size: 14px; color: #333; }
            QLineEdit { padding: 8px; border: 1px solid #ddd; border-radius: 4px; }
            QPushButton { 
                background-color: #4CAF50; color: white; padding: 10px 20px;
                border: none; border-radius: 4px;
            }
            QPushButton:hover { background-color: #45a049; }
            QListWidget { border: 1px solid #ddd; border-radius: 4px; }
        """)
        
        self.phoneme_map = None
        self.is_ready = False
        
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.layout = QVBoxLayout()
        
        header = QLabel("Homophone Finder Pro")
        header.setFont(QFont("Arial", 18, QFont.Weight.Bold))
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.setStyleSheet("color: #2c3e50; padding: 20px;")
        self.layout.addWidget(header)
        
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setStyleSheet("""
            QProgressBar { border: 1px solid #ddd; border-radius: 4px; text-align: center; }
            QProgressBar::chunk { background-color: #4CAF50; width: 20px; }
        """)
        self.layout.addWidget(self.progress)
        
        self.loading_label = QLabel("Loading pronunciation data...")
        self.loading_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.layout.addWidget(self.loading_label)
        
        self.input = QLineEdit()
        self.input.setPlaceholderText("Enter a word...")
        self.input.setFont(QFont("Arial", 14))
        self.input.setEnabled(False)
        self.layout.addWidget(self.input)
        
        # Settings panel
        settings_layout = QHBoxLayout()
        
        # Accuracy slider
        accuracy_layout = QVBoxLayout()
        accuracy_label = QLabel("Matching Accuracy:")
        accuracy_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.accuracy_slider = QSlider(Qt.Orientation.Horizontal)
        self.accuracy_slider.setRange(50, 100)
        self.accuracy_slider.setValue(90)
        self.accuracy_slider.setTickInterval(5)
        self.accuracy_slider.setEnabled(False)
        self.accuracy_value = QLabel("90%")
        self.accuracy_value.setAlignment(Qt.AlignmentFlag.AlignCenter)
        accuracy_layout.addWidget(accuracy_label)
        accuracy_layout.addWidget(self.accuracy_slider)
        accuracy_layout.addWidget(self.accuracy_value)
        
        # Frequency filter
        freq_layout = QVBoxLayout()
        freq_label = QLabel("Minimum Frequency:")
        freq_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.freq_slider = QSlider(Qt.Orientation.Horizontal)
        self.freq_slider.setRange(1, 6)
        self.freq_slider.setValue(2)
        self.freq_slider.setTickInterval(1)
        self.freq_slider.setEnabled(False)
        self.freq_value = QLabel("2.0 (Common words)")
        self.freq_value.setAlignment(Qt.AlignmentFlag.AlignCenter)
        freq_layout.addWidget(freq_label)
        freq_layout.addWidget(self.freq_slider)
        freq_layout.addWidget(self.freq_value)
        
        # Result limit
        result_layout = QVBoxLayout()
        result_label = QLabel("Max Results:")
        result_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.result_limit_slider = QSlider(Qt.Orientation.Horizontal)
        self.result_limit_slider.setRange(1, 50)
        self.result_limit_slider.setValue(10)
        self.result_limit_slider.setEnabled(False)
        self.result_limit_value = QLabel("10 results")
        self.result_limit_value.setAlignment(Qt.AlignmentFlag.AlignCenter)
        result_layout.addWidget(result_label)
        result_layout.addWidget(self.result_limit_slider)
        result_layout.addWidget(self.result_limit_value)
        
        settings_layout.addLayout(accuracy_layout)
        settings_layout.addLayout(freq_layout)
        settings_layout.addLayout(result_layout)
        self.layout.addLayout(settings_layout)
        
        # Control panel
        control_layout = QHBoxLayout()
        
        # Unlimited Results toggle button
        self.unlimited_button = QPushButton("Unlimited Results")
        self.unlimited_button.setCheckable(True)
        self.unlimited_button.setEnabled(False)
        self.unlimited_button.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50; 
                color: white; 
                padding: 10px 20px;
                border: none; 
                border-radius: 4px;
            }
            QPushButton:checked {
                background-color: #FFA726;
            }
        """)
        
        self.button = QPushButton("Find Homophones")
        self.button.setEnabled(False)
        
        control_layout.addWidget(self.unlimited_button)
        control_layout.addWidget(self.button)
        self.layout.addLayout(control_layout)
        
        # Results display
        self.results_list = QListWidget()
        self.results_list.setFont(QFont("Arial", 14))
        self.results_list.setEnabled(False)
        self.layout.addWidget(self.results_list)
        
        self.central_widget.setLayout(self.layout)
        
        # Connections
        self.button.clicked.connect(self.start_search)
        self.accuracy_slider.valueChanged.connect(self.update_accuracy_label)
        self.freq_slider.valueChanged.connect(self.update_freq_label)
        self.result_limit_slider.valueChanged.connect(self.update_result_limit_label)
        self.unlimited_button.toggled.connect(self.toggle_result_limit)
        
        self.build_phoneme_map()

    def build_phoneme_map(self):
        self.builder_thread = QThread()
        self.builder = PhonemeMapBuilder()
        self.builder.moveToThread(self.builder_thread)
        self.builder.progress.connect(self.progress.setValue)
        self.builder.finished.connect(self.on_phoneme_ready)
        self.builder_thread.started.connect(self.builder.run)
        self.builder_thread.start()

    def on_phoneme_ready(self, phoneme_map):
        self.phoneme_map = phoneme_map
        self.is_ready = True
        self.builder_thread.quit()
        self.progress.hide()
        self.loading_label.hide()
        self.input.setEnabled(True)
        self.accuracy_slider.setEnabled(True)
        self.freq_slider.setEnabled(True)
        self.result_limit_slider.setEnabled(True)
        self.button.setEnabled(True)
        self.results_list.setEnabled(True)
        self.unlimited_button.setEnabled(True)
        self.results_list.addItem("Ready! Enter a word to begin")

    def update_accuracy_label(self, value):
        self.accuracy_value.setText(f"{value}%")

    def update_freq_label(self, value):
        self.freq_value.setText(f"{value}.0 (Minimum frequency)")

    def update_result_limit_label(self, value):
        self.result_limit_value.setText(f"{value} results")

    def toggle_result_limit(self, checked):
        self.result_limit_slider.setEnabled(not checked)
        if checked:
            self.result_limit_value.setText("All results")
        else:
            self.update_result_limit_label(self.result_limit_slider.value())

    def start_search(self):
        word = self.input.text().strip().lower()
        if not word or not self.is_ready:
            return
        
        accuracy = self.accuracy_slider.value()
        min_zipf = self.freq_slider.value()
        max_results = self.result_limit_slider.value() if not self.unlimited_button.isChecked() else 0
        use_freq_filter = not self.unlimited_button.isChecked()
        
        self.results_list.clear()
        self.results_list.addItem("Searching...")
        
        self.thread = QThread()
        self.worker = HomophoneWorker(
            word=word,
            phoneme_map=self.phoneme_map,
            accuracy=accuracy,
            min_zipf=min_zipf,
            max_results=max_results,
            use_freq_filter=use_freq_filter
        )
        
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.process)
        self.worker.finished.connect(self.display_results)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.start()

    def display_results(self, homophones):
        self.results_list.clear()
        if homophones:
            self.results_list.addItems([f"• {word}" for word in homophones])
            self.results_list.addItem(f"Found {len(homophones)} homophones")
        else:
            self.results_list.addItem("No homophones found")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
