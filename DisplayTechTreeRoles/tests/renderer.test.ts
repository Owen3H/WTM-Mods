import { describe, expect, test } from "bun:test"
import { mkdtempSync, rmSync, writeFileSync } from "node:fs"
import { tmpdir } from "node:os"
import { join } from "node:path"
import { NODE_COMPONENT, NODE_CONTENT, PACKAGE_SCRIPT, patchBundle, ROLE_ICON } from "../build"

const original = NODE_COMPONENT + "x" + NODE_CONTENT

test("packages all mod files without compression", () => {
    const dir = mkdtempSync(join(tmpdir(), "tech-tree-package-test-"))
    try {
        const output = join(dir, "mod.wotmod")
        const meta = join(dir, "meta.xml")
        const compiled = join(dir, "mod.pyc")
        writeFileSync(meta, "metadata")
        writeFileSync(compiled, "compiled")
        const result = Bun.spawnSync(["py", "-2.7", "-c", PACKAGE_SCRIPT.join("\n"),
            output, meta, compiled, "gui/test.js"], { stdin: Buffer.from("bundle") })
        expect(result.exitCode).toBe(0)
        const check = Bun.spawnSync(["py", "-2.7", "-c", [
            "import sys, zipfile",
            "with zipfile.ZipFile(sys.argv[1]) as package:",
            "    expected = {'meta.xml': 'metadata', 'res/scripts/client/gui/mods/mod_displaytechtreeroles.pyc': 'compiled', 'res/gui/test.js': 'bundle'}",
            "    assert set(package.namelist()) == set(expected)",
            "    for item in package.infolist():",
            "        assert item.compress_type == zipfile.ZIP_STORED",
            "        assert package.read(item.filename) == expected[item.filename]",
        ].join("\n"), output])
        expect(check.exitCode).toBe(0)
    } finally {
        rmSync(dir, { recursive: true })
    }
})

describe("tech-tree bundle patch", () => {
    test("inserts the icon before the vehicle hover element", () => {
        const patched = patchBundle(original)
        expect(patched).toBe(original.replace("children:[", "children:[" + ROLE_ICON))
        expect(() => patchBundle(patched)).toThrow()
    })

    test("rejects missing or ambiguous renderers", () => {
        expect(() => patchBundle("unknown renderer")).toThrow()
        expect(() => patchBundle(NODE_COMPONENT + NODE_CONTENT.repeat(2))).toThrow()
        expect(() => patchBundle(NODE_COMPONENT.repeat(2) + NODE_CONTENT)).toThrow()
    })
})

test("renders configured top and bottom icons and skips missing icons", () => {
    const bundle = patchBundle(original)
    const start = bundle.indexOf('i.roleIcon&&(0,ue.jsx)')
    const end = bundle.indexOf(',(0,ue.jsx)("div",{className:Ze.hover})', start)
    expect(start).toBeGreaterThanOrEqual(0)
    expect(end).toBeGreaterThan(start)
    const renderIcon = new Function("i", "o", "ue", "return " + bundle.slice(start, end))
    const jsx = { jsx: (type: string, props: object) => ({ type, props }) }
    const top = renderIcon({
        roleIcon: "img://gui/test.png", roleIconSize: 24, roleIconMargin: -6, roleIconPosition: "top",
    }, 42, jsx)
    expect(top.type).toBe("div")
    expect(top.props["data-test-id"]).toBe("42-role-icon")
    expect(top.props.style).toMatchObject({
        backgroundImage: 'url("img://gui/test.png")', left: "50%", top: "auto", bottom: "100%",
        marginBottom: "-6px", width: "24px", height: "24px", transform: "translateX(-50%)",
        pointerEvents: "none",
    })
    const bottom = renderIcon({
        roleIcon: "img://gui/test.png", roleIconSize: 40, roleIconMargin: 8, roleIconPosition: "bottom",
    }, 43, jsx)
    expect(bottom.props.style).toMatchObject({
        top: "100%", bottom: "auto", marginTop: "8px", width: "40px", height: "40px",
    })
    expect(renderIcon({}, 42, jsx)).toBeUndefined()
})
