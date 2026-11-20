# v1.0.1
- Fixed a Python 2.7 unbound-method issue that could stop the mod cleaning up its minimap and built-in circle changes on shutdown. We now check the descriptor directly instead.
- Fixed minimap setup potentially calling itself repeatedly when the mod reloads, while preserving other mods’ minimap changes during cleanup.
- Changed the custom circle plugin’s internal ID to the mod’s own ID, reducing the chance of naming conflicts.

# v1.0.0
- Stock WoT minimap functionality is restored on death/spectate.
- The mod now mirrors every native remove/add command and will not leave a custom replacement visible after WoT native controls disable them, regardless of "Use custom style" toggle state. 
- The master switch for the mod in Aslains Mod Menu is no longer ignored and works in my testing. 
- The mod now only applies to Random Battles to avoid any issues with different view range/spotting mechanics that may be present in other modes or future modes. 
- Replacements for native circles now preserve the radii supplied by WoT. They no longer use fixed 565m or 50m values. Any unavailable radius is read from the current arena, not a hardcoded default.