from __future__ import absolute_import

import imp
import os
import sys
import types
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_MISSING = object()


class Event(object):
    def __init__(self):
        self.handlers = []

    def __iadd__(self, handler):
        self.handlers.append(handler)
        return self

    def __isub__(self, handler):
        self.handlers.remove(handler)
        return self


class HookTests(unittest.TestCase):
    def setUp(self):
        self.previous_modules = {}
        self.previous_parent_attributes = {}
        self.native_module = None

        for name in (
                'gui', 'gui.Scaleform', 'gui.Scaleform.daapi',
                'gui.Scaleform.daapi.view', 'gui.Scaleform.daapi.view.battle',
                'gui.Scaleform.daapi.view.battle.shared',
                'gui.Scaleform.daapi.view.battle.shared.minimap',
                'gui.mods', 'gui.mods.viewrangecustomizer'):
            self.add_module(name, package=True)

        self.config = self.add_module('gui.mods.viewrangecustomizer.config')
        self.config.MOD_ID = 'wtm.view_range_customizer'
        self.config.TAG = '[ViewRangeCustomizer] '
        self.config.SETTINGS_TEMPLATE = {}
        self.config.DEFAULT_SETTINGS = {}
        self.config.SETTINGS = {}
        self.config.NATIVE_CIRCLE_SETTING_KEYS = ()
        self.config.CIRCLE_SETTING_KEYS = ()
        self.config.ACTIVE_PLUGINS = []
        self.config.build_settings_template = lambda values=None: {}
        self.config.menu_settings = lambda values: values
        self.config.normalize_settings = lambda values: values

        self.native_installs = []
        self.markerplugin = self.add_module('gui.mods.viewrangecustomizer.markerplugin')
        self.markerplugin.CustomCirclesPlugin = type('CustomCirclesPlugin', (object,), {})
        self.markerplugin.install_native_circle_commands_hook = self.native_installs.append
        self.markerplugin.restore_native_circle_commands_hooks = lambda: None
        self.markerplugin.refresh_native_circles = lambda: None

        self.personal_class = type('PersonalPlugin', (object,), {})
        self.setup_calls = []
        component = self.add_module(
            'gui.Scaleform.daapi.view.battle.shared.minimap.component')

        def setup_plugins(instance, arena_visitor):
            self.setup_calls.append(arena_visitor)
            return {'personal': self.personal_class}

        self.component_class = type('MinimapComponent', (object,), {
            '_setupPlugins': setup_plugins,
        })
        component.MinimapComponent = self.component_class

        self.mod = imp.load_source(
            'test_viewrangecustomizer_mod',
            os.path.join(ROOT, 'src', 'mod_viewrangecustomizer.py'))

    def add_module(self, name, package=False):
        module = types.ModuleType(name)
        if package:
            module.__path__ = []
        self.previous_modules[name] = sys.modules.get(name, _MISSING)
        sys.modules[name] = module
        if '.' in name:
            parent_name, child_name = name.rsplit('.', 1)
            parent = sys.modules.get(parent_name)
            if parent is not None:
                key = (parent, child_name)
                if key not in self.previous_parent_attributes:
                    self.previous_parent_attributes[key] = getattr(parent, child_name, _MISSING)
                setattr(parent, child_name, module)
        return module

    def add_settings_api(self, set_template):
        menu = self.add_module('gui.aslainMenu')
        api = type('SettingsAPI', (object,), {})()
        api.onSettingsChanged = Event()
        api.onResetMod = Event()
        api.getModSettings = lambda linkage, template: None
        api.setModTemplate = set_template
        menu.g_modsSettingsApi = api
        menu.templates = object()
        return api

    def load_native_module(self):
        for name in (
                'gui.battle_control',
                'gui.Scaleform.daapi.view.battle.shared.minimap.common',
                'gui.Scaleform.daapi.view.battle.shared.minimap.settings'):
            self.add_module(name, package=name.endswith('battle_control'))
        minimap = sys.modules['gui.Scaleform.daapi.view.battle.shared.minimap']
        minimap.common = sys.modules[
            'gui.Scaleform.daapi.view.battle.shared.minimap.common']
        minimap.settings = sys.modules[
            'gui.Scaleform.daapi.view.battle.shared.minimap.settings']
        minimap.common.SimplePlugin = type('SimplePlugin', (object,), {})
        self.add_module('gui.battle_control.matrix_factory')
        self.native_module = imp.load_source(
            'test_viewrangecustomizer_markerplugin',
            os.path.join(ROOT, 'src', 'viewrangecustomizer', 'markerplugin.py'))
        return minimap.settings

    def tearDown(self):
        if self.native_module is not None:
            self.native_module.restore_native_circle_commands_hooks()
        self.mod.fini()
        sys.modules.pop('test_viewrangecustomizer_mod', None)
        sys.modules.pop('test_viewrangecustomizer_markerplugin', None)
        for name, previous in self.previous_modules.items():
            if previous is _MISSING:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = previous
        for (parent, child_name), previous in self.previous_parent_attributes.items():
            if previous is _MISSING:
                if hasattr(parent, child_name):
                    delattr(parent, child_name)
            else:
                setattr(parent, child_name, previous)

    def test_setup_wrapper_stops_modifying_results_after_fini(self):
        self.mod.init()
        instance = self.component_class()
        wrapper = self.component_class.__dict__['_setupPlugins']
        self.assertTrue(getattr(wrapper, '_viewrangecustomizer_hook_owner', False))
        self.assertIn(self.config.MOD_ID, instance._setupPlugins('active'))

        later_calls = []

        def later_wrapper(instance, *args, **kwargs):
            later_calls.append(True)
            return wrapper(instance, *args, **kwargs)

        self.component_class._setupPlugins = later_wrapper
        self.mod.fini()
        result = instance._setupPlugins('after fini')
        self.assertEqual(result, {'personal': self.personal_class})
        self.assertEqual(self.setup_calls, ['active', 'after fini'])
        self.assertEqual(later_calls, [True])
        self.assertEqual(self.native_installs, [self.personal_class])

    def test_setup_reinstall_keeps_each_captured_previous_method(self):
        self.mod.init()
        first_wrapper = self.component_class.__dict__['_setupPlugins']
        later_calls = []

        def later_wrapper(instance, *args, **kwargs):
            later_calls.append(True)
            return first_wrapper(instance, *args, **kwargs)

        self.component_class._setupPlugins = later_wrapper
        self.mod.fini()
        self.mod.init()

        instance = self.component_class()
        self.assertIn(self.config.MOD_ID, instance._setupPlugins('reinstalled'))
        self.assertEqual(self.setup_calls, ['reinstalled'])
        self.assertEqual(later_calls, [True])
        self.assertEqual(self.native_installs, [self.personal_class])

        self.mod.fini()
        self.assertEqual(instance._setupPlugins('after fini'), {'personal': self.personal_class})
        self.assertEqual(self.setup_calls, ['reinstalled', 'after fini'])
        self.assertEqual(later_calls, [True, True])
        self.assertEqual(self.native_installs, [self.personal_class])

    def test_install_hook_accepts_another_owner_and_inherited_method(self):
        class Base(object):
            def value(self, number):
                return [number]

        class Owner(Base):
            pass

        self.mod._install_hook(Owner, 'value', lambda result: result.append('hook'))
        self.assertEqual(Owner().value(3), [3, 'hook'])
        self.mod._restore_hook(Owner, 'value')
        self.assertNotIn('value', Owner.__dict__)
        self.assertEqual(Owner().value(3), [3])

    def test_repeated_install_does_not_wrap_again_after_another_mod(self):
        self.mod.init()
        wrapper = self.component_class.__dict__['_setupPlugins']

        def later_wrapper(instance, *args, **kwargs):
            return wrapper(instance, *args, **kwargs)

        self.component_class._setupPlugins = later_wrapper
        self.mod.init()
        self.assertIs(self.component_class.__dict__['_setupPlugins'], later_wrapper)
        self.assertIn(self.config.MOD_ID, self.component_class()._setupPlugins('active'))
        self.assertEqual(self.setup_calls, ['active'])
        self.assertEqual(self.native_installs, [self.personal_class])

    def test_setup_extension_failure_preserves_original_result(self):
        logged = []
        setattr(self.mod, '_logger', type('Logger', (object,), {
            'exception': lambda instance, message: logged.append(message),
        })())

        def fail_install(plugin_class):
            raise RuntimeError('native hook failed')

        self.markerplugin.install_native_circle_commands_hook = fail_install
        self.mod.init()
        result = self.component_class()._setupPlugins('active')
        self.assertEqual(result, {'personal': self.personal_class})
        self.assertEqual(self.setup_calls, ['active'])
        self.assertEqual(len(logged), 1)

    def test_native_invoke_wrapper_stops_intercepting_after_restore(self):
        self.load_native_module()

        original_calls = []

        def original_invoke(instance, entry_id, *signature):
            original_calls.append((entry_id, signature))
            return entry_id, signature

        plugin_class = type('PersonalEntriesPlugin', (object,), {
            '_invoke': original_invoke,
        })
        self.native_module.install_native_circle_commands_hook(plugin_class)
        wrapper = plugin_class.__dict__['_invoke']
        self.assertTrue(getattr(wrapper, '_viewrangecustomizer_hook_owner', False))

        def later_wrapper(instance, entry_id, *signature):
            return wrapper(instance, entry_id, *signature)

        plugin_class._invoke = later_wrapper
        self.native_module.restore_native_circle_commands_hooks()
        result = plugin_class()._invoke(17, 'native-command', 42)
        self.assertEqual(result, (17, ('native-command', 42)))
        self.assertEqual(original_calls, [(17, ('native-command', 42))])
        self.assertIs(plugin_class.__dict__['_invoke'], later_wrapper)

    def test_native_circle_errors_log_and_forward_original_once(self):
        settings = self.load_native_module()
        settings.VIEW_RANGE_CIRCLES_AS3_DESCR = type(
            'CircleCommands', (object,), {'AS_REMOVE_ALL_CIRCLES': 'remove-all'})
        self.config.NATIVE_CIRCLE_ACTIONS = {
            'add': ('view_range', 'add'),
            'remove': ('view_range', 'remove'),
        }
        self.config.NATIVE_CIRCLE_INDEX = {'view_range': 0}
        self.config.NATIVE_CIRCLE_SETTING_KEYS = (('show_circle',),)
        self.config.SETTINGS.update({
            'enabled': True, 'replace_wot_circle_markers': True, 'show_circle': True,
        })
        logged = []
        setattr(self.native_module, '_logger', type('Logger', (object,), {
            'exception': lambda instance, message: logged.append(message),
        })())
        original_calls = []

        def original_invoke(instance, entry_id, *signature):
            original_calls.append((entry_id, signature))
            return 'native result'

        def fail(*args):
            raise RuntimeError('replacement failed')

        replacement = type('Replacement', (object,), {
            'remove_replacement_circles': fail,
            'remove_replacement_circle': fail,
            'update_replacement_circle': fail,
        })()
        setattr(self.native_module, 'get_replacement_plugin', lambda parent: replacement)
        visitor = type('Visitor', (object,), {
            'gui': type('Gui', (object,), {'isRandomBattle': lambda self: True})(),
        })()
        plugin_class = type('PersonalEntriesPlugin', (object,), {
            '_invoke': original_invoke, '_parentObj': object(), '_arenaVisitor': visitor,
        })
        self.native_module.install_native_circle_commands_hook(plugin_class)

        for command in ('remove-all', 'remove', 'add'):
            self.assertEqual(plugin_class()._invoke(17, command, 1, 2, 450), 'native result')
        self.assertEqual(original_calls, [
            (17, ('remove-all', 1, 2, 450)),
            (17, ('remove', 1, 2, 450)),
            (17, ('add', 1, 2, 450)),
        ])
        self.assertEqual(len(logged), 3)

    def test_native_circle_success_suppresses_original_and_native_errors_propagate(self):
        settings = self.load_native_module()
        settings.VIEW_RANGE_CIRCLES_AS3_DESCR = type(
            'CircleCommands', (object,), {'AS_REMOVE_ALL_CIRCLES': 'remove-all'})
        self.config.NATIVE_CIRCLE_ACTIONS = {'add': ('view_range', 'add')}
        self.config.NATIVE_CIRCLE_INDEX = {'view_range': 0}
        self.config.NATIVE_CIRCLE_SETTING_KEYS = (('show_circle',),)
        self.config.SETTINGS.update({
            'enabled': True, 'replace_wot_circle_markers': True, 'show_circle': True,
        })
        updates = []
        replacement = type('Replacement', (object,), {
            'update_replacement_circle': lambda self, name, distance: updates.append((name, distance)) or True,
        })()
        setattr(self.native_module, 'get_replacement_plugin', lambda parent: replacement)
        visitor = type('Visitor', (object,), {
            'gui': type('Gui', (object,), {'isRandomBattle': lambda self: True})(),
        })()
        original_calls = []

        def original_invoke(instance, entry_id, *signature):
            original_calls.append((entry_id, signature))
            raise RuntimeError('native failure')

        plugin_class = type('PersonalEntriesPlugin', (object,), {
            '_invoke': original_invoke, '_parentObj': object(), '_arenaVisitor': visitor,
        })
        self.native_module.install_native_circle_commands_hook(plugin_class)
        self.assertIsNone(plugin_class()._invoke(17, 'add', 1, 2, 450))
        self.assertEqual(updates, [('view_range', 450)])
        self.assertEqual(original_calls, [])
        with self.assertRaises(RuntimeError):
            plugin_class()._invoke(17, 'unknown')
        self.assertEqual(original_calls, [(17, ('unknown',))])

    def test_native_fallback_is_removed_when_replacement_later_succeeds(self):
        settings = self.load_native_module()
        settings.VIEW_RANGE_CIRCLES_AS3_DESCR = type(
            'CircleCommands', (object,), {'AS_REMOVE_ALL_CIRCLES': 'remove-all'})
        self.config.NATIVE_CIRCLE_ACTIONS = {
            'add': ('view_range', 'add'),
            'remove': ('view_range', 'remove'),
        }
        self.config.NATIVE_CIRCLE_INDEX = {'view_range': 0}
        self.config.NATIVE_CIRCLE_SETTING_KEYS = (('show_circle',),)
        self.config.SETTINGS.update({
            'enabled': True, 'replace_wot_circle_markers': True, 'show_circle': True,
        })
        setattr(self.native_module, '_is_random_battle', lambda visitor: True)
        setattr(self.native_module, '_logger', type('Logger', (object,), {
            'exception': lambda instance, message: None,
        })())
        attempts = []

        class Replacement(object):
            def update_replacement_circle(self, name, distance):
                attempts.append((name, distance))
                if len(attempts) == 1:
                    raise RuntimeError('draw failed')
                return True

        replacement = Replacement()
        setattr(self.native_module, 'get_replacement_plugin', lambda parent: replacement)
        native_calls = []

        def original(instance, entry_id, *signature):
            native_calls.append((entry_id, signature))
            return 'native'

        plugin_class = type('PersonalEntriesPlugin', (object,), {
            '_invoke': original, '_parentObj': object(), '_arenaVisitor': object(),
        })
        self.native_module.install_native_circle_commands_hook(plugin_class)
        plugin = plugin_class()
        self.assertEqual(plugin._invoke(17, 'add', 1, 2, 450), 'native')
        self.assertIsNone(plugin._invoke(17, 'add', 1, 2, 450))
        self.assertEqual(native_calls, [(17, ('add', 1, 2, 450)), (17, ('remove',))])

    def test_native_circle_mode_switch_removals_and_client_radius(self):
        settings = self.load_native_module()
        settings.VIEW_RANGE_CIRCLES_AS3_DESCR = type(
            'CircleCommands', (object,), {'AS_REMOVE_ALL_CIRCLES': 'remove-all'})
        self.config.NATIVE_CIRCLE_ACTIONS = {
            'add': ('view_range', 'add'),
            'update': ('view_range', 'update'),
            'remove': ('view_range', 'remove'),
        }
        self.config.NATIVE_CIRCLE_INDEX = {'view_range': 0}
        self.config.NATIVE_CIRCLE_SETTING_KEYS = (('show_circle',),)
        self.config.SETTINGS.update({
            'enabled': True, 'replace_wot_circle_markers': True, 'show_circle': True,
        })
        calls = []

        class Replacement(object):
            def update_replacement_circle(self, name, distance):
                calls.append(('draw', name, distance))
                return True

            def remove_replacement_circle(self, name):
                calls.append(('remove', name))

            def remove_replacement_circles(self):
                calls.append(('remove-all',))

        replacement = Replacement()
        setattr(self.native_module, 'get_replacement_plugin', lambda parent: replacement)
        setattr(self.native_module, '_is_random_battle', lambda visitor: visitor)
        plugin = type('PersonalEntriesPlugin', (object,), {
            '_parentObj': object(), '_arenaVisitor': True,
        })()
        handle = self.native_module._handle_native_circle_command
        self.assertTrue(handle(plugin, ('add', 1, 2, 437)))
        self.assertTrue(handle(plugin, ('update', 422)))
        self.assertFalse(handle(plugin, ('remove',)))
        self.assertFalse(handle(plugin, ('remove-all',)))
        self.config.SETTINGS['enabled'] = False
        self.assertFalse(handle(plugin, ('add', 1, 2, 437)))
        self.config.SETTINGS['enabled'] = True
        self.config.SETTINGS['replace_wot_circle_markers'] = False
        self.assertFalse(handle(plugin, ('add', 1, 2, 437)))
        self.config.SETTINGS['replace_wot_circle_markers'] = True
        plugin._arenaVisitor = False
        self.assertFalse(handle(plugin, ('add', 1, 2, 437)))
        self.assertEqual(calls, [
            ('draw', 'view_range', 437), ('draw', 'view_range', 422),
            ('remove', 'view_range'), ('remove-all',),
            ('remove', 'view_range'), ('remove', 'view_range'), ('remove', 'view_range'),
        ])

    def test_remove_all_continues_and_hides_replacement_after_remove_failure(self):
        settings = self.load_native_module()
        settings.VIEW_RANGE_CIRCLES_AS3_DESCR = type(
            'CircleCommands', (object,), {'AS_DEL_DYN_CIRCLE': 'delete'})
        self.config.NATIVE_CIRCLE_INDEX = {'first': 0, 'second': 1}
        self.config.NATIVE_REPLACEMENTS = (
            (1, 'first', None, None), (2, 'second', None, None),
        )
        logged = []
        setattr(self.native_module, '_logger', type('Logger', (object,), {
            'exception': lambda instance, message: logged.append(message),
        })())
        plugin_class = self.native_module.CustomCirclesPlugin
        calls = []

        def invoke(instance, entry_id, command):
            calls.append(('remove', entry_id))
            if entry_id == 17:
                raise RuntimeError('remove failed')

        setattr(plugin_class, '_invoke', invoke)
        setattr(plugin_class, '_setActive',
                lambda instance, entry_id, active: calls.append(('active', entry_id, active)))
        plugin = plugin_class.__new__(plugin_class)
        plugin._CustomCirclesPlugin__nativeEntryIDs = [17, 18]
        plugin._CustomCirclesPlugin__nativeCircleData = [('first',), ('second',)]

        with self.assertRaises(RuntimeError):
            plugin.remove_replacement_circles()
        self.assertEqual(calls, [('remove', 17), ('active', 17, False), ('remove', 18)])
        self.assertEqual(plugin._CustomCirclesPlugin__nativeCircleData, [None, None])
        self.assertEqual(len(logged), 1)

    def test_failed_circle_draw_is_retried_even_if_style_reverts(self):
        settings = self.load_native_module()
        settings.VIEW_RANGE_CIRCLES_AS3_DESCR = type('CircleCommands', (object,), {
            'AS_DEL_DYN_CIRCLE': 'delete',
            'AS_ADD_DYN_CIRCLE': 'add',
        })
        self.config.NATIVE_CIRCLE_INDEX = {'view_range': 0}
        self.config.NATIVE_CIRCLE_SETTING_KEYS = (('show_circle', 'color', 'opacity'),)
        self.config.SETTINGS.update({
            'enabled': True, 'replace_wot_circle_markers': True,
            'show_circle': True, 'color': 'FFFFFF', 'opacity': 100,
        })
        setattr(self.native_module, '_is_spectator_mode', lambda plugin: False)
        setattr(self.native_module, '_is_random_battle', lambda visitor: True)
        plugin_class = self.native_module.CustomCirclesPlugin
        setattr(plugin_class, '_CustomCirclesPlugin__getVehicleInfo', lambda plugin: object())
        setattr(plugin_class, '_CustomCirclesPlugin__isObserver', lambda plugin, info: False)
        setattr(plugin_class, '_CustomCirclesPlugin__isAlive', lambda plugin, info: True)
        setattr(plugin_class, '_CustomCirclesPlugin__addNativeMarker', lambda plugin, index: None)
        setattr(plugin_class, '_setActive', lambda plugin, entry_id, active: None)

        calls = []
        fail_next = [True]

        def invoke(plugin, entry_id, command, *args):
            calls.append((entry_id, command, args))
            if command == 'add' and fail_next[0]:
                fail_next[0] = False
                raise RuntimeError('draw failed')

        setattr(plugin_class, '_invoke', invoke)
        old_data = (0, 100, 450)
        for previous_data, retry_color in ((None, 'FFFFFF'), (old_data, '000000')):
            plugin = plugin_class.__new__(plugin_class)
            plugin._arenaVisitor = object()
            plugin._CustomCirclesPlugin__nativeEntryIDs = [17]
            plugin._CustomCirclesPlugin__nativeCircleData = [previous_data]
            self.config.SETTINGS['color'] = 'FFFFFF'
            del calls[:]
            fail_next[0] = True

            with self.assertRaises(RuntimeError):
                plugin.update_replacement_circle('view_range', 450)
            self.assertIsNone(plugin._CustomCirclesPlugin__nativeCircleData[0])

            self.config.SETTINGS['color'] = retry_color
            self.assertTrue(plugin.update_replacement_circle('view_range', 450))
            self.assertEqual(plugin._CustomCirclesPlugin__nativeCircleData[0],
                             (int(retry_color, 16), 100, 450))
            self.assertEqual([call[1] for call in calls], ['delete', 'add', 'delete', 'add'])
            self.assertTrue(plugin.update_replacement_circle('view_range', 450))
            self.assertEqual(len(calls), 4)

    def test_failed_circle_initialization_is_retried_before_drawing(self):
        settings = self.load_native_module()
        settings.VIEW_RANGE_CIRCLES_AS3_DESCR = type('CircleCommands', (object,), {
            'AS_INIT_ARENA_SIZE': 'init',
            'AS_DEL_DYN_CIRCLE': 'delete',
            'AS_ADD_DYN_CIRCLE': 'add',
        })
        settings.TRANSFORM_FLAG = type('Flags', (object,), {'DEFAULT': 0, 'NO_ROTATION': 1})
        settings.ENTRY_SYMBOL_NAME = type('Symbols', (object,), {'VIEW_RANGE_CIRCLES': 'circles'})
        settings.CONTAINER_NAME = type('Containers', (object,), {'PERSONAL': 'personal'})
        self.config.NATIVE_CIRCLE_INDEX = {'view_range': 0}
        self.config.NATIVE_CIRCLE_SETTING_KEYS = (('show_circle', 'color', 'opacity'),)
        self.config.SETTINGS.update({
            'enabled': True, 'replace_wot_circle_markers': True,
            'show_circle': True, 'color': 'FFFFFF', 'opacity': 100,
        })
        setattr(self.native_module, '_is_spectator_mode', lambda plugin: False)
        setattr(self.native_module, '_is_random_battle', lambda visitor: True)
        setattr(self.native_module.matrix_factory, 'makeAttachedVehicleMatrix', lambda: object())
        plugin_class = self.native_module.CustomCirclesPlugin
        setattr(plugin_class, '_CustomCirclesPlugin__getVehicleInfo', lambda plugin: object())
        setattr(plugin_class, '_CustomCirclesPlugin__isObserver', lambda plugin, info: False)
        setattr(plugin_class, '_CustomCirclesPlugin__isAlive', lambda plugin, info: True)
        setattr(plugin_class, '_CustomCirclesPlugin__getBoundingBox',
                lambda plugin: ((0, 0), (100, 100)))
        setattr(plugin_class, '_setActive', lambda plugin, entry_id, active: None)
        calls = []

        def add_entry(plugin, *args, **kwargs):
            calls.append('create')
            return 17

        def invoke(plugin, entry_id, command, *args):
            calls.append(command)
            if command == 'init' and calls.count('init') == 1:
                raise RuntimeError('initialization failed')

        setattr(plugin_class, '_addEntry', add_entry)
        setattr(plugin_class, '_invoke', invoke)
        plugin = plugin_class.__new__(plugin_class)
        plugin._arenaVisitor = object()
        plugin._CustomCirclesPlugin__nativeEntryIDs = [None]
        plugin._CustomCirclesPlugin__nativeInitialized = [False]
        plugin._CustomCirclesPlugin__nativeCircleData = [None]

        with self.assertRaises(RuntimeError):
            plugin.update_replacement_circle('view_range', 450)
        self.assertFalse(plugin._CustomCirclesPlugin__nativeInitialized[0])
        self.assertTrue(plugin.update_replacement_circle('view_range', 450))
        self.assertEqual(calls, ['create', 'init', 'init', 'delete', 'add'])
        self.assertTrue(plugin._CustomCirclesPlugin__nativeInitialized[0])

    def test_plugin_stop_continues_after_unsubscribe_failure_and_can_retry(self):
        self.load_native_module()
        plugin_class = self.native_module.CustomCirclesPlugin
        base_stops = []
        setattr(plugin_class.__bases__[0], 'stop', lambda instance: base_stops.append(instance))
        logged = []
        setattr(self.native_module, '_logger', type('Logger', (object,), {
            'exception': lambda instance, message: logged.append(message),
        })())

        class RetryEvent(Event):
            def __init__(self, fail):
                super(RetryEvent, self).__init__()
                self.fail = fail
                self.attempts = 0

            def __isub__(self, handler):
                self.attempts += 1
                if self.fail:
                    self.fail = False
                    raise RuntimeError('unsubscribe failed')
                if handler in self.handlers:
                    self.handlers.remove(handler)
                return self

        for fail_postmortem, fail_respawn in ((True, False), (False, True), (True, True)):
            plugin = plugin_class.__new__(plugin_class)
            plugin._CustomCirclesPlugin__entryIDs = [1]
            plugin._CustomCirclesPlugin__nativeEntryIDs = [2]
            plugin._CustomCirclesPlugin__nativeInitialized = [True]
            plugin._CustomCirclesPlugin__nativeCircleData = [('data',)]
            controller = type('VehicleState', (object,), {})()
            controller.onPostMortemSwitched = RetryEvent(fail_postmortem)
            controller.onRespawnBaseMoving = RetryEvent(fail_respawn)
            controller.onPostMortemSwitched += plugin._CustomCirclesPlugin__onPostMortemSwitched
            controller.onRespawnBaseMoving += plugin._CustomCirclesPlugin__onRespawnBaseMoving
            plugin._CustomCirclesPlugin__vehicleStateCtrl = controller
            self.config.ACTIVE_PLUGINS.append(plugin)

            plugin.stop()
            self.assertEqual(controller.onPostMortemSwitched.attempts, 1)
            self.assertEqual(controller.onRespawnBaseMoving.attempts, 1)
            self.assertNotIn(plugin, self.config.ACTIVE_PLUGINS)
            self.assertEqual(plugin._CustomCirclesPlugin__entryIDs, [None])
            self.assertEqual(plugin._CustomCirclesPlugin__nativeEntryIDs, [None])
            self.assertEqual(plugin._CustomCirclesPlugin__nativeCircleData, [None])
            self.assertIs(plugin._CustomCirclesPlugin__vehicleStateCtrl, controller)
            self.assertIs(base_stops[-1], plugin)

            plugin.stop()
            self.assertEqual(controller.onPostMortemSwitched.handlers, [])
            self.assertEqual(controller.onRespawnBaseMoving.handlers, [])
            self.assertIsNone(plugin._CustomCirclesPlugin__vehicleStateCtrl)
        self.assertEqual(len(base_stops), 6)
        self.assertEqual(len(logged), 4)

    def test_partial_settings_registration_is_rolled_back(self):
        def register_then_fail(linkage, template, callback):
            api.onSettingsChanged += callback
            raise RuntimeError('registration failed')

        api = self.add_settings_api(register_then_fail)
        self.mod.init()
        self.assertEqual(api.onSettingsChanged.handlers, [])
        self.assertIsNone(self.mod._settings_api)
        self.assertIn(self.config.MOD_ID, self.component_class()._setupPlugins('active'))

    def test_settings_failure_after_loading_restores_previous_values(self):
        self.config.SETTINGS.update({'enabled': True})
        def register(linkage, template, callback):
            api.onSettingsChanged += callback
            return {'enabled': False}

        api = self.add_settings_api(register)
        api.setModDefaults = lambda linkage, defaults: None
        def fail_refresh():
            raise RuntimeError('refresh failed')
        self.markerplugin.refresh_native_circles = fail_refresh
        self.mod.init()
        self.assertEqual(self.config.SETTINGS, {'enabled': True})
        self.assertEqual(api.onSettingsChanged.handlers, [])
        self.assertIn(self.config.MOD_ID, self.component_class()._setupPlugins('active'))

    def test_setup_failure_still_rolls_back_settings(self):
        def register(linkage, template, callback):
            api.onSettingsChanged += callback
            return {}

        api = self.add_settings_api(register)
        api.setModDefaults = lambda linkage, defaults: None
        del self.component_class._setupPlugins
        with self.assertRaises(AttributeError):
            self.mod.init()
        self.assertEqual(api.onSettingsChanged.handlers, [])
        self.assertEqual(api.onResetMod.handlers, [])

    def test_invalid_settings_registration_is_rolled_back(self):
        def register_then_return_invalid(linkage, template, callback):
            api.onSettingsChanged += callback
            return None

        api = self.add_settings_api(register_then_return_invalid)
        self.mod.init()
        self.assertEqual(api.onSettingsChanged.handlers, [])
        self.assertIsNone(self.mod._settings_api)


if __name__ == '__main__':
    unittest.main()
