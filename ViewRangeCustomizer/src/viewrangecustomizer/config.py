from constants import AOI  # pyright: ignore[reportMissingImports]
from gui.Scaleform.daapi.view.battle.shared.minimap import settings

try:
    from gui.aslainMenu import templates  # pyright: ignore[reportMissingImports]
except ImportError:
    templates = None

try:
    _NUMBER_TYPES = (int, long, float) # type: ignore
except NameError:
    _NUMBER_TYPES = (int, float)

try:
    _STRING_TYPES = (basestring,) # type: ignore
except NameError:
    _STRING_TYPES = (str,)

MOD_NAME = 'ViewRangeCustomizer'
TAG = '[' + MOD_NAME + '] '
MOD_ID = 'wtm.view_range_customizer'
MOD_AUTHOR = None
MOD_VERSION = None

# Opacity values are stored as percentages (0-100) in the settings,
# but the color values are stored as hex strings (RRGGBB) without alpha.
# The alpha value is combined with the color to create a hex string (RRGGBBAA) for use in the AS3 code.
# 
# The opacity is calculated as follows: int(round(float(opacity) * 255.0 / 100.0))
# Eg: 50% would become 128/255, and 100% would become 255/255 in the colour picker.
DEFAULT_SETTINGS = {
    'enabled': True,
    'show_primary_circle': True, # primary circle
    'distance_meters_1': 400,
    'color_1': 'FF0080', # pink
    'opacity_1': 70, # 30% less opaque than native WoT circle
    'show_secondary_circle': False, # secondary circle
    'distance_meters_2': 300,
    'color_2': '8000FF', # purple
    'opacity_2': 70, # 30% less opaque than native WoT circle
    'show_alternative_circle': False, # alternative circle
    'distance_meters_3': 100,
    'color_3': '0080FF', # blue
    'opacity_3': 70, # 30% less opaque than native WoT circle
    'replace_wot_circle_markers': False,
    'show_draw_range_marker': True,
    'draw_range_color': '%06X' % settings.CIRCLE_STYLE.COLOR.DRAW_RANGE, # yellow
    'draw_range_opacity': 100,
    'show_max_view_range_marker': True,
    'max_view_range_color': '%06X' % settings.CIRCLE_STYLE.COLOR.MAX_VIEW_RANGE, # white
    'max_view_range_opacity': 100,
    'show_view_range_marker': True,
    'view_range_color': '%06X' % settings.CIRCLE_STYLE.COLOR.VIEW_RANGE, # green
    'view_range_opacity': 100,
    'show_min_spotting_range_marker': True,
    'min_spotting_range_color': '%06X' % settings.CIRCLE_STYLE.COLOR.MIN_SPOTTING_RANGE, # aqua
    'min_spotting_range_opacity': 100,
}
SETTINGS = dict(DEFAULT_SETTINGS)
ACTIVE_PLUGINS = []

NATIVE_REPLACEMENTS = (
    (settings.CIRCLE_TYPE.DRAW_RANGE, 'draw_range',
     '_PersonalEntriesPlugin__removeDrawRangeCircle',
     '_PersonalEntriesPlugin__addDrawRangeCircle'),
    (settings.CIRCLE_TYPE.MAX_VIEW_RANGE, 'max_view_range',
     '_PersonalEntriesPlugin__removeMaxViewRangeCircle',
     '_PersonalEntriesPlugin__addMaxViewRangeCircle'),
    (settings.CIRCLE_TYPE.VIEW_RANGE, 'view_range',
     '_PersonalEntriesPlugin__removeViewRangeCircle',
     '_PersonalEntriesPlugin__addViewRangeCircle'),
    (settings.CIRCLE_TYPE.MIN_SPOTTING_RANGE, 'min_spotting_range',
     '_PersonalEntriesPlugin__removeMinSpottingRangeCircle',
     '_PersonalEntriesPlugin__addMinSpottingRangeCircle'),
)
NATIVE_CIRCLE_INDEX = dict((circle_name, index) for index, (_, circle_name, _, _) in enumerate(NATIVE_REPLACEMENTS))
NATIVE_CIRCLE_ACTIONS = {
    settings.VIEW_RANGE_CIRCLES_AS3_DESCR.AS_ADD_MAX_DRAW_CIRCLE: ('draw_range', 'add'),
    settings.VIEW_RANGE_CIRCLES_AS3_DESCR.AS_DEL_MAX_DRAW_CIRCLE: ('draw_range', 'remove'),
    settings.VIEW_RANGE_CIRCLES_AS3_DESCR.AS_ADD_MAX_VIEW_CIRCLE: ('max_view_range', 'add'),
    settings.VIEW_RANGE_CIRCLES_AS3_DESCR.AS_DEL_MAX_VIEW_CIRCLE: ('max_view_range', 'remove'),
    settings.VIEW_RANGE_CIRCLES_AS3_DESCR.AS_ADD_DYN_CIRCLE: ('view_range', 'add'),
    settings.VIEW_RANGE_CIRCLES_AS3_DESCR.AS_UPDATE_DYN_CIRCLE: ('view_range', 'update'),
    settings.VIEW_RANGE_CIRCLES_AS3_DESCR.AS_DEL_DYN_CIRCLE: ('view_range', 'remove'),
    settings.VIEW_RANGE_CIRCLES_AS3_DESCR.AS_ADD_MIN_SPOTTING_CIRCLE: ('min_spotting_range', 'add'),
    settings.VIEW_RANGE_CIRCLES_AS3_DESCR.AS_DEL_MIN_SPOTTING_CIRCLE: ('min_spotting_range', 'remove'),
}
CIRCLE_SETTING_KEYS = (
    ('show_primary_circle', 'distance_meters_1', 'color_1', 'opacity_1'),
    ('show_secondary_circle', 'distance_meters_2', 'color_2', 'opacity_2'),
    ('show_alternative_circle', 'distance_meters_3', 'color_3', 'opacity_3'),
)
NATIVE_CIRCLE_SETTING_KEYS = (
    ('show_draw_range_marker', 'draw_range_color', 'draw_range_opacity'),
    ('show_max_view_range_marker', 'max_view_range_color', 'max_view_range_opacity'),
    ('show_view_range_marker', 'view_range_color', 'view_range_opacity'),
    ('show_min_spotting_range_marker', 'min_spotting_range_color', 'min_spotting_range_opacity'),
)
def menu_settings(values):
    result = dict(values)
    result['use_custom_marker_options'] = values['replace_wot_circle_markers']
    result.pop('replace_wot_circle_markers', None)
    for _, _, color_key, opacity_key in CIRCLE_SETTING_KEYS:
        result[color_key] = color_with_opacity(
            values[color_key], values[opacity_key])
    for _, color_key, opacity_key in NATIVE_CIRCLE_SETTING_KEYS:
        result[color_key] = color_with_opacity(values[color_key], values[opacity_key])
    result['enabled'] = values.get('enabled', True)
    return result


def color_with_opacity(color, opacity):
    alpha = int(round(float(opacity) * 255.0 / 100.0))
    return color + '%02X' % alpha


def _header_control(text, tooltip=None):
    if templates is not None: return templates.createLabel(text, tooltip)

    if tooltip is None: return {'type': 'Label', 'text': text}
    return {'type': 'Label', 'text': text, 'tooltip': tooltip}


def _create_empty_control(height):
    if templates is not None: return templates.createEmpty(height)
    return {'type': 'Empty', 'height': height}


def _checkbox_control(text, var_name, value):
    if templates is not None: return templates.createCheckbox(text, var_name, value)
    return {
        'type': 'CheckBox',
        'text': text,
        'value': value,
        'varName': var_name,
    }


def _slider_control(var_name, value):
    minimum, maximum, step = 50, int(AOI.VEHICLE_CIRCULAR_AOI_RADIUS), 5
    if templates is not None:
        return templates.createSlider('Distance (meters)', var_name, value, minimum, maximum, step, format='{{value}} m')
    return {
        'type': 'Slider',
        'text': 'Distance (meters)',
        'minimum': minimum,
        'maximum': maximum,
        'snapInterval': step,
        'value': value,
        'format': '{{value}} m',
        'varName': var_name,
    }


def _color_choice_control(var_name, value):
    if templates is not None:
        return templates.createColorChoice('Color+Opacity', var_name, value, enableAlpha=True)
    return {
        'type': 'ColorChoice',
        'text': 'Color+Opacity',
        'value': value,
        'alpha': True,
        'varName': var_name,
    }


def _copy_control(control):
    if isinstance(control, dict):
        return dict(control)
    return control


def _color_opacity_settings(values, normalized, color_key, opacity_key):
    color = values.get(color_key)
    color_alpha = None
    if isinstance(color, _STRING_TYPES):
        color = color.strip().lstrip('#')
        if len(color) in (6, 8):
            try:
                int(color[:6], 16)
                if len(color) == 8:
                    color_alpha = int(color[6:], 16)
                normalized[color_key] = color[:6].upper()
                if color_alpha is not None:
                    normalized[opacity_key] = int(round(color_alpha * 100.0 / 255.0))
            except ValueError:
                print(TAG + 'Ignoring invalid color value from Mod Menu')

    opacity = values.get(opacity_key)
    if (isinstance(opacity, _NUMBER_TYPES) and
            not isinstance(opacity, bool) and
            0 <= opacity <= 100 and color_alpha is None):
        normalized[opacity_key] = int(round(opacity))


def build_settings_template(values=None):
    if values is None:
        values = DEFAULT_SETTINGS

    global_settings = [
        _header_control('Global Settings'),
        _checkbox_control('Use custom style for native WoT circles', 'use_custom_marker_options', values['replace_wot_circle_markers']),
    ]
    custom_circle_sections = []
    circle_headers = (
        ('Primary', 'Configure the first extra circle added by this mod.'),
        ('Secondary', 'Configure the second extra view range circle added by this mod.'),
        ('Alternative', 'Configure the third extra view range circle added by this mod.'),
    )
    for (circle_name, tooltip), (enabled_key, distance_key, color_key, opacity_key) in zip(circle_headers, CIRCLE_SETTING_KEYS):
        custom_circle_sections.extend([
            _header_control(circle_name, tooltip),
            _checkbox_control('Enabled', enabled_key, values[enabled_key]),
            _slider_control(distance_key, values[distance_key]),
            _color_choice_control(color_key, color_with_opacity(values[color_key], values[opacity_key])),
        ])

    native_circle_sections = []
    native_circle_headers = (
        ('Draw Range (565m)', 'The view range tanks stop rendering at. Only applies when "Use custom style for native WoT circles" is toggled on.'),
        ('Max View Range (445m)', 'The maximum view range circle. Only applies when "Use custom style for native WoT circles" is toggled on.'),
        ('Variable View Range', 'The current vehicle view range. Only applies when "Use custom style for native WoT circles" is toggled on.'),
        ('Min/Proxy (50m)', 'The proxy spotting view range circle. Only applies when "Use custom style for native WoT circles" is toggled on.'),
    )
    for (circle_name, tooltip), (_, color_key, opacity_key) in zip(native_circle_headers, NATIVE_CIRCLE_SETTING_KEYS):
        native_circle_sections.extend([
            _header_control(circle_name, tooltip),
            _color_choice_control(color_key, color_with_opacity(values[color_key], values[opacity_key])),
        ])

    column2_alignment_spacers = [_create_empty_control(36), _create_empty_control(36)]
    column1 = global_settings + [_create_empty_control(20)]
    column1.extend(native_circle_sections)
    column2 = (column2_alignment_spacers + [_create_empty_control(20)] + custom_circle_sections)

    # Return the settings template as a dictionary with two columns for Mod Menu.
    return {
        'modDisplayName': 'View Range Customizer',
        'modAuthor': MOD_AUTHOR,
        'modVersion': MOD_VERSION,
        'enabled': values.get('enabled', True),
        'column1': [_copy_control(control) for control in column1],
        'column2': [_copy_control(control) for control in column2],
    }


SETTINGS_TEMPLATE = build_settings_template()


def normalize_settings(values):
    normalized = dict(DEFAULT_SETTINGS)
    normalized.update(SETTINGS)

    # Normalize the settings from Mod Menu values, retaining enabled state and custom marker options.
    enabled = values.get('enabled')
    if isinstance(enabled, bool):
        normalized['enabled'] = enabled

    use_custom_marker_options = values.get('use_custom_marker_options')
    if isinstance(use_custom_marker_options, bool):
        normalized['replace_wot_circle_markers'] = use_custom_marker_options

    for enabled_key, distance_key, color_key, opacity_key in CIRCLE_SETTING_KEYS:
        enabled = values.get(enabled_key)
        if isinstance(enabled, bool):
            normalized[enabled_key] = enabled

        distance = values.get(distance_key)
        if (isinstance(distance, _NUMBER_TYPES) and not isinstance(distance, bool) and
                50 <= distance <= int(AOI.VEHICLE_CIRCULAR_AOI_RADIUS)):
            normalized[distance_key] = int(round(distance))

        _color_opacity_settings(values, normalized, color_key, opacity_key)

    for enabled_key, color_key, opacity_key in NATIVE_CIRCLE_SETTING_KEYS:
        enabled = values.get(enabled_key)
        if isinstance(enabled, bool):
            normalized[enabled_key] = enabled
        _color_opacity_settings(values, normalized, color_key, opacity_key)

    return normalized
