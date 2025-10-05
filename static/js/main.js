// Initialize Leaflet maps when accordion items are shown and for the picker
(function () {
  function initPlaceMap(container) {
    const lat = parseFloat(container.dataset.lat);
    const lng = parseFloat(container.dataset.lng);
    const map = L.map(container).setView([lat, lng], 16);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19,
      attribution: '&copy; OpenStreetMap contributors'
    }).addTo(map);
    L.marker([lat, lng]).addTo(map);
    // Defer invalidate to handle container layout changes
    setTimeout(() => {
      map.invalidateSize();
      map.setView([lat, lng], 16);
    }, 200);
    return map;
  }

  function initPickerMap(container) {
    const latInput = document.getElementById('latitude');
    const lngInput = document.getElementById('longitude');
    const startLat = parseFloat(container.dataset.lat) || 51.3811; // Bath
    const startLng = parseFloat(container.dataset.lng) || -2.3590;
    const map = L.map(container).setView([startLat, startLng], 14);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19,
      attribution: '&copy; OpenStreetMap contributors'
    }).addTo(map);

    let marker = null;
    function setMarker(lat, lng) {
      if (marker) map.removeLayer(marker);
      marker = L.marker([lat, lng]).addTo(map);
      latInput.value = lat.toFixed(6);
      lngInput.value = lng.toFixed(6);
    }

    map.on('click', function (e) {
      setMarker(e.latlng.lat, e.latlng.lng);
    });
  }

  function getDirections(from, to, mapContainer) {
    // Simple directions using OSRM demo server; no API key required
    const url = `https://router.project-osrm.org/route/v1/foot/${from.lng},${from.lat};${to.lng},${to.lat}?overview=full&geometries=geojson`;
    fetch(url).then(r => r.json()).then(data => {
      if (!data.routes || !data.routes[0]) {
        alert('No walking route found.');
        return;
      }
      const coords = data.routes[0].geometry.coordinates.map(([x, y]) => [y, x]);
      const map = mapContainer._leaflet_map || initPlaceMap(mapContainer);
      mapContainer._leaflet_map = map;
      if (map._routeLine) {
        map.removeLayer(map._routeLine);
      }
      map._routeLine = L.polyline(coords, { color: 'blue' }).addTo(map);
      map.fitBounds(map._routeLine.getBounds(), { padding: [20, 20] });
    }).catch(() => alert('Failed to fetch directions.'));
  }

  document.addEventListener('DOMContentLoaded', () => {
    // Picker map
    const picker = document.getElementById('picker-map');
    if (picker) initPickerMap(picker);

    // Initialize maps on accordion show
    const accordion = document.getElementById('placesAccordion');
    if (!accordion) return;

    // When the main accordion for a place opens, prep the map
    accordion.addEventListener('shown.bs.collapse', (ev) => {
      const body = ev.target.querySelector('.accordion-body');
      const map = body && body.querySelector('.map');
      if (map && !map.dataset.initialized) {
        const m = initPlaceMap(map);
        map._leaflet_map = m;
        map.dataset.initialized = '1';
      }
    });

    // When the inner "Show map & directions" collapse opens, ensure map is initialized and centered
    accordion.addEventListener('shown.bs.collapse', (ev) => {
      const mapCollapse = ev.target.closest('.place-map-collapse');
      if (!mapCollapse) return;
      const mapEl = mapCollapse.querySelector('.map');
      if (!mapEl) return;
      if (!mapEl.dataset.initialized) {
        const m = initPlaceMap(mapEl);
        mapEl._leaflet_map = m;
        mapEl.dataset.initialized = '1';
      } else if (mapEl._leaflet_map) {
        const lat = parseFloat(mapEl.dataset.lat);
        const lng = parseFloat(mapEl.dataset.lng);
        setTimeout(() => {
          mapEl._leaflet_map.invalidateSize();
          mapEl._leaflet_map.setView([lat, lng], 16);
        }, 50);
      }
    });

    // Directions buttons
    accordion.addEventListener('click', (ev) => {
      const btn = ev.target.closest('.get-directions');
      if (!btn) return;
      const target = { lat: parseFloat(btn.dataset.lat), lng: parseFloat(btn.dataset.lng) };
      const panel = btn.closest('.accordion-body');
      const map = panel.querySelector('.map');
      if (!navigator.geolocation) {
        alert('Geolocation is not supported by your browser.');
        return;
      }
      navigator.geolocation.getCurrentPosition((pos) => {
        const from = { lat: pos.coords.latitude, lng: pos.coords.longitude };
        getDirections(from, target, map);
      }, () => alert('Location permission denied or unavailable.'));
    });
  });
})();
