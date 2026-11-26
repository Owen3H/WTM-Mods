MOD_ID = 'wtm.display_tech_tree_roles'
MOD_NAME = 'DisplayTechTreeRoles'
TAG = '[' + MOD_NAME + '] '

MOD_AUTHOR = None  # Replaced at build time with author from meta.xml
MOD_VERSION = None # Replaced at build time with version from meta.xml

FEATURE_NAME = 'WTM' + MOD_NAME
SCRIPT_URL = 'coui://gui/gameface/mods/wtm/' + MOD_NAME + '/roles.js'

DEFAULT_SETTINGS = {'enabled': True, 'icon_size': 28, 'margin': -16, 'position': 1}
SETTINGS = dict(DEFAULT_SETTINGS)
MARGIN_MIN = -24
MARGIN_MAX = -12

try:
    _NUMBER_TYPES = (int, long, float)  # type: ignore
except NameError:
    _NUMBER_TYPES = (int, float)


def settings_template(templates):
    return {
        'modDisplayName': 'Display Tech Tree Roles',
        'modAuthor': MOD_AUTHOR,
        'modVersion': MOD_VERSION,
        'enabled': DEFAULT_SETTINGS['enabled'],
        'column1': [
            templates.createSlider('Icon size (px)', 'icon_size', DEFAULT_SETTINGS['icon_size'],
                                   18, 32, 1, format='{{value}} px'),
            templates.createSlider('Margin (px)', 'margin', DEFAULT_SETTINGS['margin'],
                                   MARGIN_MIN, MARGIN_MAX, 1, format='{{value}} px',
                                   tooltip='Distance from the vehicle image area. Negative values overlap it.'),
            templates.createDropdown('Position', 'position', ['Top', 'Bottom'],
                                     DEFAULT_SETTINGS['position']),
        ],
        'column2': [],
    }


def normalize_settings(values, base):
    normalized = dict(base)
    if 'enabled' in values:
        if isinstance(values['enabled'], bool):
            normalized['enabled'] = values['enabled']
        else:
            print(TAG + 'Ignoring invalid enabled setting')

    sz = ('icon_size', 8, 64)
    margin = ('margin', MARGIN_MIN, MARGIN_MAX)
    position = ('position', 0, 1)

    for key, minimum, maximum in (sz, margin, position):
        if key not in values:
            continue
        value = values[key]
        if (key == 'margin' and isinstance(value, _NUMBER_TYPES) and
                not isinstance(value, bool) and -32 <= value <= 32 and value == int(value)):
            clamped = max(minimum, min(maximum, int(value)))
            if clamped != value:
                print(TAG + 'Clamping margin setting to the supported range')
            value = clamped
        if (isinstance(value, _NUMBER_TYPES) and not isinstance(value, bool) and
                minimum <= value <= maximum and value == int(value)):
            normalized[key] = int(value)
        else:
            print(TAG + 'Ignoring invalid ' + key + ' setting')
    return normalized
