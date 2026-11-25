## WTM-Mods
All of my mods for World of Tanks in one repo.
> WTM is short for WindowsTaskManager, my in-game name. :)

## Contribution
### Prerequisites
1. Read [WGMods Documentation](https://wgmods.dev/docs/wot/getting-started/setup#quick-start) to get started. Ensure Python 2.7 and 3.8 are both installed.
1. Install Bun + Typescript for compiling, testing and packaging WTM mods.
1. Run `bun install` to install the shared workspace dependencies.
1. Run `bun run update:wot-src` to fetch the decompiled WoT client. Every mod in this repo will pick it up and receive Pylance hints for easier development. It is gitignored and only exists locally.

### Developing a mod within this repo
1. Run `cd ViewRangeCustomizer` (or another mod of your choice) in the terminal.
1. After editing code, run `bun run test` which will automatically compile and open World of Tanks to test the mod.
1. Create a pull request, ideally one for each different feature/concern and clearly describe the intended changes.

Each mod's build script sets its target WoT version in `BUILD_CONFIG.gameVersion`. Update it independently for each mod; the version determines the package name and default `mods` and `res_mods` destinations. Make sure `wot-src` and the game installation match the target when developing and testing.

## List of Mods
A mod may be available on GitHub before WGMods Hub, please check the [releases](../../releases) page.

| Name | Description | Latest Version |
| --- | --- | --- |
| [View Range Customizer](ViewRangeCustomizer/) | Customize minimap view range circles and add up to three additional circles. | [v1.0.2](https://wgmods.net/8184) |
| [Display Tech Tree Roles](DisplayTechTreeRoles/) | Displays vehicle roles above tank icons in the tech tree. | v1.0.0-beta.2 |