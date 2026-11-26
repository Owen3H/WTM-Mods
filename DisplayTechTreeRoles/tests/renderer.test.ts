import { describe, expect, test } from "bun:test"
import { readFileSync } from "node:fs"
import { join } from "node:path"
import { runInNewContext } from "node:vm"

const resourceDir = join(import.meta.dir, "..", "src", "res")
const script = readFileSync(join(resourceDir, "gui", "gameface", "mods", "wtm", "DisplayTechTreeRoles", "roles.js"), "utf8")

class Element {
    className = ""
    style: Record<string, string> = {}
    attributes: Record<string, string> = {}
    parentNode: Element | null = null
    children: Element[] = []
    setAttribute(name: string, value: string) { this.attributes[name] = value }
    getAttribute(name: string) { return this.attributes[name] }
    get firstChild() { return this.children[0] || null }
    insertBefore(child: Element) {
        child.parentNode = this
        this.children.unshift(child)
    }
    removeChild(child: Element) {
        this.children.splice(this.children.indexOf(child), 1)
        child.parentNode = null
    }
    querySelector(selector: string): Element | null {
        return this.children.find(child => selector === "." + child.className) || null
    }
    querySelectorAll(selector: string): Element[] {
        const all = this.children.flatMap(child => [child, ...child.querySelectorAll(selector)])
        if (selector === ".wtm-display-tech-tree-role") return all.filter(el => el.className === selector.slice(1))
        if (selector === '[data-test-id$="-image"]') return all.filter(el => (el.attributes["data-test-id"] || "").endsWith("-image"))
        return []
    }
}

function fixture(initialPresent = true, initialRootPresent = true) {
    const root = new Element()
    const container = new Element()
    container.setAttribute("class", "VehicleNode_container_test")
    const image = new Element()
    image.setAttribute("data-test-id", "42-image")
    root.insertBefore(container)
    container.insertBefore(image)
    const handlers = new Map<string, Function>()
    const callbacks = new Map<number, Function>()
    const timeouts = new Map<number, Function>()
    let nextId = 0
    let mutation: Function = () => {}
    let disconnected = false
    let rootPresent = initialRootPresent
    let observerOptions: object | undefined
    let failCallbackRemoval = false
    let failOffName: string | null = null
    const errors: unknown[][] = []
    const model = { ModInjectModel: { name: "WTMDisplayTechTreeRoles" }, payload: "{}" }
    let present = initialPresent
    const subViews = { ids: () => present ? [5] : [], get: () => present ? { model } : null }
    const window = { subViews, addEventListener: (_: string, fn: Function) => handlers.set("unload", fn),
        removeEventListener: (_: string, fn: Function) => {
            if (handlers.get("unload") === fn) handlers.delete("unload")
        } }
    const engine = {
        whenReady: Promise.resolve(),
        on: (name: string, fn: Function) => handlers.set(name, fn),
        off: (name: string, fn: Function) => {
            if (failOffName === name) throw new Error("unsubscribe failed")
            if (handlers.get(name) === fn) handlers.delete(name)
        },
    }
    const removed: number[] = []
    const context = {
        window, engine, console: { error: (...args: unknown[]) => errors.push(args) },
        document: { querySelector: () => rootPresent ? root : null, createElement: () => new Element() },
        viewEnv: {
            addDataChangedCallback: () => 10,
            removeDataChangedCallback: (id: number) => {
                if (failCallbackRemoval) throw new Error("callback removal failed")
                removed.push(id)
            },
        },
        MutationObserver: class {
            constructor(fn: Function) { mutation = fn }
            observe(_: Element, options: object) { observerOptions = options }
            disconnect() { disconnected = true }
        },
        requestAnimationFrame: (fn: Function) => { const id = ++nextId; callbacks.set(id, fn); return id },
        cancelAnimationFrame: (id: number) => callbacks.delete(id),
        setTimeout: (fn: Function) => { const id = ++nextId; timeouts.set(id, fn); return id },
        clearTimeout: (id: number) => timeouts.delete(id),
    }
    runInNewContext(script, context)
    const flush = () => {
        while (callbacks.size) {
            const [id, callback] = callbacks.entries().next().value!
            callbacks.delete(id)
            callback()
        }
    }
    const change = (payload: object | null) => {
        model.payload = JSON.stringify(payload)
        handlers.get("viewEnv.onDataChanged")!(null, null, [10])
        flush()
    }
    return { root, container, image, model, handlers, removed, errors, flush, change,
        mutate: () => mutation([{}]), removeCarrier: () => { present = false; handlers.get("subViews.onRemoved")!([5]) },
        addCarrier: () => { present = true; handlers.get("subViews.onAdded")!([5]) },
        failCallbackRemoval: (value: boolean) => { failCallbackRemoval = value },
        failOff: (name: string | null) => { failOffName = name },
        window,
        isDisconnected: () => disconnected, observerOptions: () => observerOptions,
        setRootPresent: (value: boolean) => { rootPresent = value },
        runTimeout: () => { const [id, callback] = timeouts.entries().next().value!; timeouts.delete(id); callback() },
        pendingTimeouts: () => timeouts.size, pendingFrames: () => callbacks.size,
        retainedFrame: () => callbacks.values().next().value as Function }
}

describe("injected tech-tree renderer", () => {
    test("renders, updates, and reconciles icons without modifying native nodes", async () => {
        const f = fixture()
        await Promise.resolve()
        f.flush()
        const role = { roleIcon: "img://icon.png", roleIconSize: 24, roleIconMargin: -18, roleIconPosition: "bottom" }
        f.change({ "42": role })
        let icon = f.container.querySelector(".wtm-display-tech-tree-role")!
        expect(icon.style).toMatchObject({ top: "100%", marginTop: "-18px", width: "24px", pointerEvents: "none" })
        expect(f.observerOptions()).toMatchObject({ attributes: true, attributeFilter: ["data-test-id"] })
        f.change({ "42": { ...role, roleIconSize: 40, roleIconPosition: "top" } })
        expect(icon.style).toMatchObject({ top: "0px", marginTop: "-22px", width: "40px" })
        f.container.removeChild(icon)
        f.mutate()
        f.flush()
        icon = f.container.querySelector(".wtm-display-tech-tree-role")!
        expect(icon).toBeTruthy()
        f.change({})
        expect(f.container.querySelector(".wtm-display-tech-tree-role")).toBeNull()
        expect(f.container.children).toHaveLength(1)
    })

    test("moves top and bottom icons by the configured margin", async () => {
        const f = fixture()
        await Promise.resolve()
        const role = { roleIcon: "img://icon.png", roleIconSize: 24, roleIconMargin: 0, roleIconPosition: "top" }
        for (const [margin, offset] of [[-32, "8px"], [-24, "0px"], [-18, "-6px"], [0, "-24px"], [8, "-32px"], [16, "-40px"]] as const) {
            f.change({ "42": { ...role, roleIconMargin: margin } })
            expect(f.container.querySelector(".wtm-display-tech-tree-role")!.style).toMatchObject({
                top: "0px", marginTop: offset,
            })
        }
        for (const margin of [-32, -24, 0, 8, 16]) {
            f.change({ "42": { ...role, roleIconPosition: "bottom", roleIconMargin: margin } })
            expect(f.container.querySelector(".wtm-display-tech-tree-role")!.style).toMatchObject({
                top: "100%", marginTop: margin + "px",
            })
        }
    })

    test("removes icons and subscriptions when the carrier disappears", async () => {
        const f = fixture()
        await Promise.resolve()
        f.change({ "42": { roleIcon: "img://icon.png", roleIconSize: 24, roleIconMargin: 0, roleIconPosition: "bottom" } })
        f.removeCarrier()
        expect(f.container.querySelector(".wtm-display-tech-tree-role")).toBeNull()
        expect(f.removed).toEqual([10])
        expect(f.isDisconnected()).toBe(true)
        expect(f.handlers.has("subViews.onRemoved")).toBe(false)
        expect(f.handlers.has("viewEnv.onDataChanged")).toBe(false)
        f.addCarrier()
        f.flush()
        expect(f.container.querySelector(".wtm-display-tech-tree-role")).not.toBeNull()
        f.change(null)
        expect(f.container.querySelector(".wtm-display-tech-tree-role")).toBeNull()
        expect(f.removed).toEqual([10, 10])
        f.handlers.get("unload")!()
        expect(f.handlers.has("viewEnv.onDataChanged")).toBe(false)
    })

    test("cleans up an active carrier when the page unloads", async () => {
        const f = fixture()
        await Promise.resolve()
        f.change({ "42": { roleIcon: "img://icon.png", roleIconSize: 24, roleIconMargin: 0, roleIconPosition: "bottom" } })
        f.mutate()
        expect(f.pendingFrames()).toBe(1)
        f.handlers.get("unload")!()
        expect(f.container.querySelector(".wtm-display-tech-tree-role")).toBeNull()
        expect(f.removed).toEqual([10])
        expect(f.isDisconnected()).toBe(true)
        expect(f.pendingFrames()).toBe(0)
        expect(f.handlers.size).toBe(0)
        expect(f.errors).toHaveLength(0)
    })

    test("continues carrier cleanup when callback removal fails", async () => {
        const f = fixture()
        await Promise.resolve()
        f.change({ "42": { roleIcon: "img://icon.png", roleIconSize: 24, roleIconMargin: 0, roleIconPosition: "bottom" } })
        f.failCallbackRemoval(true)
        f.removeCarrier()
        expect(f.container.querySelector(".wtm-display-tech-tree-role")).toBeNull()
        expect(f.handlers.has("subViews.onRemoved")).toBe(false)
        expect(f.handlers.has("viewEnv.onDataChanged")).toBe(false)
        expect(f.errors).toHaveLength(1)

        f.failCallbackRemoval(false)
        f.addCarrier()
        f.flush()
        expect(f.container.querySelector(".wtm-display-tech-tree-role")).not.toBeNull()
    })

    test("handles recycled vehicle identity and removes orphan icons", async () => {
        const f = fixture()
        await Promise.resolve()
        const role = { roleIcon: "img://icon.png", roleIconSize: 24, roleIconMargin: 0, roleIconPosition: "bottom" }
        f.change({ "42": role, "43": role })
        f.image.setAttribute("data-test-id", "43-image")
        f.mutate()
        f.flush()
        expect(f.container.querySelector(".wtm-display-tech-tree-role")!.getAttribute("data-test-id")).toBe("43-role-icon")
        f.container.removeChild(f.image)
        f.mutate()
        f.flush()
        expect(f.container.children).toHaveLength(0)
    })

    test("clears malformed payloads instead of leaving stale icons", async () => {
        const f = fixture()
        await Promise.resolve()
        f.change({ "42": { roleIcon: "img://icon.png", roleIconSize: 24, roleIconMargin: 0, roleIconPosition: "bottom" } })
        f.change({ "42": { roleIcon: "img://icon.png", roleIconSize: 24, roleIconMargin: 1.5, roleIconPosition: "bottom" } })
        expect(f.container.querySelector(".wtm-display-tech-tree-role")).toBeNull()
        expect(f.errors).toHaveLength(1)
    })

    test("cancels readiness work and ignores a retained stale frame", async () => {
        const f = fixture()
        f.setRootPresent(false)
        await Promise.resolve()
        expect(f.pendingTimeouts()).toBe(1)
        f.setRootPresent(true)
        f.runTimeout()
        expect(f.pendingTimeouts()).toBe(0)
        expect(f.pendingFrames()).toBe(1)
        const staleFrame = f.retainedFrame()
        f.removeCarrier()
        expect(f.pendingFrames()).toBe(0)
        f.addCarrier()
        expect(f.pendingFrames()).toBe(1)
        staleFrame()
        expect(f.pendingFrames()).toBe(1)
        f.flush()
    })

    test("attaches a late carrier and stops root retries after the deadline", async () => {
        const f = fixture(false, false)
        await Promise.resolve()
        expect(f.pendingTimeouts()).toBe(0)
        f.addCarrier()
        for (let i = 0; i < 49; i++) f.runTimeout()
        expect(f.pendingTimeouts()).toBe(0)
        expect(f.errors).toHaveLength(1)
        f.removeCarrier()
        expect(f.handlers.has("viewEnv.onDataChanged")).toBe(false)
        f.handlers.get("unload")!()
        expect(f.handlers.size).toBe(0)
    })

    test("finishes disposal after page listener removal fails", async () => {
        const f = fixture()
        await Promise.resolve()
        f.failOff("subViews.onAdded")
        f.handlers.get("unload")!()
        expect(f.errors).toHaveLength(1)
        expect(f.handlers.has("unload")).toBe(false)
        expect(f.handlers.has("viewEnv.onDataChanged")).toBe(false)
        expect(Object.prototype.hasOwnProperty.call(f.window, "__wtmDisplayTechTreeRoles")).toBe(true)
    })
})

test("resource declaration targets the packaged carrier", () => {
    const declaration = JSON.parse(readFileSync(join(resourceDir, "gui", "gen_resources", "wtm_display_tech_tree_roles.json"), "utf8"))
    expect(declaration[0].id).toBe("R.mods.wtm.DisplayTechTreeRoles.views.Injection")
    expect(declaration[0].path).toBe("coui://gui/gameface/mods/wtm/DisplayTechTreeRoles/injection.html")
    expect(readFileSync(join(resourceDir, "gui", "gameface", "mods", "wtm", "DisplayTechTreeRoles", "injection.html"), "utf8")).toContain("<body>")
})
