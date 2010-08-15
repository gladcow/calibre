#!/usr/bin/env  python
__license__   = 'GPL v3'
__copyright__ = '2008, Kovid Goyal kovid@kovidgoyal.net'
__docformat__ = 'restructuredtext en'

'''
Job management.
'''

import re

from Queue import Empty, Queue

from PyQt4.Qt import QAbstractTableModel, QVariant, QModelIndex, Qt, \
    QTimer, pyqtSignal, QIcon, QDialog, QAbstractItemDelegate, QApplication, \
    QSize, QStyleOptionProgressBarV2, QString, QStyle, QToolTip, QFrame, \
    QHBoxLayout, QVBoxLayout, QSizePolicy, QLabel, QCoreApplication, QAction, \
    QByteArray

from calibre.utils.ipc.server import Server
from calibre.utils.ipc.job import ParallelJob
from calibre.gui2 import Dispatcher, error_dialog, NONE, config, gprefs
from calibre.gui2.device import DeviceJob
from calibre.gui2.dialogs.jobs_ui import Ui_JobsDialog
from calibre import __appname__
from calibre.gui2.dialogs.job_view_ui import Ui_Dialog
from calibre.gui2.progress_indicator import ProgressIndicator

class JobManager(QAbstractTableModel):

    job_added = pyqtSignal(int)
    job_done  = pyqtSignal(int)

    def __init__(self):
        QAbstractTableModel.__init__(self)
        self.wait_icon     = QVariant(QIcon(I('jobs.svg')))
        self.running_icon  = QVariant(QIcon(I('exec.svg')))
        self.error_icon    = QVariant(QIcon(I('dialog_error.svg')))
        self.done_icon     = QVariant(QIcon(I('ok.svg')))

        self.jobs          = []
        self.add_job       = Dispatcher(self._add_job)
        self.server        = Server(limit=int(config['worker_limit']/2.0),
                                enforce_cpu_limit=config['enforce_cpu_limit'])
        self.changed_queue = Queue()

        self.timer         = QTimer(self)
        self.timer.timeout.connect(self.update, type=Qt.QueuedConnection)
        self.timer.start(1000)

    def columnCount(self, parent=QModelIndex()):
        return 4

    def rowCount(self, parent=QModelIndex()):
        return len(self.jobs)

    def headerData(self, section, orientation, role):
        if role != Qt.DisplayRole:
            return NONE
        if orientation == Qt.Horizontal:
            if   section == 0: text = _('Job')
            elif section == 1: text = _('Status')
            elif section == 2: text = _('Progress')
            elif section == 3: text = _('Running time')
            return QVariant(text)
        else:
            return QVariant(section+1)

    def show_tooltip(self, arg):
        widget, pos = arg
        QToolTip.showText(pos, self.get_tooltip())

    def get_tooltip(self):
        running_jobs = [j for j in self.jobs if j.run_state == j.RUNNING]
        waiting_jobs = [j for j in self.jobs if j.run_state == j.WAITING]
        lines = [_('There are %d running jobs:')%len(running_jobs)]
        for job in running_jobs:
            desc = job.description
            if not desc:
                desc = _('Unknown job')
            p = 100. if job.is_finished else job.percent
            lines.append('%s:  %.0f%% done'%(desc, p))
        lines.extend(['', _('There are %d waiting jobs:')%len(waiting_jobs)])
        for job in waiting_jobs:
            desc = job.description
            if not desc:
                desc = _('Unknown job')
            lines.append(desc)
        return '\n'.join(['calibre', '']+ lines)

    def data(self, index, role):
        try:
            if role not in (Qt.DisplayRole, Qt.DecorationRole):
                return NONE
            row, col = index.row(), index.column()
            job = self.jobs[row]

            if role == Qt.DisplayRole:
                if col == 0:
                    desc = job.description
                    if not desc:
                        desc = _('Unknown job')
                    return QVariant(desc)
                if col == 1:
                    return QVariant(job.status_text)
                if col == 2:
                    p = 100. if job.is_finished else job.percent
                    return QVariant(p)
                if col == 3:
                    rtime = job.running_time
                    if rtime is None:
                        return NONE
                    return QVariant('%dm %ds'%(int(rtime)//60, int(rtime)%60))
            if role == Qt.DecorationRole and col == 0:
                state = job.run_state
                if state == job.WAITING:
                    return self.wait_icon
                if state == job.RUNNING:
                    return self.running_icon
                if job.killed or job.failed:
                    return self.error_icon
                return self.done_icon
        except:
            import traceback
            traceback.print_exc()
        return NONE

    def update(self):
        try:
            self._update()
        except BaseException:
            import traceback
            traceback.print_exc()

    def _update(self):
        # Update running time
        for i, j in enumerate(self.jobs):
            if j.run_state == j.RUNNING:
                idx = self.index(i, 3)
                self.dataChanged.emit(idx, idx)

        # Update parallel jobs
        jobs = set([])
        while True:
            try:
                jobs.add(self.server.changed_jobs_queue.get_nowait())
            except Empty:
                break
        while True:
            try:
                jobs.add(self.changed_queue.get_nowait())
            except Empty:
                break

        if jobs:
            needs_reset = False
            for job in jobs:
                orig_state = job.run_state
                job.update()
                if orig_state != job.run_state:
                    needs_reset = True
            if needs_reset:
                self.jobs.sort()
                self.reset()
                if job.is_finished:
                    self.job_done.emit(len(self.unfinished_jobs()))
            else:
                for job in jobs:
                    idx = self.jobs.index(job)
                    self.dataChanged.emit(
                        self.index(idx, 0), self.index(idx, 3))


    def _add_job(self, job):
        self.layoutAboutToBeChanged.emit()
        self.jobs.append(job)
        self.jobs.sort()
        self.job_added.emit(len(self.unfinished_jobs()))
        self.layoutChanged.emit()

    def done_jobs(self):
        return [j for j in self.jobs if j.is_finished]

    def unfinished_jobs(self):
        return [j for j in self.jobs if not j.is_finished]

    def row_to_job(self, row):
        return self.jobs[row]

    def has_device_jobs(self):
        for job in self.jobs:
            if job.is_running and isinstance(job, DeviceJob):
                return True
        return False

    def has_jobs(self):
        for job in self.jobs:
            if job.is_running:
                return True
        return False

    def run_job(self, done, name, args=[], kwargs={},
                           description='', core_usage=1):
        job = ParallelJob(name, description, done, args=args, kwargs=kwargs)
        job.core_usage = core_usage
        self.add_job(job)
        self.server.add_job(job)
        return job

    def launch_gui_app(self, name, args=[], kwargs={}, description=''):
        job = ParallelJob(name, description, lambda x: x,
                args=args, kwargs=kwargs)
        self.server.run_job(job, gui=True, redirect_output=False)


    def kill_job(self, row, view):
        job = self.jobs[row]
        if isinstance(job, DeviceJob):
            return error_dialog(view, _('Cannot kill job'),
                         _('Cannot kill jobs that communicate with the device')).exec_()
        if job.duration is not None:
            return error_dialog(view, _('Cannot kill job'),
                         _('Job has already run')).exec_()
        self.server.kill_job(job)

    def kill_all_jobs(self):
        for job in self.jobs:
            if isinstance(job, DeviceJob) or job.duration is not None:
                continue
            self.server.kill_job(job)

    def terminate_all_jobs(self):
        self.server.killall()


class ProgressBarDelegate(QAbstractItemDelegate):

    def sizeHint(self, option, index):
        return QSize(120, 30)

    def paint(self, painter, option, index):
        opts = QStyleOptionProgressBarV2()
        opts.rect = option.rect
        opts.minimum = 1
        opts.maximum = 100
        opts.textVisible = True
        percent, ok = index.model().data(index, Qt.DisplayRole).toInt()
        if not ok:
            percent = 0
        opts.progress = percent
        opts.text = QString(_('Unavailable') if percent == 0 else '%d%%'%percent)
        QApplication.style().drawControl(QStyle.CE_ProgressBar, opts, painter)

class DetailView(QDialog, Ui_Dialog):

    def __init__(self, parent, job):
        QDialog.__init__(self, parent)
        self.setupUi(self)
        self.setWindowTitle(job.description)
        self.job = job
        self.next_pos = 0
        self.update()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update)
        self.timer.start(1000)


    def update(self):
        f = self.job.log_file
        f.seek(self.next_pos)
        more = f.read()
        self.next_pos = f.tell()
        if more:
            self.log.appendPlainText(more.decode('utf-8', 'replace'))

class JobsButton(QFrame):

    def __init__(self, horizontal=False, size=48, parent=None):
        QFrame.__init__(self, parent)
        if horizontal:
            size = 24
        self.pi = ProgressIndicator(self, size)
        self._jobs = QLabel('<b>'+_('Jobs:')+' 0')
        self._jobs.mouseReleaseEvent = self.mouseReleaseEvent
        self.shortcut = _('Shift+Alt+J')

        if horizontal:
            self.setLayout(QHBoxLayout())
            self.layout().setDirection(self.layout().RightToLeft)
        else:
            self.setLayout(QVBoxLayout())
            self._jobs.setAlignment(Qt.AlignHCenter|Qt.AlignBottom)

        self.layout().addWidget(self.pi)
        self.layout().addWidget(self._jobs)
        if not horizontal:
            self.layout().setAlignment(self._jobs, Qt.AlignHCenter)
        self._jobs.setMargin(0)
        self.layout().setMargin(0)
        self._jobs.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Minimum)
        self.setCursor(Qt.PointingHandCursor)
        b = _('Click to see list of jobs')
        self.setToolTip(b + u' (%s)'%self.shortcut)
        self.action_toggle = QAction(b, parent)
        parent.addAction(self.action_toggle)
        self.action_toggle.setShortcut(self.shortcut)
        self.action_toggle.triggered.connect(self.toggle)

    def initialize(self, jobs_dialog, job_manager):
        self.jobs_dialog = jobs_dialog
        job_manager.job_added.connect(self.job_added)
        job_manager.job_done.connect(self.job_done)
        self.jobs_dialog.addAction(self.action_toggle)


    def mouseReleaseEvent(self, event):
        self.toggle()

    def toggle(self, *args):
        if self.jobs_dialog.isVisible():
            self.jobs_dialog.hide()
        else:
            self.jobs_dialog.show()

    @property
    def is_running(self):
        return self.pi.isAnimated()

    def start(self):
        self.pi.startAnimation()

    def stop(self):
        self.pi.stopAnimation()

    def jobs(self):
        src = unicode(self._jobs.text())
        return int(re.search(r'\d+', src).group())

    def job_added(self, nnum):
        jobs = self._jobs
        src = unicode(jobs.text())
        num = self.jobs()
        text = src.replace(str(num), str(nnum))
        jobs.setText(text)
        self.start()

    def job_done(self, nnum):
        jobs = self._jobs
        src = unicode(jobs.text())
        num = self.jobs()
        text = src.replace(str(num), str(nnum))
        jobs.setText(text)
        if nnum == 0:
            self.no_more_jobs()

    def no_more_jobs(self):
        if self.is_running:
            self.stop()
            QCoreApplication.instance().alert(self, 5000)


class JobsDialog(QDialog, Ui_JobsDialog):

    def __init__(self, window, model):
        QDialog.__init__(self, window)
        Ui_JobsDialog.__init__(self)
        self.setupUi(self)
        self.jobs_view.setModel(model)
        self.model = model
        self.setWindowModality(Qt.NonModal)
        self.setWindowTitle(__appname__ + _(' - Jobs'))
        self.kill_button.clicked.connect(self.kill_job)
        self.details_button.clicked.connect(self.show_details)
        self.stop_all_jobs_button.clicked.connect(self.kill_all_jobs)
        self.pb_delegate = ProgressBarDelegate(self)
        self.jobs_view.setItemDelegateForColumn(2, self.pb_delegate)
        self.jobs_view.doubleClicked.connect(self.show_job_details)
        self.jobs_view.horizontalHeader().setMovable(True)
        self.restore_state()

    def restore_state(self):
        geom = gprefs.get('jobs_dialog_geometry', bytearray(''))
        self.restoreGeometry(QByteArray(geom))
        state = gprefs.get('jobs view column layout', bytearray(''))
        self.jobs_view.horizontalHeader().restoreState(QByteArray(state))

    def save_state(self):
        state = bytearray(self.jobs_view.horizontalHeader().saveState())
        gprefs['jobs view column layout'] = state
        geom = bytearray(self.saveGeometry())
        gprefs['jobs_dialog_geometry'] = geom


    def show_job_details(self, index):
        row = index.row()
        job = self.jobs_view.model().row_to_job(row)
        d = DetailView(self, job)
        d.exec_()
        d.timer.stop()

    def kill_job(self, *args):
        for index in self.jobs_view.selectedIndexes():
            row = index.row()
            self.model.kill_job(row, self)
            return

    def show_details(self, *args):
        for index in self.jobs_view.selectedIndexes():
            self.show_job_details(index)
            return

    def kill_all_jobs(self, *args):
        self.model.kill_all_jobs()

    def closeEvent(self, e):
        self.save_state()
        return QDialog.closeEvent(self, e)

    def show(self, *args):
        self.restore_state()
        return QDialog.show(self, *args)

    def hide(self, *args):
        self.save_state()
        return QDialog.hide(self, *args)
