'''
    List Cache Keeper
    Kodi Service
    Copyright (C) 2017 Kestrel

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <http://www.gnu.org/licenses/>.
'''

import xbmc
import xbmcaddon
import xbmcgui

import os
import subprocess
import stat
import time
import inspect
import json

addon           = xbmcaddon.Addon()
language        = addon.getLocalizedString
addonName       = addon.getAddonInfo('name')
addonVersion    = addon.getAddonInfo('version')
addonid         = addon.getAddonInfo('id')

class Platform:
    Linux   = 0
    OSX     = 1
    Windows = 2

WINDOW_HOME         = 10000
WINDOW_VIDEO_NAV    = 10025
WINDOW_MUSIC_FILES  = 10501
WINDOW_PICTURES     = 10002
WINDOW_DIALOG_BUSY  = 10138
HAS_FILES_TAG       = 'hasfiles'
CACHE_FILE_EXT      = '.fi'
PROP_DO_REFRESH     = addonid + '.doRefreshList'
PROP_DO_DELETE      = addonid + '.doDeleteAllCaches'
PROP_DO_EXPIRE      = addonid + '.doCleanExpiredCaches'
PROP_SHOW_REFRESH   = addonid + '.showRefresh'
IDLE_DELAY_SECONDS  = 60

homewindow          = xbmcgui.Window(WINDOW_HOME)
pathCaches          = ''
windows             = False
platform            = 0
sudoExists          = False
requireSudo         = False
refreshing          = False
dbglevel            = 3

#Settings
checkChangeEnable       = False
checkChangeMinSeconds   = 1200
checkChangePrompt       = False
expireEnable            = False
expireFilesSeconds      = 3600
expireFoldersSeconds    = 3600
expirePrompt            = False
cleanStartup      = False
cleanIdle         = False
cleanIdleSeconds  = 3600
dbg               = False


def run():

    # Init settings
    settings_update()

    cache_path_check()

    if not platform_check():
        return False

    # Clear any existing window properties
    homewindow.setProperty(PROP_DO_REFRESH, 'false')
    homewindow.setProperty(PROP_DO_DELETE, 'false')
    homewindow.setProperty(PROP_DO_EXPIRE, 'false')

    monitor = MyMonitor(update_settings=settings_update)

    lastMaintenance = 0
    lastPath = ''
    global refreshing
    if expireEnable:
        if cleanStartup:
            # Do maintenance without interruption so expired lists
            # are loaded immediately
            maintain_caches(interruptable=False)
            lastMaintenance = time.time()
        else:
            # Do maintenance at first idle
            lastMaintenance = time.time() - 2 * cleanIdleSeconds

    _log(u'Entering main loop')
    while not monitor.abortRequested():
        if homewindow.getProperty(PROP_DO_REFRESH) == 'true':
            homewindow.setProperty(PROP_DO_REFRESH, 'false')
            # Prevent multiple refreshes
            if not refreshing:
                file = get_current_cache_file()
                refresh_list(file)
        elif homewindow.getProperty(PROP_DO_DELETE) == 'true':
            homewindow.setProperty(PROP_DO_DELETE, 'false')
            delete_all_caches(ask=True)
        elif homewindow.getProperty(PROP_DO_EXPIRE) == 'true':
            homewindow.setProperty(PROP_DO_EXPIRE, 'false')
            dialog = xbmcgui.Dialog()
            if dialog.yesno(addonName, language(32505)):
                maintain_caches(interruptable=False, manual=True)
                lastMaintenance = time.time()
            del dialog

        # Do maintenance periodically when idling and allow interruption
        if (expireEnable and
              cleanIdle and
              (time.time() - lastMaintenance > cleanIdleSeconds) and
              (xbmc.getGlobalIdleTime() > IDLE_DELAY_SECONDS)):
            if maintain_caches(interruptable=True):
                lastMaintenance = time.time()

        # Detect video, music and picture file list windows
        if xbmcgui.getCurrentWindowId() in [WINDOW_VIDEO_NAV,
                                            WINDOW_MUSIC_FILES,
                                            WINDOW_PICTURES]:

            # Only interested in plugin folders
            folderpath = xbmc.getInfoLabel('Container.FolderPath')
            if folderpath.startswith('plugin://'):
                # Use visibility of busy window to determine when
                # finished loading, favourites don't show busy window
                # so check numitems as well
                busy = xbmc.getCondVisibility(
                    'Window.IsVisible(' + str(WINDOW_DIALOG_BUSY) + ')')
                numitems = mk_int(xbmc.getInfoLabel('Container.NumItems'))

                if not busy and (numitems > 0):
                    if refreshing or (folderpath != lastPath):
                        refreshing = False
                        _log(u'Check cache for folderpath: ' + folderpath)
                        check_current_cache()
                        lastPath = folderpath
                else:
                    refreshing = True
            else:
                lastPath = ''

        monitor.waitForAbort(0.5)

    del monitor

    return True


def cache_path_check():
    global pathCaches
    pathCaches = xbmc.translatePath('special://temp/')
    buildVersion = xbmc.getInfoLabel('System.BuildVersion')
    majorVersion = int(buildVersion.split()[0].split('.')[0])
    if majorVersion >= 17:
        pathCaches = os.path.join(pathCaches, 'archive_cache')
    _log(u'Cache path: ' + pathCaches)
    if not os.path.exists(pathCaches):
        os.mkdir(pathCaches)


def platform_check():
    global platform
    if xbmc.getCondVisibility('System.Platform.Windows'):
        platform = Platform.Windows
    elif (xbmc.getCondVisibility('System.Platform.OSX') or
          xbmc.getCondVisibility('System.Platform.IOS') or
          xbmc.getCondVisibility('System.Platform.ATV2') or
          xbmc.getCondVisibility('System.Platform.Darwin')):
        platform = Platform.OSX
    else:
        platform = Platform.Linux

    # Require command to change files to read-only
    missing = ''
    if platform == Platform.OSX:
        if not which('chflags'):
            missing = 'chflags'
    elif platform == Platform.Linux:
        if not which('chattr'):
            missing = 'chattr'

    if missing:
        _log(u"ERROR: System does not have '" + missing +
             "' command. Aborting.")
        dialog = xbmcgui.Dialog()
        dialog.ok(
            addonName,
            language(32507) + " '" + missing + "' " + language(32508),
            language(32509),
            addonName + ' ' + language(32510))
        del dialog
        return False
    else:
        if platform == Platform.Linux:
            # Check that sudo command exists
            global sudoExists
            sudoExists = which('sudo')

        # Test protection
        filename = 'keeptest'
        file = os.path.join(pathCaches, filename)
        worked = True
        if os.path.exists(file):
            # Try to remove existing test file
            if platform == Platform.Linux:
                test_require_sudo(file)
            change_readonly(file, False)
            try:
                os.remove(file)
            except:
                worked = False
        else:
            # Create test file
            open(file, 'a').close()
            if platform == Platform.Linux:
                test_require_sudo(file)

        if worked:
            # Try to change test file to read-only and see if it can
            # be deleted
            change_readonly(file, True)
            try:
                os.remove(file)
                worked = False
            except:
                worked = True

        if worked:
            delete_cache_file(file)
        else:
            _log(u'ERROR: Insufficient permission to protect cache file.')
            dialog = xbmcgui.Dialog()
            dialog.ok(
                addonName,
                language(32512),
                '',
                addonName + ' ' + language(32510))
            del dialog
            return False

    return True


def maintain_caches(interruptable, manual=False):
    _log(u'Maintenance started')
    hasFilesLen = HAS_FILES_TAG.__len__()
    for filename in os.listdir(pathCaches):

        # Only perform maintenance when idle for more than 60 seconds
        if (interruptable and
              xbmc.getGlobalIdleTime() < IDLE_DELAY_SECONDS):
            _log(u'Maintenance interrupted')
            return False

        if not filename.endswith(CACHE_FILE_EXT):
            continue

        file = os.path.join(pathCaches, filename)
        _log(u'Found list cache file: ' + filename)

        if (expireEnable or manual):
            # Use modified time, creation time is windows specific
            # and has tunneling issue
            age = time.time() - os.path.getmtime(file)
            # Make sure file is big enough
            if os.path.getsize(file) <= hasFilesLen:
                _log(u'File is too small.')
                delete_cache_file(file)
            else:
                # Determine if cache list includes files
                # (tag previously appended to end of file)
                with open(file, 'r') as openedfile:
                    # Seek from end of file
                    openedfile.seek(-hasFilesLen, 2)
                    hasFiles = openedfile.read(hasFilesLen) == HAS_FILES_TAG
                _log(u'List contains files: ' + str(bool(hasFiles)))
                if ((hasFiles and (age > expireFilesSeconds)) or
                      (not hasFiles and (age > expireFoldersSeconds))):
                    _log(u'File is expired: ' + str(age//3600) + ' hours old')
                    delete_cache_file(file)

        else:
            change_readonly(file, True)

    _log(u'Maintenance complete')
    return True


def settings_update():
    global checkChangeEnable
    global checkChangeMinSeconds
    global checkChangePrompt
    global expireEnable
    global expireFilesSeconds
    global expireFoldersSeconds
    global expirePrompt
    global cleanStartup
    global cleanIdle
    global cleanIdleSeconds
    global dbg

    checkChangeEnable = addon.getSetting('checkChangeEnable') == 'true'
    checkChangeMinSeconds = 60 * int(addon.getSetting('checkChangeMinMinutes'))
    checkChangePrompt = addon.getSetting('checkChangePrompt') == 'true'

    expireEnable = addon.getSetting('expireEnable') == 'true'
    expireFilesSeconds = 3600 * int(addon.getSetting('expireFilesHours'))
    expireFoldersSeconds = 3600 * int(addon.getSetting('expireFoldersHours'))
    expirePrompt = addon.getSetting('expirePrompt') == 'true'

    cleanStartup = addon.getSetting('cleanStartup') == 'true'
    cleanIdle = addon.getSetting('cleanIdle') == 'true'
    cleanIdleSeconds = 3600 * int(addon.getSetting('cleanIdleHours'))

    homewindow.setProperty(PROP_SHOW_REFRESH, addon.getSetting('showRefresh'))
    dbg = addon.getSetting('debug') == 'true'


def check_current_cache():
    file = get_current_cache_file()

    if not file:
        return False

    # Refresh when cache file is empty
    if os.path.getsize(file) == 0:
        refresh_list(file)
        return True

    # Check for expiration using modified time, can't use creation
    # time due to tunneling
    age = time.time() - os.path.getmtime(file)
    hasFiles = xbmc.getCondVisibility('Container.HasFiles')
    _log(u'List contains files: ' + str(bool(hasFiles)))
    if hasFiles:
        expire = expireFilesSeconds
    else:
        expire = expireFoldersSeconds

    # Refresh when expired
    if expireEnable and (age > expire):
        doRefresh = False
        if expirePrompt:
            dialog = xbmcgui.Dialog()
            doRefresh = dialog.yesno(addonName, language(32503))
            del dialog
        else:
            doRefresh = True

        if doRefresh:
            _log(u'Refreshing expired file: ' + str(age//3600) +
                 ' hours old')
            refresh_list(file)
        else:
            update_modification_time(file)
    else:
        # Protect cache
        _log(u'Keeping cache: ' + os.path.basename(file))
        write_hasfiles(file)
        change_readonly(file, True)
        # Check for remote changes, must be after protection
        if checkChangeEnable:
            check_change_refresh(file)


def check_change_refresh(file):

    if not os.path.exists(file):
        return False

    jsonFile = os.path.splitext(file)[0] + '.json'
    exists = os.path.exists(jsonFile)
    age = time.time() - os.path.getmtime(file)
    # Fetch list when json file doesn't exist or cache old enough
    if not exists or (exists and age > checkChangeMinSeconds):

        # Fetching list takes some time
        folderPath = xbmc.getInfoLabel('Container.FolderPath')
        jsonrpc = ('{"jsonrpc":"2.0",' +
                    '"id":1,' +
                    '"method":"Files.GetDirectory",' +
                    '"params":{' +
                      '"directory":"' + folderPath + '"}}')
        newList = xbmc.executeJSONRPC(jsonrpc);

        data = json.loads(newList)
        if 'error' in data:
            return False

        update = False
        # Only compare files when json file already exists and list
        # folder hasn't changed since fetch
        if (exists and
            xbmc.getInfoLabel('Container.FolderPath') == folderPath):

            # Compare files
            different = False
            try:
                with open(jsonFile, 'r') as openedfile:
                    oldList = openedfile.read()
                different = newList != oldList
            except:
                pass

            if different:
                if checkChangePrompt:
                    dialog = xbmcgui.Dialog()
                    if dialog.yesno(addonName, language(32513)):
                        update = True
                        refresh_list(file)
                    else:
                        update_modification_time(file)
                    del dialog
                else:
                    refresh_list(file)

        if not exists or update:
            # Create/update json list file for future comparison
            try:
                with open(jsonFile, 'w') as openedfile:
                    openedfile.write(newList)
            except:
                pass


def refresh_list(file):
    _log(u'Refresh')
    delete_cache_file(file)
    global refreshing
    refreshing = True
    xbmc.executebuiltin('Container.Refresh')


def get_current_cache_file():
    file = ''
    # Cache filename for current list consists of current windowid
    # and crc32 of current path
    folderpath = xbmc.getInfoLabel('Container.FolderPath')
    # Only interested in plugin folders
    if folderpath and folderpath.startswith('plugin://'):
        # Remove trailing separator from xbmc path
        if folderpath.endswith('/'):
            folderpath = folderpath[:-1]
        _log(u'Current folder path: ' + folderpath)
        filename = construct_cache_filename(
            xbmcgui.getCurrentWindowId(),
            folderpath)
        file = os.path.join(pathCaches, filename)
        exists = os.path.exists(file)
        _log(u'Cache file is: ' + filename + ' exists: ' + str(exists))
        if not exists:
            file = ''

    return file


def delete_all_caches(ask):
    dialog = xbmcgui.Dialog()
    if not ask or dialog.yesno(addonName, language(32501)):
        for filename in os.listdir(pathCaches):
            if filename.endswith(CACHE_FILE_EXT):
                file = os.path.join(pathCaches, filename)
                delete_cache_file(file)
    del dialog


def test_require_sudo(file):
    global requireSudo
    # Try to use chattr without sudo
    try:
        subprocess.call(['chattr', '+i', file])
        subprocess.call(['chattr', '-i', file])
        requireSudo = False
    except IOError as e:
        # Test to see if user has suitable permissions,
        # otherwise use sudo
        if (e[0] == errno.EPERM):
            requireSudo = True


def change_readonly(file, enable):
    result = 0
    if enable:
        _log(u'Protecting file.')
        if platform == Platform.Windows:
            try:
                mode = os.stat(file).st_mode
                os.chmod(file, mode & ~stat.S_IWUSR)
            except:
                _log(u'chmod failed.')
        elif platform == Platform.OSX:
            try:
                result = subprocess.call(['chflags', 'uchg', file])
            except:
                _log(u'chflags failed: ' + str(result))
        else:
            try:
                if requireSudo and sudoExists:
                    result = subprocess.call(['sudo', 'chattr', '+i', file])
                else:
                    result = subprocess.call(['chattr', '+i', file])
            except:
                _log(u'chattr failed: ' + str(result))
    else:
        _log(u'Removing file protection.')
        if platform == Platform.Windows:
            try:
                mode = os.stat(file).st_mode
                os.chmod(file, mode | stat.S_IWUSR)
            except:
                _log(u'chmod failed.')
        elif platform == Platform.OSX:
            try:
                result = subprocess.call(['chflags', 'nouchg', file])
            except:
                _log(u'chflags failed: ' + str(result))
        else:
            try:
                if requireSudo and sudoExists:
                    result = subprocess.call(['sudo', 'chattr', '-i', file])
                else:
                    result = subprocess.call(['chattr', '-i', file])
            except:
                _log(u'chattr failed: ' + str(result))


def delete_cache_file(file):
    if file:
        _log(u'Deleting cache file: ' + os.path.basename(file))
        change_readonly(file, False)
        try:
            os.remove(file)
        except:
            _log(u'Failed.')
    jsonFile = os.path.splitext(file)[0] + '.json'
    if jsonFile:
        _log(u'Deleting json file: ' + os.path.basename(jsonFile))
        try:
            os.remove(jsonFile)
        except:
            _log(u'Failed.')


def construct_cache_filename(windowid, folderpath):
    return str(windowid) + '-' + get_crc32(folderpath) + CACHE_FILE_EXT


def write_hasfiles(file):
    hasFiles = xbmc.getCondVisibility('Container.HasFiles')
    if hasFiles:
        # Append HAS_FILES_TAG to end of file, fails when read-only but
        # should already be appended
        try:
            with open(file, 'a') as openedfile:
                openedfile.write(HAS_FILES_TAG)
        except:
            pass


def get_crc32(string):
    string = string.lower()
    bytes = bytearray(string.encode())
    crc = 0xffffffff;
    for b in bytes:
        crc = crc ^ (b << 24)
        for i in range(8):
            if (crc & 0x80000000 ):
                crc = (crc << 1) ^ 0x04C11DB7
            else:
                crc = crc << 1;
        crc = crc & 0xFFFFFFFF
    return '%08x' % crc


def which(program):
    path, name = os.path.split(program)
    if path:
        if (os.path.isfile(program) and
            os.access(program, os.X_OK)):
            return program

    for path in os.environ['PATH'].split(os.pathsep):
        path = path.strip('"')
        file = os.path.join(path, program)
        if (os.path.isfile(file) and
            os.access(file, os.X_OK)):
            return file

    return None


def update_modification_time(file):
    change_readonly(file, False)
    os.utime(file, None)
    change_readonly(file, True)


def mk_int(s):
    s = s.strip()
    return int(s) if s else 0


def _log(description, level=0):
    if dbg and dbglevel > level:
        try:
            xbmc.log(u"[%s] %s : '%s'" % (
                    addonName + ' v' + addonVersion,
                    repr(inspect.stack()[1][3]),
                    description),
                xbmc.LOGNOTICE)
        except:
            xbmc.log(u"[%s] %s : '%s'" % (
                    addonName + ' v' + addonVersion,
                    repr(inspect.stack()[1][3]),
                    repr(description)),
                xbmc.LOGNOTICE)


class MyMonitor(xbmc.Monitor):
    def __init__( self, *args, **kwargs ):
        xbmc.Monitor.__init__(self)
        self.update_settings = kwargs['update_settings']

    def onSettingsChanged(self):
        self.update_settings()

if __name__ == '__main__':
    run()






