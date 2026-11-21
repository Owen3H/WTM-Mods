import { copyFileSync, mkdirSync, readFileSync } from "node:fs"
import { join } from "node:path"

const PROJECT_DIR = import.meta.dir
const DIST_DIR = join(PROJECT_DIR, "dist")
const WOT_SRC_DIR = join(PROJECT_DIR, "..", "wot-src")
const VERSION_FILE = join(WOT_SRC_DIR, "sources", "version.xml")
const versionMatch = readFileSync(VERSION_FILE, "utf8").match(/<version>\s*v\.([0-9]+\.[0-9]+\.[0-9]+\.[0-9]+)\s+/)
if (!versionMatch) throw new Error(`Could not determine World of Tanks version from ${VERSION_FILE}`)
const GAME_VER = versionMatch[1]
const GAME_DIR = process.env.WOT_GAME_DIR
if (!GAME_DIR) throw new Error("WOT_GAME_DIR variable is not set in .env file or system environment.")
const PACKAGED_MODS_DIR = process.env.WOT_PACKAGED_MODS_DIR || join(GAME_DIR, "mods", GAME_VER)
const META_FILE = join(PROJECT_DIR, "meta.xml")
const COMPILED_MOD = join(DIST_DIR, "mod_displaytechtreeroles.pyc")
const BUNDLE_PATH = "gui/gameface/_dist/production/mono/tech_tree/main/bundle.js"

export const NODE_COMPONENT = 'ni=(0,F.memo)(function e(i){const{name:r,techName:a,id:o,'
export const NODE_CONTENT = 'children:[(0,ue.jsx)("div",{className:Ze.hover}),(0,ue.jsx)("div",{className:Ze.image,'
export const ROLE_ICON = [
    'i.roleIcon&&(0,ue.jsx)("div",{"data-test-id":o+"-role-icon",',
    'style:{position:"absolute",left:"50%",',
    'top:i.roleIconPosition==="bottom"?"100%":"auto",',
    'bottom:i.roleIconPosition==="bottom"?"auto":"100%",',
    'marginTop:i.roleIconPosition==="bottom"?`${i.roleIconMargin}px`:0,',
    'marginBottom:i.roleIconPosition==="bottom"?0:`${i.roleIconMargin}px`,',
    'width:`${i.roleIconSize}px`,height:`${i.roleIconSize}px`,',
    'transform:"translateX(-50%)",backgroundImage:`url("${i.roleIcon}")`,',
    'backgroundSize:"contain",backgroundRepeat:"no-repeat",',
    'backgroundPosition:"center",pointerEvents:"none",zIndex:2}}),',
].join("")

const READ_BUNDLE_SCRIPT = [
    "import os, sys, zipfile, msvcrt",
    "packages_dir, bundle_path = sys.argv[1:3]",
    "matches = []",
    "for name in sorted(os.listdir(packages_dir)):",
    "    if name.startswith('gui-part') and name.endswith('.pkg'):",
    "        with zipfile.ZipFile(os.path.join(packages_dir, name), 'r') as package:",
    "            if bundle_path in package.namelist(): matches.append(package.read(bundle_path))",
    "if len(matches) != 1: raise ValueError('Expected exactly one tech-tree bundle, found %d' % len(matches))",
    "msvcrt.setmode(sys.stdout.fileno(), os.O_BINARY)",
    "sys.stdout.write(matches[0])",
]
const COMPILE_SCRIPT = [
    "import py_compile, sys",
    "py_compile.compile(sys.argv[1], cfile=sys.argv[2], doraise=True)",
]
export const PACKAGE_SCRIPT = [
    "import os, sys, zipfile, msvcrt",
    "output, meta, compiled, bundle_path = sys.argv[1:5]",
    "msvcrt.setmode(sys.stdin.fileno(), os.O_BINARY)",
    "bundle = sys.stdin.read()",
    "with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_STORED) as package:",
    "    package.write(meta, 'meta.xml')",
    "    package.write(compiled, 'res/scripts/client/gui/mods/mod_displaytechtreeroles.pyc')",
    "    package.writestr('res/' + bundle_path, bundle)",
]

export function patchBundle(bundle: string): string {
    if (bundle.split(NODE_COMPONENT).length !== 2 || bundle.split(NODE_CONTENT).length !== 2) {
        throw new Error("Unsupported tech-tree renderer; the expected vehicle component was not found exactly once")
    }
    return bundle.replace(NODE_CONTENT, NODE_CONTENT.replace("children:[", "children:[" + ROLE_ICON))
}

function compile(): void {
    mkdirSync(DIST_DIR, { recursive: true })
    const result = Bun.spawnSync(["py", "-2.7", "-c", COMPILE_SCRIPT.join("\n"),
        join(PROJECT_DIR, "src", "mod_displaytechtreeroles.py"), COMPILED_MOD], {
        cwd: PROJECT_DIR,
        stderr: "inherit",
        stdout: "inherit",
    })
    if (result.exitCode !== 0) throw new Error("Python compilation failed with exit code " + result.exitCode)
    console.log("Python compilation complete.")
}

function packageMod(): void {
    console.log("Packaging mod...")
    const metadata = readFileSync(META_FILE, "utf8")
    const modId = metadata.match(/<id>\s*([^<]+)\s*<\/id>/)
    const modVersion = metadata.match(/<version>\s*([^<]+)\s*<\/version>/)
    if (!modId || !modVersion) throw new Error("meta.xml must define an id and version.")

    const readResult = Bun.spawnSync(["py", "-2.7", "-c", READ_BUNDLE_SCRIPT.join("\n"),
        join(GAME_DIR!, "res", "packages"), BUNDLE_PATH], {
        cwd: PROJECT_DIR,
        stdout: "pipe",
        stderr: "inherit",
    })
    if (readResult.exitCode !== 0) throw new Error("Reading the game bundle failed with exit code " + readResult.exitCode)
    const bundle = patchBundle(new TextDecoder("utf-8", { fatal: true }).decode(readResult.stdout))
    const output = join(DIST_DIR, `${modId[1].trim()}_${GAME_VER}_${modVersion[1].trim()}.wotmod`)
    const packageResult = Bun.spawnSync(["py", "-2.7", "-c", PACKAGE_SCRIPT.join("\n"),
        output, META_FILE, COMPILED_MOD, BUNDLE_PATH], {
        cwd: PROJECT_DIR,
        stdin: Buffer.from(bundle, "utf8"),
        stdout: "inherit",
        stderr: "inherit",
    })
    if (packageResult.exitCode !== 0) throw new Error("Mod packaging failed with exit code " + packageResult.exitCode)
    console.log("Created package at " + output)

    console.log("Copying packaged mod to mods directory...")
    mkdirSync(PACKAGED_MODS_DIR, { recursive: true })
    const destination = join(PACKAGED_MODS_DIR, `${modId[1].trim()}_${GAME_VER}_${modVersion[1].trim()}.wotmod`)
    copyFileSync(output, destination)
    console.log("Copied packaged mod to " + destination)
}

function test(): void {
    const pythonTests = Bun.spawnSync(["py", "-2.7", "-B", "-m", "unittest", "discover", "-s", "tests", "-v"], {
        cwd: PROJECT_DIR,
        stderr: "inherit",
        stdout: "inherit",
    })
    if (pythonTests.exitCode !== 0) throw new Error("Python tests failed with exit code " + pythonTests.exitCode)
    const rendererTests = Bun.spawnSync(["bun", "test", join("tests", "renderer.test.ts")], {
        cwd: PROJECT_DIR,
        stderr: "inherit",
        stdout: "inherit",
    })
    if (rendererTests.exitCode !== 0) throw new Error("Renderer tests failed with exit code " + rendererTests.exitCode)
}

if (import.meta.main) {
    const cmd = process.argv[2] || "build"
    if (cmd === "compile") compile()
    else if (cmd === "build" || cmd === "package") {
        compile()
        packageMod()
    } else if (cmd === "test") test()
    else throw new Error("Unknown build command: " + cmd)
}
