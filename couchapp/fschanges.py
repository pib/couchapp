import logging
import time
import re
import os
import os.path

try:
    import gamin
except ImportError:
    gamin = None
try:
    import win32file
    import win32event
    import win32con
except ImportError:
    win32file = None

logger = logging.getLogger(__name__)


def _gamin_watch(path, ignore):
    watched_events = {gamin.GAMChanged: 'changed',
                      gamin.GAMCreated: 'created',
                      gamin.GAMDeleted: 'deleted',
                      gamin.GAMMoved: 'moved'}

    status = {'changes': [], 'new_watch': []}

    def callback(path, event, base_dir):
        full_path = os.path.join(base_dir, path)
        if event in watched_events and not ignore.search(full_path):
            if os.path.isdir(full_path):
                watch_recursive(full_path, callback)
            status['new_watch'].append(full_path)
            status['changes'].append((full_path, watched_events[event]))

    mon = gamin.WatchMonitor()

    def watch_recursive(path, callback):
        mon.watch_directory(path, callback, path)
        for root, dirs, _files in os.walk(path):
            for sub_dir in dirs:
                sub_path = os.path.join(root, sub_dir)
                if not ignore.search(sub_path):
                    mon.watch_directory(sub_path, callback, sub_path)
    watch_recursive(path, callback)

    while True:
        time.sleep(.5)
        if mon.event_pending():
            mon.handle_events()
            if len(status['changes']):
                yield status['changes']
                status['changes'] = []


def _win32_watch(path, ignore):
    # based on http://timgolden.me.uk/python/win32_how_do_i/watch_directory_for_changes.html
    watched_events = {
        1: "created",
        2: "deleted",
        3: "updated",
        4: "renamed to",
        5: "renamed from",
        }
    FILE_LIST_DIRECTORY = 0x0001

    hDir = win32file.CreateFile(
        path,
        FILE_LIST_DIRECTORY,
        win32con.FILE_SHARE_READ | win32con.FILE_SHARE_WRITE,
        None,
        win32con.OPEN_EXISTING,
        win32con.FILE_FLAG_BACKUP_SEMANTICS,
        None,
        )
    while True:
        results = win32file.ReadDirectoryChangesW(
            hDir,
            1024,
            True,
            win32con.FILE_NOTIFY_CHANGE_FILE_NAME |
            win32con.FILE_NOTIFY_CHANGE_DIR_NAME |
            win32con.FILE_NOTIFY_CHANGE_ATTRIBUTES |
            win32con.FILE_NOTIFY_CHANGE_SIZE |
            win32con.FILE_NOTIFY_CHANGE_LAST_WRITE |
            win32con.FILE_NOTIFY_CHANGE_SECURITY,
            None,
            None,
            )
        changes = []
        for action, filename in results:
            full_path = os.path.join(path, filename)
            if action in watched_events and not ignore.search(full_path):
                event = watched_events.get(action)
                changes.append((full_path, event))
        if len(changes):
            yield changes
            changes = []


def watch(path, ignore):
    logger.info('Watching "%s" for changes' % path)
    ignore_re = re.compile(ignore)
    try:
        if gamin:
            return _gamin_watch(path, ignore_re)
        elif win32file:
            return _win32_watch(path, ignore_re)
        else:
            return _poll_watch(path, ignore_re)
    except KeyboardInterrupt:
        logger.info("Caught Keyboard Interrupt. Exiting.")
