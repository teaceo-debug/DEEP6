from __future__ import annotations
import logging
from pathlib import Path
from typing import Any

import joblib
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QTableWidget, QTableWidgetItem, QFrame, QScrollArea,
    QSplitter, QGroupBox,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

logger = logging.getLogger(__name__)


class MetricCard(QFrame):
    """Single metric display: big number + label."""
    def __init__(self, label: str, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.StyledPanel)
        self.setStyleSheet("background-color: #161b22; border: 1px solid #30363d; border-radius: 6px; padding: 8px;")
        
        self._value_label = QLabel("—")
        self._value_label.setAlignment(Qt.AlignCenter)
        self._value_label.setStyleSheet("font-family: Consolas; font-size: 28px; font-weight: bold; color: #e6edf3; border: none;")
        
        self._name_label = QLabel(label)
        self._name_label.setAlignment(Qt.AlignCenter)
        self._name_label.setStyleSheet("font-size: 11px; color: #8b949e; border: none;")
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addWidget(self._value_label)
        layout.addWidget(self._name_label)
    
    def set_value(self, text: str) -> None:
        self._value_label.setText(text)


class ModelDashboard(QWidget):
    """Dashboard showing V4 model training metrics."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Model info header
        self._model_info = QLabel("No model loaded")
        self._model_info.setStyleSheet("color: #8b949e; font-size: 13px; padding: 4px;")
        
        # Metric cards row
        self._f1_card = MetricCard("Weighted F1")
        self._precision_card = MetricCard("Precision")
        self._recall_card = MetricCard("Recall")
        self._accuracy_card = MetricCard("Accuracy")
        
        cards_layout = QHBoxLayout()
        cards_layout.setSpacing(8)
        for card in [self._f1_card, self._precision_card, self._recall_card, self._accuracy_card]:
            cards_layout.addWidget(card)
        
        # Confusion matrix table
        self._confusion_group = QGroupBox("Confusion Matrix")
        self._confusion_group.setStyleSheet("QGroupBox { color: #e6edf3; font-weight: bold; border: 1px solid #30363d; border-radius: 4px; margin-top: 8px; padding-top: 16px; }")
        self._confusion_table = QTableWidget()
        self._confusion_table.setStyleSheet("font-family: Consolas; font-size: 12px;")
        confusion_layout = QVBoxLayout(self._confusion_group)
        confusion_layout.addWidget(self._confusion_table)
        
        # Per-class metrics table
        self._class_group = QGroupBox("Per-Class Metrics")
        self._class_group.setStyleSheet("QGroupBox { color: #e6edf3; font-weight: bold; border: 1px solid #30363d; border-radius: 4px; margin-top: 8px; padding-top: 16px; }")
        self._class_table = QTableWidget()
        self._class_table.setStyleSheet("font-family: Consolas; font-size: 12px;")
        class_layout = QVBoxLayout(self._class_group)
        class_layout.addWidget(self._class_table)
        
        # Feature importance list
        self._feature_group = QGroupBox("Top 15 Feature Importance")
        self._feature_group.setStyleSheet("QGroupBox { color: #e6edf3; font-weight: bold; border: 1px solid #30363d; border-radius: 4px; margin-top: 8px; padding-top: 16px; }")
        self._feature_list = QVBoxLayout()
        feature_container = QWidget()
        feature_container.setLayout(self._feature_list)
        feature_scroll = QScrollArea()
        feature_scroll.setWidget(feature_container)
        feature_scroll.setWidgetResizable(True)
        feature_scroll.setStyleSheet("border: none;")
        feature_group_layout = QVBoxLayout(self._feature_group)
        feature_group_layout.addWidget(feature_scroll)
        
        # Empty state
        self._empty_label = QLabel("Model not trained yet.\n\nRun: python scripts/train_depth_radar_v4.py --skip-label --output-dir data/depth_radar_v4")
        self._empty_label.setAlignment(Qt.AlignCenter)
        self._empty_label.setStyleSheet("color: #8b949e; font-size: 14px;")
        self._empty_label.setWordWrap(True)
        
        # Main layout with scroll
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.addWidget(self._model_info)
        content_layout.addLayout(cards_layout)
        content_layout.addWidget(self._confusion_group)
        content_layout.addWidget(self._class_group)
        content_layout.addWidget(self._feature_group)
        content_layout.addStretch()
        
        scroll = QScrollArea(self)
        scroll.setWidget(content)
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("border: none;")
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(scroll)
        layout.addWidget(self._empty_label)
        
        self._content_scroll = scroll
        self._content_scroll.setVisible(False)
    
    def load_model_metrics(self, model_path: Path) -> None:
        """Load metrics from a trained V4 model joblib file."""
        model_path = Path(model_path)
        if not model_path.exists():
            logger.warning("model_dashboard.model_not_found path=%s", model_path)
            self._empty_label.setVisible(True)
            self._content_scroll.setVisible(False)
            return
        
        try:
            payload = joblib.load(model_path)
            metrics = payload.get("training_metrics", {})
            class_names = payload.get("class_names", [])
            version = payload.get("version", "?")
            
            # Model info
            self._model_info.setText(
                f"Model: {model_path.name}  |  Version: {version}  |  "
                f"Classes: {len(class_names)}  |  Features: {len(payload.get('feature_names', []))}"
            )
            
            # Metric cards
            self._f1_card.set_value(f"{metrics.get('weighted_f1', 0):.3f}")
            self._precision_card.set_value(f"{metrics.get('precision', 0):.3f}")
            self._recall_card.set_value(f"{metrics.get('recall', 0):.3f}")
            self._accuracy_card.set_value(f"{metrics.get('accuracy', 0):.3f}")
            
            # Confusion matrix
            cm = metrics.get("confusion_matrix", [])
            if cm and class_names:
                n = len(class_names)
                self._confusion_table.setRowCount(n)
                self._confusion_table.setColumnCount(n)
                self._confusion_table.setHorizontalHeaderLabels(class_names)
                self._confusion_table.setVerticalHeaderLabels(class_names)
                max_val = max(max(row) for row in cm) if cm else 1
                for i, row in enumerate(cm):
                    for j, val in enumerate(row):
                        item = QTableWidgetItem(str(int(val)))
                        item.setTextAlignment(int(Qt.AlignCenter))
                        # Color intensity by value
                        intensity = int(min(val / max(max_val, 1), 1.0) * 80)
                        if i == j:  # diagonal = correct
                            item.setBackground(QColor(63, 185, 80, intensity))
                        else:  # off-diagonal = errors
                            item.setBackground(QColor(248, 81, 73, intensity))
                        self._confusion_table.setItem(i, j, item)
                self._confusion_table.resizeColumnsToContents()
            
            # Per-class metrics
            per_class = metrics.get("per_class", {})
            if per_class:
                self._class_table.setRowCount(len(per_class))
                self._class_table.setColumnCount(4)
                self._class_table.setHorizontalHeaderLabels(["Precision", "Recall", "F1", "Support"])
                self._class_table.setVerticalHeaderLabels(list(per_class.keys()))
                for i, (name, vals) in enumerate(per_class.items()):
                    for j, key in enumerate(["precision", "recall", "f1", "support"]):
                        v = vals.get(key, 0)
                        text = f"{v:.3f}" if key != "support" else str(int(v))
                        item = QTableWidgetItem(text)
                        item.setTextAlignment(int(Qt.AlignCenter))
                        self._class_table.setItem(i, j, item)
                self._class_table.resizeColumnsToContents()
            
            # Feature importance (top 15)
            feat_imp = metrics.get("feature_importance", {})
            if feat_imp:
                # Clear old items
                while self._feature_list.count():
                    child = self._feature_list.takeAt(0)
                    if child.widget():
                        child.widget().deleteLater()
                
                sorted_feats = sorted(feat_imp.items(), key=lambda x: x[1], reverse=True)[:15]
                max_imp = sorted_feats[0][1] if sorted_feats else 1.0
                
                for rank, (name, imp) in enumerate(sorted_feats, 1):
                    bar_pct = int(min(imp / max(max_imp, 1e-9), 1.0) * 100)
                    row = QLabel(
                        f'<span style="color:#8b949e">{rank:2d}.</span> '
                        f'<span style="color:#e6edf3">{name}</span>'
                        f'<span style="color:#8b949e; float:right">{imp:.1f}</span>'
                    )
                    row.setTextFormat(Qt.RichText)
                    row.setStyleSheet(
                        f"font-family: Consolas; font-size: 12px; padding: 2px 4px; "
                        f"border-left: {max(bar_pct // 4, 1)}px solid #58a6ff; margin: 1px 0;"
                    )
                    self._feature_list.addWidget(row)
                self._feature_list.addStretch()
            
            self._empty_label.setVisible(False)
            self._content_scroll.setVisible(True)
            logger.info("model_dashboard.loaded path=%s f1=%.4f", model_path, metrics.get("weighted_f1", 0))
            
        except Exception as exc:
            logger.error("model_dashboard.load_failed error=%s", exc)
            self._empty_label.setText(f"Error loading model: {exc}")
            self._empty_label.setVisible(True)
            self._content_scroll.setVisible(False)
