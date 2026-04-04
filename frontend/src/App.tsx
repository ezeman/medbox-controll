import { useEffect, useMemo, useRef, useState } from "react";

type Slot = {
  id: number;
  status: string;
  station_code: string | null;
  item_count: number;
};

type ScanItem = {
  id: number;
  item_id: string;
  drug_code: string;
  hn: string;
  station_code: string;
  bed_no: string | null;
  scanned_at: string;
};

type RelayOpenResult = {
  slot_id: number;
  status: string;
  relay_result: string;
};

type ScanHistoryRow = {
  id: number;
  slot_id: number;
  batch_id: number;
  item_id: string;
  drug_code: string;
  hn: string;
  station_code: string;
  bed_no: string | null;
  qty: number;
  scanned_at: string;
};

type MissionHistoryRow = {
  id: number;
  slot_id: number;
  batch_id: number;
  station_code: string;
  status: string;
  robot_mission_id: string | null;
  created_at: string;
};

type RemovalHistoryRow = {
  id: number;
  slot_id: number;
  batch_id: number;
  item_id: string;
  drug_code: string;
  hn: string;
  station_code: string;
  removed_by: string;
  removed_at: string;
};

type RobotConfig = {
  robot_ip: string | null;
  robot_api_url: string | null;
};

type AppTab = "operation" | "history" | "settings";

const RAW_API_BASE = import.meta.env.VITE_API_BASE || "";
const API_BASE = RAW_API_BASE.endsWith("/") ? RAW_API_BASE.slice(0, -1) : RAW_API_BASE;
const ANSI_ESCAPE_PATTERN = /\u001b\[[0-?]*[ -/]*[@-~]|\u001bO./g;
const DISALLOWED_CONTROL_PATTERN = /[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/g;
const AUTO_SEND_IDLE_MS = 350;

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers || {}),
    },
    ...init,
  });

  const contentType = response.headers.get("content-type") || "";
  const isJson = contentType.includes("application/json");

  if (!response.ok) {
    if (isJson) {
      const body = await response.json().catch(() => ({ detail: "Request failed" }));
      throw new Error(body.detail || "Request failed");
    }

    const bodyText = await response.text().catch(() => "");
    const hasHtmlBody = /^\s*<!doctype html>/i.test(bodyText);
    if (hasHtmlBody) {
      throw new Error("API endpoint returned HTML. Check backend URL/proxy settings.");
    }

    throw new Error(`Request failed (${response.status})`);
  }

  if (!isJson) {
    throw new Error("API response is not JSON. Check backend URL/proxy settings.");
  }

  return response.json();
}

function ajax<T>(path: string, method: string, body?: unknown): Promise<T> {
  return new Promise((resolve, reject) => {
    const request = new XMLHttpRequest();
    request.open(method, `${API_BASE}${path}`);
    request.responseType = "json";
    request.setRequestHeader("Content-Type", "application/json");

    request.onload = () => {
      const contentType = request.getResponseHeader("content-type") || "";
      const isJson = contentType.includes("application/json");
      const responseBody = isJson ? request.response : null;

      if (request.status >= 200 && request.status < 300) {
        if (!isJson) {
          reject(new Error("API response is not JSON. Check backend URL/proxy settings."));
          return;
        }
        resolve(responseBody as T);
        return;
      }

      const detail = typeof responseBody === "object" && responseBody && "detail" in responseBody
        ? String((responseBody as { detail?: string }).detail || "Request failed")
        : "Request failed";
      reject(new Error(detail));
    };

    request.onerror = () => {
      reject(new Error("Network error"));
    };

    request.send(body ? JSON.stringify(body) : null);
  });
}

function normalizeScannerPayload(raw: string): string {
  return raw
    .replace(ANSI_ESCAPE_PATTERN, "")
    .replace(DISALLOWED_CONTROL_PATTERN, "")
    .replace(/\r/g, "")
    .trim();
}

export function App() {
  const [slots, setSlots] = useState<Slot[]>([]);
  const [selectedSlot, setSelectedSlot] = useState<number | null>(null);
  const [items, setItems] = useState<ScanItem[]>([]);
  const [scanHistory, setScanHistory] = useState<ScanHistoryRow[]>([]);
  const [missionHistory, setMissionHistory] = useState<MissionHistoryRow[]>([]);
  const [removalHistory, setRemovalHistory] = useState<RemovalHistoryRow[]>([]);
  const [activeTab, setActiveTab] = useState<AppTab>("operation");
  const [robotIp, setRobotIp] = useState("");
  const [robotApiUrl, setRobotApiUrl] = useState("");
  const [configBusy, setConfigBusy] = useState(false);
  const [scanBuffer, setScanBuffer] = useState("");
  const [message, setMessage] = useState("Ready");
  const [busy, setBusy] = useState(false);
  const scanInputRef = useRef<HTMLTextAreaElement | null>(null);
  const scanOutInputRef = useRef<HTMLInputElement | null>(null);
  const selectedSlotRef = useRef<number | null>(null);
  const activeTabRef = useRef<AppTab>("operation");
  const scanBufferRef = useRef("");
  const busyRef = useRef(false);
  const autoSendTimerRef = useRef<number | null>(null);

  const focusScanInput = (attempt = 0) => {
    window.requestAnimationFrame(() => {
      const input = scanInputRef.current;
      if (!input) {
        return;
      }

      if (input.disabled) {
        if (attempt < 8) {
          window.setTimeout(() => focusScanInput(attempt + 1), 40);
        }
        return;
      }

      input.focus({ preventScroll: true });
      const end = input.value.length;
      input.setSelectionRange(end, end);
    });
  };

  const onClearScanBuffer = () => {
    if (autoSendTimerRef.current !== null) {
      window.clearTimeout(autoSendTimerRef.current);
      autoSendTimerRef.current = null;
    }
    scanBufferRef.current = "";
    setScanBuffer("");
    focusScanInput();
  };

  const appendToScanTextarea = (chunk: string) => {
    scanBufferRef.current = `${scanBufferRef.current}${chunk}`;
    setScanBuffer(scanBufferRef.current);
  };

  const submitScanPayload = async (slotId: number, qrRaw: string) => {
    setBusy(true);
    busyRef.current = true;
    try {
      const result = await ajax<{ item_id: string; station_code: string }>(`/api/slots/${slotId}/scan`, "POST", {
        qr_raw: qrRaw,
      });
      scanBufferRef.current = "";
      setScanBuffer("");
      await Promise.all([reloadSlots(), reloadItems(slotId)]);
      setMessage(`Added ${result.item_id} (${result.station_code})`);
      focusScanInput();
    } catch (error) {
      setMessage((error as Error).message);
    } finally {
      setBusy(false);
      busyRef.current = false;
    }
  };

  const scheduleAutoSend = () => {
    if (autoSendTimerRef.current !== null) {
      window.clearTimeout(autoSendTimerRef.current);
    }

    autoSendTimerRef.current = window.setTimeout(() => {
      autoSendTimerRef.current = null;

      if (busyRef.current) {
        return;
      }

      const slotId = selectedSlotRef.current;
      const qrRaw = normalizeScannerPayload(scanBufferRef.current);
      if (!slotId || !qrRaw) {
        return;
      }

      void submitScanPayload(slotId, qrRaw);
    }, AUTO_SEND_IDLE_MS);
  };

  const preventNativeScannerTextareaBehavior = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
    event.preventDefault();
  };

  const preventNativeScannerPaste = (event: React.ClipboardEvent<HTMLTextAreaElement>) => {
    event.preventDefault();
  };

  const selectedData = useMemo(
    () => slots.find((slot) => slot.id === selectedSlot) || null,
    [slots, selectedSlot]
  );
  const currentTab: AppTab = activeTab;

  const reloadSlots = async () => {
    const data = await api<Slot[]>("/api/slots");
    setSlots(data);
  };

  const reloadItems = async (slotId: number) => {
    const data = await api<ScanItem[]>(`/api/slots/${slotId}/items`);
    setItems(data);
  };

  const reloadHistory = async () => {
    const [scans, missions, removals] = await Promise.all([
      api<ScanHistoryRow[]>("/api/history/scans?limit=30"),
      api<MissionHistoryRow[]>("/api/history/missions?limit=30"),
      api<RemovalHistoryRow[]>("/api/history/removals?limit=30"),
    ]);
    setScanHistory(scans);
    setMissionHistory(missions);
    setRemovalHistory(removals);
  };

  const reloadRobotConfig = async () => {
    const config = await api<RobotConfig>("/api/config/robot");
    setRobotIp(config.robot_ip || "");
    setRobotApiUrl(config.robot_api_url || "");
  };

  const onSelectSlot = async (slotId: number) => {
    const previousSelectedSlot = selectedSlot;
    setBusy(true);
    busyRef.current = true;
    if (autoSendTimerRef.current !== null) {
      window.clearTimeout(autoSendTimerRef.current);
      autoSendTimerRef.current = null;
    }
    setSelectedSlot(slotId);
    selectedSlotRef.current = slotId;
    setMessage(`Slot ${slotId} selected`);
    try {
      await api(`/api/slots/${slotId}/select`, { method: "POST" });
      await Promise.all([reloadSlots(), reloadItems(slotId)]);
      setMessage(`Slot ${slotId} selected`);
      focusScanInput();
    } catch (error) {
      setSelectedSlot(previousSelectedSlot);
      selectedSlotRef.current = previousSelectedSlot;
      setMessage((error as Error).message);
    } finally {
      setBusy(false);
      busyRef.current = false;
    }
  };

  const onScanSubmit = async () => {
    const slotId = selectedSlotRef.current;
    if (!slotId) {
      setMessage("Select slot first");
      return;
    }

    const qrRaw = normalizeScannerPayload(scanBufferRef.current);
    if (!qrRaw) {
      setMessage("Scan data is empty");
      return;
    }

    if (autoSendTimerRef.current !== null) {
      window.clearTimeout(autoSendTimerRef.current);
      autoSendTimerRef.current = null;
    }

    await submitScanPayload(slotId, qrRaw);
  };

  const onDelete = async (scanId: number) => {
    if (!selectedSlot) {
      return;
    }
    setBusy(true);
    busyRef.current = true;
    try {
      await api(`/api/slots/${selectedSlot}/items/${scanId}`, { method: "DELETE" });
      await Promise.all([reloadSlots(), reloadItems(selectedSlot)]);
      setMessage("Removed item");
    } catch (error) {
      setMessage((error as Error).message);
    } finally {
      setBusy(false);
      busyRef.current = false;
    }
  };

  const onStartMission = async () => {
    if (!selectedSlot) {
      return;
    }
    setBusy(true);
    busyRef.current = true;
    try {
      const result = await api<{ mission_id: number; station_code: string }>(`/api/slots/${selectedSlot}/start-mission`, {
        method: "POST",
      });
      await Promise.all([reloadSlots(), reloadHistory()]);
      setMessage(`Mission ${result.mission_id} started for ${result.station_code}`);
    } catch (error) {
      setMessage((error as Error).message);
    } finally {
      setBusy(false);
      busyRef.current = false;
    }
  };

  const onScanOutSubmit = async () => {
    if (!selectedSlot) {
      setMessage("Select slot first");
      return;
    }

    const qrRaw = scanOutInputRef.current?.value.trim() || "";
    if (!qrRaw) {
      setMessage("Scan out data is empty");
      return;
    }

    setBusy(true);
    busyRef.current = true;
    try {
      const result = await ajax<{ message: string }>(`/api/slots/${selectedSlot}/scan-out`, "POST", {
        qr_raw: qrRaw,
      });
      if (scanOutInputRef.current) {
        scanOutInputRef.current.value = "";
      }
      await Promise.all([reloadSlots(), reloadItems(selectedSlot), reloadHistory()]);
      setMessage(`Removed ${result.message.replace("removed:", "")}`);
      focusScanInput();
    } catch (error) {
      setMessage((error as Error).message);
    } finally {
      setBusy(false);
      busyRef.current = false;
    }
  };

  const onReopen = async () => {
    if (!selectedSlot) {
      return;
    }
    setBusy(true);
    busyRef.current = true;
    try {
      await api(`/api/slots/${selectedSlot}/reopen`, { method: "POST" });
      await Promise.all([reloadSlots(), reloadItems(selectedSlot)]);
      setMessage(`Slot ${selectedSlot} reopened`);
    } catch (error) {
      setMessage((error as Error).message);
    } finally {
      setBusy(false);
      busyRef.current = false;
    }
  };

  const onOpenSelectedSlot = async () => {
    if (!selectedSlot) {
      setMessage("Select slot first");
      return;
    }

    setBusy(true);
    busyRef.current = true;
    try {
      const result = await api<RelayOpenResult>(`/api/slots/${selectedSlot}/open`, { method: "POST" });
      setSelectedSlot(result.slot_id);
      selectedSlotRef.current = result.slot_id;
      await Promise.all([reloadSlots(), reloadItems(result.slot_id)]);
      setMessage(`Slot ${result.slot_id} opened (${result.relay_result})`);
      focusScanInput();
    } catch (error) {
      setMessage((error as Error).message);
    } finally {
      setBusy(false);
      busyRef.current = false;
    }
  };

  const onOpenEmptySlot = async () => {
    setBusy(true);
    busyRef.current = true;
    try {
      const result = await api<RelayOpenResult>(`/api/slots/open-empty`, { method: "POST" });
      setSelectedSlot(result.slot_id);
      selectedSlotRef.current = result.slot_id;
      await Promise.all([reloadSlots(), reloadItems(result.slot_id)]);
      setMessage(`Opened empty slot ${result.slot_id} (${result.relay_result})`);
      focusScanInput();
    } catch (error) {
      setMessage((error as Error).message);
    } finally {
      setBusy(false);
      busyRef.current = false;
    }
  };

  const onSaveRobotConfig = async () => {
    setConfigBusy(true);
    try {
      const saved = await api<RobotConfig>("/api/config/robot", {
        method: "POST",
        body: JSON.stringify({
          robot_ip: robotIp.trim() || null,
          robot_api_url: robotApiUrl.trim() || null,
        }),
      });
      setRobotIp(saved.robot_ip || "");
      setRobotApiUrl(saved.robot_api_url || "");
      setMessage("Robot configuration saved");
    } catch (error) {
      setMessage((error as Error).message);
    } finally {
      setConfigBusy(false);
    }
  };

  useEffect(() => {
    Promise.all([reloadSlots(), reloadHistory(), reloadRobotConfig()]).catch((error) => setMessage((error as Error).message));
  }, []);

  useEffect(() => {
    selectedSlotRef.current = selectedSlot;
  }, [selectedSlot]);

  useEffect(() => {
    activeTabRef.current = currentTab;
  }, [currentTab]);

  useEffect(() => {
    busyRef.current = busy;
  }, [busy]);

  useEffect(() => {
    if (selectedSlot) {
      reloadItems(selectedSlot).catch((error) => setMessage((error as Error).message));
      if (currentTab === "operation" && !busy) {
        focusScanInput();
      }
    } else {
      setItems([]);
    }
  }, [selectedSlot, currentTab, busy]);

  useEffect(() => {
    const handleWindowKeyDown = (event: KeyboardEvent) => {
      if (activeTabRef.current !== "operation") {
        return;
      }

      if (selectedSlotRef.current == null) {
        return;
      }

      if (document.activeElement === scanOutInputRef.current) {
        return;
      }

      if (busyRef.current) {
        return;
      }

      if (event.ctrlKey || event.metaKey || event.altKey) {
        return;
      }

      const isPrintable = event.key.length === 1;
      const isBackspace = event.key === "Backspace";
      const isLineBreak = event.key === "Enter";
      const isFocusMover = event.key === "Tab";

      if (!isPrintable && !isBackspace && !isLineBreak && !isFocusMover) {
        return;
      }

      if (isPrintable) {
        appendToScanTextarea(event.key);
      }

      if (isBackspace) {
        scanBufferRef.current = scanBufferRef.current.slice(0, -1);
        setScanBuffer(scanBufferRef.current);
      }

      if (isLineBreak) {
        appendToScanTextarea("\n");
      }

      if (isFocusMover) {
        appendToScanTextarea("\t");
      }

      scheduleAutoSend();

      event.preventDefault();
      event.stopPropagation();
      focusScanInput();
    };

    window.addEventListener("keydown", handleWindowKeyDown, true);
    return () => {
      window.removeEventListener("keydown", handleWindowKeyDown, true);
    };
  }, []);

  useEffect(() => {
    return () => {
      if (autoSendTimerRef.current !== null) {
        window.clearTimeout(autoSendTimerRef.current);
      }
    };
  }, []);

  return (
    <div className="app">
      <header>
        <div className="header-top">
          <h1>Med Slot Control</h1>
          <div className="kiosk-tabs" role="tablist" aria-label="Main tabs">
            <button tabIndex={-1} className={`tab-button ${activeTab === "operation" ? "active" : ""}`} onClick={() => setActiveTab("operation")}>Operation</button>
            <button tabIndex={-1} className={`tab-button ${activeTab === "history" ? "active" : ""}`} onClick={() => setActiveTab("history")}>History</button>
            <button tabIndex={-1} className={`tab-button ${activeTab === "settings" ? "active" : ""}`} onClick={() => setActiveTab("settings")}>Settings</button>
          </div>
        </div>

        <p>Choose a tab, then run tasks with large touch-friendly controls.</p>

        <p className="status">{message}</p>
      </header>

      <section className="tab-content">
      {currentTab === "operation" && (
      <section className="work-area">
        <div className="slots">
          {slots.map((slot) => (
            <button
              key={slot.id}
              tabIndex={-1}
              className={`slot ${slot.id === selectedSlot ? "active" : ""}`}
              disabled={busy}
              onClick={() => onSelectSlot(slot.id)}
            >
              <span className="slot-number-label">SLOT {slot.id}</span>
              <span className="slot-meta">Status: {slot.status}</span>
              <span className="slot-meta">Station: {slot.station_code || "-"}</span>
              <span className="slot-meta">Items: {slot.item_count}</span>
            </button>
          ))}
        </div>

        <div className="work-side">
          <div className="panel-left scanner-card" onClick={focusScanInput}>
            <h2>Scanner Input</h2>
            <p className="scanner-help">1. Select slot 2. Click scanner box once 3. Scan 4. Press Send To Slot</p>
            <div className="actions top-actions">
              <button tabIndex={-1} onClick={onOpenEmptySlot} disabled={busy}>
                Open Empty Slot
              </button>
              <button tabIndex={-1} onClick={onOpenSelectedSlot} disabled={!selectedSlot || busy}>
                Open Selected Slot
              </button>
            </div>
            <div className="scanner-box">
              <textarea
                ref={scanInputRef}
                rows={3}
                value={scanBuffer}
                readOnly
                onKeyDown={preventNativeScannerTextareaBehavior}
                onPaste={preventNativeScannerPaste}
                placeholder="Select slot, click here once, then scan QR. Review the text and press Send To Slot."
                disabled={!selectedSlot || busy}
              />
            </div>
            <div className="actions scanner-buffer-actions">
              <button tabIndex={-1} type="button" onClick={onScanSubmit} disabled={!selectedSlot || busy}>Send To Slot</button>
              <button tabIndex={-1} type="button" onClick={onClearScanBuffer} disabled={!selectedSlot || busy}>Clear</button>
            </div>

            <div className="scan-out-row">
              <input
                ref={scanOutInputRef}
                placeholder="Scan QR to remove item from selected slot"
                disabled={!selectedSlot || busy}
              />
              <button tabIndex={-1} type="button" onClick={onScanOutSubmit} disabled={!selectedSlot || busy}>Scan Out From Slot</button>
            </div>

            <div className="actions">
              <button tabIndex={-1} onClick={onStartMission} disabled={!selectedSlot || busy || items.length === 0}>
                Start Mission
              </button>
              <button tabIndex={-1} onClick={onReopen} disabled={!selectedSlot || busy}>
                Reopen Slot
              </button>
            </div>
          </div>

          <div className="panel-right items-card">
            <h2>Current Slot Items {selectedData ? `(Slot ${selectedData.id})` : ""}</h2>
            <ul>
              {items.map((item) => (
                <li key={item.id}>
                  <div>
                    <strong>{item.item_id}</strong> {item.drug_code} HN:{item.hn} Bed:{item.bed_no || "-"}
                  </div>
                  <button tabIndex={-1} disabled={busy} onClick={() => onDelete(item.id)}>
                    Remove
                  </button>
                </li>
              ))}
            </ul>
            {items.length === 0 && <p>No items in selected slot.</p>}
          </div>
        </div>
      </section>
      )}

      {currentTab === "history" && (
      <section className="history-panel">
        <div className="history-header">
          <h2>History And Export</h2>
          <div className="actions">
            <button tabIndex={-1} disabled={busy} onClick={() => reloadHistory().catch((error) => setMessage((error as Error).message))}>
              Refresh History
            </button>
            <a className="link-button" href={`${API_BASE}/api/history/export/scans.csv`} target="_blank" rel="noreferrer">
              Export Scans CSV
            </a>
            <a className="link-button" href={`${API_BASE}/api/history/export/missions.csv`} target="_blank" rel="noreferrer">
              Export Missions CSV
            </a>
            <a className="link-button" href={`${API_BASE}/api/history/export/removals.csv`} target="_blank" rel="noreferrer">
              Export Removals CSV
            </a>
          </div>
        </div>

        <div className="history-grid">
          <div className="history-card">
            <h3>Recent Scans</h3>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Time</th>
                    <th>Slot</th>
                    <th>Item</th>
                    <th>Station</th>
                    <th>HN</th>
                  </tr>
                </thead>
                <tbody>
                  {scanHistory.map((row) => (
                    <tr key={row.id}>
                      <td>{new Date(row.scanned_at).toLocaleString()}</td>
                      <td>{row.slot_id}</td>
                      <td>{row.item_id}</td>
                      <td>{row.station_code}</td>
                      <td>{row.hn}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {scanHistory.length === 0 && <p>No scan history.</p>}
            </div>
          </div>

          <div className="history-card">
            <h3>Recent Missions</h3>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Time</th>
                    <th>Slot</th>
                    <th>Station</th>
                    <th>Status</th>
                    <th>Robot ID</th>
                  </tr>
                </thead>
                <tbody>
                  {missionHistory.map((row) => (
                    <tr key={row.id}>
                      <td>{new Date(row.created_at).toLocaleString()}</td>
                      <td>{row.slot_id}</td>
                      <td>{row.station_code}</td>
                      <td>{row.status}</td>
                      <td>{row.robot_mission_id || "-"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {missionHistory.length === 0 && <p>No mission history.</p>}
            </div>
          </div>

          <div className="history-card">
            <h3>Recent Removals</h3>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Time</th>
                    <th>Slot</th>
                    <th>Item</th>
                    <th>Station</th>
                    <th>Removed By</th>
                  </tr>
                </thead>
                <tbody>
                  {removalHistory.map((row) => (
                    <tr key={row.id}>
                      <td>{new Date(row.removed_at).toLocaleString()}</td>
                      <td>{row.slot_id}</td>
                      <td>{row.item_id}</td>
                      <td>{row.station_code}</td>
                      <td>{row.removed_by}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {removalHistory.length === 0 && <p>No removal history.</p>}
            </div>
          </div>
        </div>

      </section>
      )}

      {currentTab === "settings" && (
      <section className="settings-panel">
        <div className="panel-left">
          <h2>Robot Configuration</h2>
          <div className="robot-config-form">
            <label>
              Robot IP
              <input
                value={robotIp}
                onChange={(event) => setRobotIp(event.target.value)}
                placeholder="ex: 192.168.1.50"
                disabled={configBusy}
              />
            </label>
            <label>
              Robot API URL
              <input
                value={robotApiUrl}
                onChange={(event) => setRobotApiUrl(event.target.value)}
                placeholder="ex: http://192.168.1.50:8080/mission"
                disabled={configBusy}
              />
            </label>
          </div>
          <div className="actions">
            <button tabIndex={-1} onClick={onSaveRobotConfig} disabled={configBusy}>Save Config</button>
            <button tabIndex={-1} onClick={() => reloadRobotConfig().catch((error) => setMessage((error as Error).message))} disabled={configBusy}>Reload</button>
          </div>
        </div>

        <div className="panel-right">
          <h2>Kiosk Quick Actions</h2>
          <div className="actions">
            <button tabIndex={-1} onClick={() => setActiveTab("operation")}>Go To Operation</button>
            <button tabIndex={-1} onClick={() => setActiveTab("history")}>Go To History</button>
          </div>
          <p>Current API Base: {API_BASE || "/"}</p>
          <p>Selected Slot: {selectedSlot ?? "-"}</p>
        </div>
      </section>
      )}
      </section>
    </div>
  );
}
