(function () {
    const osmAttribution = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';
    const cartoAttribution = osmAttribution +
        ', &copy; <a href="https://carto.com/attribution/">CARTO</a>';

    window.ResQGridMaps = {
        addBasemaps: function (map) {
            const key = window.RESQGRID_CARTO_API_KEY || '';
            const osm = L.tileLayer(
                'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
                { attribution: osmAttribution, maxZoom: 19 }
            );
            const layers = { 'OpenStreetMap': osm };

            if (key) {
                const cartoUrl = function (style) {
                    return 'https://basemaps.cartocdn.com/' + style +
                        '/{z}/{x}/{y}.png?key=' + encodeURIComponent(key);
                };
                const cartoOptions = {
                    attribution: cartoAttribution,
                    maxZoom: 20,
                    maxNativeZoom: 18
                };
                layers['CARTO Voyager'] = L.tileLayer(
                    cartoUrl('rastertiles/voyager'), cartoOptions
                );
                layers['CARTO Positron'] = L.tileLayer(
                    cartoUrl('light_all'), cartoOptions
                );
                layers['CARTO Dark Matter'] = L.tileLayer(
                    cartoUrl('dark_all'), cartoOptions
                );
            }

            const defaultLayer = key ? layers['CARTO Voyager'] : osm;
            defaultLayer.addTo(map);
            L.control.layers(layers, null, { collapsed: true }).addTo(map);

            let failedLayer = null;
            const failedTiles = new WeakMap();
            let warningMessage;
            let retryButton;
            let switchButton;
            const warning = L.control({ position: 'topright' });

            warning.onAdd = function () {
                const container = L.DomUtil.create('div', 'leaflet-control map-tile-warning');
                container.setAttribute('role', 'status');
                container.setAttribute('aria-live', 'polite');
                container.hidden = true;
                warningMessage = L.DomUtil.create('span', 'map-tile-warning-message', container);
                const actions = L.DomUtil.create('div', 'map-tile-warning-actions', container);
                retryButton = L.DomUtil.create('button', 'btn btn-sm btn-outline-primary', actions);
                retryButton.type = 'button';
                retryButton.textContent = 'Retry';
                switchButton = L.DomUtil.create('button', 'btn btn-sm btn-outline-secondary', actions);
                switchButton.type = 'button';

                L.DomEvent.disableClickPropagation(container);
                L.DomEvent.on(retryButton, 'click', function () {
                    if (failedLayer) {
                        failedTiles.set(failedLayer, new Set());
                        failedLayer.redraw();
                    }
                });
                L.DomEvent.on(switchButton, 'click', function () {
                    const target = failedLayer === osm ? defaultLayer : osm;
                    if (target === failedLayer) {
                        return;
                    }
                    Object.keys(layers).forEach(function (name) {
                        if (map.hasLayer(layers[name])) {
                            map.removeLayer(layers[name]);
                        }
                    });
                    target.addTo(map);
                    failedLayer = null;
                    container.hidden = true;
                });
                return container;
            };
            warning.addTo(map);

            Object.keys(layers).forEach(function (name) {
                const layer = layers[name];
                failedTiles.set(layer, new Set());
                layer.on('tileerror', function (event) {
                    if (!map.hasLayer(layer)) {
                        return;
                    }
                    const coords = event.coords || {};
                    failedTiles.get(layer).add([coords.z, coords.x, coords.y].join('/'));
                    failedLayer = layer;
                    warningMessage.textContent = name + ' tiles could not be loaded. Retry or switch basemaps.';
                    retryButton.hidden = false;
                    switchButton.hidden = Object.keys(layers).length < 2;
                    switchButton.textContent = layer === osm
                        ? 'Switch to CARTO Voyager'
                        : 'Switch to OpenStreetMap';
                    warning.getContainer().hidden = false;
                });
                layer.on('tileload', function (event) {
                    const coords = event.coords || {};
                    failedTiles.get(layer).delete([coords.z, coords.x, coords.y].join('/'));
                    if (failedTiles.get(layer).size === 0 && failedLayer === layer) {
                        failedLayer = null;
                        warning.getContainer().hidden = true;
                    }
                });
            });

            map.on('baselayerchange', function () {
                failedLayer = null;
                warning.getContainer().hidden = true;
            });

            if (!key) {
                const notice = L.control({ position: 'bottomleft' });
                notice.onAdd = function () {
                    const container = L.DomUtil.create('div', 'leaflet-control map-provider-notice');
                    container.setAttribute('role', 'status');
                    container.textContent =
                        'CARTO key missing; using OpenStreetMap. Configure CARTO_API_KEY to enable CARTO.';
                    const closeButton = L.DomUtil.create(
                        'button', 'map-provider-notice-close', container
                    );
                    closeButton.type = 'button';
                    closeButton.setAttribute('aria-label', 'Dismiss basemap information');
                    closeButton.textContent = '×';
                    L.DomEvent.disableClickPropagation(container);
                    L.DomEvent.on(closeButton, 'click', function () {
                        container.hidden = true;
                    });
                    return container;
                };
                notice.addTo(map);
            }

            return layers;
        },

        watchResize: function (map) {
            const container = map.getContainer();
            const invalidateSize = function () {
                window.requestAnimationFrame(function () {
                    map.invalidateSize({ pan: false });
                });
            };
            if (window.ResizeObserver) {
                new ResizeObserver(invalidateSize).observe(container);
            }
            window.addEventListener('resize', invalidateSize, { passive: true });
            map.whenReady(function () {
                window.setTimeout(invalidateSize, 0);
            });
        }
    };
})();
