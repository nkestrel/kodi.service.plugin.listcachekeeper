## List Cache Keeper
Kodi Service

![](/icon.png)

**Reshow media plugin lists faster.**

Keeps media plugin list's cache files so they can be used to reshow lists
faster. Lists can be automatically expired after a specified number of hours or
manually refreshed via context menu or keymap.

Once installed you can find this addon in the Services section of My Addons.

    My Addons -> Services -> List Cache Keeper -> Configure

On Linux the `chattr` command needs to be available to protect cache files 
and either root access or permission to `sudo chattr`.


**Keeping lists**

Kodi caches most plugin lists but only keeps the cache files for going 
backwards to the previous list. This addon runs as a service in the 
background, protecting cache files it encounters for video, music and picture 
plugin lists so they are reused rather than deleted. Cached lists are much 
faster to load as they don't need to start any scripts or access the network 
which is beneficial for lower performance hardware and internet connections. 
Faster systems can also benefit from virtually instant list reshow.

Cached lists will not refresh when they are shown unless they have expired,
so any changes like new items, favorites, categories or search results will
not be seen until the list is manually refreshed.

Plugins can prevent their own lists from being cached but this is usually
only done for hard-coded lists that load quickly. Accessing lists remotely
with JSON RPC does not use cache files so there is no benefit.

On startup and when displaying cached lists, the log will show errors as Kodi
tries and fails to delete the protected cache files, this is normal and
expected behavior.


**Expiring lists**

Lists that have exceeded the specified expiry age are automatically refreshed
when they are displayed. File links may change over time causing the cached
ones to stop working, so it is best not to set the expire time too long. Lists
that contain only folders are less likely to need regular refreshing so can
be given a separate and much longer expire time.

Changes to the current list can be detected in the background, if the list 
has changed the user can be prompted to refresh or it can be done 
automatically.

Expired cache files are cleaned when the system starts and periodically when
the system is idle so that they don't accumulate. If a cache file has expired
but is still available when its list is shown, it will briefly appear before
being automatically refreshed. This behavior can be changed so that it
prompts before refreshing so the expired list can be retained. Expired cache
files can also be manually cleaned in the settings.


**Manually refreshing lists**

Lists can be manually refreshed with the "Refresh list" context menu item
(Jarvis 16+) or by key mapping.

Assign cache operations to buttons by editing the keymap file
`userdata/keymaps/keymap.xml`. The standard refresh operation
`Container.Refresh` won't work and requires functions provided by this addon.
The following example maps "Refresh list" to the <kbd>F5</kbd> key, "Expire
now" to the <kbd>F6</kbd> key and "Delete all list caches" to the
<kbd>F8</kbd> key.

    <keymap>
      <global>
        <keyboard>
          <F5>SetProperty(service.plugin.listcachekeeper.doRefreshList, true, Home)</F5>
          <F6>SetProperty(service.plugin.listcachekeeper.doCleanExpiredCaches, true, Home)</F6>
          <F8>SetProperty(service.plugin.listcachekeeper.doDeleteAllCaches, true, Home)</F8>
        </keyboard>
      </global>
    </keymap>


**Notes**

When updating Kodi it is possible for the cache file format to change which
will break any cached lists from the previous version. This may cause strange
errors when these lists are displayed but is easily fixed by deleting all
cache files.

Lists will stop being refreshed if the service crashes for whatever reason,
disabling and re-enabling the addon will restart the service.

**Uninstalling**

Disabling/uninstalling this addon within Kodi will automatically remove
protection from all cache files to avoid being stuck with old lists. Manual
removal of this addon outside of Kodi requires doing this manually to the
`*.fi` files in the `cache/archive_cache` folder or simply deleting them.

