import sys
import os
import string
from collections import defaultdict
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QWidget, QHBoxLayout,
    QPushButton, QLabel, QLineEdit, QTextEdit, QSpinBox,
    QFileDialog, QFrame, QMessageBox, QCheckBox
)
from PyQt6.QtCore import QSize
from PyQt6.QtGui import QAction
from docx import Document
import fitz  # PyMuPDF
import matplotlib.pyplot as plt
from io import BytesIO
import base64
import webbrowser

# Attempt to use the desired style, with a fallback
plt.style.use('seaborn-darkgrid' if 'seaborn-darkgrid' in plt.style.available else 'ggplot')

class PrecisionTextAnalyzer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Precision Text Analyzer")
        self.setGeometry(100, 100, 800, 600)
        self.loaded_text = ""
        self.current_analysis = {}
        self.ignore_characters = ""
        self.init_ui()

    def init_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout(main_widget)

        # Menu Bar
        menubar = self.menuBar()
        file_menu = menubar.addMenu("&File")
        open_action = QAction("&Open Files", self)
        open_action.triggered.connect(self.load_files)
        file_menu.addAction(open_action)

        # Analysis Controls
        control_layout = QHBoxLayout()
        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Enter target character (e.g., a, 5, #)")
        
        self.n_spin = QSpinBox()
        self.n_spin.setRange(1, 5)
        self.n_spin.setValue(1)

        # Checkboxes for letters, numbers, and symbols
        self.letter_check = QCheckBox("Analyze Letters")
        self.letter_check.setChecked(True)
        self.number_check = QCheckBox("Analyze Numbers")
        self.number_check.setChecked(True)
        self.symbol_check = QCheckBox("Analyze Symbols")
        self.symbol_check.setChecked(True)

        # Input for ignored characters
        self.ignore_input = QLineEdit()
        self.ignore_input.setPlaceholderText("Characters to ignore (e.g., !@#)")
        self.ignore_input.setFixedWidth(250)

        self.analyze_btn = QPushButton("Analyze")
        self.analyze_btn.clicked.connect(self.analyze_text)
        
        self.analyze_a_z_btn = QPushButton("Analyze A-Z")
        self.analyze_a_z_btn.clicked.connect(self.analyze_a_to_z)
        
        control_layout.addWidget(QLabel("Target:"))
        control_layout.addWidget(self.input_field)
        control_layout.addWidget(QLabel("Sequence Length (n):"))
        control_layout.addWidget(self.n_spin)
        control_layout.addWidget(self.letter_check)
        control_layout.addWidget(self.number_check)
        control_layout.addWidget(self.symbol_check)
        control_layout.addWidget(QLabel("Ignore:"))
        control_layout.addWidget(self.ignore_input)
        control_layout.addWidget(self.analyze_btn)
        control_layout.addWidget(self.analyze_a_z_btn)
        control_layout.addStretch()

        # Results Display
        self.results_display = QTextEdit()
        self.results_display.setReadOnly(True)
        self.results_display.setStyleSheet("""
            QTextEdit {
                background-color: #f8f9fa;
                color: #212529;
                border: 1px solid #dee2e6;
                padding: 10px;
                font-family: 'Consolas';
            }
        """)

        layout.addLayout(control_layout)
        layout.addWidget(self.create_hsep())
        layout.addWidget(self.results_display)

    def create_hsep(self):
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("background-color: #dee2e6; margin: 10px 0;")
        return sep

    def load_files(self):
        file_paths, _ = QFileDialog.getOpenFileNames(
            self, "Select Files", "",
            "Text Files (*.txt);;Word Documents (*.docx);;PDF Files (*.pdf)"
        )
        
        if not file_paths:
            return

        combined_text = ""
        for path in file_paths:
            try:
                combined_text += self.extract_text(path) + "\n"
            except Exception as e:
                self.show_error(f"Error reading {os.path.basename(path)}:\n{str(e)}")
        
        self.loaded_text = combined_text.lower()
        self.results_display.setPlainText(f"Loaded {len(file_paths)} files\nTotal characters: {len(combined_text):,}")

    def extract_text(self, path):
        ext = os.path.splitext(path)[1].lower()
        if ext == ".txt":
            with open(path, 'r', encoding='utf-8') as f:
                return f.read()
        elif ext == ".docx":
            doc = Document(path)
            return "\n".join(p.text for p in doc.paragraphs)
        elif ext == ".pdf":
            doc = fitz.open(path)
            return "".join(page.get_text() for page in doc)
        raise ValueError("Unsupported file format")

    def analyze_text(self):
        target = self.input_field.text().strip()
        n = self.n_spin.value()
        self.ignore_characters = self.ignore_input.text().strip()
        
        if not self.loaded_text:
            self.show_error("Please load text files first")
            return
        
        if len(target) != 1:
            self.show_error("Please enter exactly one target character")
            return

        sequences = defaultdict(int)
        total = 0
        valid_chars = self.get_valid_characters()
        
        # Iterate through the loaded text
        for i in range(len(self.loaded_text) - n):
            if self.loaded_text[i] == target:
                seq = self.loaded_text[i+1:i+1+n]
                # Check if the sequence is valid (letters, numbers, or symbols)
                if len(seq) == n and all(char in valid_chars for char in seq):
                    sequences[seq] += 1
                    total += 1

        if not sequences:
            self.show_info("No matching sequences found")
            return

        self.current_analysis = {
            'target': target,
            'n': n,
            'sequences': sequences,
            'total': total
        }

        self.display_results()

    def analyze_a_to_z(self):
        if not self.loaded_text:
            self.show_error("Please load text files first")
            return

        n = self.n_spin.value()
        self.ignore_characters = self.ignore_input.text().strip()

        # Collect all HTML content for each letter
        html_content = ""
        for target in string.ascii_lowercase:
            self.input_field.setText(target)
            self.analyze_text()
            html_content += self._generate_single_letter_html()

        # Save the combined HTML content to a single file
        combined_html = f"""
        <html>
            <head>
                <title>Precision Analysis: A-Z</title>
                <style>
                    body {{ 
                        font-family: 'Segoe UI', sans-serif;
                        margin: 30px;
                        background-color: #f8f9fa;
                    }}
                    .container {{ 
                        max-width: 1400px;
                        margin: 0 auto;
                        padding: 30px;
                        background-color: white;
                        box-shadow: 0 0 20px rgba(0,0,0,0.1);
                        border-radius: 10px;
                    }}
                    h1 {{ 
                        color: #2c3e50;
                        border-bottom: 2px solid #4c72b0;
                        padding-bottom: 10px;
                    }}
                    img {{ 
                        width: 100%;
                        height: auto;
                        margin: 20px 0;
                    }}
                </style>
            </head>
            <body>
                <div class="container">
                    <h1>Precision Analysis: A-Z (n={n})</h1>
                    {html_content}
                </div>
            </body>
        </html>
        """

        # Save the combined HTML file
        temp_file = "precision_analysis_a_z.html"
        with open(temp_file, "w") as f:
            f.write(combined_html)
        webbrowser.open(f"file://{os.path.abspath(temp_file)}")

    def _generate_single_letter_html(self):
        img_data = self._generate_single_letter_graph()  # Get the image data
        img_base64 = base64.b64encode(img_data).decode('utf-8')  # Encode to base64

        return f"""
        <h2>Target: '{self.current_analysis['target']}'</h2>
        <img src="data:image/png;base64,{img_base64}">
        """

    def _generate_single_letter_graph(self):
        fig = plt.figure(figsize=(10, 6), dpi=100)
        visible_categories = [('letters', string.ascii_letters)]

        gs = fig.add_gridspec(len(visible_categories), 1)
        
        for idx, (category_name, category_chars) in enumerate(visible_categories):
            ax = fig.add_subplot(gs[idx])
            data = self._prepare_category_data(category_chars)
            self._plot_category(ax, data, category_name.capitalize(), 
                              '#4c72b0')

        plt.tight_layout()
        
        # Save the figure to a BytesIO buffer instead of showing it
        buf = BytesIO()
        fig.savefig(buf, format='png', bbox_inches='tight')
        plt.close(fig)  # Close the figure to free memory
        buf.seek(0)  # Rewind the buffer to the beginning
        return buf.getvalue()  # Return the image data

    def get_valid_characters(self):
        valid_chars = ""
        if self.letter_check.isChecked():
            valid_chars += string.ascii_letters  # Only letters for A-Z analysis
        if self.number_check.isChecked():
            valid_chars += string.digits
        if self.symbol_check.isChecked():
            valid_chars += string.punctuation
        
        # Remove ignored characters
        return ''.join(c for c in valid_chars if c not in self.ignore_characters)

    def display_results(self):
        sorted_seqs = sorted(self.current_analysis['sequences'].items(), 
                           key=lambda x: (-x[1], x[0]))
        
        result_text = (
            f"Precision Analysis Report\n"
            f"Target: '{self.current_analysis['target']}'\n"
            f"Sequence Length: {self.current_analysis['n']}\n"
            f"Total Sequences Found: {self.current_analysis['total']:,}\n\n"
            "Top Sequences:\n"
        )
        
        for seq, count in sorted_seqs[:50]:
            percentage = (count / self.current_analysis['total']) * 100
            result_text += f"▸ {seq}: {count:,} ({percentage:.2f}%)\n"
        
        self.results_display.setPlainText(result_text)

    def _prepare_category_data(self, category_chars):
        freq = defaultdict(int)
        total = 0
        
        for seq, count in self.current_analysis['sequences'].items():
            for char in seq:
                if char in category_chars:
                    freq[char] += count
                    total += count
        
        sorted_items = sorted(freq.items(), key=lambda x: (-x[1], x[0]))
        return {
            'labels': [k for k, v in sorted_items],
            'values': [v for k, v in sorted_items],
            'total': total
        }

    def _plot_category(self, ax, data, title, color):
        if data['total'] == 0:
            ax.axis('off')
            ax.text(0.5, 0.5, 'No Data Available', 
                    ha='center', va='center', fontsize=12)
            return
        
        percentages = [(v / data['total']) * 100 for v in data['values']]
        
        bars = ax.bar(data['labels'], percentages, color=color)
        ax.set_title(f"{title} Distribution", fontsize=14, pad=20, fontweight='bold')
        ax.set_xlabel("Characters", fontsize=12)
        ax.set_ylabel("Frequency (%)", fontsize=12)
        ax.grid(True, alpha=0.3)
        ax.set_axisbelow(True)
        
        for bar in bars:
            height = bar.get_height()
            if height > 0.5:
                ax.text(bar.get_x() + bar.get_width()/2, height,
                        f'{height:.1f}%', ha='center', va='bottom',
                        fontsize=9, color='#333333')

    def show_error(self, message):
        QMessageBox.critical(self, "Error", message)

    def show_info(self, message):
        QMessageBox.information(self, "Information", message)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = PrecisionTextAnalyzer()
    window.show()
    sys.exit(app.exec())
