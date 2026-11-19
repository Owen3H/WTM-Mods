from gui.Scaleform.daapi.view.battle.shared.minimap.component import MinimapComponent
from gui.mods.viewrangecustomizer import config, markerplugin  # pyright: ignore[reportMissingImports]

_settings_registered = False
_settings_api = None
_reset_hooked = {}
_original_setup_plugins = MinimapComponent._setupPlugins
_setup_hook_installed = False

def _get_settings_api():
    try:
        from gui.aslainMenu import g_modsSettingsApi  # pyright: ignore[reportMissingImports]
        return g_modsSettingsApi
    except ImportError:
        return None

def _restore_template_defaults(api):
    defaults = config.menu_settings(config.DEFAULT_SETTINGS)
    set_defaults = getattr(api, 'setModDefaults', None)
    if callable(set_defaults):
        set_defaults(config.MOD_ID, defaults)
    else:
        print(config.TAG + 'Mod Menu cannot register reset defaults')

def _update_settings_template(api):
    template = config.build_settings_template(config.SETTINGS)
    reload_template = getattr(api, 'reloadModTemplate', None)
    if callable(reload_template):
        reload_template(config.MOD_ID, template)
    else:
        print(config.TAG + 'Mod Menu cannot reload the updated template')


def _on_settings_changed(linkage, values):
    """Called when the settings are changed in the Mod Settings menu."""
    if (not _settings_registered or linkage != config.MOD_ID or not isinstance(values, dict)):
        return
    
    previous_settings = dict(config.SETTINGS)
    config.SETTINGS.update(config.normalize_settings(values))
    native_setting_keys = ['enabled', 'replace_wot_circle_markers']
    native_setting_keys.extend(key for marker_keys in config.NATIVE_CIRCLE_SETTING_KEYS for key in marker_keys)
    
    if any(previous_settings[key] != config.SETTINGS[key] for key in native_setting_keys):
        markerplugin.refresh_native_circle_visibility()
    
    api = _get_settings_api()
    color_settings_changed = False
    color_settings = [(color_key, opacity_key) for _, _, color_key, opacity_key in config.CIRCLE_SETTING_KEYS]
    color_settings.extend((color_key, opacity_key) for _, color_key, opacity_key in config.NATIVE_CIRCLE_SETTING_KEYS)
    for color_key, opacity_key in color_settings:
        color = config.color_with_opacity(config.SETTINGS[color_key], config.SETTINGS[opacity_key])
        if (values.get(color_key) != color or values.get(opacity_key) != config.SETTINGS[opacity_key]):
            color_settings_changed = True
        values[color_key] = color
        values[opacity_key] = config.SETTINGS[opacity_key]
    if color_settings_changed:
        update_settings = getattr(api, 'updateModSettings', None)
        if callable(update_settings):
            update_settings(config.MOD_ID, values)
        else:
            print(config.TAG + 'Mod Settings API cannot save normalized colors')
    if previous_settings['replace_wot_circle_markers'] != config.SETTINGS['replace_wot_circle_markers']:
        _update_settings_template(api)
    for plugin in list(config.ACTIVE_PLUGINS):
        plugin.apply_settings()
    _restore_template_defaults(api)

def _on_settings_reset(linkage, defaults):
    """Called when the settings are reset in the Mod Settings menu."""
    if not _settings_registered or linkage != config.MOD_ID:
        return

    if isinstance(defaults, dict):
        reset_settings = config.normalize_settings(defaults)
    else:
        print(config.TAG + 'Reset event did not include settings; using built-in defaults')
        reset_settings = dict(config.DEFAULT_SETTINGS)

    config.SETTINGS.clear()
    config.SETTINGS.update(reset_settings)
    markerplugin.refresh_native_circle_visibility()
    api = _get_settings_api()
    for plugin in list(config.ACTIVE_PLUGINS):
        plugin.apply_settings()
    _restore_template_defaults(api)

def _register_reset_callback(api):
    if id(api) in _reset_hooked:
        return
    if not hasattr(api, 'onResetMod'):
        print(config.TAG + 'Mod Menu cannot register the reset callback')
        return
    try:
        api.onResetMod += _on_settings_reset
        _reset_hooked[id(api)] = api
    except Exception as error:
        print(config.TAG + 'Could not register reset callback: ' + str(error))

def _register_settings():
    global _settings_registered, _settings_api
    if _settings_registered:
        return

    api = _get_settings_api()
    if api is None:
        print(config.TAG + 'Mod Settings menu not found; using built-in defaults')
        return

    get_settings = getattr(api, 'getModSettings', None)
    if not callable(get_settings):
        print(config.TAG + 'Mod Menu cannot load saved settings')
        return
    
    saved_settings = get_settings(config.MOD_ID, config.SETTINGS_TEMPLATE)
    if isinstance(saved_settings, dict): saved_settings = dict(saved_settings)

    settings_template = config.build_settings_template()
    set_template = getattr(api, 'setModTemplate', None)
    if not callable(set_template):
        print(config.TAG + 'Mod Menu cannot register this settings template')
        return

    registered_settings = set_template(
        config.MOD_ID, settings_template, _on_settings_changed)
    if not isinstance(registered_settings, dict):
        print(config.TAG + 'Mod Menu did not return registered settings')
        return

    if isinstance(saved_settings, dict):
        restored_settings = dict(registered_settings)
        restored_settings.update(config.menu_settings(config.normalize_settings(saved_settings)))
        if restored_settings != registered_settings:
            update_settings = getattr(api, 'updateModSettings', None)
            if callable(update_settings):
                update_settings(config.MOD_ID, restored_settings)
            else:
                print(config.TAG + 'Mod Menu cannot restore saved settings')
        saved_settings = restored_settings
    else:
        saved_settings = registered_settings

    if isinstance(saved_settings, dict):
        config.SETTINGS.clear()
        config.SETTINGS.update(config.normalize_settings(saved_settings))
    markerplugin.refresh_native_circle_visibility()
    _restore_template_defaults(api)
    _register_reset_callback(api)
    _settings_registered = True
    _settings_api = api
    print(config.TAG + 'Registered settings with Mod Settings menu')

def _unregister_settings():
    global _settings_registered, _settings_api
    
    api = _settings_api
    if api is None: return

    if hasattr(api, 'onSettingsChanged'):
        try:
            api.onSettingsChanged -= _on_settings_changed
        except Exception as error:
            print(config.TAG + 'Could not unregister settings callback: ' + str(error))
    else:
        print(config.TAG + 'Mod Menu cannot unregister the settings callback')

    for api_id, reset_api in list(_reset_hooked.items()):
        if api_id != id(api):
            continue
        try:
            reset_api.onResetMod -= _on_settings_reset
            del _reset_hooked[api_id]
        except Exception as error:
            print(config.TAG + 'Could not unregister reset callback: ' + str(error))
   
    _settings_registered = False
    _settings_api = None

def _setup_plugins(self, arenaVisitor):
    plugins = _original_setup_plugins(self, arenaVisitor)
    personal_plugin_class = plugins.get('personal')
    if personal_plugin_class is not None:
        markerplugin.install_native_circle_visibility_hook(personal_plugin_class)
    else:
        print(config.TAG + 'Built-in minimap circle plugin was not found')
    plugins['distanceMarker'] = markerplugin.DistanceMarkerPlugin
    return plugins

def init():
    global _original_setup_plugins, _setup_hook_installed
    _register_settings()
    if not _setup_hook_installed:
        _original_setup_plugins = MinimapComponent._setupPlugins
        MinimapComponent._setupPlugins = _setup_plugins
        _setup_hook_installed = True

def fini():
    global _setup_hook_installed
    _unregister_settings()
    if MinimapComponent._setupPlugins is _setup_plugins:
        MinimapComponent._setupPlugins = _original_setup_plugins
        _setup_hook_installed = False
    markerplugin.restore_native_circle_visibility_hooks()
