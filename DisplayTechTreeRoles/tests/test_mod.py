from __future__ import absolute_import

import imp
import os
import sys
import types
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class IconResource(object):
    def __init__(self, size):
        self.size = size

    def dyn(self, label):
        return lambda: (self.size, label)


class VehicleNode(object):
    def __init__(self, label):
        self.item = type('Vehicle', (object,), {'roleLabel': label})()

    def getItem(self):
        return self.item


class Event(object):
    def __init__(self):
        self.handlers = []

    def __iadd__(self, handler):
        self.handlers.append(handler)
        return self

    def __isub__(self, handler):
        self.handlers.remove(handler)
        return self

    def fire(self, *args):
        for handler in list(self.handlers):
            handler(*args)


class Templates(object):
    @staticmethod
    def createSlider(text, varName, value, minimum, maximum, step, **kwargs):
        return {'type': 'Slider', 'varName': varName, 'value': value}

    @staticmethod
    def createDropdown(text, varName, options, value):
        return {'type': 'Dropdown', 'varName': varName, 'value': value,
                'options': [{'label': option} for option in options]}


class SettingsAPI(object):
    def __init__(self, saved=None):
        self.saved = saved
        self.onSettingsChanged = Event()
        self.onResetMod = Event()
        self.defaults = None

    def getModSettings(self, linkage, template):
        return self.saved

    def setModTemplate(self, linkage, template, callback):
        self.template = template
        self.onSettingsChanged += callback
        result = {'enabled': template['enabled']}
        result.update((control['varName'], control['value']) for control in template['column1'])
        return result

    def updateModSettings(self, linkage, settings):
        self.saved = dict(settings)

    def setModDefaults(self, linkage, defaults):
        self.defaults = defaults


class HookTests(unittest.TestCase):
    def setUp(self):
        self.previous_modules = {}
        self.add_module('gui', package=True)
        impl = self.add_module('gui.impl', package=True)
        gen = self.add_module('gui.impl.gen')
        self.add_module('gui.impl.utils', package=True)
        path = self.add_module('gui.impl.utils.path')
        self.add_module('gui.impl.lobby', package=True)
        self.add_module('gui.impl.lobby.tech_tree', package=True)
        view = self.add_module('gui.impl.lobby.tech_tree.tech_tree_view')

        roles = type('Roles', (object,), {
            'c_24x24': IconResource('24x24'),
            'c_32x32': IconResource('32x32'),
        })()
        icons = type('Icons', (object,), {'roleExp': type('RoleExp', (object,), {'roles': roles})()})()
        maps = type('Maps', (object,), {'icons': icons})()
        gui = type('Gui', (object,), {'maps': maps})()
        gen.R = type('Resources', (object,), {'images': type('Images', (object,), {'gui': gui})()})()
        impl.backport = type('Backport', (object,), {'image': staticmethod(lambda resource: resource)})()
        path.normalizeGfImagePath = lambda resource: 'img://%s/%s' % resource

        class Dumper(object):
            def _getTechTreeNodes(self, node, nodeRows):
                return {'original': nodeRows}

        class TechTreeView(object):
            def __init__(self):
                self.redraws = 0

            def _onLoading(self):
                return 'loaded'

            def _finalize(self):
                return 'finalized'

            def redraw(self):
                self.redraws += 1

        view._NationTreeViewDumper = Dumper
        view.TechTreeView = TechTreeView
        self.dumper = Dumper
        self.view_class = TechTreeView
        menu = self.add_module('gui.aslainMenu')
        self.api = SettingsAPI()
        menu.g_modsSettingsApi = self.api
        menu.templates = Templates
        self.mod = imp.load_source('test_displaytechtreeroles',
                                   os.path.join(ROOT, 'src', 'mod_displaytechtreeroles.py'))

    def add_module(self, name, package=False):
        self.previous_modules[name] = sys.modules.get(name)
        module = types.ModuleType(name)
        if package:
            module.__path__ = []
        sys.modules[name] = module
        return module

    def tearDown(self):
        self.mod.fini()
        for name, previous in self.previous_modules.items():
            if previous is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = previous
        sys.modules.pop('test_displaytechtreeroles', None)

    def test_role_icons_and_exact_restoration(self):
        original = self.dumper.__dict__['_getTechTreeNodes']
        self.mod.init()
        self.mod.init()
        dumper = self.dumper()
        self.assertEqual(dumper._getTechTreeNodes(VehicleNode('role_HT_break'), {}),
                         {'original': {}, 'roleIcon': 'img://24x24/role_HT_break',
                          'roleIconSize': 25, 'roleIconMargin': -20, 'roleIconPosition': 'bottom'})
        self.assertEqual(dumper._getTechTreeNodes(VehicleNode('role_SPG'), {}),
                         {'original': {}, 'roleIcon': 'img://32x32/role_SPG',
                          'roleIconSize': 25, 'roleIconMargin': -20, 'roleIconPosition': 'bottom'})
        self.assertEqual(dumper._getTechTreeNodes(VehicleNode('NotDefined'), {}),
                         {'original': {}})
        self.mod.fini()
        self.assertIs(self.dumper.__dict__['_getTechTreeNodes'], original)

    def test_fini_does_not_replace_a_later_hook(self):
        self.mod.init()
        later_hook = lambda self, node, nodeRows: {}
        self.dumper._getTechTreeNodes = later_hook
        self.mod.fini()
        self.assertIs(self.dumper.__dict__['_getTechTreeNodes'], later_hook)

    def test_saved_settings_live_changes_reset_and_cleanup(self):
        self.api.saved = {'enabled': True, 'icon_size': 36, 'margin': 4, 'position': 1}
        original_loading = self.view_class.__dict__['_onLoading']
        original_finalize = self.view_class.__dict__['_finalize']
        self.mod.init()
        self.assertEqual(self.api.saved, self.mod.SETTINGS)
        self.assertEqual(self.api.defaults, self.mod.DEFAULT_SETTINGS)
        self.assertEqual(self.api.template['column1'][2]['options'],
                         [{'label': 'Top'}, {'label': 'Bottom'}])
        view = self.view_class()
        self.assertEqual(view._onLoading(), 'loaded')
        data = self.dumper()._getTechTreeNodes(VehicleNode('role_HT_break'), {})
        self.assertEqual((data['roleIconSize'], data['roleIconMargin'], data['roleIconPosition']),
                         (36, 4, 'bottom'))

        self.api.onSettingsChanged.fire(self.mod.MOD_ID, {'icon_size': 42, 'margin': -3, 'position': 0})
        self.assertEqual(view.redraws, 1)
        data = self.dumper()._getTechTreeNodes(VehicleNode('role_HT_break'), {})
        self.assertEqual((data['roleIconSize'], data['roleIconMargin'], data['roleIconPosition']),
                         (42, -3, 'top'))
        self.api.onSettingsChanged.fire(self.mod.MOD_ID, {'enabled': False})
        self.assertEqual(self.dumper()._getTechTreeNodes(VehicleNode('role_HT_break'), {}),
                         {'original': {}})
        self.api.onResetMod.fire(self.mod.MOD_ID, dict(self.mod.DEFAULT_SETTINGS))
        self.assertEqual(self.mod.SETTINGS, self.mod.DEFAULT_SETTINGS)
        self.assertEqual(view.redraws, 3)
        self.assertEqual(view._finalize(), 'finalized')
        self.api.onSettingsChanged.fire(self.mod.MOD_ID, {'icon_size': 30})
        self.assertEqual(view.redraws, 3)
        self.mod.fini()
        self.assertIs(self.view_class.__dict__['_onLoading'], original_loading)
        self.assertIs(self.view_class.__dict__['_finalize'], original_finalize)
        self.assertEqual(self.api.onSettingsChanged.handlers, [])
        self.assertEqual(self.api.onResetMod.handlers, [])

    def test_invalid_settings_are_ignored_and_logged(self):
        self.mod.init()
        self.api.onSettingsChanged.fire(self.mod.MOD_ID, {
            'icon_size': 100, 'margin': float('nan'), 'position': 2, 'enabled': 'yes',
        })
        self.assertEqual(self.mod.SETTINGS, self.mod.DEFAULT_SETTINGS)

    def test_missing_menu_keeps_defaults_and_hooks_work(self):
        del sys.modules['gui.aslainMenu']
        self.mod.init()
        data = self.dumper()._getTechTreeNodes(VehicleNode('role_HT_break'), {})
        self.assertEqual(data['roleIconSize'], 25)
        self.assertEqual(data['roleIconMargin'], -20)
        self.assertEqual(data['roleIconPosition'], 'bottom')
        self.assertFalse(self.mod._settings_registered)


if __name__ == '__main__':
    unittest.main()
