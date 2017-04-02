
import xbmcaddon
import xbmcgui

addon      = xbmcaddon.Addon()
addonid    = addon.getAddonInfo('id')
homewindow = xbmcgui.Window(10000)

if __name__ == '__main__':
    homewindow.setProperty(addonid + '.doRefreshList', 'true')