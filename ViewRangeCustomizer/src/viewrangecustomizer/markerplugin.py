"""Minimap hooks and entries for extra and restyled view-range circles."""

import logging
import weakref

from gui.Scaleform.daapi.view.battle.shared.minimap import common, settings
from gui.battle_control import matrix_factory
from gui.mods.viewrangecustomizer import config # pyright: ignore[reportMissingImports]

# Keep each original method paired with our wrapper so teardown never
# overwrites a hook installed by another minimap mod.
_native_invoke_originals = {}
_logger = logging.getLogger(__name__)


def _is_random_battle(arena_visitor):
    """Use the game GUI visitor to identify a Random Battle."""
    if arena_visitor is None:
        return False
    return arena_visitor.gui.isRandomBattle()


def _is_spectator_mode(plugin):
    """Return True in postmortem, video/free-camera, or respawn-death modes.

    Callers check this before adding the mod's extra circles or replacing the WoT native circles.
    """
    return plugin._isInPostmortemMode() or plugin._isInVideoMode() or plugin._isInRespawnDeath()


def install_native_circle_commands_hook(plugin_class):
    """Intercept WoT's native circle commands while preserving its _invoke.

    plugin_class is WoT's personal minimap plugin class. It sends circle
    commands through _invoke; our wrapper handles supported commands and
    passes the rest to the previous method, which may be another mod's hook.
    """
    if plugin_class in _native_invoke_originals:
        return

    # __dict__ contains only attributes defined on this class, not inherited
    # ones. Save the raw entry so teardown can restore it exactly; normal class
    # lookup returns an unbound method instead of the raw function in Python 2.
    class_attrs = plugin_class.__dict__
    invoke_defined_here = '_invoke' in class_attrs
    original_invoke_descriptor = class_attrs.get('_invoke')
    original_invoke = getattr(plugin_class, '_invoke', None)
    if not callable(original_invoke):
        print(config.TAG + 'Cannot hook built-in minimap circle visibility')
        return
    
    active = [True]

    # Remember native fallbacks so a successful replacement can remove them.
    # Since this hook stays installed across battles, a regular dictionary
    # would keep tracked plugins alive after WoT disposes of the minimap.
    # Weak keys let plugins and their entries be collected when no longer used.
    native_circles = weakref.WeakKeyDictionary()

    def invoke_with_native_circle_handling(self, entry_id, *signature):
        """Style supported native draw commands and forward all other calls."""
        if not active[0]:
            return original_invoke(self, entry_id, *signature)

        try:
            if _handle_native_circle_command(self, signature):
                circle_name = config.NATIVE_CIRCLE_ACTIONS[signature[0]][0]
                circle_key = (entry_id, circle_name)
                visible = native_circles.get(self, set())
                if circle_key in visible:
                    remove_command = next(
                        command for command, action in config.NATIVE_CIRCLE_ACTIONS.items()
                        if action == (circle_name, 'remove'))
                    original_invoke(self, entry_id, remove_command)
                    visible.remove(circle_key)
                return
        except Exception:
            _logger.exception(config.TAG + 'Could not handle native minimap circle command')
        result = original_invoke(self, entry_id, *signature)
        try:
            action = config.NATIVE_CIRCLE_ACTIONS.get(signature[0]) if signature else None
            if action is not None:
                circle_key = (entry_id, action[0])
                if action[1] == 'remove':
                    native_circles.get(self, set()).discard(circle_key)
                else:
                    native_circles.setdefault(self, set()).add(circle_key)
            elif signature and signature[0] == settings.VIEW_RANGE_CIRCLES_AS3_DESCR.AS_REMOVE_ALL_CIRCLES:
                visible = native_circles.get(self, set())
                visible.difference_update(key for key in list(visible) if key[0] == entry_id)
        except Exception:
            _logger.exception(config.TAG + 'Could not track native minimap circles')
        return result

    setattr(invoke_with_native_circle_handling, '_viewrangecustomizer_hook_owner', True)
    plugin_class._invoke = invoke_with_native_circle_handling
    _native_invoke_originals[plugin_class] = (
        original_invoke_descriptor, invoke_with_native_circle_handling,
        invoke_defined_here, active
    )


def _handle_native_circle_command(plugin, signature):
    """Return True only when a styled replacement handles the native command."""
    # The stock "remove all" action has no per-circle command to inspect.
    # Clear every replacement first, then let the game clear its own entry.
    if signature and signature[0] == settings.VIEW_RANGE_CIRCLES_AS3_DESCR.AS_REMOVE_ALL_CIRCLES:
        replacement_plugin = get_replacement_plugin(plugin._parentObj)
        if replacement_plugin is not None:
            replacement_plugin.remove_replacement_circles()
        return False

    action = config.NATIVE_CIRCLE_ACTIONS.get(signature[0]) if signature else None
    if action is None:
        return False

    # Action metadata maps the client's AS3 command to a setting and circle.
    circle_name, operation = action
    replacement_plugin = get_replacement_plugin(plugin._parentObj)
    circle_index = config.NATIVE_CIRCLE_INDEX[circle_name]
    enabled_key = config.NATIVE_CIRCLE_SETTING_KEYS[circle_index][0]
    replace_markers = config.SETTINGS['replace_wot_circle_markers']
    if operation == 'remove':
        # Native visibility options can change during battle; mirror removals.
        if replacement_plugin is not None:
            replacement_plugin.remove_replacement_circle(circle_name)
        return False

    # If styling is unavailable or disabled, preserve the native draw path.
    random_battle = _is_random_battle(plugin._arenaVisitor)
    if (not config.SETTINGS['enabled'] or not replace_markers or
            not config.SETTINGS[enabled_key] or not random_battle):
        if replacement_plugin is not None:
            replacement_plugin.remove_replacement_circle(circle_name)
        return False

    if replacement_plugin is None:
        print(config.TAG + 'Replacement circle plugin unavailable; keeping WoT marker')
        return False

    # Add commands carry their radius in the last argument. Dynamic view
    # range updates carry it immediately after the command name.
    if operation == 'add':
        distance = signature[3] if len(signature) > 3 else None
    else:
        distance = (signature[1]
                    if circle_name == 'view_range' and len(signature) > 1
                    else None)
    return replacement_plugin.update_replacement_circle(circle_name, distance)


def get_replacement_plugin(parent):
    """Return this mod's circle plugin when the minimap has created it."""
    get_plugin = getattr(parent, 'getPlugin', None)
    if callable(get_plugin):
        plugin = get_plugin(config.MOD_ID)
        if isinstance(plugin, CustomCirclesPlugin):
            return plugin
        if plugin is not None:
            print(config.TAG + 'Replacement circle plugin has an unexpected type')
    return None


def _restore_native_circle_commands_hook(plugin_class, hook_state):
    """Restore one WoT plugin class without overwriting a later mod's hook.

    Use the raw class dictionary to test wrapper ownership. Restore the saved
    descriptor if _invoke was defined on this class; otherwise remove our
    override so the inherited WoT method becomes visible again.
    """
    original_descriptor, wrapper, defined_here, active = hook_state
    active[0] = False
    if plugin_class.__dict__.get('_invoke') is wrapper:
        if defined_here:
            plugin_class._invoke = original_descriptor
        else:
            del plugin_class._invoke


def restore_native_circle_commands_hooks():
    """Undo this mod's native-circle hooks when its WoT plugin is unloaded.

    A hook changed by another mod is left untouched. Clear saved references
    afterward so a later initialization can capture the current hook chain.
    """
    try:
        for plugin_class, hooks in list(_native_invoke_originals.items()):
            try:
                _restore_native_circle_commands_hook(plugin_class, hooks)
            except Exception as error:
                print(config.TAG + 'Could not restore native circle hook: ' + str(error))
    finally:
        _native_invoke_originals.clear()


def refresh_native_circles():
    """Redraw currently visible native circles after a style setting changes."""
    for marker_plugin in list(config.ACTIVE_PLUGINS):
        get_plugin = getattr(marker_plugin._parentObj, 'getPlugin', None)
        if not callable(get_plugin): continue

        native_plugin = get_plugin('personal')
        if native_plugin is None: continue

        visibility_state = getattr(native_plugin, '_PersonalEntriesPlugin__circlesVisibilityState', 0)
        
        # This bitmask reflects the game's own options; leave hidden circles hidden.
        # Calling the stock remove/add methods reuses the game's current
        # visibility options and supplies the up-to-date radius to our hook.
        for circle_type, _, remove_name, add_name in config.NATIVE_REPLACEMENTS:
            if not visibility_state & circle_type: continue
            
            remove_circle = getattr(native_plugin, remove_name, None)
            add_circle = getattr(native_plugin, add_name, None)
            if callable(remove_circle) and callable(add_circle):
                remove_circle()
                add_circle()
            else:
                print(config.TAG + 'Cannot refresh a built-in minimap circle')
                break


class CustomCirclesPlugin(common.SimplePlugin):
    """Owns the mod's extra circles and its styled copies of native circles."""

    __slots__ = ('__entryIDs', '__nativeEntryIDs', '__nativeInitialized',
                 '__nativeCircleData', '__vehicleStateCtrl')

    def __init__(self, parent):
        """Create empty entry slots aligned with the circle setting tables."""
        super(CustomCirclesPlugin, self).__init__(parent)
        self.__entryIDs = [None] * len(config.CIRCLE_SETTING_KEYS)
        self.__nativeEntryIDs = [None] * len(config.NATIVE_REPLACEMENTS)
        self.__nativeInitialized = [False] * len(config.NATIVE_REPLACEMENTS)
        # Each native circle stores (RGB color, opacity percent, client radius).
        self.__nativeCircleData = [None] * len(config.NATIVE_REPLACEMENTS) # type: list
        self.__vehicleStateCtrl = None

    def start(self):
        """Track this battle plugin and listen for death/respawn transitions."""
        super(CustomCirclesPlugin, self).start()
        config.ACTIVE_PLUGINS.append(self)
        self.__vehicleStateCtrl = self.sessionProvider.shared.vehicleState
        if self.__vehicleStateCtrl is not None:
            self.__vehicleStateCtrl.onPostMortemSwitched += self.__onPostMortemSwitched
            self.__vehicleStateCtrl.onRespawnBaseMoving += self.__onRespawnBaseMoving

    def stop(self):
        """Unsubscribe and clean up circles when the plugin stops."""
        if self in config.ACTIVE_PLUGINS:
            config.ACTIVE_PLUGINS.remove(self)
        if self.__vehicleStateCtrl is not None:
            unsubscribe_failed = False
            try:
                self.__vehicleStateCtrl.onPostMortemSwitched -= self.__onPostMortemSwitched
            except Exception:
                unsubscribe_failed = True
                _logger.exception(config.TAG + 'Could not unsubscribe postmortem callback')
            try:
                self.__vehicleStateCtrl.onRespawnBaseMoving -= self.__onRespawnBaseMoving
            except Exception:
                unsubscribe_failed = True
                _logger.exception(config.TAG + 'Could not unsubscribe respawn callback')
            if not unsubscribe_failed:
                self.__vehicleStateCtrl = None
        # WoT removes all entries before stopping plugins during minimap disposal.
        self.__entryIDs = [None] * len(self.__entryIDs)
        self.__nativeEntryIDs = [None] * len(self.__nativeEntryIDs)
        self.__nativeInitialized = [False] * len(self.__nativeInitialized)
        self.__nativeCircleData = [None] * len(self.__nativeCircleData)
        super(CustomCirclesPlugin, self).stop()

    def initControlMode(self, mode, available):
        """Create enabled circles when the minimap enters its initial mode."""
        super(CustomCirclesPlugin, self).initControlMode(mode, available)
        for index, keys in enumerate(config.CIRCLE_SETTING_KEYS):
            if config.SETTINGS[keys[0]]:
                self.__addMarker(index)

    def updateControlMode(self, mode, vehicleID):
        """Reattach entries to the controlled vehicle and handle observer switches."""
        super(CustomCirclesPlugin, self).updateControlMode(mode, vehicleID)
        for entryID in self.__entryIDs + self.__nativeEntryIDs:
            if entryID is not None:
                self._setMatrix(entryID, matrix_factory.makeAttachedVehicleMatrix())
        vehicleInfo = self.__getVehicleInfo()
        spectator_mode = _is_spectator_mode(self)
        if spectator_mode or vehicleInfo is None or self.__isObserver(vehicleInfo):
            # The stock minimap owns visibility while spectating or dead.
            for index in range(len(self.__entryIDs)):
                self.__removeMarker(index)
            self.remove_replacement_circles()
        else:
            is_alive = self.__isAlive(vehicleInfo)
            for entryID in self.__entryIDs + self.__nativeEntryIDs:
                if entryID is not None:
                    self._setActive(entryID, is_alive)
            for index, keys in enumerate(config.CIRCLE_SETTING_KEYS):
                if config.SETTINGS['enabled'] and config.SETTINGS[keys[0]]:
                    self.__addMarker(index)
        if not spectator_mode:
            refresh_native_circles()

    def __getVehicleInfo(self):
        """Get the current vehicle data needed for alive/observer checks."""
        get_vehicle_info = getattr(self._arenaDP, 'getVehicleInfo', None)
        if not callable(get_vehicle_info):
            return None
        get_attached_vehicle_id = getattr(self._arenaDP, 'getAttachedVehicleID', None)
        if callable(get_attached_vehicle_id):
            vehicle_id = get_attached_vehicle_id()
            if vehicle_id:
                return get_vehicle_info(vehicle_id)
        return get_vehicle_info()

    def __getBoundingBox(self):
        """Return minimap arena bounds used to size each circle entry."""
        get_bounding_box = getattr(self._parentObj, 'getBoundingBox', None)
        if not callable(get_bounding_box):
            return None
        bounds = get_bounding_box()
        if not isinstance(bounds, (tuple, list)) or len(bounds) != 2:
            return None
        return bounds[0], bounds[1]

    def __isObserver(self, vehicleInfo):
        """Fail closed if vehicle observer status is unavailable."""
        is_observer = getattr(vehicleInfo, 'isObserver', None)
        if not callable(is_observer):
            return True
        return bool(is_observer())

    def __isAlive(self, vehicleInfo):
        """Check alive status so circles are inactive while the vehicle is dead."""
        is_alive = getattr(vehicleInfo, 'isAlive', None)
        if not callable(is_alive):
            return False
        return bool(is_alive())

    def __addMarker(self, index):
        """Create and draw one user-configured extra circle."""
        enabled_key = config.CIRCLE_SETTING_KEYS[index][0]
        # Avoid duplicates and honor both the global switch and this circle's toggle.
        if (not config.SETTINGS['enabled'] or 
                self.__entryIDs[index] is not None or 
                not config.SETTINGS[enabled_key] or
                _is_spectator_mode(self) or 
                not _is_random_battle(self._arenaVisitor)):
            return

        vehicleInfo = self.__getVehicleInfo()
        if vehicleInfo is None or self.__isObserver(vehicleInfo):
            return # Don't add a circle if vehicle info is missing or marked as an observer (watching but not a player).

        matrix = matrix_factory.makeAttachedVehicleMatrix()
        transformProps = settings.TRANSFORM_FLAG.DEFAULT ^ settings.TRANSFORM_FLAG.NO_ROTATION
        entryID = self._addEntry(
            settings.ENTRY_SYMBOL_NAME.VIEW_RANGE_CIRCLES,
            settings.CONTAINER_NAME.PERSONAL,
            matrix=matrix,
            active=self.__isAlive(vehicleInfo),
            transformProps=transformProps)
        if not entryID:
            print(config.TAG + 'Failed to add circle ' + str(index + 1) + ' to minimap')
            return

        self.__entryIDs[index] = entryID
        # The Flash circle widget needs the full minimap dimensions before drawing.
        bounds = self.__getBoundingBox()
        if bounds is None:
            self.__removeMarker(index)
            return
        bottomLeft, upperRight = bounds
        width = upperRight[0] - bottomLeft[0]
        height = upperRight[1] - bottomLeft[1]
        self._invoke(entryID, settings.VIEW_RANGE_CIRCLES_AS3_DESCR.AS_INIT_ARENA_SIZE, width, height)
        self.__drawCircle(index)

    def __removeMarker(self, index):
        """Delete one extra circle entry, if it currently exists."""
        entryID = self.__entryIDs[index]
        if entryID is not None:
            self._delEntry(entryID)
            self.__entryIDs[index] = None

    def __drawCircle(self, index):
        """Send the selected extra circle's configured radius and style to Flash."""
        entryID = self.__entryIDs[index]
        if entryID is None: return

        distance_key, color_key, opacity_key = config.CIRCLE_SETTING_KEYS[index][1:]
        distance = int(config.SETTINGS[distance_key])

        self._invoke(entryID, settings.VIEW_RANGE_CIRCLES_AS3_DESCR.AS_DEL_DYN_CIRCLE)
        self._invoke(
            entryID,
            settings.VIEW_RANGE_CIRCLES_AS3_DESCR.AS_ADD_DYN_CIRCLE,
            int(config.SETTINGS[color_key], 16),
            float(config.SETTINGS[opacity_key]) / 100.0,
            distance)

    def __addNativeMarker(self, index):
        """Create and initialize a Flash entry, retrying incomplete initialization."""
        if self.__nativeInitialized[index] or not _is_random_battle(self._arenaVisitor):
            return

        vehicleInfo = self.__getVehicleInfo()
        # If no replacement can be drawn, the hook lets the native command through.
        if vehicleInfo is None or self.__isObserver(vehicleInfo):
            return

        entryID = self.__nativeEntryIDs[index]
        if entryID is None:
            matrix = matrix_factory.makeAttachedVehicleMatrix()
            transformProps = settings.TRANSFORM_FLAG.DEFAULT ^ settings.TRANSFORM_FLAG.NO_ROTATION
            entryID = self._addEntry(
                settings.ENTRY_SYMBOL_NAME.VIEW_RANGE_CIRCLES,
                settings.CONTAINER_NAME.PERSONAL,
                matrix=matrix,
                active=self.__isAlive(vehicleInfo),
                transformProps=transformProps)
            if not entryID:
                print(config.TAG + 'Failed to add WoT marker ' + str(index + 1))
                return

            self.__nativeEntryIDs[index] = entryID
        # Replacement entries need the same arena initialization as extra ones.
        bounds = self.__getBoundingBox()
        if bounds is None:
            self._delEntry(entryID)
            self.__nativeEntryIDs[index] = None
            return
        bottomLeft, upperRight = bounds
        width = upperRight[0] - bottomLeft[0]
        height = upperRight[1] - bottomLeft[1]
        self._invoke(entryID, settings.VIEW_RANGE_CIRCLES_AS3_DESCR.AS_INIT_ARENA_SIZE, width, height)
        self.__nativeInitialized[index] = True

    def __getNativeViewRangeRadius(self, circle_name):
        """Read the current mode's native radius when no client command supplied it."""
        get_plugin = getattr(self._parentObj, 'getPlugin', None)
        if not callable(get_plugin):
            return None
        personal_plugin = get_plugin('personal')
        arena_visitor = getattr(personal_plugin, '_arenaVisitor', None)
        if circle_name == 'draw_range':
            get_radius = getattr(arena_visitor, 'getVehicleCircularAoiRadius', None)
        elif circle_name == 'max_view_range':
            get_radius = getattr(arena_visitor, 'getVisibilityMaxRadius', None)
        elif circle_name == 'min_spotting_range':
            get_radius = getattr(arena_visitor, 'getVisibilityMinRadius', None)
        else:
            get_radius = getattr(personal_plugin, '_getViewRangeRadius', None)
        if callable(get_radius):
            return get_radius()
        return None

    def update_replacement_circle(self, circle_name, distance=None):
        """Draw a styled native circle without changing its game-provided radius.

        If distance is omitted, use the current native radius or the last
        successfully drawn radius. Return True when the replacement is drawn
        or already current; return False to let WoT draw its own circle.
        Invalidate cached data before drawing so a failed draw can be retried.
        """
        index = config.NATIVE_CIRCLE_INDEX[circle_name]
        enabled_key, color_key, opacity_key = config.NATIVE_CIRCLE_SETTING_KEYS[index]
        if (not config.SETTINGS['enabled'] or
                not config.SETTINGS['replace_wot_circle_markers'] or
                not config.SETTINGS[enabled_key] or
                _is_spectator_mode(self) or
                not _is_random_battle(self._arenaVisitor)):
            self.remove_replacement_circle(circle_name)
            return False

        vehicleInfo = self.__getVehicleInfo()
        if vehicleInfo is None or self.__isObserver(vehicleInfo):
            self.remove_replacement_circle(circle_name)
            return False

        previous_data = self.__nativeCircleData[index]
        if distance is None:
            distance = self.__getNativeViewRangeRadius(circle_name)
        if distance is None and previous_data is not None:
            distance = previous_data[2]
        if distance is None:
            print(config.TAG + 'Current WoT view range radius is unavailable; keeping its marker')
            return False

        # Preserve the client's radius; only color and opacity come from settings.
        data = (int(config.SETTINGS[color_key], 16), config.SETTINGS[opacity_key], distance)

        self.__addNativeMarker(index)
        entryID = self.__nativeEntryIDs[index]
        if entryID is None: return False

        self._setActive(entryID, vehicleInfo is not None and self.__isAlive(vehicleInfo))
        if previous_data == data: return True
        self.__nativeCircleData[index] = None
        self.__drawNativeCircle(index, data)
        self.__nativeCircleData[index] = data
        return True

    def __drawNativeCircle(self, index, data):
        """Draw the color, opacity, and radius for a native replacement."""
        entryID = self.__nativeEntryIDs[index]
        if entryID is None: return

        as3Descr = settings.VIEW_RANGE_CIRCLES_AS3_DESCR
        self._invoke(entryID, as3Descr.AS_DEL_DYN_CIRCLE)
        self._invoke(entryID, as3Descr.AS_ADD_DYN_CIRCLE, data[0], float(data[1]) / 100.0, data[2])

    def remove_replacement_circle(self, circle_name):
        """Hide one replacement while keeping its reusable Flash entry allocated."""
        index = config.NATIVE_CIRCLE_INDEX[circle_name]
        entryID = self.__nativeEntryIDs[index]
        self.__nativeCircleData[index] = None
        if entryID is not None:
            try:
                self._invoke(entryID, settings.VIEW_RANGE_CIRCLES_AS3_DESCR.AS_DEL_DYN_CIRCLE)
            except Exception:
                try:
                    _logger.exception(config.TAG + 'Failed to delete native circle ' + " entryID " + str(entryID) + ', hiding it instead.')
                    self._setActive(entryID, False)
                except Exception:
                    _logger.exception(config.TAG + 'Could not hide replacement circle')
                raise

    def remove_replacement_circles(self):
        """Hide all native-circle replacements, for remove-all and disable paths."""
        first_error = None
        for _, circle_name, _, _ in config.NATIVE_REPLACEMENTS:
            try:
                self.remove_replacement_circle(circle_name)
            except Exception as error:
                _logger.exception(config.TAG + 'Could not remove replacement circle ' + circle_name)
                if first_error is None:
                    first_error = error
        if first_error is not None:
            raise first_error

    def apply_settings(self):
        """Apply current Mod Menu settings to extra and replacement circles."""
        if (not config.SETTINGS['enabled'] or not _is_random_battle(self._arenaVisitor)):
            # The game's own visibility settings decide which native circles return.
            for index in range(len(self.__entryIDs)):
                self.__removeMarker(index)
            self.remove_replacement_circles()
            return

        for index, keys in enumerate(config.CIRCLE_SETTING_KEYS):
            if not config.SETTINGS[keys[0]]:
                self.__removeMarker(index)
            elif self.__entryIDs[index] is None:
                self.__addMarker(index)
            else:
                self.__drawCircle(index)

    def __onPostMortemSwitched(self, noRespawnPossible, respawnAvailable):
        """Hide all mod entries when the controlled vehicle dies."""
        for entryID in self.__entryIDs + self.__nativeEntryIDs:
            if entryID is not None:
                self._setActive(entryID, False)

    def __onRespawnBaseMoving(self):
        """Reactivate configured entries after respawn, unless the mod is disabled."""
        random_battle = _is_random_battle(self._arenaVisitor)
        if (not config.SETTINGS['enabled'] or not random_battle or
                _is_spectator_mode(self)):
            return

        for index, keys in enumerate(config.CIRCLE_SETTING_KEYS):
            if not config.SETTINGS[keys[0]]: continue

            entryID = self.__entryIDs[index]
            if entryID is None:
                self.__addMarker(index)
                entryID = self.__entryIDs[index]
                
            if entryID is not None:
                self._setMatrix(entryID, matrix_factory.makeAttachedVehicleMatrix())
                self._setActive(entryID, True)
        for index, entryID in enumerate(self.__nativeEntryIDs):
            if entryID is None or self.__nativeCircleData[index] is None: continue
            self._setMatrix(entryID, matrix_factory.makeAttachedVehicleMatrix())
            self._setActive(entryID, True)
