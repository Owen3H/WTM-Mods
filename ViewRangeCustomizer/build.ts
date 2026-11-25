import { copyFileSync, existsSync, mkdirSync, readFileSync, readdirSync, rmSync, writeFileSync } from "node:fs"
import { basename, dirname, join, relative } from "node:path"
import { spawn } from "node:child_process"

type BundlePatch = {
    resourcePath: string
    componentMarker: string
    contentMarker: string
    insertion: string
}

type BuildConfig = {
    gameVersion: string
    pythonArchiveRoot: string
    bundlePatch: BundlePatch | null
    openResModsFolder: boolean
    test: { kind: "commands"; commands: { program: string; args: string[] }[] } | { kind: "launch" }
}

const PROJECT_DIR = import.meta.dir
const META_FILE = join(PROJECT_DIR, "meta.xml")
const DIST_DIR = join(PROJECT_DIR, "dist")
const SOURCE_DIR = join(PROJECT_DIR, "src")
// const RESOURCES_DIR = join(SOURCE_DIR, "res") // This mod does not use or require resources yet.

const BUILD_CONFIG: BuildConfig = {
    gameVersion: "2.4.2.0",
    pythonArchiveRoot: "res/scripts/client/gui/mods",
    bundlePatch: null,
    openResModsFolder: true,
    test: { kind: "launch" },
}

if (!/^\d+\.\d+\.\d+\.\d+$/.test(BUILD_CONFIG.gameVersion)) {
    throw new Error("gameVersion must be a four-part version, e.g. 2.4.1.1")
}
const GAME_VER = BUILD_CONFIG.gameVersion
const GAME_DIR = process.env.WOT_GAME_DIR
if (!GAME_DIR) throw new Error("WOT_GAME_DIR variable is not set in .env file or system environment.")
const PACKAGED_MODS_DIR = process.env.WOT_PACKAGED_MODS_DIR || join(GAME_DIR, "mods", GAME_VER)

const PYTHON_COMPILE_SCRIPT = [
    "import os, py_compile, sys, tempfile, xml.etree.ElementTree as ET",
    "source_path, output_path, meta_path = sys.argv[1:4]",
    "with open(source_path, 'rb') as f: source = f.read()",
    "if 'MOD_AUTHOR = None' in source or 'MOD_VERSION = None' in source:",
    "    metadata = ET.parse(meta_path).getroot()",
    "    for field in ('author', 'version'):",
    "        value = metadata.findtext(field)",
    "        marker = 'MOD_' + field.upper() + ' = None'",
    "        if not value or not value.strip() or source.count(marker) != 1: raise ValueError('Missing metadata or placeholder: ' + field)",
    "        source = source.replace(marker, 'MOD_' + field.upper() + ' = ' + repr(value.strip()))",
    "    temp = tempfile.NamedTemporaryFile(suffix='.py', delete=False)",
    "    try:",
    "        with temp: temp.write(source)",
    "        py_compile.compile(temp.name, cfile=output_path, dfile=source_path, doraise=True)",
    "    finally: os.remove(temp.name)",
    "else:",
    "    py_compile.compile(source_path, cfile=output_path, dfile=source_path, doraise=True)",
]

const READ_BUNDLE_SCRIPT = [
    "import os, sys, zipfile, msvcrt",
    "packages_dir, bundle_path = sys.argv[1:3]",
    "matches = []",
    "for name in sorted(os.listdir(packages_dir)):",
    "    if name.startswith('gui-part') and name.endswith('.pkg'):",
    "        with zipfile.ZipFile(os.path.join(packages_dir, name), 'r') as package:",
    "            if bundle_path in package.namelist(): matches.append(package.read(bundle_path))",
    "if len(matches) != 1: raise ValueError('Expected exactly one game bundle, found %d' % len(matches))",
    "msvcrt.setmode(sys.stdout.fileno(), os.O_BINARY)",
    "sys.stdout.write(matches[0])",
]

export const PACKAGE_SCRIPT = [
    "import sys, zipfile",
    "meta_path, output_path = sys.argv[1:3]",
    "file_args = sys.argv[3:]",
    "if len(file_args) % 2: raise ValueError('Package files must be source/archive-path pairs')",
    "with zipfile.ZipFile(output_path, 'w', compression=zipfile.ZIP_STORED) as package:",
    "    package.write(meta_path, 'meta.xml')",
    "    for source, archive_path in zip(file_args[::2], file_args[1::2]):",
    "        package.write(source, archive_path)",
]

type CompiledModule = { source: string; output: string; archivePath: string }

function discoverPythonModules(): CompiledModule[] {
    const sources: string[] = []
    const visit = (directory: string): void => {
        for (const entry of readdirSync(directory, { withFileTypes: true })) {
            const path = join(directory, entry.name)
            if (entry.isDirectory()) visit(path)
            else if (entry.isFile() && entry.name.endsWith(".py")) sources.push(path)
        }
    }
    visit(SOURCE_DIR)
    if (sources.length === 0) throw new Error(`No Python modules found under ${SOURCE_DIR}`)
    return sources.sort().map((source) => {
        const output = relative(SOURCE_DIR, source).replace(/\.py$/, ".pyc")
        return {
            source,
            output,
            archivePath: BUILD_CONFIG.pythonArchiveRoot + "/" + output.replace(/\\/g, "/"),
        }
    })
}

export function patchBundle(bundle: string): string {
    const patch = BUILD_CONFIG.bundlePatch
    if (!patch) throw new Error("No game bundle patch is configured")
    if (bundle.split(patch.componentMarker).length !== 2 ||
        bundle.split(patch.contentMarker).length !== 2) {
        throw new Error("Unsupported game renderer; expected markers were not found exactly once")
    }
    return bundle.replace(
        patch.contentMarker,
        patch.contentMarker.replace("children:[", "children:[" + patch.insertion),
    )
}

function runPython(script: string[], args: string[], stdout: "inherit" | "pipe" = "inherit"): Uint8Array | undefined {
    const result = Bun.spawnSync(["py", "-2.7", "-B", "-c", script.join("\n"), ...args], {
        cwd: PROJECT_DIR,
        stdout,
        stderr: "inherit",
    })
    if (result.exitCode !== 0) throw new Error("Python command failed with exit code " + result.exitCode)
    return stdout === "pipe" ? result.stdout : undefined
}

function metadataValue(name: string): string {
    const metadata = readFileSync(META_FILE, "utf8")
    const match = metadata.match(new RegExp("<" + name + ">\\s*([^<]+)\\s*</" + name + ">"))
    if (!match) throw new Error("meta.xml must define " + name + ".")
    return match[1].trim()
}

function compile(): void {
    mkdirSync(DIST_DIR, { recursive: true })
    console.log("Compiling Python 2.7 modules...")
    for (const module of discoverPythonModules()) {
        const outputPath = join(DIST_DIR, module.output)
        mkdirSync(dirname(outputPath), { recursive: true })
        runPython(PYTHON_COMPILE_SCRIPT, [
            module.source,
            outputPath,
            META_FILE,
        ])
    }
    console.log("Compilation complete.")
}

function packageMod(): string {
    console.log("Packaging mod...")
    const modId = metadataValue("id")
    const modVersion = metadataValue("version")
    const output = join(DIST_DIR, `${modId}_${GAME_VER}_${modVersion}.wotmod`)
    const files: { source: string; archivePath: string }[] = discoverPythonModules().map((module) => ({
        source: join(DIST_DIR, module.output),
        archivePath: module.archivePath,
    }))

    if (BUILD_CONFIG.bundlePatch) {
        const bundlePath = BUILD_CONFIG.bundlePatch.resourcePath
        const bundleBytes = runPython(READ_BUNDLE_SCRIPT, [
            join(GAME_DIR!, "res", "packages"),
            bundlePath,
        ], "pipe")
        if (!bundleBytes) throw new Error("The game bundle reader returned no data.")
        const bundle = patchBundle(new TextDecoder("utf-8", { fatal: true }).decode(bundleBytes))
        const patchedBundle = join(DIST_DIR, "patched", basename(bundlePath))
        mkdirSync(dirname(patchedBundle), { recursive: true })
        writeFileSync(patchedBundle, bundle, "utf8")
        files.push({ source: patchedBundle, archivePath: "res/" + bundlePath })
    }

    const args = [META_FILE, output]
    for (const file of files) args.push(file.source, file.archivePath)
    runPython(PACKAGE_SCRIPT, args)
    console.log("Created package at " + output)
    return output
}

function copyPackageToMods(packagePath: string): void {
    mkdirSync(PACKAGED_MODS_DIR, { recursive: true })
    const destination = join(PACKAGED_MODS_DIR, basename(packagePath))
    copyFileSync(packagePath, destination)
    console.log("Copied packaged mod to " + destination)
}

function getResModsDir(): string {
    return process.env.WOT_MODS_DIR || join(GAME_DIR!, "res_mods", GAME_VER, "scripts", "client", "gui", "mods")
}

function copyToResMods(): void {
    const modules = discoverPythonModules()
    const destinationRoot = getResModsDir()
    console.log("Copying compiled mods to res_mods...")
    for (const module of modules) {
        const destination = join(destinationRoot, module.output)
        mkdirSync(dirname(destination), { recursive: true })
        copyFileSync(join(DIST_DIR, module.output), destination)
    }
    console.log("Copied mods to " + destinationRoot)
    if (BUILD_CONFIG.openResModsFolder) {
        const explorer = spawn("explorer.exe", [destinationRoot], { detached: true, stdio: "ignore" })
        explorer.unref()
        console.log("Opened mods folder in File Explorer.")
    }
}

function removeResModsCopies(): void {
    const destinationRoot = getResModsDir()
    for (const module of discoverPythonModules()) {
        const file = join(destinationRoot, module.output)
        if (existsSync(file)) rmSync(file)
    }
}

function launchGame(): void {
    const gameExecutable = join(GAME_DIR!, "WorldOfTanks.exe")
    if (!existsSync(gameExecutable)) throw new Error("World of Tanks executable not found: " + gameExecutable)
    const game = spawn(gameExecutable, [], { cwd: GAME_DIR, detached: true, stdio: "ignore" })
    game.unref()
}

function runTests(): void {
    if (BUILD_CONFIG.test.kind === "commands") {
        console.log("Starting test...")
        for (const command of BUILD_CONFIG.test.commands) {
            const result = Bun.spawnSync([command.program, ...command.args], {
                cwd: PROJECT_DIR,
                stdout: "inherit",
                stderr: "inherit",
            })
            if (result.exitCode !== 0) throw new Error("Test command failed with exit code " + result.exitCode)
        }
        return
    }
    compile()
    copyToResMods()
    launchGame()
}

if (import.meta.main) {
    const command = process.argv[2] || "build"
    if (command === "compile") compile()
    else if (command === "copy") copyToResMods()
    else if (command === "build" || command === "package") {
        if (command === "build") console.log("Building mod...")
        compile()
        copyPackageToMods(packageMod())
        removeResModsCopies()
    } else if (command === "test") runTests()
    else throw new Error("Unknown build command: " + command)
}
