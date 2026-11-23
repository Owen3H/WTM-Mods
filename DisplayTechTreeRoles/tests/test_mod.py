from __future__ import absolute_import

import imp
import json
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
        return {'type': 'Slider', 'varName': varName, 'value': value,
                'minimum': minimum, 'maximum': maximum}

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
        self.add_module('gui.mods', package=True)
        mod_package = self.add_module('gui.mods.displaytechtreeroles', package=True)
        mod_package.__path__ = [os.path.join(ROOT, 'src', 'displaytechtreeroles')]
        name = 'gui.mods.displaytechtreeroles.config'
        self.previous_modules[name] = sys.modules.pop(name, None)
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
        layout = type('Injection', (object,), {'Injection': staticmethod(lambda: 123)})()
        gen.R.mods = type('Mods', (object,), {
            'wtm': type('Vendor', (object,), {
                'DisplayTechTreeRoles': type('Feature', (object,), {'views': layout})()
            })()
        })()
        impl.backport = type('Backport', (object,), {'image': staticmethod(lambda resource: resource)})()
        path.normalizeGfImagePath = lambda resource: 'img://%s/%s' % resource

        self.add_module('frameworks', package=True)
        wulf = self.add_module('frameworks.wulf')
        self.add_module('gui.impl.pub', package=True)
        pub = self.add_module('gui.impl.pub.view_component')
        injection = self.add_module('openwg_gameface')

        class ViewModel(object):
            def __init__(self, properties=0, commands=0):
                self.fields = []
                self._initialize()
            def _initialize(self):
                pass
            def _addViewModelProperty(self, name, value):
                self.fields.append((name, value))
            def _addStringProperty(self, name, value):
                self.fields.append((name, value))
            def _setString(self, index, value):
                self.fields[index] = (self.fields[index][0], value)
            def transaction(self):
                return self
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False

        class ViewComponent(object):
            def __init__(self, layoutID, model):
                self.model = model()
                self.destroyed = False
            def getViewModel(self):
                return self.model
            def destroy(self):
                self.destroyed = True

        wulf.ViewModel = ViewModel
        pub.ViewComponent = ViewComponent
        injection.gf_mod_inject = lambda model, name, **kwargs: model._addViewModelProperty(
            'ModInjectModel', (name, kwargs))

        class Dumper(object):
            def _getTechTreeNodes(self, node, nodeRows):
                return {'original': nodeRows}

        class TechTreeView(object):
            def __init__(self):
                self.redraws = 0
                self.children = {}
                self.nodes = {}
                self.viewModel = self

            def _onLoading(self):
                return 'loaded'

            def _onLoaded(self):
                return 'ready'

            def __fullUpdateOfViewModel(self):
                return 'updated'

            def getTechTreeNodes(self):
                return self.nodes

            def getChildView(self, layout_id):
                return self.children.get(layout_id)

            def setChildView(self, layout_id, child):
                if child is None:
                    self.children.pop(layout_id, None)
                else:
                    self.children[layout_id] = child

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
                          'roleIconSize': 24, 'roleIconMargin': -18, 'roleIconPosition': 'bottom'})
        self.assertEqual(dumper._getTechTreeNodes(VehicleNode('role_SPG'), {}),
                         {'original': {}, 'roleIcon': 'img://32x32/role_SPG',
                          'roleIconSize': 24, 'roleIconMargin': -18, 'roleIconPosition': 'bottom'})
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

    def test_inherited_hooks_restore_inheritance(self):
        module = sys.modules['gui.impl.lobby.tech_tree.tech_tree_view']
        class InheritedDumper(self.dumper):
            pass
        class InheritedView(self.view_class):
            pass
        module._NationTreeViewDumper = InheritedDumper
        module.TechTreeView = InheritedView
        self.mod.init()
        self.assertIn('roleIcon', InheritedDumper()._getTechTreeNodes(VehicleNode('role_HT_break'), {}))
        view = InheritedView()
        view._onLoading()
        self.api.onSettingsChanged.fire(self.mod.config.MOD_ID, {'icon_size': 30})
        self.assertEqual(view.redraws, 1)
        self.mod.fini()
        self.assertNotIn('_getTechTreeNodes', InheritedDumper.__dict__)
        self.assertNotIn('_onLoading', InheritedView.__dict__)
        self.assertNotIn('_finalize', InheritedView.__dict__)

    def test_failed_initialization_restores_hooks(self):
        original_nodes = self.dumper.__dict__['_getTechTreeNodes']
        original_loading = self.view_class.__dict__['_onLoading']
        del self.view_class._finalize
        with self.assertRaises((KeyError, AttributeError)):
            self.mod.init()
        self.assertIs(self.dumper.__dict__['_getTechTreeNodes'], original_nodes)
        self.assertIs(self.view_class.__dict__['_onLoading'], original_loading)

    def test_failed_settings_registration_unsubscribes_and_restores_hooks(self):
        original_nodes = self.dumper.__dict__['_getTechTreeNodes']
        def fail_defaults(linkage, defaults):
            raise RuntimeError('defaults failed')
        self.api.setModDefaults = fail_defaults
        with self.assertRaises(RuntimeError):
            self.mod.init()
        self.assertEqual(self.api.onSettingsChanged.handlers, [])
        self.assertEqual(self.api.onResetMod.handlers, [])
        self.assertIs(self.dumper.__dict__['_getTechTreeNodes'], original_nodes)

    def test_reset_callback_removed_if_settings_unsubscribe_fails(self):
        self.mod.init()
        class FailingEvent(Event):
            def __isub__(self, handler):
                raise RuntimeError('unsubscribe failed')
        self.api.onSettingsChanged = FailingEvent()
        with self.assertRaises(RuntimeError):
            self.mod.fini()
        self.assertEqual(self.api.onResetMod.handlers, [])

    def test_later_hooks_do_not_keep_mod_active_after_fini(self):
        self.mod.init()
        previous_nodes = self.dumper._getTechTreeNodes
        previous_loading = self.view_class._onLoading
        def later_nodes(instance, node, rows):
            return previous_nodes(instance, node, rows)
        def later_loading(instance):
            return previous_loading(instance)
        self.dumper._getTechTreeNodes = later_nodes
        self.view_class._onLoading = later_loading
        self.mod.fini()
        self.assertEqual(self.dumper()._getTechTreeNodes(VehicleNode('role_HT_break'), {}), {'original': {}})
        self.view_class()._onLoading()
        self.assertEqual(self.mod._active_views, [])
        self.mod.init()
        view = self.view_class()
        view._onLoading()
        self.assertEqual(self.mod._active_views, [view])

    def test_saved_settings_live_changes_reset_and_cleanup(self):
        self.api.saved = {'enabled': True, 'icon_size': 36, 'margin': 4, 'position': 1}
        original_loading = self.view_class.__dict__['_onLoading']
        original_finalize = self.view_class.__dict__['_finalize']
        self.mod.init()
        self.assertEqual(self.api.saved, self.mod.config.SETTINGS)
        self.assertEqual(self.api.defaults, self.mod.config.DEFAULT_SETTINGS)
        self.assertEqual(self.api.template['column1'][2]['options'],
                         [{'label': 'Top'}, {'label': 'Bottom'}])
        view = self.view_class()
        self.assertEqual(view._onLoading(), 'loaded')
        data = self.dumper()._getTechTreeNodes(VehicleNode('role_HT_break'), {})
        self.assertEqual((data['roleIconSize'], data['roleIconMargin'], data['roleIconPosition']),
                         (36, 4, 'bottom'))

        self.api.onSettingsChanged.fire(self.mod.config.MOD_ID, {'icon_size': 42, 'margin': -3, 'position': 0})
        self.assertEqual(view.redraws, 1)
        data = self.dumper()._getTechTreeNodes(VehicleNode('role_HT_break'), {})
        self.assertEqual((data['roleIconSize'], data['roleIconMargin'], data['roleIconPosition']),
                         (42, -3, 'top'))
        self.api.onSettingsChanged.fire(self.mod.config.MOD_ID, {'enabled': False})
        self.assertEqual(self.dumper()._getTechTreeNodes(VehicleNode('role_HT_break'), {}),
                         {'original': {}})
        self.api.onResetMod.fire(self.mod.config.MOD_ID, dict(self.mod.config.DEFAULT_SETTINGS))
        self.assertEqual(self.mod.config.SETTINGS, self.mod.config.DEFAULT_SETTINGS)
        self.assertEqual(view.redraws, 3)
        self.assertEqual(view._finalize(), 'finalized')
        self.api.onSettingsChanged.fire(self.mod.config.MOD_ID, {'icon_size': 30})
        self.assertEqual(view.redraws, 3)
        self.mod.fini()
        self.assertIs(self.view_class.__dict__['_onLoading'], original_loading)
        self.assertIs(self.view_class.__dict__['_finalize'], original_finalize)
        self.assertEqual(self.api.onSettingsChanged.handlers, [])
        self.assertEqual(self.api.onResetMod.handlers, [])

    def test_invalid_settings_are_ignored_and_logged(self):
        self.mod.init()
        self.api.onSettingsChanged.fire(self.mod.config.MOD_ID, {
            'icon_size': 100, 'margin': float('nan'), 'position': 2, 'enabled': 'yes',
        })
        self.assertEqual(self.mod.config.SETTINGS, self.mod.config.DEFAULT_SETTINGS)

    def test_margin_range_and_saved_values(self):
        config = self.mod.config
        slider = config.settings_template(Templates)['column1'][1]
        self.assertEqual((slider['minimum'], slider['maximum']), (-24, 8))
        for value, expected in ((-32, -24), (-27, -24), (-24, -24), (0, 0), (8, 8), (16, 8), (32, 8)):
            self.assertEqual(config.normalize_settings({'margin': value}, config.DEFAULT_SETTINGS)['margin'],
                             expected)
        self.api.saved = {'margin': -32}
        self.mod.init()
        self.assertEqual(config.SETTINGS['margin'], -24)
        self.assertEqual(self.api.saved['margin'], -24)

    def test_missing_menu_keeps_defaults_and_hooks_work(self):
        del sys.modules['gui.aslainMenu']
        self.mod.init()
        data = self.dumper()._getTechTreeNodes(VehicleNode('role_HT_break'), {})
        self.assertEqual(data['roleIconSize'], 24)
        self.assertEqual(data['roleIconMargin'], -18)
        self.assertEqual(data['roleIconPosition'], 'bottom')
        self.assertFalse(self.mod._settings_registered)

    def test_injection_config_matches_packaged_resources(self):
        config = self.mod.config
        path = os.path.join(ROOT, 'src', 'res', 'gui', 'gen_resources', 'wtm_display_tech_tree_roles.json')
        with open(path) as resource_file:
            declaration = json.load(resource_file)[0]
        self.assertEqual(declaration['id'], 'R.mods.wtm.%s.views.Injection' % config.MOD_NAME)
        self.assertEqual(declaration['parameters']['entrance'], config.FEATURE_NAME)
        self.assertEqual(declaration['path'],
                         'coui://gui/gameface/mods/wtm/%s/injection.html' % config.MOD_NAME)
        script_path = os.path.join(ROOT, 'src', 'res', *config.SCRIPT_URL[len('coui://'):].split('/'))
        with open(script_path) as script_file:
            self.assertIn("const feature = '%s';" % config.FEATURE_NAME, script_file.read())

    def test_injection_attaches_updates_and_detaches(self):
        self.mod.init()
        view = self.view_class()
        view.nodes[42] = json.dumps(self.dumper()._getTechTreeNodes(VehicleNode('role_HT_break'), {}))
        view._onLoading()
        self.assertEqual(view._onLoaded(), 'ready')
        child = view.children[123]
        model = child.getViewModel()
        self.assertEqual(json.loads(model.fields[1][1])['42']['roleIcon'], 'img://24x24/role_HT_break')
        view._onLoaded()
        self.assertIs(view.children[123], child)
        view.nodes.clear()
        self.assertEqual(view._TechTreeView__fullUpdateOfViewModel(), 'updated')
        self.assertEqual(json.loads(model.fields[1][1]), {})
        self.assertEqual(view._finalize(), 'finalized')
        self.assertEqual(model.fields[1][1], 'null')
        self.assertEqual(view.children, {})

    def test_fini_detaches_open_view_without_replacing_other_children(self):
        self.mod.init()
        view = self.view_class()
        other = object()
        view.children[456] = other
        view._onLoading()
        view._onLoaded()
        child = view.children[123]
        self.mod.fini()
        self.assertEqual(child.model.fields[1][1], 'null')
        self.assertEqual(view.children, {456: other})

    def test_fini_does_not_detach_replaced_child(self):
        self.mod.init()
        view = self.view_class()
        view._onLoaded()
        replacement = object()
        view.children[123] = replacement
        self.mod.fini()
        self.assertIs(view.children[123], replacement)


if __name__ == '__main__':
    unittest.main()
