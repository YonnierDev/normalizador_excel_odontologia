// ==UserScript==
// @name         DentOS - Exportar Listado de Pagos (Dia/Semana)
// @namespace    yonnier.dentos
// @version      1.0.0
// @description  Exporta Listado de pagos por dia o semana (Lun-Sab) en JSON
// @match        https://previred.clinicos.co/cuadrecaja/*
// @grant        none
// @run-at       document-idle
// ==/UserScript==

(function () {
  "use strict";

  // ===== Config =====
  const DIAS_HABILES_SEMANA = 6; // Lun-Sab
  const AUTO_AVANZAR_FECHA_TRAS_EXPORT_DIA = false;
  const ESPERA_CORTA_MS = 400;
  const SCROLL_WAIT_MS = 250;
  const SCROLL_MAX_STEPS = 40;
  const ESPERA_ENTRE_DESCARGAS_MS = 1200;
  const TIMEOUT_ACCION_MS = 20000;
  const TIMEOUT_TABLA_MS = 20000;

  let busy = false;

  function log(...args) {
    console.log("[DentOS Export]", ...args);
  }

  function sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  async function waitFor(checkFn, opts = {}) {
    const timeout = opts.timeout || TIMEOUT_ACCION_MS;
    const interval = opts.interval || 250;
    const label = opts.label || "condicion";
    const start = Date.now();

    while (Date.now() - start < timeout) {
      try {
        if (checkFn()) return true;
      } catch (_) {
        // no-op
      }
      await sleep(interval);
    }
    throw new Error(`Timeout esperando: ${label}`);
  }

  function cleanText(s) {
    return (s || "").replace(/\s+/g, " ").trim();
  }

  function keyText(s) {
    return cleanText(s)
      .toLowerCase()
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "");
  }

  function parseFechaDDMMYYYY(s) {
    const m = cleanText(s).match(/^(\d{2})\/(\d{2})\/(\d{4})$/);
    if (!m) return null;
    const d = Number(m[1]), mo = Number(m[2]), y = Number(m[3]);
    return new Date(y, mo - 1, d);
  }

  function formatFechaDDMMYYYY(date) {
    const d = String(date.getDate()).padStart(2, "0");
    const m = String(date.getMonth() + 1).padStart(2, "0");
    const y = date.getFullYear();
    return `${d}/${m}/${y}`;
  }

  function formatFechaISO(date) {
    const d = String(date.getDate()).padStart(2, "0");
    const m = String(date.getMonth() + 1).padStart(2, "0");
    const y = date.getFullYear();
    return `${y}-${m}-${d}`;
  }

  function monthTag(date) {
    return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}`;
  }

  function nombreDia(date) {
    const dias = ["Domingo", "Lunes", "Martes", "Miercoles", "Jueves", "Viernes", "Sabado"];
    return dias[date.getDay()] || "";
  }

  function isSunday(date) {
    return date.getDay() === 0;
  }

  function nextHabil(date) {
    const d = new Date(date);
    d.setDate(d.getDate() + 1);
    while (isSunday(d)) d.setDate(d.getDate() + 1);
    return d;
  }

  function addHabilDays(startDate, dias) {
    const d = new Date(startDate);
    let count = 0;
    while (count < dias) {
      d.setDate(d.getDate() + 1);
      if (!isSunday(d)) count += 1;
    }
    return d;
  }

  function endOfWeekSaturday(date) {
    const d = new Date(date);
    const day = d.getDay(); // 0=Dom,1=Lun,...,6=Sab
    let add = 6 - day;
    if (day === 0) add = 6; // domingo -> sabado siguiente
    d.setDate(d.getDate() + add);
    return d;
  }

  function getFechaInput() {
    return document.querySelector('input[name="fecha"]');
  }

  function setFechaInput(date) {
    const input = getFechaInput();
    if (!input) throw new Error("No se encontro input fecha");
    const value = formatFechaDDMMYYYY(date);
    // Simula el flujo visual: abrir selector de fecha antes de asignar.
    const pickLink = document.querySelector("a.dp-choose-date");
    if (pickLink) pickLink.click();
    input.value = value;
    input.dispatchEvent(new Event("input", { bubbles: true }));
    input.dispatchEvent(new Event("change", { bubbles: true }));
    input.dispatchEvent(new Event("blur", { bubbles: true }));
    log("Fecha seteada:", value);
  }

  function clickMostrar() {
    const btn =
      document.querySelector('input[name="btmostrar"]') ||
      Array.from(document.querySelectorAll("input[type='button'],button"))
        .find((b) => cleanText(b.value || b.textContent).toLowerCase() === "mostrar");

    if (!btn) throw new Error("No se encontro boton Mostrar");
    btn.click();
    log("Click Mostrar");
  }

  function hasResumenODetallesLinks() {
    return Array.from(document.querySelectorAll("a")).some((a) => {
      const txt = keyText(a.textContent);
      return txt === "resumen" || txt === "detalles";
    });
  }

  function getFirstListadoDate() {
    const table = findListadoTable();
    if (!table) return "";
    const firstRow = table.querySelectorAll("tr")[1];
    if (!firstRow) return "";
    const cells = firstRow.querySelectorAll("td");
    if (cells.length < 3) return "";
    return cleanText(cells[2].textContent);
  }

  async function clickMostrarAndWait(expectedDate) {
    clickMostrar();
    await waitFor(() => hasResumenODetallesLinks() || !!findListadoTable(), {
      label: "respuesta luego de Mostrar",
      timeout: TIMEOUT_ACCION_MS
    });
    if (expectedDate) {
      await waitFor(
        () => !findListadoTable() || getFirstListadoDate() === expectedDate,
        { label: `actualizacion de fecha ${expectedDate}`, timeout: TIMEOUT_ACCION_MS }
      );
    }
    await sleep(ESPERA_CORTA_MS);
  }

  function clickDetallesIfNeeded() {
    const detalleLink = Array.from(document.querySelectorAll("a"))
      .find((a) => keyText(a.textContent) === "detalles");
    if (detalleLink) {
      detalleLink.click();
      log("Click Detalles");
      return true;
    }
    return false;
  }

  async function clickDetallesAndWaitTable(expectedDate) {
    const clicked = clickDetallesIfNeeded();
    if (!clicked && findListadoTable()) {
      if (!expectedDate || getFirstListadoDate() === expectedDate) return;
    }
    await waitFor(() => {
      if (!findListadoTable()) return false;
      if (!expectedDate) return true;
      return getFirstListadoDate() === expectedDate;
    }, {
      timeout: TIMEOUT_TABLA_MS,
      label: expectedDate ? `tabla "Listado de pagos" con fecha ${expectedDate}` : 'tabla "Listado de pagos"'
    });
  }

  async function forceScrollListado() {
    const root = document.scrollingElement || document.documentElement;
    if (!root) return;

    let lastHeight = -1;
    let stableCount = 0;

    for (let i = 0; i < SCROLL_MAX_STEPS; i += 1) {
      root.scrollTop = root.scrollHeight;
      await sleep(SCROLL_WAIT_MS);

      const currentHeight = root.scrollHeight;
      if (currentHeight === lastHeight) {
        stableCount += 1;
      } else {
        stableCount = 0;
      }
      lastHeight = currentHeight;

      if (stableCount >= 2) break;
    }

    // Regresa cerca de la tabla para mantener contexto visual en pantalla.
    const table = findListadoTable();
    if (table) {
      table.scrollIntoView({ behavior: "auto", block: "start" });
      await sleep(SCROLL_WAIT_MS);
    }
    log("Scroll obligatorio completado para validar carga de filas");
  }

  function findListadoTable() {
    const tables = Array.from(document.querySelectorAll("#cuadre_caja_detallado table, table"));
    for (const table of tables) {
      const heads = Array.from(table.querySelectorAll("tr:first-child td, tr:first-child th"))
        .map((x) => keyText(x.textContent));
      if (
        heads.length >= 5 &&
        heads[0].includes("codigo tipo doc") &&
        heads[1].includes("tipo de doc") &&
        heads[2].includes("fecha") &&
        heads[3].includes("tercero") &&
        heads[4].includes("valor")
      ) {
        return table;
      }
    }
    return null;
  }

  async function waitForListadoTable(timeoutMs = TIMEOUT_TABLA_MS) {
    const start = Date.now();
    while (Date.now() - start < timeoutMs) {
      const table = findListadoTable();
      if (table) return table;
      await sleep(300);
    }
    throw new Error('Timeout esperando tabla "Listado de pagos"');
  }

  function parseCOP(valueText) {
    const n = cleanText(valueText).replace(/,/g, "");
    const v = Number.parseFloat(n);
    return Number.isFinite(v) ? Math.round(v) : 0;
  }

  function extractListado(table) {
    const rows = Array.from(table.querySelectorAll("tr")).slice(1);
    const listado = [];

    for (const tr of rows) {
      const td = tr.querySelectorAll("td");
      if (td.length < 5) continue;

      const codigo_tipo_doc = cleanText(td[0].textContent);
      const tipo_doc = cleanText(td[1].textContent);
      const fecha = cleanText(td[2].textContent);
      const tercero = cleanText(td[3].textContent);
      const valor_raw = cleanText(td[4].textContent);
      const valor = parseCOP(valor_raw);

      listado.push({ codigo_tipo_doc, tipo_doc, fecha, tercero, valor, valor_raw });
    }

    return listado;
  }

  function downloadJSON(payload, filename) {
    const content = JSON.stringify(payload, null, 2);
    const blob = new Blob([content], { type: "application/json;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    try {
      const a = document.createElement("a");
      a.style.display = "none";
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      log(`Descarga solicitada: ${filename}`);
    } catch (e) {
      console.error("Fallo descarga por anchor, abriendo respaldo en nueva pestana.", e);
      const dataUrl = `data:application/json;charset=utf-8,${encodeURIComponent(content)}`;
      window.open(dataUrl, "_blank");
      alert("No se pudo descargar automatico. Se abrio el JSON en una pestana para guardarlo manualmente.");
    } finally {
      setTimeout(() => URL.revokeObjectURL(url), 1500);
    }
  }

  async function exportDia(dateObj, source = "dia", batchMeta = null) {
    const targetDate = formatFechaDDMMYYYY(dateObj);
    log(`Procesando: ${targetDate} (${nombreDia(dateObj)})`);
    setFechaInput(dateObj);
    await clickMostrarAndWait(targetDate);
    await clickDetallesAndWaitTable(targetDate);
    await forceScrollListado();

    const table = await waitForListadoTable();
    const listado = extractListado(table);
    const total = listado.reduce((acc, r) => acc + r.valor, 0);
    const iso = formatFechaISO(dateObj);

    const payload = {
      fuente: "DentOS/cuadrecaja",
      modo: source,
      destino_sugerido: "export_json/facturacion_json",
      fecha_consulta: formatFechaDDMMYYYY(dateObj),
      fecha_iso: iso,
      mes_tag: monthTag(dateObj),
      semana_rango: batchMeta ? batchMeta.weekRange : null,
      extraido_en: new Date().toISOString(),
      registros: listado.length,
      total_valor: total,
      listado_pagos: listado
    };

    let fileName = `listado_pagos_${iso}.json`;
    if (source === "semana" && batchMeta) {
      fileName = `listado_pagos_${batchMeta.weekRange}_${iso}.json`;
    }
    downloadJSON(payload, fileName);
    log(`Exportado ${fileName} | registros=${listado.length} | total=${total}`);
  }

  async function exportarDiaEnVistaActual() {
    // Modo manual: no cambia fecha ni hace click en Mostrar.
    await clickDetallesAndWaitTable(null);
    await forceScrollListado();

    const table = await waitForListadoTable();
    const listado = extractListado(table);
    const total = listado.reduce((acc, r) => acc + r.valor, 0);
    if (!listado.length) throw new Error("Listado de pagos vacio en la vista actual");

    const fechaTexto = cleanText(listado[0].fecha);
    const fechaObj = parseFechaDDMMYYYY(fechaTexto);
    if (!fechaObj) throw new Error(`Fecha invalida en tabla: ${fechaTexto}`);
    const iso = formatFechaISO(fechaObj);

    const payload = {
      fuente: "DentOS/cuadrecaja",
      modo: "dia",
      destino_sugerido: "export_json/facturacion_json",
      fecha_consulta: fechaTexto,
      fecha_iso: iso,
      mes_tag: monthTag(fechaObj),
      semana_rango: null,
      extraido_en: new Date().toISOString(),
      registros: listado.length,
      total_valor: total,
      listado_pagos: listado
    };

    const fileName = `listado_pagos_${iso}.json`;
    downloadJSON(payload, fileName);
    log(`Exportado (vista actual) ${fileName} | registros=${listado.length} | total=${total}`);
  }

  async function exportarDiaActual() {
    if (busy) return;
    busy = true;
    try {
      await exportarDiaEnVistaActual();
      alert("Exportar dia: OK");
    } catch (e) {
      console.error(e);
      alert(`Error exportar dia: ${e.message}`);
    } finally {
      busy = false;
    }
  }

  async function exportarSemanaDesdeFechaActual() {
    if (busy) return;
    busy = true;
    try {
      const input = getFechaInput();
      if (!input) throw new Error("No se encontro input fecha");
      let date = parseFechaDDMMYYYY(input.value);
      if (!date) throw new Error(`Fecha invalida en input: ${input.value}`);

      if (isSunday(date)) date = nextHabil(date);
      const weekEnd = endOfWeekSaturday(date);
      const weekRange = `${formatFechaISO(date)}_a_${formatFechaISO(weekEnd)}`;
      const batchMeta = { weekRange };
      log(`Semana objetivo: ${weekRange}`);

      let procesados = 0;
      while (date <= weekEnd) {
        if (isSunday(date)) {
          date = nextHabil(date);
          if (date > weekEnd) break;
        }
        log(`Inicio dia ${procesados + 1}: ${formatFechaDDMMYYYY(date)} (${nombreDia(date)})`);
        await exportDia(date, "semana", batchMeta);
        procesados += 1;
        await sleep(ESPERA_ENTRE_DESCARGAS_MS);
        date = nextHabil(date);
        if (date <= weekEnd) {
          log(`Siguiente fecha habil: ${formatFechaDDMMYYYY(date)} (${nombreDia(date)})`);
        }
      }

      alert(`Exportar semana: OK (${procesados} dias)`);
    } catch (e) {
      console.error(e);
      alert(`Error exportar semana: ${e.message}`);
    } finally {
      busy = false;
    }
  }

  function addUI() {
    if (document.getElementById("dentos-export-ui")) return;

    const box = document.createElement("div");
    box.id = "dentos-export-ui";
    box.style.position = "fixed";
    box.style.right = "16px";
    box.style.bottom = "16px";
    box.style.zIndex = "999999";
    box.style.display = "flex";
    box.style.gap = "8px";
    box.style.flexDirection = "column";

    const btnDia = document.createElement("button");
    btnDia.textContent = "Exportar dia";
    btnDia.style.cssText = "padding:10px 12px;border:none;border-radius:8px;background:#1a73e8;color:#fff;font-weight:700;cursor:pointer;";
    btnDia.addEventListener("click", exportarDiaActual);

    const btnSemana = document.createElement("button");
    btnSemana.textContent = "Exportar semana";
    btnSemana.style.cssText = "padding:10px 12px;border:none;border-radius:8px;background:#0f9d58;color:#fff;font-weight:700;cursor:pointer;";
    btnSemana.addEventListener("click", exportarSemanaDesdeFechaActual);

    box.appendChild(btnDia);
    box.appendChild(btnSemana);
    document.body.appendChild(box);
  }

  addUI();
})();
