import logging

from gui.Scaleform.daapi.view.battle.shared.minimap.component import MinimapComponent
from gui.mods.viewrangecustomizer import config, markerplugin  # pyright: ignore[reportMissingImports]

_logger = logging.getLogger(__name__)
_settings_registered = False
_settings_api = None
_reset_hooked = {}
_hooks = {}

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
        print(config.TAG + 'Aslain\'s Mod Menu was unable to register reset defaults')

def _update_settings_template(api):
    template = config.build_settings_template(config.SETTINGS)
    reload_template = getattr(api, 'reloadModTemplate', None)
    if callable(reload_template):
        reload_template(config.MOD_ID, template)
    else:
        print(config.TAG + 'Aslain\'s Mod Menu was unable to reload the updated template')

def _on_settings_changed(linkage, values):
    """Called when the settings are changed in the Mod Settings menu."""
    if (not _settings_registered or linkage != config.MOD_ID or not isinstance(values, dict)):
        return
    
    previous_settings = dict(config.SETTINGS)
    config.SETTINGS.update(config.normalize_settings(values))
    native_setting_keys = ['enabled', 'replace_wot_circle_markers']
    native_setting_keys.extend(key for marker_keys in config.NATIVE_CIRCLE_SETTING_KEYS for key in marker_keys)
    
    if any(previous_settings[key] != config.SETTINGS[key] for key in native_setting_keys):
        markerplugin.refresh_native_circles()
    
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
            print(config.TAG + 'Aslain\'s Mod Menu API cannot save normalized colors')
    if previous_settings['replace_wot_circle_markers'] != config.SETTINGS['replace_wot_circle_markers']:
        _update_settings_template(api)
    for plugin in list(config.ACTIVE_PLUGINS):
        plugin.apply_settings()
    _restore_template_defaults(api)

def _on_settings_reset(linkage, defaults):
    """Called when the settings are reset in Aslain's Mod Menu."""
    if not _settings_registered or linkage != config.MOD_ID:
        return

    if isinstance(defaults, dict):
        reset_settings = config.normalize_settings(defaults)
    else:
        print(config.TAG + 'Reset event did not include settings; using built-in defaults')
        reset_settings = dict(config.DEFAULT_SETTINGS)

    config.SETTINGS.clear()
    config.SETTINGS.update(reset_settings)

    markerplugin.refresh_native_circles()
    api = _get_settings_api()
    for plugin in list(config.ACTIVE_PLUGINS):
        plugin.apply_settings()

    _restore_template_defaults(api)

def _register_reset_callback(api):
    if id(api) in _reset_hooked:
        return
    if not hasattr(api, 'onResetMod'):
        print(config.TAG + 'Aslain\'s Mod Menu cannot register the reset callback')
        return
    _reset_hooked[id(api)] = api
    try:
        api.onResetMod += _on_settings_reset
    except Exception as error:
        print(config.TAG + 'Could not register reset callback: ' + str(error))

def _register_settings():
    """Register the mod's settings with Aslain's Mod Menu, if available."""
    global _settings_registered, _settings_api
    if _settings_registered:
        return

    api = _get_settings_api()
    if api is None:
        print(config.TAG + 'Aslain\'s Mod Menu not found; using built-in defaults')
        return

    get_settings = getattr(api, 'getModSettings', None)
    if not callable(get_settings):
        print(config.TAG + 'Aslain\'s Mod Menu was unable to load saved settings')
        return
    
    saved_settings = get_settings(config.MOD_ID, config.SETTINGS_TEMPLATE)
    if isinstance(saved_settings, dict): saved_settings = dict(saved_settings)

    settings_template = config.build_settings_template()
    set_template = getattr(api, 'setModTemplate', None)
    if not callable(set_template):
        print(config.TAG + 'Aslain\'s Mod Menu was unable to register this settings template')
        return

    _settings_api = api
    registered_settings = set_template(config.MOD_ID, settings_template, _on_settings_changed)
    if not isinstance(registered_settings, dict):
        print(config.TAG + 'Aslain\'s Mod Menu did not return registered settings')
        _unregister_settings()
        return

    if isinstance(saved_settings, dict):
        restored_settings = dict(registered_settings)
        restored_settings.update(config.menu_settings(config.normalize_settings(saved_settings)))
        if restored_settings != registered_settings:
            update_settings = getattr(api, 'updateModSettings', None)
            if callable(update_settings):
                update_settings(config.MOD_ID, restored_settings)
            else:
                print(config.TAG + 'Aslain\'s Mod Menu was unable to restore saved settings')
        saved_settings = restored_settings
    else:
        saved_settings = registered_settings

    if isinstance(saved_settings, dict):
        config.SETTINGS.clear()
        config.SETTINGS.update(config.normalize_settings(saved_settings))
    markerplugin.refresh_native_circles()
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
        print(config.TAG + 'Aslain\'s Mod Menu was unable to unregister the settings callback')

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

def _setup_plugins(plugins):
    """Add this mod's plugin without replacing WoT's existing plugins."""
    personal_plugin_class = plugins.get('personal') # Get the built-in plugin class that controls minimap circles
    if personal_plugin_class is not None:
        markerplugin.install_native_circle_commands_hook(personal_plugin_class)
    else:
        print(config.TAG + 'Built-in minimap circle plugin was not found')
    plugins[config.MOD_ID] = markerplugin.CustomCirclesPlugin

def _install_hook(owner, method_name, after):
    """Wrap a method and remember its raw class attribute for restoration.

    Python 2.7 returns an unbound method from normal class lookup.
    """
    key = (owner, method_name)
    if key in _hooks:
        return

    previous = getattr(owner, method_name)
    if getattr(previous, '_viewrangecustomizer_hook_owner', False):
        return

    class_attrs = owner.__dict__
    defined_here = method_name in class_attrs
    original_descriptor = class_attrs.get(method_name)
    active = [True]

    def wrapper(self, *args, **kwargs):
        result = previous(self, *args, **kwargs)
        if active[0]:
            try:
                after(result)
            except Exception:
                _logger.exception(config.TAG + 'Hook extension failed for ' + method_name)
        return result

    setattr(wrapper, '_viewrangecustomizer_hook_owner', True)
    setattr(owner, method_name, wrapper)
    _hooks[key] = (defined_here, original_descriptor, wrapper, active)

def _restore_hook(owner, method_name):
    """Undo our hook only if it is still installed.

    Restore the raw class attribute when the owner defined it. If it was
    inherited, delete our temporary override so normal inheritance resumes.
    """
    state = _hooks.pop((owner, method_name), None)
    if state is not None:
        defined_here, original_descriptor, wrapper, active = state
        active[0] = False
        if owner.__dict__.get(method_name) is wrapper:
            if defined_here:
                setattr(owner, method_name, original_descriptor)
            else:
                delattr(owner, method_name)

def init():
    """Register settings and install this mod's WoT minimap hook."""
    try:
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
        _install_hook(MinimapComponent, '_setupPlugins', _setup_plugins)
    except Exception:
        try:
            _logger.exception(config.TAG + 'Failed to initialize mod.')
            fini()
        except Exception as error:
            print(config.TAG + 'Could not clean up after initialization failure: ' + str(error))
        raise

def fini():
    """Unregister settings and restore only the minimap hooks we still own."""
    try:
        _unregister_settings()
    finally:
        try:
            _restore_hook(MinimapComponent, '_setupPlugins')
        finally:
            markerplugin.restore_native_circle_commands_hooks()
