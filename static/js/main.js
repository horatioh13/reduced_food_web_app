// Initialize Leaflet maps when accordion items are shown and for the picker
(function () {
  // Create a tile layer used everywhere
  function createTileLayer() {
    return L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19,
      attribution: '&copy; OpenStreetMap contributors'
    });
  }

  function initTinyMap(el, lat, lng, zoom) {
    const map = L.map(el).setView([lat, lng], zoom || 16);
    createTileLayer().addTo(map);
    L.marker([lat, lng]).addTo(map);
    // ensure correct sizing when shown in collapses
    setTimeout(() => { map.invalidateSize(); map.setView([lat, lng], zoom || 16); }, 150);
    return map;
  }

  function initPicker(el) {
    const latInput = document.getElementById('latitude');
    const lngInput = document.getElementById('longitude');
    const lat = parseFloat(el.dataset.lat) || 51.3811;
    const lng = parseFloat(el.dataset.lng) || -2.3590;
    const map = L.map(el).setView([lat, lng], 14);
    createTileLayer().addTo(map);
    let marker = null;
    map.on('click', e => {
      if (marker) map.removeLayer(marker);
      marker = L.marker(e.latlng).addTo(map);
      latInput.value = e.latlng.lat.toFixed(6);
      lngInput.value = e.latlng.lng.toFixed(6);
    });
    return map;
  }

  function fetchAndDrawRoute(map, from, to) {
    const url = `https://router.project-osrm.org/route/v1/foot/${from.lng},${from.lat};${to.lng},${to.lat}?overview=full&geometries=geojson`;
    return fetch(url).then(r => r.json()).then(data => {
      if (!data.routes || !data.routes[0]) throw new Error('no route');
      const coords = data.routes[0].geometry.coordinates.map(([x, y]) => [y, x]);
      if (map._routeLine) map.removeLayer(map._routeLine);
      map._routeLine = L.polyline(coords, { color: 'blue' }).addTo(map);
      map.fitBounds(map._routeLine.getBounds(), { padding: [20, 20] });
    });
  }

  document.addEventListener('DOMContentLoaded', () => {
    // Init any picker map
    document.querySelectorAll('.map-picker').forEach(el => {
      if (!el.dataset.initialized) { initPicker(el); el.dataset.initialized = '1'; }
    });

    // Init small place maps lazily when accordion inner collapse opens
    const accordion = document.getElementById('placesAccordion');
    if (accordion) {
      accordion.addEventListener('shown.bs.collapse', ev => {
        // show map inside opened panel
        const mapEl = ev.target.querySelector('.map');
        if (!mapEl) return;
        if (!mapEl.dataset.initialized) {
          const lat = parseFloat(mapEl.dataset.lat);
          const lng = parseFloat(mapEl.dataset.lng);
          const m = initTinyMap(mapEl, lat, lng, 16);
          mapEl._leaflet_map = m;
          mapEl.dataset.initialized = '1';
        } else if (mapEl._leaflet_map) {
          setTimeout(() => { mapEl._leaflet_map.invalidateSize(); }, 50);
        }
      });

      // handle directions button (event delegation)
      accordion.addEventListener('click', ev => {
        const btn = ev.target.closest('.get-directions');
        if (!btn) return;
        const target = { lat: parseFloat(btn.dataset.lat), lng: parseFloat(btn.dataset.lng) };
        const panel = btn.closest('.accordion-body');
        const mapEl = panel.querySelector('.map');
        if (!navigator.geolocation) { alert('Geolocation not supported.'); return; }
        navigator.geolocation.getCurrentPosition(pos => {
          const from = { lat: pos.coords.latitude, lng: pos.coords.longitude };
          // ensure map exists
          let map = (mapEl && mapEl._leaflet_map) || (mapEl && initTinyMap(mapEl, target.lat, target.lng, 13));
          if (mapEl && !mapEl._leaflet_map) mapEl._leaflet_map = map;
          fetchAndDrawRoute(map, from, target).catch(() => alert('Failed to fetch directions.'));
        }, () => alert('Location permission denied or unavailable.'));
      });
    }
  });
})();
