## WTM-Mods
All of my mods for World of Tanks in one repo.
> WTM is short for WindowsTaskManager, my in-game name. :)

## Contribution
### Prerequisites
1. Read [WGMods Documentation](https://wgmods.dev/docs/wot/getting-started/setup#quick-start) to get started. Ensure Python 2.7 and 3.8 are both installed.
1. Install Bun + Typescript for compiling, testing and packaging WTM mods.

### Developing a mod within this repo
1. Fetch the [wot-src](https://github.com/izeberg/wot-src/) repo and place it in the root. Every mod in this repo will pick it up and receive Pylance hints for easier development.
1. Run `bun install` from the repository root to install the shared workspace dependencies.
1. Run `cd ViewRangeCustomizer` (or another mod of your choice) in the terminal.
1. After editing code, run `bun run test` which will automatically compile and open World of Tanks to test the mod.
1. Create a pull request, ideally one for each different feature/concern and clearly describe the intended changes.

## List of Mods
A mod may be available on GitHub before WGMods Hub, please check the [releases](../../releases) page.

| Name | Description | Latest Version |
| --- | --- | --- |
| [View Range Customizer](ViewRangeCustomizer/) | Customize minimap view range circles and add up to three additional circles. | [v1.0.1](https://wgmods.net/8184) |
| [Display Tech Tree Roles](DisplayTechTreeRoles/) | Displays vehicle roles above tank icons in the tech tree. | v1.0.0-beta.2 |