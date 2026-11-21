MOD_ID = 'wtm.display_tech_tree_roles'
TAG = '[DisplayTechTreeRoles] '
DEFAULT_SETTINGS = {'enabled': True, 'icon_size': 25, 'margin': -20, 'position': 1}
SETTINGS = dict(DEFAULT_SETTINGS)

try:
    _NUMBER_TYPES = (int, long, float)  # type: ignore
except NameError:
    _NUMBER_TYPES = (int, float)

_settings_api = None
_settings_registered = False
_reset_registered = False
_tech_tree_hook_state = None
_view_hook_states = []
_active_views = []


def _settings_template(templates):
    return {
        'modDisplayName': 'Display Tech Tree Roles',
        'enabled': DEFAULT_SETTINGS['enabled'],
        'column1': [
            templates.createSlider('Icon size (px)', 'icon_size', DEFAULT_SETTINGS['icon_size'],
                                   8, 64, 1, format='{{value}} px'),
            templates.createSlider('Margin (px)', 'margin', DEFAULT_SETTINGS['margin'],
                                   -32, 32, 1, format='{{value}} px',
                                   tooltip='Distance from the vehicle image area. Negative values overlap it.'),
            templates.createDropdown('Position', 'position', ['Top', 'Bottom'],
                                     DEFAULT_SETTINGS['position']),
        ],
        'column2': [],
    }


def _normalize_settings(values, base):
    normalized = dict(base)
    if 'enabled' in values:
        if isinstance(values['enabled'], bool):
            normalized['enabled'] = values['enabled']
        else:
            print(TAG + 'Ignoring invalid enabled setting')
    for key, minimum, maximum in (('icon_size', 8, 64), ('margin', -32, 32),
                                  ('position', 0, 1)):
        if key not in values:
            continue
        value = values[key]
        if (isinstance(value, _NUMBER_TYPES) and not isinstance(value, bool) and
                minimum <= value <= maximum and value == int(value)):
            normalized[key] = int(value)
        else:
            print(TAG + 'Ignoring invalid ' + key + ' setting')
    return normalized


def _apply_settings(values, base):
    updated = _normalize_settings(values, base)
    if updated != SETTINGS:
        SETTINGS.clear()
        SETTINGS.update(updated)
        for view in list(_active_views):
            view.redraw()


def _on_settings_changed(linkage, values):
    if not _settings_registered or linkage != MOD_ID:
        return
    if not isinstance(values, dict):
        print(TAG + 'Settings change did not include a settings dictionary')
        return
    _apply_settings(values, SETTINGS)


def _on_settings_reset(linkage, defaults):
    if not _settings_registered or linkage != MOD_ID:
        return
    if not isinstance(defaults, dict):
        print(TAG + 'Reset event did not include settings; using built-in defaults')
        defaults = {}
    _apply_settings(defaults, DEFAULT_SETTINGS)


def _register_settings():
    global _settings_api, _settings_registered, _reset_registered
    if _settings_registered:
        return
    try:
        from gui.aslainMenu import g_modsSettingsApi, templates  # pyright: ignore[reportMissingImports]
    except ImportError:
        print(TAG + 'Aslain Mod Menu not found; using built-in defaults')
        return

    api = g_modsSettingsApi
    get_settings = getattr(api, 'getModSettings', None)
    set_template = getattr(api, 'setModTemplate', None)
    if not callable(get_settings) or not callable(set_template):
        print(TAG + 'Aslain Mod Menu cannot register settings')
        return

    saved = get_settings(MOD_ID, _settings_template(templates))
    registered = set_template(MOD_ID, _settings_template(templates), _on_settings_changed)
    if not isinstance(registered, dict):
        print(TAG + 'Aslain Mod Menu did not return registered settings')
        return
    restored = _normalize_settings(registered, DEFAULT_SETTINGS)
    if isinstance(saved, dict):
        restored = _normalize_settings(saved, restored)
    elif saved is not None:
        print(TAG + 'Aslain Mod Menu returned invalid saved settings')
    if restored != registered:
        update_settings = getattr(api, 'updateModSettings', None)
        if callable(update_settings):
            update_settings(MOD_ID, restored)
        else:
            print(TAG + 'Aslain Mod Menu cannot restore saved settings')
    _apply_settings(restored, DEFAULT_SETTINGS)

    set_defaults = getattr(api, 'setModDefaults', None)
    if callable(set_defaults):
        set_defaults(MOD_ID, dict(DEFAULT_SETTINGS))
    else:
        print(TAG + 'Aslain Mod Menu cannot register reset defaults')
    if hasattr(api, 'onResetMod'):
        api.onResetMod += _on_settings_reset
        _reset_registered = True
    else:
        print(TAG + 'Aslain Mod Menu cannot register the reset callback')
    _settings_api = api
    _settings_registered = True


def _unregister_settings():
    global _settings_api, _settings_registered, _reset_registered
    api = _settings_api
    if api is None:
        return
    if hasattr(api, 'onSettingsChanged'):
        api.onSettingsChanged -= _on_settings_changed
    else:
        print(TAG + 'Aslain Mod Menu cannot unregister the settings callback')
    if _reset_registered:
        api.onResetMod -= _on_settings_reset
    _settings_api = None
    _settings_registered = False
    _reset_registered = False


def _make_tech_tree_nodes_hook(previous_get_tech_tree_nodes):
    def get_tech_tree_nodes(self, node, nodeRows):
        data = previous_get_tech_tree_nodes(self, node, nodeRows)
        vehicle = node.getItem()
        role_label = vehicle.roleLabel
        if SETTINGS['enabled'] and role_label and role_label != 'NotDefined':
            from gui.impl import backport
            from gui.impl.gen import R
            from gui.impl.utils.path import normalizeGfImagePath
            roles = R.images.gui.maps.icons.roleExp.roles
            icons = roles.c_32x32 if role_label == 'role_SPG' else roles.c_24x24
            data['roleIcon'] = normalizeGfImagePath(backport.image(icons.dyn(role_label)()))
            data['roleIconSize'] = SETTINGS['icon_size']
            data['roleIconMargin'] = SETTINGS['margin']
            data['roleIconPosition'] = 'bottom' if SETTINGS['position'] else 'top'
        return data

    return get_tech_tree_nodes


def _install_tech_tree_hook():
    global _tech_tree_hook_state
    if _tech_tree_hook_state is not None:
        return

    from gui.impl.lobby.tech_tree.tech_tree_view import _NationTreeViewDumper
    original = _NationTreeViewDumper.__dict__.get('_getTechTreeNodes')
    if original is None:
        raise RuntimeError('DisplayTechTreeRoles: tech tree node method not found')
    wrapper = _make_tech_tree_nodes_hook(original)
    _NationTreeViewDumper._getTechTreeNodes = wrapper
    _tech_tree_hook_state = (_NationTreeViewDumper, original, wrapper)


def _restore_tech_tree_hook():
    global _tech_tree_hook_state
    state = _tech_tree_hook_state
    if state is None:
        return

    dumper_class, original, wrapper = state
    if dumper_class.__dict__.get('_getTechTreeNodes') is wrapper:
        setattr(dumper_class, '_getTechTreeNodes', original)
    _tech_tree_hook_state = None


def _make_view_loading_hook(previous):
    def on_loading(self, *args, **kwargs):
        result = previous(self, *args, **kwargs)
        if self not in _active_views:
            _active_views.append(self)
        return result
    return on_loading


def _make_view_finalize_hook(previous):
    def finalize(self):
        if self in _active_views:
            _active_views.remove(self)
        return previous(self)
    return finalize


def _install_view_hooks():
    if _view_hook_states:
        return
    from gui.impl.lobby.tech_tree.tech_tree_view import TechTreeView
    for name, make_hook in (('_onLoading', _make_view_loading_hook),
                            ('_finalize', _make_view_finalize_hook)):
        original = TechTreeView.__dict__[name]
        wrapper = make_hook(original)
        setattr(TechTreeView, name, wrapper)
        _view_hook_states.append((TechTreeView, name, original, wrapper))


def _restore_view_hooks():
    for view_class, name, original, wrapper in _view_hook_states:
        if view_class.__dict__.get(name) is wrapper:
            setattr(view_class, name, original)
    del _view_hook_states[:]
    del _active_views[:]


def init():
    _install_tech_tree_hook()
    _install_view_hooks()
    _register_settings()


def fini():
    try:
        _unregister_settings()
    finally:
        _restore_view_hooks()
        _restore_tech_tree_hook()