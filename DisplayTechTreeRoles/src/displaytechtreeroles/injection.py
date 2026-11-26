"""Add role icons to the game's existing tech tree.

A small extra view supplies roles.js and each vehicle's icon data (image, size, margin, and position). 
The script uses that data to draw the icons. This module also updates and cleans up the extra view.
"""

import json
import logging

from gui.mods.displaytechtreeroles import config  # pyright: ignore[reportMissingImports]

_logger = logging.getLogger(__name__)
_injected_views = {}

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


def sync_role_model(view):
    """Send the latest role icon data to the mod's extra view, if it has one."""
    state = _injected_views.get(view)
    if state is not None:
        model = state[1].getViewModel()
        with model.transaction():
            model.setPayload(_role_payload(view))


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


def attach(view):
    """Attach the mod's extra view to the given tech tree view, if it is not already attached."""
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
        try:
            if view.getChildView(layout_id) is child:
                view.setChildView(layout_id, None)
        except Exception:
            _logger.exception(config.TAG + 'Could not roll back Gameface injection')
        try:
            child.destroy()
        except Exception:
            _logger.exception(config.TAG + 'Could not destroy failed Gameface injection')
        raise
    _injected_views[view] = (layout_id, child)


def _detach_injection(view):
    """Remove the mod's extra view if the mod stops before the tech tree closes.

    Ask the icon display to clean up, remove the extra view, and clean it up if
    the game has not already done so. If it is missing, another view is in its
    place, or the tree is unavailable, log what happened and leave it alone.
    Do nothing if the mod has no record of an extra view for this tree.
    """
    state = _injected_views.pop(view, None)
    if state is not None:
        layout_id, child = state
        attached_child = view.getChildView(layout_id)
        if attached_child is not child:
            if attached_child is not None:
                _logger.warning(config.TAG + 'Gameface injection slot contains a different child')
            elif view.proxy is None:
                _logger.warning(config.TAG + 'Gameface injection parent view is unavailable')
            else:
                _logger.warning(config.TAG + 'Gameface injection slot has no child')
            return
        try:
            model = child.getViewModel()
            with model.transaction():
                model.setPayload('null')
        finally:
            view.setChildView(layout_id, None)
            from frameworks.wulf import ViewStatus
            if child.viewStatus not in (ViewStatus.DESTROYING, ViewStatus.DESTROYED):
                child.destroy()


def forget(view):
    """Forget the extra view when the game closes its tech tree."""
    _injected_views.pop(view, None)


def cleanup():
    """When the mod stops or fails to start, try to remove its extra views."""
    for view in list(_injected_views):
        try:
            _detach_injection(view)
        except Exception:
            _logger.exception(config.TAG + 'Could not detach Gameface injection')
