/*
 * Browser console recorder for the Virtual Fleet page.
 *
 * Paste this file into DevTools before clicking "Generate Scene".
 * Commands:
 *   virtualFleetRecorder.report()
 *   virtualFleetRecorder.download()
 *   virtualFleetRecorder.clear()
 *   virtualFleetRecorder.stop()
 */
(function installVirtualFleetRecorder() {
  if (window.virtualFleetRecorder) {
    console.warn("virtualFleetRecorder is already installed.");
    return;
  }

  var state = {
    startedAt: new Date().toISOString(),
    scenario: null,
    scenarioReady: null,
    firstBatch: null,
    batches: [],
  };

  function asArray(value) {
    return Array.isArray(value) ? value : [];
  }

  function poseCode(pose) {
    return String(
      pose && (pose.deviceCode || pose.code || pose.deviceId || pose.id) || "",
    ).toUpperCase();
  }

  function toPoseMap(poses) {
    var map = {};
    asArray(poses).forEach(function (pose) {
      var code = poseCode(pose);
      if (code) map[code] = pose;
    });
    return map;
  }

  function number(value) {
    var parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }

  function poseValues(pose) {
    if (!pose) return null;
    return {
      eastM: number(pose.eastM),
      northM: number(pose.northM),
      upM: number(pose.upM),
      headingDeg: number(pose.headingDeg),
    };
  }

  function distance(a, b) {
    if (!a || !b) return null;
    if (![a.eastM, a.northM, a.upM, b.eastM, b.northM, b.upM]
      .every(function (value) { return value !== null; })) return null;
    return Math.sqrt(
      Math.pow(b.eastM - a.eastM, 2)
      + Math.pow(b.northM - a.northM, 2)
      + Math.pow(b.upM - a.upM, 2),
    );
  }

  function headingDelta(a, b) {
    if (a === null || b === null) return null;
    return Math.abs((b - a + 180) % 360 - 180);
  }

  function extractCommand(message) {
    var payload = message && message.payload || {};
    if (payload.type && payload.payload) {
      return {
        type: String(payload.type),
        payload: payload.payload || {},
      };
    }
    return null;
  }

  function onMessage(event) {
    if (!event.data || event.data.source !== "unity-webgl") return;
    var message = event.data.message || event.data;
    if (!message || !message.type) return;

    if (message.type === "scenarioReady") {
      state.scenarioReady = message;
      return;
    }

    if (message.type !== "vueCommandReceived") return;
    var command = extractCommand(message);
    if (!command) return;

    if (command.type === "loadScenario") {
      state.scenario = {
        requestId: message.requestId || "",
        timestamp: message.timestamp || Date.now(),
        payload: command.payload,
      };
      return;
    }

    if (command.type !== "applyPoseBatch") return;
    var payload = command.payload || {};
    var poses = asArray(payload.vehicles)
      .concat(asArray(payload.targets))
      .concat(asArray(payload.poses));
    var batch = {
      requestId: message.requestId || "",
      sequence: number(payload.sequence),
      timestamp: message.timestamp || Date.now(),
      runId: payload.runId || "",
      poses: poses,
    };
    state.batches.push(batch);
    if (!state.firstBatch) state.firstBatch = batch;
  }

  function compare() {
    var initialPayload = state.scenario && state.scenario.payload || {};
    var initialMap = toPoseMap(initialPayload.initialPoses);
    var firstMap = toPoseMap(state.firstBatch && state.firstBatch.poses);
    var codes = {};
    Object.keys(initialMap).forEach(function (code) { codes[code] = true; });
    Object.keys(firstMap).forEach(function (code) { codes[code] = true; });

    return Object.keys(codes).sort().map(function (code) {
      var initial = poseValues(initialMap[code]);
      var first = poseValues(firstMap[code]);
      return {
        deviceCode: code,
        initial: initial,
        firstFrame: first,
        positionDeltaM: distance(initial, first),
        headingDeltaDeg: headingDelta(
          initial && initial.headingDeg,
          first && first.headingDeg,
        ),
        foundInFirstFrame: !!first,
      };
    });
  }

  function report() {
    var result = {
      startedAt: state.startedAt,
      scenarioRequestId: state.scenario && state.scenario.requestId || "",
      scenarioReadyRequestId: state.scenarioReady && state.scenarioReady.requestId || "",
      runId: state.scenario && state.scenario.payload
        ? state.scenario.payload.runId
        : "",
      uavCount: state.scenario && state.scenario.payload
        ? state.scenario.payload.uavCount
        : null,
      usvCount: state.scenario && state.scenario.payload
        ? state.scenario.payload.usvCount
        : null,
      initialPoseCount: state.scenario && state.scenario.payload
        ? asArray(state.scenario.payload.initialPoses).length
        : 0,
      batchCount: state.batches.length,
      firstSequence: state.firstBatch && state.firstBatch.sequence,
      comparisons: compare(),
    };
    console.table(result.comparisons);
    console.log("[VirtualFleetRecorder]", result);
    return result;
  }

  function download() {
    var result = report();
    var jsonBlob = new Blob(
      [JSON.stringify(result, null, 2)],
      { type: "application/json;charset=utf-8" },
    );
    var jsonUrl = URL.createObjectURL(jsonBlob);
    var jsonLink = document.createElement("a");
    jsonLink.href = jsonUrl;
    jsonLink.download = "virtual-fleet-pose-comparison.json";
    jsonLink.click();
    URL.revokeObjectURL(jsonUrl);

    var rows = result.comparisons.map(function (item) {
      return [
        item.deviceCode,
        item.initial && item.initial.eastM,
        item.initial && item.initial.northM,
        item.initial && item.initial.upM,
        item.firstFrame && item.firstFrame.eastM,
        item.firstFrame && item.firstFrame.northM,
        item.firstFrame && item.firstFrame.upM,
        item.positionDeltaM,
        item.headingDeltaDeg,
        item.foundInFirstFrame,
      ];
    });
    var csv = [
      [
        "deviceCode",
        "initialEastM",
        "initialNorthM",
        "initialUpM",
        "firstEastM",
        "firstNorthM",
        "firstUpM",
        "positionDeltaM",
        "headingDeltaDeg",
        "foundInFirstFrame",
      ],
    ].concat(rows).map(function (row) {
      return row.map(function (value) {
        return JSON.stringify(value == null ? "" : value);
      }).join(",");
    }).join("\n");
    var csvBlob = new Blob(["\ufeff" + csv], { type: "text/csv;charset=utf-8" });
    var csvUrl = URL.createObjectURL(csvBlob);
    var csvLink = document.createElement("a");
    csvLink.href = csvUrl;
    csvLink.download = "virtual-fleet-pose-comparison.csv";
    csvLink.click();
    URL.revokeObjectURL(csvUrl);
  }

  function clear() {
    state.startedAt = new Date().toISOString();
    state.scenario = null;
    state.scenarioReady = null;
    state.firstBatch = null;
    state.batches = [];
    console.log("[VirtualFleetRecorder] cleared");
  }

  window.addEventListener("message", onMessage);
  window.virtualFleetRecorder = {
    report: report,
    download: download,
    clear: clear,
    stop: function () {
      window.removeEventListener("message", onMessage);
      delete window.virtualFleetRecorder;
      console.log("[VirtualFleetRecorder] stopped");
    },
  };
  console.log(
    "[VirtualFleetRecorder] installed. Run virtualFleetRecorder.report() after the first algorithm frame.",
  );
})();
