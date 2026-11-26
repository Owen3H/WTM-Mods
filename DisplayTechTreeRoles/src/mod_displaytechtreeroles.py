import logging

from gui.mods.displaytechtreeroles import config, injection  # pyright: ignore[reportMissingImports]

_logger = logging.getLogger(__name__)
_settings_api = None
_settings_registered = False
_reset_registered = False

_active_views = []
_hooks = {}

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

    template = config.settings_template(templates)
    saved = get_settings(config.MOD_ID, template)
    _settings_api = api
    registered = set_template(config.MOD_ID, template, _on_settings_changed)
    if not isinstance(registered, dict):
        print(config.TAG + 'Aslain Mod Menu did not return registered settings')
        _unregister_settings()
        return
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
        _reset_registered = True
        api.onResetMod += _on_settings_reset
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
                try:
                    api.onSettingsChanged -= _on_settings_changed
                except ValueError:
                    print(config.TAG + 'Aslain Mod Menu settings callback was not registered')
            else:
                print(config.TAG + 'Aslain Mod Menu cannot unregister the settings callback')
        finally:
            if _reset_registered:
                try:
                    api.onResetMod -= _on_settings_reset
                except ValueError:
                    print(config.TAG + 'Aslain Mod Menu reset callback was not registered')
    finally:
        _settings_api = None
        _reset_registered = False


def _make_tech_tree_nodes_hook(previous_get_tech_tree_nodes, active):
    def get_tech_tree_nodes(self, node, nodeRows):
        data = previous_get_tech_tree_nodes(self, node, nodeRows)
        if active[0]:
            try:
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
            except Exception:
                _logger.exception(config.TAG + 'Could not add vehicle role data')
        return data

    return get_tech_tree_nodes


def _install_hook(cls, name, make_hook):
    key = (cls, name)
    if key in _hooks:
        return
    defined_here = name in cls.__dict__
    original = cls.__dict__.get(name)
    previous = getattr(cls, name)
    # A later wrapper may retain this callable after the class attribute is restored.
    active = [True]
    wrapper = make_hook(previous, active)
    wrapper._wtm_displaytechtreeroles_owner = name
    setattr(cls, name, wrapper)
    _hooks[key] = (defined_here, original, wrapper, active)


def _restore_hook(cls, name):
    state = _hooks.pop((cls, name), None)
    if state is None:
        return
    defined_here, original, wrapper, active = state
    active[0] = False
    if cls.__dict__.get(name) is wrapper:
        if defined_here:
            setattr(cls, name, original)
        else:
            delattr(cls, name)

def _restore_hooks():
    first_error = None
    for cls, name in list(_hooks):
        try:
            _restore_hook(cls, name)
        except Exception as error:
            _logger.exception(config.TAG + 'Could not restore hook ' + name)
            if first_error is None:
                first_error = error
    if first_error is not None:
        raise first_error


def _make_view_loading_hook(previous, active):
    def on_loading(self, *args, **kwargs):
        result = previous(self, *args, **kwargs)
        if active[0] and self not in _active_views:
            _active_views.append(self)
        return result
    return on_loading


def _make_view_loaded_hook(previous, active):
    """Add the mod's extra view after the tech tree has loaded."""
    def on_loaded(self, *args, **kwargs):
        result = previous(self, *args, **kwargs)
        if active[0]:
            try:
                injection.attach(self)
            except Exception:
                _logger.exception(config.TAG + 'Could not attach Gameface injection')
        return result
    return on_loaded


def _make_view_update_hook(previous, active):
    """After the game updates the tech tree, send role data to the extra view.

    If sending fails, log the error and return the game's original result.
    """
    def update(self, *args, **kwargs):
        result = previous(self, *args, **kwargs)
        if active[0]:
            try:
                injection.sync_role_model(self)
            except Exception:
                _logger.exception(config.TAG + 'Could not update Gameface role icons')
        return result
    return update


def _make_view_finalize_hook(previous, active):
    """When the tech tree closes, stop keeping references to it and its extra view.

    Leave removing the extra view as the game's responsibility.
    """
    def finalize(self):
        if active[0]:
            if self in _active_views:
                _active_views.remove(self)
            injection.forget(self)
        return previous(self)
    return finalize


def _install_view_hooks():
    """Set up the mod to respond when the tech tree opens, changes, or closes.

    Opening adds the extra view, changes update it, and closing clears the
    mod's references to the tree.
    """
    on_loading = ('_onLoading', _make_view_loading_hook)
    on_loaded = ('_onLoaded', _make_view_loaded_hook)
    on_update = ('_TechTreeView__fullUpdateOfViewModel', _make_view_update_hook)
    on_finalize = ('_finalize', _make_view_finalize_hook)
    
    from gui.impl.lobby.tech_tree.tech_tree_view import TechTreeView
    for name, make_hook in (on_loading, on_loaded, on_update, on_finalize): 
        _install_hook(TechTreeView, name, make_hook)


def _install_tech_tree_hook():
    from gui.impl.lobby.tech_tree.tech_tree_view import _NationTreeViewDumper
    _install_hook(_NationTreeViewDumper, '_getTechTreeNodes', _make_tech_tree_nodes_hook)


def _cleanup_views():
    """When the mod stops or fails to start, try to remove its extra views."""
    injection.cleanup()
    del _active_views[:]


def init():
    initialized = False
    try:
        _install_tech_tree_hook()
        _install_view_hooks()
        previous_settings = dict(config.SETTINGS)
        try:
            _register_settings()
        except Exception:
            _logger.exception(config.TAG + 'Could not register settings; using previous settings')
            try:
                _unregister_settings()
            except Exception:
                _logger.exception(config.TAG + 'Could not clean up failed settings registration')
            config.SETTINGS.clear()
            config.SETTINGS.update(previous_settings)
        initialized = True
    finally:
        if not initialized:
            fini()


def fini():
    """When the mod stops or fails to start, clean up its settings, views, and hooks."""
    try:
        _unregister_settings()
    finally:
        try:
            _cleanup_views()
        finally:
            _restore_hooks()