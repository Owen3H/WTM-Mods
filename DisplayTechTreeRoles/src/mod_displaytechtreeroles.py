import json
import logging

from gui.mods.displaytechtreeroles import config  # pyright: ignore[reportMissingImports]

_settings_api = None
_settings_registered = False
_reset_registered = False

_tech_tree_hook_state = None
_view_hook_states = []

_active_views = []
_injected_views = {}

_logger = logging.getLogger(__name__)


def _apply_settings(values, base):
    updated = config.normalize_settings(values, base)
    if updated != config.SETTINGS:
        config.SETTINGS.clear()
        config.SETTINGS.update(updated)
        for view in list(_active_views):
            view.redraw()


def _on_settings_changed(linkage, values):
    if not _settings_registered or linkage != config.MOD_ID:
        return
    if not isinstance(values, dict):
        print(config.TAG + 'Settings change did not include a settings dictionary')
        return
    _apply_settings(values, config.SETTINGS)


def _on_settings_reset(linkage, defaults):
    if not _settings_registered or linkage != config.MOD_ID:
        return
    if not isinstance(defaults, dict):
        print(config.TAG + 'Reset event did not include settings; using built-in defaults')
        defaults = {}
    _apply_settings(defaults, config.DEFAULT_SETTINGS)


def _register_settings():
    global _settings_api, _settings_registered, _reset_registered
    if _settings_registered:
        return
    try:
        from gui.aslainMenu import g_modsSettingsApi, templates  # pyright: ignore[reportMissingImports]
    except ImportError:
        print(config.TAG + 'Aslain Mod Menu not found; using built-in defaults')
        return

    api = g_modsSettingsApi
    get_settings = getattr(api, 'getModSettings', None)
    set_template = getattr(api, 'setModTemplate', None)
    if not callable(get_settings) or not callable(set_template):
        print(config.TAG + 'Aslain Mod Menu cannot register settings')
        return

    saved = get_settings(config.MOD_ID, config.settings_template(templates))
    registered = set_template(config.MOD_ID, config.settings_template(templates), _on_settings_changed)
    if not isinstance(registered, dict):
        print(config.TAG + 'Aslain Mod Menu did not return registered settings')
        return
    _settings_api = api
    restored = config.normalize_settings(registered, config.DEFAULT_SETTINGS)
    if isinstance(saved, dict):
        restored = config.normalize_settings(saved, restored)
    elif saved is not None:
        print(config.TAG + 'Aslain Mod Menu returned invalid saved settings')
    if restored != registered:
        update_settings = getattr(api, 'updateModSettings', None)
        if callable(update_settings):
            update_settings(config.MOD_ID, restored)
        else:
            print(config.TAG + 'Aslain Mod Menu cannot restore saved settings')
    _apply_settings(restored, config.DEFAULT_SETTINGS)

    set_defaults = getattr(api, 'setModDefaults', None)
    if callable(set_defaults):
        set_defaults(config.MOD_ID, dict(config.DEFAULT_SETTINGS))
    else:
        print(config.TAG + 'Aslain Mod Menu cannot register reset defaults')
    if hasattr(api, 'onResetMod'):
        api.onResetMod += _on_settings_reset
        _reset_registered = True
    else:
        print(config.TAG + 'Aslain Mod Menu cannot register the reset callback')
    _settings_registered = True


def _unregister_settings():
    global _settings_api, _settings_registered, _reset_registered
    api = _settings_api
    if api is None:
        return
    _settings_registered = False
    try:
        try:
            if hasattr(api, 'onSettingsChanged'):
                api.onSettingsChanged -= _on_settings_changed
            else:
                print(config.TAG + 'Aslain Mod Menu cannot unregister the settings callback')
        finally:
            if _reset_registered:
                api.onResetMod -= _on_settings_reset
    finally:
        _settings_api = None
        _reset_registered = False


def _make_tech_tree_nodes_hook(previous_get_tech_tree_nodes, active):
    def get_tech_tree_nodes(self, node, nodeRows):
        data = previous_get_tech_tree_nodes(self, node, nodeRows)
        if not active[0]:
            return data
        vehicle = node.getItem()
        role_label = vehicle.roleLabel
        if config.SETTINGS['enabled'] and role_label and role_label != 'NotDefined':
            from gui.impl import backport
            from gui.impl.gen import R
            from gui.impl.utils.path import normalizeGfImagePath
            roles = R.images.gui.maps.icons.roleExp.roles
            icons = roles.c_32x32 if role_label == 'role_SPG' else roles.c_24x24
            data['roleIcon'] = normalizeGfImagePath(backport.image(icons.dyn(role_label)()))
            data['roleIconSize'] = config.SETTINGS['icon_size']
            data['roleIconMargin'] = config.SETTINGS['margin']
            data['roleIconPosition'] = 'bottom' if config.SETTINGS['position'] else 'top'
        return data

    return get_tech_tree_nodes


def _install_hook(cls, name, make_hook):
    defined_here = name in cls.__dict__
    original = cls.__dict__.get(name)
    previous = getattr(cls, name)
    # A later mod may retain this wrapper after our class attribute is restored.
    active = [True]
    wrapper = make_hook(previous, active)
    setattr(cls, name, wrapper)
    return cls, name, defined_here, original, wrapper, active


def _restore_hook(state):
    cls, name, defined_here, original, wrapper, active = state
    active[0] = False
    if cls.__dict__.get(name) is wrapper:
        if defined_here:
            setattr(cls, name, original)
        else:
            delattr(cls, name)


def _install_tech_tree_hook():
    global _tech_tree_hook_state
    if _tech_tree_hook_state is not None:
        return

    from gui.impl.lobby.tech_tree.tech_tree_view import _NationTreeViewDumper
    _tech_tree_hook_state = _install_hook(_NationTreeViewDumper, '_getTechTreeNodes',
                                          _make_tech_tree_nodes_hook)


def _restore_tech_tree_hook():
    global _tech_tree_hook_state
    state = _tech_tree_hook_state
    if state is None:
        return

    _restore_hook(state)
    _tech_tree_hook_state = None


def _make_view_loading_hook(previous, active):
    def on_loading(self, *args, **kwargs):
        result = previous(self, *args, **kwargs)
        if active[0] and self not in _active_views:
            _active_views.append(self)
        return result
    return on_loading


def _make_view_finalize_hook(previous, active):
    def finalize(self):
        if active[0] and self in _active_views:
            _active_views.remove(self)
        if active[0]:
            try:
                _detach_injection(self)
            except Exception:
                _logger.exception(config.TAG + 'Could not detach Gameface injection')
        return previous(self)
    return finalize


def _role_payload(view):
    roles = {}
    for vehicle_id, value in view.viewModel.getTechTreeNodes().items():
        record = json.loads(value)
        if 'roleIcon' in record:
            roles[str(vehicle_id)] = {
                key: record[key] for key in
                ('roleIcon', 'roleIconSize', 'roleIconMargin', 'roleIconPosition')
            }
    return json.dumps(roles, separators=(',', ':'))


def _create_injection(layout_id, payload):
    from frameworks.wulf import ViewModel
    from gui.impl.pub.view_component import ViewComponent
    from openwg_gameface import gf_mod_inject  # pyright: ignore[reportMissingImports]

    class InjectionModel(ViewModel):
        def __init__(self):
            super(InjectionModel, self).__init__(properties=2, commands=0)

        def _initialize(self):
            super(InjectionModel, self)._initialize()
            gf_mod_inject(self, config.FEATURE_NAME, scripts=[config.SCRIPT_URL])
            self._addStringProperty('payload', payload)

        def setPayload(self, value):
            self._setString(1, value)

    return ViewComponent(layoutID=layout_id, model=InjectionModel)


def _attach_injection(view):
    if view in _injected_views:
        return
    from gui.impl.gen import R
    layout_id = getattr(R.mods.wtm, config.MOD_NAME).views.Injection()
    if layout_id < 0:
        raise ValueError('Gameface injection layout is not registered')
    if view.getChildView(layout_id) is not None:
        raise ValueError('Gameface injection slot is already occupied')
    child = _create_injection(layout_id, _role_payload(view))
    try:
        view.setChildView(layout_id, child)
        if view.getChildView(layout_id) is not child:
            raise RuntimeError('Gameface injection child was not attached')
    except Exception:
        child.destroy()
        raise
    _injected_views[view] = (layout_id, child)


def _sync_injected_role_model(view):
    state = _injected_views.get(view)
    if state is not None:
        model = state[1].getViewModel()
        with model.transaction():
            model.setPayload(_role_payload(view))


def _detach_injection(view):
    state = _injected_views.pop(view, None)
    if state is not None:
        layout_id, child = state
        if view.getChildView(layout_id) is not child:
            _logger.warning(config.TAG + 'Gameface injection child is no longer attached')
            return
        try:
            model = child.getViewModel()
            with model.transaction():
                model.setPayload('null')
        finally:
            view.setChildView(layout_id, None)


def _make_view_loaded_hook(previous, active):
    def on_loaded(self, *args, **kwargs):
        result = previous(self, *args, **kwargs)
        if active[0]:
            try:
                _attach_injection(self)
            except Exception:
                _logger.exception(config.TAG + 'Could not attach Gameface injection')
        return result
    return on_loaded


def _make_view_update_hook(previous, active):
    def update(self, *args, **kwargs):
        result = previous(self, *args, **kwargs)
        if active[0]:
            try:
                _sync_injected_role_model(self)
            except Exception:
                _logger.exception(config.TAG + 'Could not update Gameface role icons')
        return result
    return update


def _install_view_hooks():
    if _view_hook_states:
        return
    from gui.impl.lobby.tech_tree.tech_tree_view import TechTreeView
    for name, make_hook in (('_onLoading', _make_view_loading_hook),
                            ('_onLoaded', _make_view_loaded_hook),
                            ('_TechTreeView__fullUpdateOfViewModel', _make_view_update_hook),
                            ('_finalize', _make_view_finalize_hook)):
        _view_hook_states.append(_install_hook(TechTreeView, name, make_hook))


def _restore_view_hooks():
    for view in list(_injected_views):
        try:
            _detach_injection(view)
        except Exception:
            _logger.exception(config.TAG + 'Could not detach Gameface injection')
    for state in _view_hook_states:
        _restore_hook(state)
    del _view_hook_states[:]
    del _active_views[:]


def init():
    initialized = False
    try:
        _install_tech_tree_hook()
        _install_view_hooks()
        _register_settings()
        initialized = True
    finally:
        if not initialized:
            fini()


def fini():
    try:
        _unregister_settings()
    finally:
        try:
            _restore_view_hooks()
        finally:
            _restore_tech_tree_hook()