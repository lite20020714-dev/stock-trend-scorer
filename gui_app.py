"""PySide6 native GUI for Stock Trend Scorer.

A thin UI layer over the existing CLI logic (stock_trend_scorer.data /
.scoring / .portfolio / .screening / .universe / .market) -- none of that
code is modified here. Network I/O (scan/watch) runs on a QThread so the
UI never blocks.

Run:
    python gui_app.py
"""

from __future__ import annotations

import random
import re
import sys

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QButtonGroup,
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from stock_trend_scorer.market import detect_market, normalize_code
from stock_trend_scorer.portfolio.repository import (
    AmbiguousHoldingError,
    DuplicateHoldingError,
    HoldingNotFoundError,
    HoldingsRepository,
)
from stock_trend_scorer.scoring import CLASSIFICATION_DOWN, CLASSIFICATION_UP, TrendScorer
from stock_trend_scorer.screening import ScreeningError, ScreeningResult, score_codes
from stock_trend_scorer.universe import load_universe

PERIOD_CHOICES = ["6mo", "1y", "2y"]
POSITIVE_COLOR = QColor("#d9f0d3")
NEGATIVE_COLOR = QColor("#f8d7d7")
RESULT_HEADERS = ["コード", "市場", "スコア", "現在値", "52週高値乖離率", "判定"]


def score_row_color(score: float) -> QColor | None:
    if score > 0:
        return POSITIVE_COLOR
    if score < 0:
        return NEGATIVE_COLOR
    return None


class NumericTableWidgetItem(QTableWidgetItem):
    """A QTableWidgetItem that sorts numerically instead of lexicographically."""

    def __init__(self, value: float, text: str):
        super().__init__(text)
        self.value = value

    def __lt__(self, other: object) -> bool:
        if isinstance(other, NumericTableWidgetItem):
            return self.value < other.value
        return super().__lt__(other)


class ScreeningWorker(QThread):
    """Runs a blocking (network I/O) screening task off the UI thread."""

    succeeded = Signal(object, object)  # (list[ScreeningResult], list[ScreeningError])
    failed = Signal(str)

    def __init__(self, task, parent=None):
        super().__init__(parent)
        self._task = task

    def run(self) -> None:
        try:
            results, errors = self._task()
        except Exception as exc:  # surface any failure to the UI instead of crashing the thread
            self.failed.emit(str(exc))
            return
        self.succeeded.emit(results, errors)


def populate_results_table(table: QTableWidget, results: list[ScreeningResult]) -> None:
    table.setSortingEnabled(False)
    table.setRowCount(len(results))
    for row, result in enumerate(results):
        score = result.score
        color = score_row_color(score.total_score)
        code_item = QTableWidgetItem(score.code)
        market_item = QTableWidgetItem(result.market)
        score_item = NumericTableWidgetItem(score.total_score, f"{score.total_score:.3f}")
        price_item = NumericTableWidgetItem(score.current_price, f"{score.current_price:.2f}")
        week52_item = NumericTableWidgetItem(score.week52_high_pct, f"{score.week52_high_pct:.2f}%")
        classification_item = QTableWidgetItem(score.classification)
        items = (code_item, market_item, score_item, price_item, week52_item, classification_item)
        for item in items:
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            if color is not None:
                item.setBackground(color)
        for column, item in enumerate(items):
            table.setItem(row, column, item)
    table.setSortingEnabled(True)


def format_errors(errors: list[ScreeningError]) -> str:
    if not errors:
        return ""
    lines = [f"{e.code} ({e.market}): {e.message}" for e in errors]
    return "取得・計算できなかった銘柄:\n" + "\n".join(lines)


def make_results_table() -> QTableWidget:
    table = QTableWidget(0, len(RESULT_HEADERS))
    table.setHorizontalHeaderLabels(RESULT_HEADERS)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.horizontalHeader().setStretchLastSection(True)
    table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
    table.setSortingEnabled(True)
    return table


class ScreeningTabBase(QWidget):
    """Shared plumbing for the Scan/Watch tabs: busy state + worker lifecycle."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker: ScreeningWorker | None = None
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)  # indeterminate
        self.progress.setVisible(False)
        self.status_label = QLabel("")
        self.summary_label = QLabel("")
        self.table = make_results_table()
        self.table.cellDoubleClicked.connect(self._show_detail)
        self.error_view = QPlainTextEdit()
        self.error_view.setReadOnly(True)
        self.error_view.setMaximumHeight(80)
        self.error_view.setVisible(False)
        self._last_results: list[ScreeningResult] = []

    def _run_buttons(self) -> list[QPushButton]:
        raise NotImplementedError

    def _set_busy(self, busy: bool) -> None:
        self.progress.setVisible(busy)
        self.status_label.setText("取得中..." if busy else "")
        for button in self._run_buttons():
            button.setEnabled(not busy)

    def _start(self, task, on_success) -> None:
        self._set_busy(True)
        self._worker = ScreeningWorker(task)
        self._worker.succeeded.connect(on_success)
        self._worker.failed.connect(self._on_failed)
        self._worker.finished.connect(lambda: self._set_busy(False))
        self._worker.start()

    def _on_failed(self, message: str) -> None:
        QMessageBox.critical(self, "エラー", message)

    def _render_results(self, results: list[ScreeningResult], errors: list[ScreeningError], summary: str) -> None:
        self._last_results = results
        self.summary_label.setText(summary)
        populate_results_table(self.table, results)
        error_text = format_errors(errors)
        self.error_view.setPlainText(error_text)
        self.error_view.setVisible(bool(error_text))

    def _show_detail(self, row: int, _column: int) -> None:
        if row >= len(self._last_results):
            return
        # table rows may be re-sorted by the user; look up by the code shown in that row
        code = self.table.item(row, 0).text()
        result = next((r for r in self._last_results if r.score.code == code), None)
        if result is None:
            return
        lines = [f"{ind.name}: {ind.score:.3f}" for ind in result.score.indicators]
        QMessageBox.information(self, f"{code} の指標内訳", "\n".join(lines) or "指標データなし")


class ScanTab(ScreeningTabBase):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.random_radio = QRadioButton("ランダム抽出")
        self.manual_radio = QRadioButton("銘柄コード手入力")
        self.random_radio.setChecked(True)
        mode_group = QButtonGroup(self)
        mode_group.addButton(self.random_radio)
        mode_group.addButton(self.manual_radio)
        self.random_radio.toggled.connect(self._sync_mode)

        self.universe_combo = QComboBox()
        self.universe_combo.addItems(["JP", "US"])
        self.random_count = QSpinBox()
        self.random_count.setRange(1, 500)
        self.random_count.setValue(20)

        self.codes_edit = QLineEdit()
        self.codes_edit.setPlaceholderText("例: 7203 6758, AAPL MSFT")
        self.codes_edit.setEnabled(False)

        self.period_combo = QComboBox()
        self.period_combo.addItems(PERIOD_CHOICES)
        self.period_combo.setCurrentText("1y")

        self.run_button = QPushButton("スキャン実行")
        self.run_button.clicked.connect(self._run_scan)

        random_row = QHBoxLayout()
        random_row.addWidget(self.random_radio)
        random_row.addWidget(QLabel("市場:"))
        random_row.addWidget(self.universe_combo)
        random_row.addWidget(QLabel("件数:"))
        random_row.addWidget(self.random_count)
        random_row.addStretch(1)

        manual_row = QHBoxLayout()
        manual_row.addWidget(self.manual_radio)
        manual_row.addWidget(self.codes_edit)

        options_box = QGroupBox("抽出方法")
        options_layout = QVBoxLayout()
        options_layout.addLayout(random_row)
        options_layout.addLayout(manual_row)
        options_box.setLayout(options_layout)

        period_row = QHBoxLayout()
        period_row.addWidget(QLabel("取得期間:"))
        period_row.addWidget(self.period_combo)
        period_row.addWidget(self.run_button)
        period_row.addWidget(self.progress)
        period_row.addWidget(self.status_label)
        period_row.addStretch(1)

        layout = QVBoxLayout()
        layout.addWidget(options_box)
        layout.addLayout(period_row)
        layout.addWidget(self.summary_label)
        layout.addWidget(self.table)
        layout.addWidget(self.error_view)
        self.setLayout(layout)

    def _sync_mode(self, random_checked: bool) -> None:
        self.universe_combo.setEnabled(random_checked)
        self.random_count.setEnabled(random_checked)
        self.codes_edit.setEnabled(not random_checked)

    def _run_buttons(self) -> list[QPushButton]:
        return [self.run_button]

    def _collect_pairs(self) -> list[tuple[str, str]] | None:
        if self.random_radio.isChecked():
            market = self.universe_combo.currentText()
            universe_codes = load_universe(market)
            sample_size = min(self.random_count.value(), len(universe_codes))
            sampled = random.sample(universe_codes, sample_size)
            return list(dict.fromkeys((code, market) for code in sampled))

        raw = re.split(r"[\s,]+", self.codes_edit.text().strip())
        codes = [c for c in raw if c]
        if not codes:
            QMessageBox.warning(self, "入力エラー", "銘柄コードを入力してください")
            return None
        pairs = []
        for code in codes:
            market = detect_market(code)
            pairs.append((normalize_code(code, market), market))
        return list(dict.fromkeys(pairs))

    def _run_scan(self) -> None:
        pairs = self._collect_pairs()
        if not pairs:
            return
        period = self.period_combo.currentText()

        def task():
            scorer = TrendScorer(mode="discovery")
            return score_codes(pairs, scorer=scorer, is_held=False, period=period)

        self._start(task, self._on_scan_done)

    def _on_scan_done(self, results: list[ScreeningResult], errors: list[ScreeningError]) -> None:
        results = sorted(results, key=lambda r: r.score.total_score, reverse=True)
        candidates = [r for r in results if r.score.classification == CLASSIFICATION_UP]
        summary = f"{len(results)}件中 上昇トレンド候補 {len(candidates)}件"
        self._render_results(results, errors, summary)


class WatchTab(ScreeningTabBase):
    def __init__(self, repo: HoldingsRepository, parent=None):
        super().__init__(parent)
        self.repo = repo

        self.period_combo = QComboBox()
        self.period_combo.addItems(PERIOD_CHOICES)
        self.period_combo.setCurrentText("1y")

        self.run_button = QPushButton("保有監視 実行")
        self.run_button.clicked.connect(self._run_watch)

        top_row = QHBoxLayout()
        top_row.addWidget(QLabel("取得期間:"))
        top_row.addWidget(self.period_combo)
        top_row.addWidget(self.run_button)
        top_row.addWidget(self.progress)
        top_row.addWidget(self.status_label)
        top_row.addStretch(1)

        layout = QVBoxLayout()
        layout.addLayout(top_row)
        layout.addWidget(self.summary_label)
        layout.addWidget(self.table)
        layout.addWidget(self.error_view)
        self.setLayout(layout)

    def _run_buttons(self) -> list[QPushButton]:
        return [self.run_button]

    def _run_watch(self) -> None:
        holdings = self.repo.list()
        if not holdings:
            QMessageBox.information(self, "保有監視", "保有銘柄はありません")
            return

        pairs = [(h.code, h.market) for h in holdings]
        period = self.period_combo.currentText()

        def task():
            scorer = TrendScorer(mode="watch")
            return score_codes(pairs, scorer=scorer, is_held=True, period=period)

        self._start(task, self._on_watch_done)

    def _on_watch_done(self, results: list[ScreeningResult], errors: list[ScreeningError]) -> None:
        results = sorted(results, key=lambda r: r.score.total_score)
        warnings = [r for r in results if r.score.classification == CLASSIFICATION_DOWN]
        summary = f"{len(results)}件中 下落トレンド警告 {len(warnings)}件"
        self._render_results(results, errors, summary)


class PortfolioTab(QWidget):
    def __init__(self, repo: HoldingsRepository, parent=None):
        super().__init__(parent)
        self.repo = repo

        self.code_edit = QLineEdit()
        self.code_edit.setPlaceholderText("銘柄コード (例: 7203, AAPL)")
        self.market_combo = QComboBox()
        self.market_combo.addItems(["自動判定", "JP", "US"])

        self.add_button = QPushButton("追加")
        self.add_button.clicked.connect(self._add)
        self.remove_button = QPushButton("選択を削除")
        self.remove_button.clicked.connect(self._remove_selected)
        self.refresh_button = QPushButton("更新")
        self.refresh_button.clicked.connect(self.refresh)

        form_row = QHBoxLayout()
        form_row.addWidget(self.code_edit)
        form_row.addWidget(self.market_combo)
        form_row.addWidget(self.add_button)
        form_row.addStretch(1)

        button_row = QHBoxLayout()
        button_row.addWidget(self.remove_button)
        button_row.addWidget(self.refresh_button)
        button_row.addStretch(1)

        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["コード", "市場"])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.horizontalHeader().setStretchLastSection(True)

        layout = QVBoxLayout()
        layout.addLayout(form_row)
        layout.addLayout(button_row)
        layout.addWidget(self.table)
        self.setLayout(layout)

        self.refresh()

    def refresh(self) -> None:
        holdings = self.repo.list()
        self.table.setRowCount(len(holdings))
        for row, holding in enumerate(holdings):
            self.table.setItem(row, 0, QTableWidgetItem(holding.code))
            self.table.setItem(row, 1, QTableWidgetItem(holding.market))

    def _add(self) -> None:
        raw_code = self.code_edit.text().strip()
        if not raw_code:
            QMessageBox.warning(self, "入力エラー", "銘柄コードを入力してください")
            return

        market_choice = self.market_combo.currentText()
        market = detect_market(raw_code) if market_choice == "自動判定" else market_choice
        code = normalize_code(raw_code, market)

        try:
            self.repo.add(code, market)
        except DuplicateHoldingError as exc:
            QMessageBox.warning(self, "追加エラー", str(exc))
            return

        self.code_edit.clear()
        self.refresh()

    def _remove_selected(self) -> None:
        selected_rows = self.table.selectionModel().selectedRows()
        if not selected_rows:
            QMessageBox.information(self, "保有銘柄の削除", "削除する行を選択してください")
            return

        row = selected_rows[0].row()
        code = self.table.item(row, 0).text()
        market = self.table.item(row, 1).text()

        try:
            self.repo.remove(code, market)
        except (HoldingNotFoundError, AmbiguousHoldingError) as exc:
            QMessageBox.warning(self, "削除エラー", str(exc))
            return

        self.refresh()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Stock Trend Scorer")
        self.resize(900, 600)

        repo = HoldingsRepository()

        tabs = QTabWidget()
        self.portfolio_tab = PortfolioTab(repo)
        self.scan_tab = ScanTab()
        self.watch_tab = WatchTab(repo)
        tabs.addTab(self.portfolio_tab, "保有銘柄")
        tabs.addTab(self.scan_tab, "新規発掘 (Scan)")
        tabs.addTab(self.watch_tab, "保有監視 (Watch)")
        tabs.currentChanged.connect(self._on_tab_changed)

        self.setCentralWidget(tabs)

    def _on_tab_changed(self, _index: int) -> None:
        self.portfolio_tab.refresh()


def main() -> None:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
