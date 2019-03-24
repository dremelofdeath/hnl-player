#!/usr/bin/python
# -*- coding: utf-8 -*-
# vim:ts=2:sw=2:et:ai

import mutagen
import os.path
import sys

from euphonogenizer import titleformat as tf

from PyQt5 import QtCore
from PyQt5.QtCore import Qt, QAbstractTableModel, QModelIndex, QUrl
from PyQt5.QtWidgets import *


playlistAllowedMimeTypes = [
    'application/x-qabstractitemmodeldatalist',
    'text/uri-list',
]


class PlaylistModel(QAbstractTableModel):
  def __init__(self, columnFormats, tracks, parent=None):
    super().__init__(parent)
    self.columnFormats = columnFormats
    self.tracks = tracks

  def rowCount(self, parent=QModelIndex()):
    return len(self.tracks)

  def columnCount(self, parent=QModelIndex()):
    return len(self.columnFormats)

  def data(self, index, role):
    if index.isValid() and role == Qt.DisplayRole:
      return self.columnFormats[index.column()][2](self.tracks[index.row()])

  def headerData(self, section, orientation, role):
    if role == Qt.DisplayRole and orientation == Qt.Horizontal:
      return self.columnFormats[section][0]

  def insertTrack(self, row, track):
    if row < 0:
      row = len(self.tracks)
    self.layoutAboutToBeChanged.emit()
    self.tracks.insert(row, track)
    self.layoutChanged.emit()

  def insertTrackPath(self, row, track_path):
    track = mutagen.File(track_path, easy=True)
    if track:
      self.insertTrack(row, track)
    else:
      print(f'Failed to insert file "{track_path}"')

  def moveRow(
      self, sourceParent, sourceRow, destinationParent, destinationChild):
    self.beginMoveRows(
        sourceParent, sourceRow, sourceRow,
        destinationParent, destinationChild)
    if sourceRow > destinationChild:
      self.tracks.insert(destinationChild, self.tracks.pop(sourceRow))
    elif sourceRow < destinationChild:
      self.tracks.insert(destinationChild - 1, self.tracks.pop(sourceRow))
    self.endMoveRows()
    return True

  def moveRows(
      self, sourceParent, sourceRow, count,
      destinationParent, destinationChild):
    self.beginMoveRows(
        sourceParent, sourceRow, sourceRow + count - 1,
        destinationParent, destinationChild)
    if sourceRow > destinationChild:
      self.tracks = (self.tracks[:destinationChild]
              + self.tracks[destinationChild:sourceRow]
              + self.tracks[sourceRow:sourceRow+count]
              + self.tracks[sourceRow+count:])
    else:
      self.tracks = (self.tracks[:sourceRow]
              + self.tracks[sourceRow:sourceRow+count]
              + self.tracks[sourceRow+count:destinationChild]
              + self.tracks[destinationChild:])
    self.endMoveRows()
    return True

  def removeRow(self, row, parent):
    self.beginRemoveRows(parent, row, row)
    del self.tracks[row]
    self.endRemoveRows()
    return True

  def removeRows(self, row, count, parent):
    self.beginRemoveRows(parent, row, row + count - 1)
    del self.tracks[row:row + count - 1]
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


class PlaylistTableView(QTableView):
  def __init__(self, playlist: PlaylistModel, parent=None):
    super().__init__(parent)
    self.playlist = playlist
    self.setModel(playlist)
    self.setShowGrid(False)
    self.setWordWrap(False)
    self.setAlternatingRowColors(True)
    self.setSelectionBehavior(QAbstractItemView.SelectRows)
    self.setSelectionMode(QAbstractItemView.ExtendedSelection)
    self.setAcceptDrops(True)
    self.setDropIndicatorShown(True)
    self.setDragDropMode(QAbstractItemView.DragDrop)
    hh = self.horizontalHeader()
    hh.setHighlightSections(False)
    hh.setDefaultAlignment(Qt.AlignLeft)
    vh = self.verticalHeader()
    vh.setSectionResizeMode(QHeaderView.ResizeToContents)
    vh.setSectionsMovable(True)
    vh.setDragEnabled(True)
    vh.setDragDropMode(QAbstractItemView.InternalMove)
    vh.hide()
    for i, each in enumerate(playlist.columnFormats):
      self.setColumnWidth(i, each[1])

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
  def __init__(self, menu):
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
  def __init__(self, menu):
    self.menu = menu
    self.undo = menu.addAction('Undo', lambda: None)
    self.redo = menu.addAction('Redo', lambda: None)


class PlayerViewMenuContainer:
  def __init__(self, menu):
    self.menu = menu


class PlayerPlaybackMenuContainer:
  def __init__(self, menu):
    self.menu = menu


class PlayerLibraryMenuContainer:
  def __init__(self, menu):
    self.menu = menu


class PlayerHelpMenuContainer:
  def __init__(self, menu):
    self.menu = menu
    self.checkForUpdates = menu.addAction('Check for Updates...', lambda: None)
    self.creditsSeparator = menu.addSeparator()
    self.about = menu.addAction('About', lambda: None)


class PlayerMenuBarContainer:
  def __init__(self, menuBar):
    self.menuBar = menuBar
    self.file = PlayerFileMenuContainer(menuBar.addMenu('File'))
    self.edit = PlayerEditMenuContainer(menuBar.addMenu('Edit'))
    self.view = PlayerViewMenuContainer(menuBar.addMenu('View'))
    self.playback = PlayerPlaybackMenuContainer(menuBar.addMenu('Playback'))
    self.library = PlayerLibraryMenuContainer(menuBar.addMenu('Library'))
    self.help = PlayerHelpMenuContainer(menuBar.addMenu('Help'))


def fetch_meta(obj, field):
  if type(obj[field]) is list:
    return obj[field][0]
  return obj[field]


class PlayerMainWindow(QMainWindow):
  def __init__(self):
    super().__init__()
    self.setWindowTitle('HNL')
    self.menuBarContainer = PlayerMenuBarContainer(self.menuBar())
    self.playerControlsToolbar = self.buildPlayerControlsToolbar()
    self.resize(800, 600)
    self.layout = QVBoxLayout()
    self.playlist = PlaylistModel([
        ('Track', 30, lambda x: fetch_meta(x, 'tracknumber')),
        ('Title', 180, lambda x: fetch_meta(x, 'title')),
        ('Artist', 180, lambda x: fetch_meta(x, 'artist')),
        ('Album', 180, lambda x: fetch_meta(x, 'album')),
      ], [])
    self.playlistView = PlaylistTableView(self.playlist)
    self.layout.addWidget(self.playlistView)
    self.slider = NowPlayingSlider()
    self.layout.addWidget(self.slider)
    self.centralWidget = QWidget()
    self.centralWidget.setLayout(self.layout)
    self.setCentralWidget(self.centralWidget)

  def buildPlayerControlsToolbar(self):
    toolbar = self.addToolBar('Controls')
    stop = toolbar.addAction(
        self.style().standardIcon(QStyle.SP_MediaStop), '', lambda: None)
    play = toolbar.addAction(
        self.style().standardIcon(QStyle.SP_MediaPlay), '', lambda: None)
    pause = toolbar.addAction(
        self.style().standardIcon(QStyle.SP_MediaPause), '', lambda: None)
    back = toolbar.addAction(
        self.style().standardIcon(QStyle.SP_MediaSkipBackward), '', lambda: None)
    forward = toolbar.addAction(
        self.style().standardIcon(QStyle.SP_MediaSkipForward), '', lambda: None)
    return toolbar


def main():
  app = QApplication([])
  main_window = PlayerMainWindow()
  main_window.show()
  sys.exit(app.exec_())


if __name__ == "__main__":
  main()
