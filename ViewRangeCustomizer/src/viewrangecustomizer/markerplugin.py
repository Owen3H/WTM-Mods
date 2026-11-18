from gui.Scaleform.daapi.view.battle.shared.minimap import common, settings
from gui.battle_control import matrix_factory
from gui.mods.viewrangecustomizer import config  # pyright: ignore[reportMissingImports]

_native_invoke_originals = {}


def install_native_circle_visibility_hook(plugin_class):
    if plugin_class in _native_invoke_originals:
        return

    original_invoke = getattr(plugin_class, '_invoke', None)
    if not callable(original_invoke):
        print(config.TAG + 'Cannot hook built-in minimap circle visibility')
        return

    def invoke_with_circle_visibility(self, entry_id, *signature):
        if signature and signature[0] == settings.VIEW_RANGE_CIRCLES_AS3_DESCR.AS_REMOVE_ALL_CIRCLES:
            return original_invoke(self, entry_id, *signature)

        action = config.NATIVE_CIRCLE_ACTIONS.get(signature[0]) if signature else None
        if action is None:
            return original_invoke(self, entry_id, *signature)

        circle_name, operation = action
        replacement_plugin = get_replacement_plugin(self._parentObj)
        circle_index = config.NATIVE_CIRCLE_INDEX[circle_name]
        enabled_key = config.NATIVE_CIRCLE_SETTING_KEYS[circle_index][0]
        replace_markers = config.SETTINGS['replace_wot_circle_markers']
        if operation == 'add':
            if not replace_markers:
                if replacement_plugin is not None:
                    replacement_plugin.remove_replacement_circle(circle_name)
                return original_invoke(self, entry_id, *signature)
            if not config.SETTINGS[enabled_key]:
                if replacement_plugin is not None:
                    replacement_plugin.remove_replacement_circle(circle_name)
                return
            if replacement_plugin is None:
                print(config.TAG + 'Replacement circle plugin unavailable; keeping WoT marker')
                return original_invoke(self, entry_id, *signature)
            distance = (signature[3]
                        if circle_name in ('max_view_range', 'view_range') and
                        len(signature) > 3 else None)
            if not replacement_plugin.update_replacement_circle(
                    circle_name, distance):
                return original_invoke(self, entry_id, *signature)
            return

        if operation == 'update':
            if not replace_markers:
                return original_invoke(self, entry_id, *signature)
            if not config.SETTINGS[enabled_key]:
                if replacement_plugin is not None:
                    replacement_plugin.remove_replacement_circle(circle_name)
                return
            if replacement_plugin is None:
                print(config.TAG + 'Replacement circle plugin unavailable; keeping WoT marker')
                return original_invoke(self, entry_id, *signature)
            distance = (signature[1]
                        if circle_name == 'view_range' and len(signature) > 1
                        else None)
            if not replacement_plugin.update_replacement_circle(
                    circle_name, distance):
                return original_invoke(self, entry_id, *signature)
            return

        if replacement_plugin is not None and (
                not replace_markers or not config.SETTINGS[enabled_key]):
            replacement_plugin.remove_replacement_circle(circle_name)
        return original_invoke(self, entry_id, *signature)

    _native_invoke_originals[plugin_class] = original_invoke
    plugin_class._invoke = invoke_with_circle_visibility


def get_replacement_plugin(parent):
    get_plugin = getattr(parent, 'getPlugin', None)
    if callable(get_plugin):
        plugin = get_plugin('distanceMarker')
        if isinstance(plugin, DistanceMarkerPlugin):
            return plugin
        if plugin is not None:
            print(config.TAG + 'Replacement circle plugin has an unexpected type')
    return None


def restore_native_circle_visibility_hooks():
    for plugin_class, original_invoke in _native_invoke_originals.items():
        plugin_class._invoke = original_invoke
    _native_invoke_originals.clear()


def refresh_native_circle_visibility():
    for marker_plugin in list(config.ACTIVE_PLUGINS):
        get_plugin = getattr(marker_plugin._parentObj, 'getPlugin', None)
        if not callable(get_plugin):
            continue
        native_plugin = get_plugin('personal')
        if native_plugin is None:
            continue
        visibility_state = getattr(
            native_plugin, '_PersonalEntriesPlugin__circlesVisibilityState', 0)
        for circle_type, _, remove_name, add_name in config.NATIVE_REPLACEMENTS:
            if not visibility_state & circle_type:
                continue
            remove_circle = getattr(native_plugin, remove_name, None)
            add_circle = getattr(native_plugin, add_name, None)
            if callable(remove_circle) and callable(add_circle):
                remove_circle()
                add_circle()
            else:
                print(config.TAG + 'Cannot refresh a built-in minimap circle')
                break


class DistanceMarkerPlugin(common.SimplePlugin):
    __slots__ = ('__entryIDs', '__nativeEntryIDs', '__nativeCircleData', '__vehicleStateCtrl')

    def __init__(self, parent):
        super(DistanceMarkerPlugin, self).__init__(parent)
        self.__entryIDs = [None] * len(config.CIRCLE_SETTING_KEYS)
        self.__nativeEntryIDs = [None] * len(config.NATIVE_REPLACEMENTS)
        self.__nativeCircleData = [None] * len(config.NATIVE_REPLACEMENTS) # type: list
        self.__vehicleStateCtrl = None

    def start(self):
        super(DistanceMarkerPlugin, self).start()
        config.ACTIVE_PLUGINS.append(self)
        self.__vehicleStateCtrl = self.sessionProvider.shared.vehicleState
        if self.__vehicleStateCtrl is not None:
            self.__vehicleStateCtrl.onPostMortemSwitched += self.__onPostMortemSwitched
            self.__vehicleStateCtrl.onRespawnBaseMoving += self.__onRespawnBaseMoving

    def stop(self):
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
        super(DistanceMarkerPlugin, self).stop()

    def initControlMode(self, mode, available):
        super(DistanceMarkerPlugin, self).initControlMode(mode, available)
        for index, keys in enumerate(config.CIRCLE_SETTING_KEYS):
            if config.SETTINGS[keys[0]]:
                self.__addMarker(index)
        for _, circle_name, _, _ in config.NATIVE_REPLACEMENTS:
            self.update_replacement_circle(circle_name)

    def updateControlMode(self, mode, vehicleID):
        super(DistanceMarkerPlugin, self).updateControlMode(mode, vehicleID)
        for entryID in self.__entryIDs + self.__nativeEntryIDs:
            if entryID is not None:
                self._setMatrix(entryID, matrix_factory.makeAttachedVehicleMatrix())

    def __getVehicleInfo(self):
        get_vehicle_info = getattr(self._arenaDP, 'getVehicleInfo', None)
        if not callable(get_vehicle_info):
            raise RuntimeError(config.TAG + 'Arena data provider is unavailable')
        return get_vehicle_info()

    def __getBoundingBox(self):
        get_bounding_box = getattr(self._parentObj, 'getBoundingBox', None)
        if not callable(get_bounding_box):
            raise RuntimeError(config.TAG + 'Minimap parent is unavailable')
        bounds = get_bounding_box()
        if not isinstance(bounds, (tuple, list)) or len(bounds) != 2:
            raise RuntimeError(config.TAG + 'Minimap parent returned invalid bounds')
        return bounds[0], bounds[1]

    def __isObserver(self, vehicleInfo):
        is_observer = getattr(vehicleInfo, 'isObserver', None)
        if not callable(is_observer):
            raise RuntimeError(config.TAG + 'Vehicle info cannot report observer state')
        return bool(is_observer())

    def __isAlive(self, vehicleInfo):
        is_alive = getattr(vehicleInfo, 'isAlive', None)
        if not callable(is_alive):
            raise RuntimeError(config.TAG + 'Vehicle info cannot report alive state')
        return bool(is_alive())

    def __addMarker(self, index):
        enabled_key = config.CIRCLE_SETTING_KEYS[index][0]
        if self.__entryIDs[index] is not None or not config.SETTINGS[enabled_key]:
            return

        vehicleInfo = self.__getVehicleInfo()
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
        bottomLeft, upperRight = self.__getBoundingBox()
        width = upperRight[0] - bottomLeft[0]
        height = upperRight[1] - bottomLeft[1]
        self._invoke(entryID, settings.VIEW_RANGE_CIRCLES_AS3_DESCR.AS_INIT_ARENA_SIZE, width, height)
        self.__drawCircle(index)

    def __removeMarker(self, index):
        entryID = self.__entryIDs[index]
        if entryID is not None:
            self._delEntry(entryID)
            self.__entryIDs[index] = None

    def __drawCircle(self, index):
        entryID = self.__entryIDs[index]
        if entryID is None: return

        distance_key, color_key, opacity_key = config.CIRCLE_SETTING_KEYS[index][1:]
        self._invoke(entryID, settings.VIEW_RANGE_CIRCLES_AS3_DESCR.AS_DEL_DYN_CIRCLE)
        self._invoke(
            entryID,
            settings.VIEW_RANGE_CIRCLES_AS3_DESCR.AS_ADD_DYN_CIRCLE,
            int(config.SETTINGS[color_key], 16),
            float(config.SETTINGS[opacity_key]) / 100.0,
            config.SETTINGS[distance_key])

    def __addNativeMarker(self, index):
        if self.__nativeEntryIDs[index] is not None:
            return

        vehicleInfo = self.__getVehicleInfo()
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
        bottomLeft, upperRight = self.__getBoundingBox()
        width = upperRight[0] - bottomLeft[0]
        height = upperRight[1] - bottomLeft[1]
        self._invoke(entryID, settings.VIEW_RANGE_CIRCLES_AS3_DESCR.AS_INIT_ARENA_SIZE, width, height)

    def __getNativeViewRangeRadius(self, circle_name):
        get_plugin = getattr(self._parentObj, 'getPlugin', None)
        if not callable(get_plugin):
            return None
        personal_plugin = get_plugin('personal')
        if circle_name == 'max_view_range':
            arena_visitor = getattr(personal_plugin, '_arenaVisitor', None)
            get_radius = getattr(arena_visitor, 'getVisibilityMaxRadius', None)
        else:
            get_radius = getattr(personal_plugin, '_getViewRangeRadius', None)
        if callable(get_radius):
            return get_radius()
        return None

    def update_replacement_circle(self, circle_name, distance=None):
        index = config.NATIVE_CIRCLE_INDEX[circle_name]
        enabled_key, color_key, opacity_key = config.NATIVE_CIRCLE_SETTING_KEYS[index]
        if (not config.SETTINGS['replace_wot_circle_markers'] or not config.SETTINGS[enabled_key]):
            self.remove_replacement_circle(circle_name)
            return False

        previous_data = self.__nativeCircleData[index]
        if circle_name in ('max_view_range', 'view_range'):
            if distance is None:
                distance = self.__getNativeViewRangeRadius(circle_name)
            if distance is None and previous_data is not None:
                distance = previous_data[2]
            if distance is None:
                print(config.TAG + 'Current WoT view range is unavailable; keeping its marker')
                return False
        else:
            distance_key = config.NATIVE_CIRCLE_DISTANCE_KEYS[circle_name]
            distance = config.SETTINGS[distance_key]

        data = (
            int(config.SETTINGS[color_key], 16),
            config.SETTINGS[opacity_key],
            distance
        )

        self.__addNativeMarker(index)
        entryID = self.__nativeEntryIDs[index]
        if entryID is None: return False

        vehicleInfo = self.__getVehicleInfo()
        self._setActive(entryID, vehicleInfo is not None and self.__isAlive(vehicleInfo))
        self.__nativeCircleData[index] = data

        if previous_data == data: return True
        self.__drawNativeCircle(index)
        return True

    def __drawNativeCircle(self, index):
        entryID = self.__nativeEntryIDs[index]
        data = self.__nativeCircleData[index]
        if entryID is None or data is None:
            return

        self._invoke(entryID, settings.VIEW_RANGE_CIRCLES_AS3_DESCR.AS_DEL_DYN_CIRCLE)
        self._invoke(
            entryID,
            settings.VIEW_RANGE_CIRCLES_AS3_DESCR.AS_ADD_DYN_CIRCLE,
            data[0],
            float(data[1]) / 100.0,
            data[2])

    def remove_replacement_circle(self, circle_name):
        index = config.NATIVE_CIRCLE_INDEX[circle_name]
        entryID = self.__nativeEntryIDs[index]
        if entryID is not None:
            self._invoke(entryID, settings.VIEW_RANGE_CIRCLES_AS3_DESCR.AS_DEL_DYN_CIRCLE)
        self.__nativeCircleData[index] = None

    def remove_replacement_circles(self):
        for _, circle_name, _, _ in config.NATIVE_REPLACEMENTS:
            self.remove_replacement_circle(circle_name)

    def apply_settings(self):
        for index, keys in enumerate(config.CIRCLE_SETTING_KEYS):
            if not config.SETTINGS[keys[0]]:
                self.__removeMarker(index)
            elif self.__entryIDs[index] is None:
                self.__addMarker(index)
            else:
                self.__drawCircle(index)
        for _, circle_name, _, _ in config.NATIVE_REPLACEMENTS:
            self.update_replacement_circle(circle_name)

    def __onPostMortemSwitched(self, noRespawnPossible, respawnAvailable):
        for entryID in self.__entryIDs + self.__nativeEntryIDs:
            if entryID is not None:
                self._setActive(entryID, False)

    def __onRespawnBaseMoving(self):
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
