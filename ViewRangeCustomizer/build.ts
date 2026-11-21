import { copyFileSync, existsSync, mkdirSync, readFileSync, rmSync } from "node:fs"
import { spawn } from "node:child_process"
import { join } from "node:path"

const PROJECT_DIR = import.meta.dir
const DIST_DIR = join(PROJECT_DIR, "dist")
const PACKAGE_DIST_DIR = join(DIST_DIR, "viewrangecustomizer")
const WOT_SRC_DIR = join(PROJECT_DIR, "..", "wot-src")
const VERSION_FILE = join(WOT_SRC_DIR, "sources", "version.xml")
const versionMatch = readFileSync(VERSION_FILE, "utf8").match(/<version>\s*v\.([0-9]+\.[0-9]+\.[0-9]+\.[0-9]+)\s+/)
if (!versionMatch) throw new Error(`Could not determine World of Tanks version from ${VERSION_FILE}`)

const GAME_VER = versionMatch[1]
const GAME_DIR = process.env.WOT_GAME_DIR
if (!GAME_DIR) throw new Error("WOT_GAME_DIR variable is not set in .env file or system environment.")

const GAME_MODS_DIR = process.env.WOT_MODS_DIR || join(GAME_DIR, "res_mods", GAME_VER, "scripts", "client", "gui", "mods")
const PACKAGED_MODS_DIR = process.env.WOT_PACKAGED_MODS_DIR || join(GAME_DIR, "mods", GAME_VER)
const META_FILE = join(PROJECT_DIR, "meta.xml")
const META_CONTENT = readFileSync(META_FILE, "utf8")
const META_ID = META_CONTENT.match(/<id>\s*([^<]+)\s*<\/id>/)
const META_VERSION = META_CONTENT.match(/<version>\s*([^<]+)\s*<\/version>/)
if (!META_ID || !META_VERSION) throw new Error("meta.xml must define an id and version.")

const MOD_PACKAGE_NAME =
    META_ID[1].trim() + "_" + GAME_VER + "_" + META_VERSION[1].trim()
const MOD_PACKAGE_PATH = join(DIST_DIR, MOD_PACKAGE_NAME + ".wotmod")
const MODULE_NAMES = ["__init__", "config", "markerplugin"]
const PY_SCRIPT = [
    "import os, py_compile",
    "py_compile.compile(os.path.join('src', 'mod_viewrangecustomizer.py'), os.path.join('dist', 'mod_viewrangecustomizer.pyc'), doraise=True)",
    "for name in ('__init__', 'markerplugin'):",
    "    py_compile.compile(os.path.join('src', 'viewrangecustomizer', name + '.py'), os.path.join('dist', 'viewrangecustomizer', name + '.pyc'), doraise=True)",
]
const METADATA_COMPILE_SCRIPT = [
    "import os, py_compile, sys, tempfile, xml.etree.ElementTree as ET",
    "source_path, output_path, meta_path = sys.argv[1:4]",
    "metadata = ET.parse(meta_path).getroot()",
    "with open(source_path, 'rb') as f: source = f.read()",
    "for field in ('author', 'version'):",
    "    value = metadata.findtext(field)",
    "    marker = 'MOD_' + field.upper() + ' = None'",
    "    if not value or not value.strip() or source.count(marker) != 1: raise ValueError('Missing metadata or placeholder: ' + field)",
    "    source = source.replace(marker, 'MOD_' + field.upper() + ' = ' + repr(value.strip()))",
    "temp = tempfile.NamedTemporaryFile(suffix='.py', delete=False)",
    "try:",
    "    with temp: temp.write(source)",
    "    py_compile.compile(temp.name, cfile=output_path, dfile=source_path, doraise=True)",
    "finally: os.remove(temp.name)",
]
const PACKAGE_SCRIPT = [
    "import os, sys, zipfile, xml.etree.ElementTree as ET",
    "meta_path, dist_dir, game_version = sys.argv[1:4]",
    "metadata = ET.parse(meta_path).getroot()",
    "mod_id = metadata.findtext('id')",
    "version = metadata.findtext('version')",
    "if not mod_id or not version: raise ValueError('meta.xml must define an id and version')",
    "package_path = os.path.join(dist_dir, '%s_%s_%s.wotmod' % (mod_id, game_version, version))",
    "mod_files = [(os.path.join(dist_dir, 'mod_viewrangecustomizer.pyc'), 'res/scripts/client/gui/mods/mod_viewrangecustomizer.pyc')]",
    "for name in ('__init__', 'config', 'markerplugin'):",
    "    mod_files.append((os.path.join(dist_dir, 'viewrangecustomizer', name + '.pyc'), 'res/scripts/client/gui/mods/viewrangecustomizer/' + name + '.pyc'))",
    "with zipfile.ZipFile(package_path, 'w', zipfile.ZIP_STORED) as package:",
    "    for source, archive_path in mod_files:",
    "        package.write(source, archive_path)",
    "print('Created package at ' + package_path)",
]

function compileWithMetadata(source: string, output: string): void {
    const result = Bun.spawnSync(["py", "-2.7", "-B", "-c", METADATA_COMPILE_SCRIPT.join("\n"),
        source, output, META_FILE], {
        cwd: PROJECT_DIR, stderr: "inherit", stdout: "inherit",
    })
    if (result.exitCode !== 0) throw new Error("Python compilation failed with exit code " + result.exitCode)
}

function compile(): void {
    mkdirSync(PACKAGE_DIST_DIR, { recursive: true })
    console.log("Compiling Python 2.7 modules...")

    const result = Bun.spawnSync(["py", "-2.7", "-B", "-c", PY_SCRIPT.join("\n")], {
        cwd: PROJECT_DIR,
        stderr: "inherit",
        stdout: "inherit",
    })
    if (result.exitCode !== 0) throw new Error("Python compilation failed with exit code " + result.exitCode)
    compileWithMetadata(join(PROJECT_DIR, "src", "viewrangecustomizer", "config.py"),
        join(PACKAGE_DIST_DIR, "config.pyc"))
    console.log("Compilation complete.")
}

function copyToResMods(): void {
    console.log("Copying compiled mods to res_mods...")
    mkdirSync(GAME_MODS_DIR, { recursive: true })

    const packageDestination = join(GAME_MODS_DIR, "viewrangecustomizer")
    mkdirSync(packageDestination, { recursive: true })
    copyFileSync(
        join(DIST_DIR, "mod_viewrangecustomizer.pyc"),
        join(GAME_MODS_DIR, "mod_viewrangecustomizer.pyc"),
    )
    for (const name of MODULE_NAMES) {
        copyFileSync(join(PACKAGE_DIST_DIR, name + ".pyc"), join(packageDestination, name + ".pyc"))
    }
    console.log("Copied mods to " + GAME_MODS_DIR)

    const explorer = spawn("explorer.exe", [GAME_MODS_DIR], {
        detached: true,
        stdio: "ignore",
    })
    explorer.unref()
    console.log("Opened mods folder in File Explorer.")
}

function copyToMods(): void {
    if (!existsSync(MOD_PACKAGE_PATH)) throw new Error("Packaged mod not found. Run the package command first.")

    console.log("Copying packaged mod to mods directory...")
    mkdirSync(PACKAGED_MODS_DIR, { recursive: true })
    const destination = join(PACKAGED_MODS_DIR, MOD_PACKAGE_NAME + ".wotmod")
    copyFileSync(MOD_PACKAGE_PATH, destination)
    console.log("Copied packaged mod to " + destination)

    const unpackedFiles = [
        join(GAME_MODS_DIR, "mod_viewrangecustomizer.pyc"),
        ...MODULE_NAMES.map((name) => join(GAME_MODS_DIR, "viewrangecustomizer", name + ".pyc")),
    ]
    for (const file of unpackedFiles) {
        if (existsSync(file)) rmSync(file)
    }
}

function packageMod(): void {
    console.log("Packaging mod...")
    const result = Bun.spawnSync(["py", "-2.7", "-c", PACKAGE_SCRIPT.join("\n"), META_FILE, DIST_DIR, GAME_VER], {
        cwd: PROJECT_DIR,
        stderr: "inherit",
        stdout: "inherit",
    })
    if (result.exitCode !== 0) {
        throw new Error("Mod packaging failed with exit code " + result.exitCode)
    }
}

function launchGame(): void {
    const gameExecutable = join(GAME_DIR || "", "WorldOfTanks.exe")
    if (!existsSync(gameExecutable)) throw new Error("World of Tanks executable not found: " + gameExecutable)

    const game = spawn(gameExecutable, [], { cwd: GAME_DIR, detached: true, stdio: "ignore" })
    game.unref()
}

const cmd = process.argv[2] || "build"
if (cmd === "compile") compile()
else if (cmd === "copy") copyToResMods()
else if (cmd === "build") {
    console.log("Building mod...")
    compile()
    copyToResMods()
} else if (cmd === "test") {
    console.log("Starting test...")
    compile()
    copyToResMods()
    launchGame()
} else if (cmd === "package") {
    compile()
    packageMod()
    copyToMods()
} else throw new Error("Unknown build command: " + cmd)
