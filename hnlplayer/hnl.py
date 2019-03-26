#!/usr/bin/python
# -*- coding: utf-8 -*-
# vim:ts=2:sw=2:et:ai

import copy
import mutagen
import os.path
import sys
import traceback

from euphonogenizer import titleformat as tf

from typing import Dict, List

from PyQt5 import QtCore
from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *


class FatalError(Exception):
  pass


class BenignError(Exception):
  pass


class InvalidActionError(BenignError):
  pass


def get_standard_icon(
    style: QStyle, sp: QStyle.StandardPixmap,
    minimumWidth: int, parent: QWidget = None) -> QLabel:
  si = style.standardIcon(sp)
  icon = QLabel(parent)
  i = 0
  avail = si.availableSizes()
  l = len(avail)
  while i < l and avail[i].width() < minimumWidth:
    i += 1
  icon.setPixmap(si.pixmap(avail[i]))
  return icon


class InternalErrorDialog(QDialog):
  def __init__(self, title, msg, parent=None):
    super().__init__(parent)

    self.setWindowTitle(title)
    self.resize(320, 120)
    self.setWindowFlags(
        Qt.Dialog | Qt.CustomizeWindowHint
        | Qt.WindowTitleHint | Qt.WindowCloseButtonHint)

    self.gridLayout = QGridLayout(self)
    self.gridLayout.setSpacing(8)

    self.icon = get_standard_icon(
        self.style(), QStyle.SP_MessageBoxCritical, 32, self)

    self.msg = QLabel(f'An unexpected error occurred.\n\n{msg}', self)

    self.msg.setWordWrap(True)
    self.msg.setAlignment(Qt.AlignLeft | Qt.AlignTop)

    self.gridLayout.addWidget(self.icon, 0, 0, Qt.AlignLeft | Qt.AlignTop)
    self.gridLayout.addWidget(self.msg, 0, 1, 1, 3)
    self.gridLayout.setColumnStretch(1, 1)

    self.showDetailsButton = QPushButton('Show Details', self)
    self.okButton = QPushButton('OK', self)

    self.gridLayout.addWidget(
        self.showDetailsButton, 1, 0, 1, 2, Qt.AlignLeft | Qt.AlignBottom)
    self.gridLayout.addWidget(
        self.okButton, 1, 2, 1, 2, Qt.AlignRight | Qt.AlignBottom)

    self.okButton.clicked.connect(self.accept)
    self.showDetailsButton.clicked.connect(lambda: self.done(2))


class ShowErrorDetailsDialog(QDialog):
  def __init__(self, title, msg, parent=None):
    super().__init__(parent)

    self.setWindowTitle(title)
    self.resize(520, 390)
    self.setWindowFlags(
        Qt.Dialog | Qt.CustomizeWindowHint
        | Qt.WindowTitleHint | Qt.WindowCloseButtonHint)

    self.gridLayout = QVBoxLayout(self)

    self.detailsBox = QPlainTextEdit(msg, self)
    self.okButton = QPushButton('OK', self)

    self.detailsBox.setReadOnly(True)
    self.okButton.clicked.connect(self.accept)

    self.gridLayout.addWidget(self.detailsBox)
    self.gridLayout.addWidget(self.okButton, 0, Qt.AlignCenter)


def hnl_exception_hook(etype, value, tb):
  dialog = InternalErrorDialog('Internal Error', str(value))
  if dialog.exec() == 2:
    dialog = ShowErrorDetailsDialog('Error Details',
        ''.join(traceback.format_exception(etype, value, tb)))
    dialog.exec()


sys.excepthook = hnl_exception_hook


disabledPalette = QPalette()
disabledPalette.setColor(QPalette.Base, Qt.lightGray)


# From Foobar-like keys to Mutagen keys
mutagen_redirect_keys: Dict[str, str] = {
    'album artist': 'albumartist',
    'publisher': 'organization',
    'totaldiscs': 'disctotal',
    'totaltracks': 'tracktotal',
}


def marshal_key(key: str) -> str:
  if key not in mutagen_redirect_keys:
    return key
  return mutagen_redirect_keys[key]


class MutagenFileProxy:
  __slots__ = 'mutagen_file'

  def __init__(self, mutagen_file):
    self.mutagen_file = mutagen_file

  def __getattr__(self, attr):
    if attr in (
        'get', 'mutagen_file', '__getitem__', '__setitem__', '__delitem__'):
      return object.__getattribute__(self, attr)
    return getattr(self.mutagen_file, attr)

  def get(self, key, default=None):
    item = self.mutagen_file.get(marshal_key(key), default)
    if isinstance(item, list):
      return item[0]
    return item

  def __getitem__(self, key):
    item = self.mutagen_file[marshal_key(key)]
    if isinstance(item, list):
      return item[0]
    return item

  def __setitem__(self, key, value):
    self.mutagen_file[key] = value

  def __delitem__(self, key):
    del self.mutagen_file[key]


playlistAllowedMimeTypes = [
    'application/x-qabstractitemmodeldatalist',
    'text/uri-list',
]


class PlaylistColumn:
  __slots__ = 'name', 'defaultWidth', '_fmt', '_tfc'

  def __init__(self, name='', defaultWidth=180, fmt=''):
    self.name = name
    self.defaultWidth = defaultWidth
    self.fmt = fmt

  @property
  def fmt(self):
    return self._fmt

  @fmt.setter
  def fmt(self, fmt: str):
    self._fmt = fmt
    self._tfc = tf.compile(fmt)

  def format(self, track):
    return self._tfc(track)

  def __copy__(self):
    return PlaylistColumn(self.name, self.defaultWidth, self.fmt)

  def __deepcopy__(self, memo=None):
    return PlaylistColumn(self.name, self.defaultWidth, self.fmt)


class PlaylistModel(QAbstractTableModel):
  def __init__(
      self,
      columns: List[PlaylistColumn],
      tracks: List[MutagenFileProxy],
      parent=None):
    super().__init__(parent)
    self._columns: List[PlaylistColumn] = columns
    self._tracks: List[MutagenFileProxy] = tracks

  @property
  def columns(self):
    return self._columns

  @columns.setter
  def columns(self, columns: List[PlaylistColumn]) -> None:
    self.layoutAboutToBeChanged.emit()
    self._columns = columns
    self.layoutChanged.emit()

  def getTrack(self, index: QModelIndex) -> MutagenFileProxy:
    if index.isValid():
      return self._tracks[index.row()]

  def rowCount(self, parent=QModelIndex()):
    return len(self._tracks)

  def columnCount(self, parent=QModelIndex()):
    return len(self.columns)

  def data(self, index, role):
    if index.isValid() and role == Qt.DisplayRole:
      return self.columns[index.column()].format(self._tracks[index.row()])

  def headerData(self, section, orientation, role):
    if role == Qt.DisplayRole and orientation == Qt.Horizontal:
      return self.columns[section].name

  def insertTrack(self, row, track):
    if row < 0:
      row = len(self._tracks)
    self.layoutAboutToBeChanged.emit()
    self._tracks.insert(row, track)
    self.layoutChanged.emit()

  def insertTrackPath(self, row, track_path):
    track = mutagen.File(track_path, easy=True)
    if track:
      self.insertTrack(row, MutagenFileProxy(track))
    else:
      print(f'Failed to insert file "{track_path}"')

  def moveRow(
      self, sourceParent, sourceRow, destinationParent, destinationChild):
    self.beginMoveRows(
        sourceParent, sourceRow, sourceRow,
        destinationParent, destinationChild)
    if sourceRow > destinationChild:
      self._tracks.insert(destinationChild, self._tracks.pop(sourceRow))
    elif sourceRow < destinationChild:
      self._tracks.insert(destinationChild - 1, self._tracks.pop(sourceRow))
    self.endMoveRows()
    return True

  def moveRows(
      self, sourceParent, sourceRow, count,
      destinationParent, destinationChild):
    self.beginMoveRows(
        sourceParent, sourceRow, sourceRow + count - 1,
        destinationParent, destinationChild)
    if sourceRow > destinationChild:
      self._tracks = (self._tracks[:destinationChild]
              + self._tracks[destinationChild:sourceRow]
              + self._tracks[sourceRow:sourceRow+count]
              + self._tracks[sourceRow+count:])
    else:
      self._tracks = (self._tracks[:sourceRow]
              + self._tracks[sourceRow:sourceRow+count]
              + self._tracks[sourceRow+count:destinationChild]
              + self._tracks[destinationChild:])
    self.endMoveRows()
    return True

  def removeRow(self, row, parent):
    self.beginRemoveRows(parent, row, row)
    del self._tracks[row]
    self.endRemoveRows()
    return True

  def removeRows(self, row, count, parent):
    self.beginRemoveRows(parent, row, row + count - 1)
    del self._tracks[row:row + count - 1]
    self.endRemoveRows()
    return True

  def supportedDropActions(self):
    return Qt.CopyAction | Qt.MoveAction

  def flags(self, index: QModelIndex) -> Qt.ItemFlags:
    if index.isValid():
      return Qt.ItemIsDragEnabled | super().flags(index)
    return Qt.ItemIsDropEnabled | super().flags(index)

  def mimeTypes(self):
    return playlistAllowedMimeTypes

  def dropMimeData(self, data, action, row, column, parent):
    if action & Qt.CopyAction and data.hasUrls():
      row_delta = row >= 0
      for each in data.urls():
        each = each.toString(QUrl.PreferLocalFile)
        print(each)
        if os.path.isfile(each):
          self.insertTrackPath(row, each)
          row += row_delta
        elif os.path.isdir(each):
          for dirpath, dirnames, filenames in os.walk(each):
            for filename in filenames:
              fullpath = os.path.join(dirpath, filename)
              if os.path.isfile(fullpath):
                self.insertTrackPath(row, fullpath)
                row += row_delta

      return True
    return super().dropMimeData(data, action, row, column, parent)


def is_contiguous(seq):
  last = seq[0].row()

  for i in seq:
    if i.row() != last + 1 and i.row() != last:
      return False
  return True


def set_basic_table_styles(
    tableView: QTableView, hh: QHeaderView, vh: QHeaderView) -> None:
  tableView.setShowGrid(False)
  tableView.setWordWrap(False)
  tableView.setAlternatingRowColors(True)
  tableView.setSelectionBehavior(QAbstractItemView.SelectRows)
  hh.setHighlightSections(False)
  hh.setDefaultAlignment(Qt.AlignLeft)
  vh.setSectionResizeMode(QHeaderView.ResizeToContents)
  vh.setHighlightSections(False)


class ColumnConfigurationModel(QAbstractTableModel):
  def __init__(self, columnsToConfigure: List[PlaylistColumn], parent):
    super().__init__(parent)
    self.columnsToConfigure = columnsToConfigure

  def rowCount(self, parent=QModelIndex()):
    return len(self.columnsToConfigure)

  def columnCount(self, parent=QModelIndex()):
    return 3

  def data(self, index, role):
    if index.isValid() and role == Qt.DisplayRole:
      col = index.column()
      if col == 0:
        return self.columnsToConfigure[index.row()].name
      elif col == 1:
        return self.columnsToConfigure[index.row()].defaultWidth
      elif col == 2:
        return self.columnsToConfigure[index.row()].fmt

  def headerData(self, section, orientation, role):
    if role == Qt.DisplayRole and orientation == Qt.Horizontal:
      if section == 0:
        return 'Name'
      elif section == 1:
        return 'Width'
      elif section == 2:
        return 'Format'


class ColumnConfigurationTableView(QTableView):
  def __init__(self, columns, parent):
    super().__init__(parent)
    self.columns = columns
    self.columnsModel = ColumnConfigurationModel(columns, self)
    self.setModel(self.columnsModel)

    hh = self.horizontalHeader()
    vh = self.verticalHeader()

    set_basic_table_styles(self, hh, vh)

    self.setSelectionMode(QAbstractItemView.SingleSelection)

    hh.setStretchLastSection(True)


class ColumnConfigurationLayout(QGridLayout):
  def __init__(
      self,
      columns: List[PlaylistColumn],
      mainWindow: QMainWindow,
      parent: QWidget):
    super().__init__(parent)

    columns = copy.deepcopy(columns)
    self.columns = columns
    self.mainWindow = mainWindow
    self.parent = parent

    self.columnsTableView = ColumnConfigurationTableView(columns, parent)
    self.addWidget(self.columnsTableView, 1, 1, 2, 4)

    self.columnNameLabel = QLabel('&Name:', parent)
    self.columnNameTextBox = QLineEdit(parent)
    self.columnNameLabel.setBuddy(self.columnNameTextBox)
    self.columnWidthLabel = QLabel('&Width:', parent)
    self.columnWidthTextBox = QLineEdit(parent)
    self.columnWidthLabel.setBuddy(self.columnWidthTextBox)
    self.columnFormatLabel = QLabel('&Format:', parent)
    self.columnFormatTextBox = QLineEdit(parent)
    self.columnFormatLabel.setBuddy(self.columnFormatTextBox)

    widthValidator = QIntValidator(self.columnWidthTextBox)
    widthLocale = QLocale()
    widthLocale.setNumberOptions(QLocale.NumberOption.RejectGroupSeparator)
    widthValidator.setLocale(widthLocale)
    self.columnWidthTextBox.setValidator(widthValidator)

    self.addWidget(self.columnNameLabel, 3, 1)
    self.addWidget(self.columnNameTextBox, 3, 2)
    self.addWidget(self.columnWidthLabel, 3, 3)
    self.addWidget(self.columnWidthTextBox, 3, 4)
    self.addWidget(self.columnFormatLabel, 4, 1, 1, 1)
    self.addWidget(self.columnFormatTextBox, 4, 2, 1, 3)

    self.columnNameTextBox.textChanged.connect(self.onColumnNameChanged)
    self.columnWidthTextBox.textChanged.connect(self.onColumnWidthChanged)
    self.columnFormatTextBox.textChanged.connect(self.onColumnFormatChanged)
    self.columnNameTextBox.textEdited.connect(self.onColumnNameEdited)
    self.columnWidthTextBox.textEdited.connect(self.onColumnWidthEdited)
    self.columnFormatTextBox.textEdited.connect(self.onColumnFormatEdited)

    self.previewLabel = QLabel('Preview:', parent)
    self.previewTextBox = QLineEdit(parent)
    self.previewLabel.setBuddy(self.previewTextBox)
    self.previewTextBox.setReadOnly(True)
    self.previewTextBox.setPalette(disabledPalette)

    self.addWidget(self.previewLabel, 5, 1, 1, 1)
    self.addWidget(self.previewTextBox, 5, 2, 1, 3)

    self.addNewButton = QPushButton('Add New', parent)
    self.deleteButton = QPushButton('Delete', parent)
    self.resetButton = QPushButton('Reset', parent)

    if isinstance(parent, QDialog):
      self.saveButton = QPushButton('OK', parent)
    else:
      self.saveButton = QPushButton('Save', parent)

    self.addNewButton.clicked.connect(self.onAddNewButtonClicked)
    self.deleteButton.clicked.connect(self.onDeleteButtonClicked)
    self.resetButton.clicked.connect(self.onResetButtonClicked)
    self.saveButton.clicked.connect(self.onSaveButtonClicked)

    self.buttonLayout = QHBoxLayout()
    self.buttonLayout.addWidget(self.addNewButton)
    self.buttonLayout.addWidget(self.deleteButton)
    self.buttonLayout.addWidget(self.resetButton)
    self.buttonLayout.addStretch()
    self.buttonLayout.addWidget(self.saveButton)

    self.addLayout(self.buttonLayout, 6, 1, 1, 4)

    self.selectionModel = self.columnsTableView.selectionModel()
    self.selectionModel.currentRowChanged.connect(self.onCurrentRowChanged)

  def onCurrentRowChanged(self, current, previous):
    col = self.columns[current.row()]
    self.columnNameTextBox.setText(col.name)
    self.columnWidthTextBox.setText(str(col.defaultWidth))
    self.columnFormatTextBox.setText(col.fmt)

  def onColumnNameChanged(self, text):
    pass

  def onColumnNameEdited(self, text):
    self.onColumnNameChanged(text)
    self.handleColumnEdit(0, text)

  def onColumnWidthChanged(self, text):
    pass

  def onColumnWidthEdited(self, text):
    self.onColumnWidthChanged(text)
    self.handleColumnEdit(1, text)

  def onColumnFormatChanged(self, text):
    self.previewTextBox.setText(
        str(tf.format(text, self.mainWindow.playlistView.currentTrack)))

  def onColumnFormatEdited(self, text):
    self.onColumnFormatChanged(text)
    self.handleColumnEdit(2, text)

  def handleColumnEdit(self, col, text):
    index = self.selectionModel.currentIndex()
    if index.isValid():
      row = index.row()
      if col == 0:
        self.columns[row].name = text
      elif col == 1:
        self.columns[row].defaultWidth = int(text) if text else 0
      elif col == 2:
        self.columns[row].fmt = text
      else:
        raise IndexError(f"Can't edit nonexistent column {col}.")
      index = self.columnsTableView.columnsModel.createIndex(row, col)
      self.columnsTableView.dataChanged(index, index)

  def onAddNewButtonClicked(self, checked):
    if len(self.columns) == 1:
      self.deleteButton.setEnabled(True)

    cm = self.columnsTableView.columnsModel

    cm.layoutAboutToBeChanged.emit()
    self.columns.append(PlaylistColumn())
    cm.layoutChanged.emit()

    newRowIndex = cm.index(len(self.columns) - 1, 0)
    sm = self.selectionModel

    sm.setCurrentIndex(newRowIndex, QItemSelectionModel.NoUpdate)
    sm.select(
        newRowIndex,
        QItemSelectionModel.ClearAndSelect | QItemSelectionModel.Rows)

    self.columnNameTextBox.setFocus()

  def onDeleteButtonClicked(self, checked):
    if len(self.columns) <= 1:
      raise InvalidActionError('Attempted to delete the only remaining column.')

    index = self.selectionModel.currentIndex()
    if index.isValid():
      row = index.row()
      cm = self.columnsTableView.columnsModel

      cm.layoutAboutToBeChanged.emit()
      del self.columns[row]
      cm.layoutChanged.emit()

      if row != len(self.columns):
        # Force the update because changing the index to itself does nothing
        self.onCurrentRowChanged(cm.index(row, 0), None)
        return

      newRowIndex = cm.index(row - 1, 0)
      sm = self.selectionModel

      sm.setCurrentIndex(newRowIndex, QItemSelectionModel.NoUpdate)
      sm.select(
          newRowIndex,
          QItemSelectionModel.ClearAndSelect | QItemSelectionModel.Rows)

      if len(self.columns) <= 1:
        self.deleteButton.setEnabled(False)

  def onResetButtonClicked(self, checked):
    # TODO: Dialog asking if the user wants to reset to the playlist or defaults
    self.deleteButton.setEnabled(True)

  def onSaveButtonClicked(self, checked):
    self.mainWindow.playlistView.columns = self.columns
    if isinstance(self.parent, QDialog):
      self.parent.done(QDialog.Accepted)


class ConfigureColumnsDialog(QDialog):
  def __init__(self, columns, mainWindow, parent):
    super().__init__(parent)
    self.columns = columns
    self.mainWindow = mainWindow

    self.setModal(False)
    self.setWindowTitle('Configure Columns')
    self.resize(640, 480)

    self.contents = ColumnConfigurationLayout(columns, mainWindow, self)


class PlaylistTableView(QTableView):
  def __init__(self, parent=None):
    super().__init__(parent)

    self.mainWindow = parent

    self.playlist = PlaylistModel([
        PlaylistColumn('Track', 30, '%track%'),
        PlaylistColumn('Title', 180, '%title%'),
        PlaylistColumn('Artist', 180, '%artist%'),
        PlaylistColumn('Album', 180, '%album%'),
      ], [])

    self.setModel(self.playlist)
    self.nowPlaying: int = -1

    hh = self.horizontalHeader()
    vh = self.verticalHeader()

    set_basic_table_styles(self, hh, vh)

    self.setSelectionMode(QAbstractItemView.ExtendedSelection)
    self.setAcceptDrops(True)
    self.setDropIndicatorShown(True)
    self.setDragDropMode(QAbstractItemView.DragDrop)

    hh.setContextMenuPolicy(Qt.CustomContextMenu)
    hh.customContextMenuRequested.connect(self.enactColumnContextMenu)

    ccm = QMenu()
    self.addColumn = ccm.addAction('Add Column...', lambda: None)
    self.columnContextMenu = ccm

    vh.setSectionsMovable(True)
    vh.setDragEnabled(True)
    vh.setDragDropMode(QAbstractItemView.InternalMove)
    vh.hide()

    for i, each in enumerate(self.playlist.columns):
      self.setColumnWidth(i, each.defaultWidth)

    self.doubleClicked.connect(self.onDoubleClicked)

  @property
  def columns(self):
    return self.playlist.columns

  @columns.setter
  def columns(self, columns: List[PlaylistColumn]) -> None:
    self.playlist.columns = columns

  @property
  def currentTrack(self):
    if self.nowPlaying >= 0:
      return self.playlist._tracks[self.nowPlaying]

  def onDoubleClicked(self, index: QModelIndex) -> None:
    if index.isValid():
      self.play(index)

  def play(self, trackIndex: QModelIndex) -> None:
    self.nowPlaying = trackIndex.row()
    track = self.playlist.getTrack(trackIndex)
    self.mainWindow.updateTitleForPlayingTrack(track)

  def enactColumnContextMenu(self, pos):
    self.columnContextMenu.exec_(self.mapToGlobal(pos))

  def dropEvent(self, event):
    if not event.isAccepted() and event.source() == self:
      if event.dropAction() == Qt.CopyAction:
        event.setDropAction(Qt.MoveAction)
        selectionModel = self.selectionModel()

        if not selectionModel.hasSelection():
          return

        moving = list(sorted(item for item in selectionModel.selectedRows()))

        if moving:
          pos = event.pos()
          dest = self.indexAt(pos)
          rect = self.visualRect(dest)


          if not dest.isValid():
            dest = self.playlist.rowCount()
          else:
            dest = dest.row() + (rect.bottom() - pos.y() < 0
              or rect.contains(pos) and pos.y() >= rect.center().y())

          if is_contiguous(moving):
            start = moving[0].row()
            count = len(moving)
            if start + count != dest:
              if count > 1:
                self.playlist.moveRows(
                    self.playlist.createIndex(start, -1), start, count,
                    self.playlist.createIndex(dest, -1), dest)
              else:
                self.playlist.moveRow(
                    self.playlist.createIndex(start, -1), start,
                    self.playlist.createIndex(dest, -1), dest)

            event.accept()
          else:
            pass

    super().dropEvent(event)


class SliderSelectDirectJumpProxyStyle(QProxyStyle):
  def __init__(self, style):
    super().__init__(style)

  def styleHint(self, hint, option, widget, returnData):
    if hint == QStyle.SH_Slider_AbsoluteSetButtons:
      return Qt.LeftButton
    return super().styleHint(hint, option, widget, returnData)


class NowPlayingSlider(QSlider):
  def __init__(self, parent=None):
    super().__init__(Qt.Horizontal, parent)
    self.setInvertedControls(True)
    self.setStyle(SliderSelectDirectJumpProxyStyle(self.style()))


class PlayerFileMenuContainer:
  def __init__(self, mainWindow, menu):
    self.menu = menu
    self.open = menu.addAction('Open...', lambda: None)
    self.openDisc = menu.addAction('Open Disc...', lambda: None)
    self.openSeparator = menu.addSeparator()
    self.newPlaylist = menu.addAction('New Playlist', lambda: None)
    self.openPlaylist = menu.addAction('Open Playlist', lambda: None)
    self.savePlaylist = menu.addAction('Save Playlist', lambda: None)
    self.playlistSeparator = menu.addSeparator()
    self.exit = menu.addAction('Exit', lambda: None)


class PlayerEditMenuContainer:
  def __init__(self, mainWindow, menu):
    self.menu = menu
    self.undo = menu.addAction('Undo', lambda: None)
    self.redo = menu.addAction('Redo', lambda: None)


class PlayerViewMenuContainer:
  def __init__(self, mainWindow, menu):
    self.mainWindow = mainWindow
    self.menu = menu
    self.configureColumns = menu.addAction(
        'Configure Columns...', self.onConfigureColumns)

  def onConfigureColumns(self):
    configureColumnsDialog = ConfigureColumnsDialog(
        self.mainWindow.playlistView.columns, self.mainWindow, self.mainWindow)
    configureColumnsDialog.show()


class PlayerPlaybackMenuContainer:
  def __init__(self, mainWindow, menu):
    self.menu = menu


class PlayerLibraryMenuContainer:
  def __init__(self, mainWindow, menu):
    self.menu = menu


class PlayerHelpMenuContainer:
  def __init__(self, mainWindow, menu):
    self.menu = menu
    self.checkForUpdates = menu.addAction('Check for Updates...', lambda: None)
    self.creditsSeparator = menu.addSeparator()
    self.about = menu.addAction('About', lambda: None)


class PlayerMenuBarContainer:
  def __init__(self, mainWindow, menuBar):
    self.menuBar = menuBar
    self.file = PlayerFileMenuContainer(
        mainWindow, menuBar.addMenu('File'))
    self.edit = PlayerEditMenuContainer(
        mainWindow, menuBar.addMenu('Edit'))
    self.view = PlayerViewMenuContainer(
        mainWindow, menuBar.addMenu('View'))
    self.playback = PlayerPlaybackMenuContainer(
        mainWindow, menuBar.addMenu('Playback'))
    self.library = PlayerLibraryMenuContainer(
        mainWindow, menuBar.addMenu('Library'))
    self.help = PlayerHelpMenuContainer(
        mainWindow, menuBar.addMenu('Help'))


class PlayerMainWindow(QMainWindow):
  def __init__(self):
    super().__init__()
    self.setWindowTitle('HNL')
    self.menuBarContainer = PlayerMenuBarContainer(self, self.menuBar())
    self.playerControlsToolbar = self.buildPlayerControlsToolbar()
    self.resize(800, 600)
    self.layout = QVBoxLayout()
    self.playlistView = PlaylistTableView(self)
    self.layout.addWidget(self.playlistView)
    self.slider = NowPlayingSlider()
    self.layout.addWidget(self.slider)
    self.centralWidget = QWidget()
    self.centralWidget.setLayout(self.layout)
    self.setCentralWidget(self.centralWidget)

    self.playingTitleFormat = tf.compile(
      "HNL - %title% - %artist% - %album% '('#%track% / %totaltracks%')'")

  def buildPlayerControlsToolbar(self):
    style = self.style()
    toolbar = self.addToolBar('Controls')
    stop = toolbar.addAction(
        style.standardIcon(QStyle.SP_MediaStop), '', lambda: None)
    play = toolbar.addAction(
        style.standardIcon(QStyle.SP_MediaPlay), '', lambda: None)
    pause = toolbar.addAction(
        style.standardIcon(QStyle.SP_MediaPause), '', lambda: None)
    back = toolbar.addAction(
        style.standardIcon(QStyle.SP_MediaSkipBackward), '', lambda: None)
    forward = toolbar.addAction(
        style.standardIcon(QStyle.SP_MediaSkipForward), '', lambda: None)
    return toolbar

  def updateTitleForPlayingTrack(self, track: MutagenFileProxy) -> None:
    self.setWindowTitle(self.playingTitleFormat(track))


def main():
  app = QApplication(sys.argv)
  main_window = PlayerMainWindow()
  main_window.show()
  sys.exit(app.exec_())


if __name__ == "__main__":
  main()
