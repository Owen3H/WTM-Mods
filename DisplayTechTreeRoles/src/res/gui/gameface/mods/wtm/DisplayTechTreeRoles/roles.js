(function () {
    'use strict';

    const feature = 'WTMDisplayTechTreeRoles';
    const iconClass = 'wtm-display-tech-tree-role';
    const singleton = '__wtmDisplayTechTreeRoles';
    if (window[singleton]) return;

    let alive = true;
    let resourceId = null;
    let callbackId = null;
    let observer = null;
    let root = null;
    let frame = null;
    let retry = null;
    let rootAttempts = 0;
    let generation = 0;
    let roles = {};
    let addedSubscribed = false;
    let removedSubscribed = false;
    let dataSubscribed = false;

    function removeIcons() {
        if (!root) return;
        root.querySelectorAll('.' + iconClass).forEach(function (icon) {
            if (icon.parentNode) icon.parentNode.removeChild(icon);
        });
    }

    function disconnectView() {
        generation += 1;
        if (retry !== null) clearTimeout(retry);
        retry = null;
        if (observer) observer.disconnect();
        observer = null;
        if (frame !== null) cancelAnimationFrame(frame);
        frame = null;
        removeIcons();
        root = null;
        roles = {};
        if (callbackId !== null) {
            viewEnv.removeDataChangedCallback(callbackId, resourceId);
            callbackId = null;
        }
        if (removedSubscribed) engine.off('subViews.onRemoved', onSubViewRemoved);
        if (dataSubscribed) engine.off('viewEnv.onDataChanged', onDataChanged);
        removedSubscribed = false;
        dataSubscribed = false;
        resourceId = null;
    }

    function updateStyle(icon, key, value) {
        if (icon.style[key] !== value) icon.style[key] = value;
    }

    function isVehicleContainer(element) {
        return element && /(?:^|\s)VehicleNode_container_/.test(element.getAttribute('class') || '');
    }

    function vehicleId(image) {
        const match = /^(\d+)-image$/.exec(image.getAttribute('data-test-id'));
        return match && isVehicleContainer(image.parentNode) ? match[1] : null;
    }

    function render() {
        frame = null;
        if (!alive || !root) return;
        root.querySelectorAll('.' + iconClass).forEach(function (icon) {
            const parent = icon.parentNode;
            let found = false;
            if (isVehicleContainer(parent)) {
                parent.querySelectorAll('[data-test-id$="-image"]').forEach(function (image) {
                    if (image.parentNode === parent && vehicleId(image)) found = true;
                });
            }
            if (!found && parent) parent.removeChild(icon);
        });
        root.querySelectorAll('[data-test-id$="-image"]').forEach(function (image) {
            const id = vehicleId(image);
            if (!id) return;
            const parent = image.parentNode;
            let icon = parent.querySelector('.' + iconClass);
            const role = roles[id];
            if (!role) {
                if (icon) parent.removeChild(icon);
                return;
            }
            if (!icon) {
                icon = document.createElement('div');
                icon.className = iconClass;
                parent.insertBefore(icon, parent.firstChild);
            }
            if (icon.getAttribute('data-test-id') !== id + '-role-icon') {
                icon.setAttribute('data-test-id', id + '-role-icon');
            }
            const bottom = role.roleIconPosition === 'bottom';
            const style = {
                position: 'absolute', left: '50%',
                top: bottom ? '100%' : '0px',
                marginTop: (bottom ? role.roleIconMargin : -(role.roleIconSize + role.roleIconMargin)) + 'px',
                width: role.roleIconSize + 'px', height: role.roleIconSize + 'px',
                transform: 'translateX(-50%)',
                backgroundImage: 'url("' + role.roleIcon + '")',
                backgroundSize: 'contain', backgroundRepeat: 'no-repeat',
                backgroundPosition: 'center', pointerEvents: 'none', zIndex: '2'
            };
            Object.keys(style).forEach(function (key) { updateStyle(icon, key, style[key]); });
        });
    }

    function scheduleRender() {
        if (!alive || resourceId === null || !root || frame !== null) return;
        const owner = generation;
        frame = requestAnimationFrame(function () {
            if (alive && owner === generation) render();
        });
    }

    function validRole(role) {
        return role && typeof role === 'object' && !Array.isArray(role) &&
            typeof role.roleIcon === 'string' && role.roleIcon.indexOf('img://') === 0 &&
            typeof role.roleIconSize === 'number' && role.roleIconSize % 1 === 0 &&
            role.roleIconSize >= 8 && role.roleIconSize <= 64 &&
            typeof role.roleIconMargin === 'number' && role.roleIconMargin % 1 === 0 &&
            (role.roleIconPosition === 'top' || role.roleIconPosition === 'bottom');
    }

    function readPayload() {
        const subview = window.subViews.get(resourceId);
        if (!subview || !subview.model) return;
        let value;
        try {
            value = JSON.parse(subview.model.payload);
        } catch (error) {
            console.error('[DisplayTechTreeRoles] Invalid role payload', error);
            roles = {};
            scheduleRender();
            return;
        }
        if (value === null) {
            disconnectView();
            return;
        }
        if (typeof value !== 'object' || Array.isArray(value) ||
                Object.keys(value).some(function (id) { return !/^\d+$/.test(id) || !validRole(value[id]); })) {
            console.error('[DisplayTechTreeRoles] Invalid role payload shape');
            roles = {};
        } else {
            roles = value;
        }
        scheduleRender();
    }

    function onDataChanged(data, indexes, callbackIds) {
        if (callbackId !== null && callbackIds && callbackIds.indexOf(callbackId) !== -1) readPayload();
    }

    function findCarrier() {
        if (!alive || resourceId !== null) return;
        window.subViews.ids().forEach(function (id) {
            if (resourceId !== null) return;
            const subview = window.subViews.get(id);
            const model = subview && subview.model;
            if (!model || !model.ModInjectModel || model.ModInjectModel.name !== feature) return;
            resourceId = id;
            try {
                engine.on('subViews.onRemoved', onSubViewRemoved);
                removedSubscribed = true;
                engine.on('viewEnv.onDataChanged', onDataChanged);
                dataSubscribed = true;
                callbackId = viewEnv.addDataChangedCallback('model', id, true);
                rootAttempts = 0;
                readPayload();
            } catch (error) {
                disconnectView();
                console.error('[DisplayTechTreeRoles] Could not observe injection model', error);
            }
        });
    }

    function findRoot() {
        retry = null;
        if (!alive || resourceId === null || root) return;
        root = document.querySelector('[class^="App_"]');
        if (root) {
            const owner = generation;
            observer = new MutationObserver(function (records) {
                if (records.length && alive && owner === generation) scheduleRender();
            });
            observer.observe(root, {
                childList: true, subtree: true, attributes: true, attributeFilter: ['data-test-id']
            });
            scheduleRender();
        } else if (++rootAttempts === 50) {
            console.error('[DisplayTechTreeRoles] Tech tree DOM root not found');
        } else {
            const owner = generation;
            retry = setTimeout(function () {
                if (alive && owner === generation) findRoot();
            }, 100);
        }
    }

    function onSubViewAdded() {
        findCarrier();
        if (resourceId !== null && !root && retry === null && rootAttempts < 50) findRoot();
    }

    function onSubViewRemoved(ids) {
        if (resourceId !== null && ids.indexOf(resourceId) !== -1) disconnectView();
    }

    function dispose() {
        if (!alive) return;
        alive = false;
        if (addedSubscribed) engine.off('subViews.onAdded', onSubViewAdded);
        window.removeEventListener('unload', dispose);
        disconnectView();
        delete window[singleton];
    }

    window[singleton] = true;
    window.addEventListener('unload', dispose);
    engine.whenReady.then(function () {
        if (!alive) return;
        // The helper retains injected scripts after a child is detached.
        engine.on('subViews.onAdded', onSubViewAdded);
        addedSubscribed = true;
        onSubViewAdded();
    }).catch(function (error) {
        console.error('[DisplayTechTreeRoles] Gameface startup failed', error);
        dispose();
    });
}());
