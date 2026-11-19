"""Minimap hooks and entries for extra and restyled view-range circles."""

from gui.Scaleform.daapi.view.battle.shared.minimap import common, settings
from gui.battle_control import matrix_factory
from gui.mods.viewrangecustomizer import config # pyright: ignore[reportMissingImports]

# Keep each original method paired with our wrapper so teardown never
# overwrites a hook installed by another minimap mod.
_native_invoke_originals = {}


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


def install_native_circle_visibility_hook(plugin_class):
    """Intercept native circle commands by wrapping the game's _invoke method.

    The wrapper runs this mod's circle logic first, then calls the original
    game method when the native circle should be shown or changed.
    """
    if plugin_class in _native_invoke_originals:
        return

    original_invoke = getattr(plugin_class, '_invoke', None)
    if not callable(original_invoke):
        print(config.TAG + 'Cannot hook built-in minimap circle visibility')
        return

    def invoke_with_circle_visibility(self, entry_id, *signature):
        """Style supported native draw commands and forward all other calls."""
        # The stock "remove all" action has no per-circle command to inspect.
        # Clear every replacement first, then let the game clear its own entry.
        if signature and signature[0] == settings.VIEW_RANGE_CIRCLES_AS3_DESCR.AS_REMOVE_ALL_CIRCLES:
            replacement_plugin = get_replacement_plugin(self._parentObj)
            if replacement_plugin is not None:
                replacement_plugin.remove_replacement_circles()
            return original_invoke(self, entry_id, *signature)

        action = config.NATIVE_CIRCLE_ACTIONS.get(signature[0]) if signature else None
        if action is None:
            return original_invoke(self, entry_id, *signature)

        # Action metadata maps the client's AS3 command to a setting and circle.
        circle_name, operation = action
        replacement_plugin = get_replacement_plugin(self._parentObj)
        circle_index = config.NATIVE_CIRCLE_INDEX[circle_name]
        enabled_key = config.NATIVE_CIRCLE_SETTING_KEYS[circle_index][0]
        replace_markers = config.SETTINGS['replace_wot_circle_markers']
        if operation == 'remove':
            # Native visibility options can change during battle; mirror removals.
            if replacement_plugin is not None:
                replacement_plugin.remove_replacement_circle(circle_name)
            return original_invoke(self, entry_id, *signature)

        # If styling is unavailable or disabled, preserve the native draw path.
        random_battle = _is_random_battle(self._arenaVisitor)
        if (not config.SETTINGS['enabled'] or not replace_markers or
                not config.SETTINGS[enabled_key] or not random_battle):
            if replacement_plugin is not None:
                replacement_plugin.remove_replacement_circle(circle_name)
            return original_invoke(self, entry_id, *signature)

        if replacement_plugin is None:
            print(config.TAG + 'Replacement circle plugin unavailable; keeping WoT marker')
            return original_invoke(self, entry_id, *signature)

        # Add commands carry their radius in the last argument. Dynamic view
        # range updates carry it immediately after the command name.
        if operation == 'add':
            distance = signature[3] if len(signature) > 3 else None
        else:
            distance = (signature[1]
                        if circle_name == 'view_range' and len(signature) > 1
                        else None)
        if not replacement_plugin.update_replacement_circle(circle_name, distance):
            return original_invoke(self, entry_id, *signature)
        return

    _native_invoke_originals[plugin_class] = (
        original_invoke, invoke_with_circle_visibility)
    plugin_class._invoke = invoke_with_circle_visibility


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


def restore_native_circle_visibility_hooks():
    """Restore original circle methods only when this mod still owns them.

    Our wrapper replaces the game's _invoke method while the mod is active.
    "Owning" it means _invoke still points to this exact wrapper. If another
    minimap mod has replaced _invoke in the meantime, we leave its change alone
    and only discard our stored wrapper reference.
    """
    for plugin_class, hooks in _native_invoke_originals.items():
        original_invoke, wrapper = hooks
        if plugin_class.__dict__.get('_invoke') is wrapper: # Only restore if our wrapper is still in place
            plugin_class._invoke = original_invoke
    _native_invoke_originals.clear()


def refresh_native_circle_visibility():
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

    __slots__ = ('__entryIDs', '__nativeEntryIDs', '__nativeCircleData', '__vehicleStateCtrl')

    def __init__(self, parent):
        """Create empty entry slots aligned with the circle setting tables."""
        super(CustomCirclesPlugin, self).__init__(parent)
        self.__entryIDs = [None] * len(config.CIRCLE_SETTING_KEYS)
        self.__nativeEntryIDs = [None] * len(config.NATIVE_REPLACEMENTS)
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
        """Unsubscribe and delete all entries so later battles start cleanly."""
        if self in config.ACTIVE_PLUGINS:
            config.ACTIVE_PLUGINS.remove(self)
        if self.__vehicleStateCtrl is not None:
            self.__vehicleStateCtrl.onPostMortemSwitched -= self.__onPostMortemSwitched
            self.__vehicleStateCtrl.onRespawnBaseMoving -= self.__onRespawnBaseMoving
            self.__vehicleStateCtrl = None
        for index in range(len(self.__entryIDs)):
            self.__removeMarker(index)
        for index, entryID in enumerate(self.__nativeEntryIDs):
            if entryID is not None:
                self._delEntry(entryID)
                self.__nativeEntryIDs[index] = None
                self.__nativeCircleData[index] = None
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
            refresh_native_circle_visibility()

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
        if (not config.SETTINGS['enabled'] or self.__entryIDs[index] is not None or
                not config.SETTINGS[enabled_key] or
                _is_spectator_mode(self) or
                not _is_random_battle(self._arenaVisitor)):
            return

        vehicleInfo = self.__getVehicleInfo()
        # Observer minimaps use the game's native handling instead.
        if vehicleInfo is None or self.__isObserver(vehicleInfo): return

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
        """Create a separate Flash entry used to render one native circle style."""
        if (self.__nativeEntryIDs[index] is not None or
                not _is_random_battle(self._arenaVisitor)):
            return

        vehicleInfo = self.__getVehicleInfo()
        # If no replacement can be drawn, the hook lets the native command through.
        if vehicleInfo is None or self.__isObserver(vehicleInfo):
            return

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
        """Draw a styled native circle without changing its game-provided radius."""
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
        self.__nativeCircleData[index] = data

        if previous_data == data: return True
        self.__drawNativeCircle(index)
        return True

    def __drawNativeCircle(self, index):
        """Draw the cached color, opacity, and radius for a native replacement."""
        entryID = self.__nativeEntryIDs[index]
        data = self.__nativeCircleData[index]
        if entryID is None or data is None: return

        as3Descr = settings.VIEW_RANGE_CIRCLES_AS3_DESCR
        self._invoke(entryID, as3Descr.AS_DEL_DYN_CIRCLE)
        self._invoke(entryID, as3Descr.AS_ADD_DYN_CIRCLE, data[0], float(data[1]) / 100.0, data[2])

    def remove_replacement_circle(self, circle_name):
        """Hide one replacement while keeping its reusable Flash entry allocated."""
        index = config.NATIVE_CIRCLE_INDEX[circle_name]
        entryID = self.__nativeEntryIDs[index]
        if entryID is not None:
            self._invoke(entryID, settings.VIEW_RANGE_CIRCLES_AS3_DESCR.AS_DEL_DYN_CIRCLE)
        self.__nativeCircleData[index] = None

    def remove_replacement_circles(self):
        """Hide all native-circle replacements, for remove-all and disable paths."""
        for _, circle_name, _, _ in config.NATIVE_REPLACEMENTS:
            self.remove_replacement_circle(circle_name)

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
