import { FormEvent, useEffect, useMemo, useRef, useState } from "react";

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

type RobotConfig = {
  robot_ip: string | null;
  robot_api_url: string | null;
};

const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers || {}),
    },
    ...init,
  });

  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: "Request failed" }));
    throw new Error(body.detail || "Request failed");
  }

  return response.json();
}

export function App() {
  const [slots, setSlots] = useState<Slot[]>([]);
  const [selectedSlot, setSelectedSlot] = useState<number | null>(null);
  const [items, setItems] = useState<ScanItem[]>([]);
  const [scanHistory, setScanHistory] = useState<ScanHistoryRow[]>([]);
  const [missionHistory, setMissionHistory] = useState<MissionHistoryRow[]>([]);
  const [showRobotConfig, setShowRobotConfig] = useState(false);
  const [robotIp, setRobotIp] = useState("");
  const [robotApiUrl, setRobotApiUrl] = useState("");
  const [configBusy, setConfigBusy] = useState(false);
  const [scanRaw, setScanRaw] = useState("");
  const [message, setMessage] = useState("Ready");
  const [busy, setBusy] = useState(false);
  const scanInputRef = useRef<HTMLInputElement | null>(null);

  const selectedData = useMemo(
    () => slots.find((slot) => slot.id === selectedSlot) || null,
    [slots, selectedSlot]
  );

  const reloadSlots = async () => {
    const data = await api<Slot[]>("/api/slots");
    setSlots(data);
  };

  const reloadItems = async (slotId: number) => {
    const data = await api<ScanItem[]>(`/api/slots/${slotId}/items`);
    setItems(data);
  };

  const reloadHistory = async () => {
    const [scans, missions] = await Promise.all([
      api<ScanHistoryRow[]>("/api/history/scans?limit=30"),
      api<MissionHistoryRow[]>("/api/history/missions?limit=30"),
    ]);
    setScanHistory(scans);
    setMissionHistory(missions);
  };

  const reloadRobotConfig = async () => {
    const config = await api<RobotConfig>("/api/config/robot");
    setRobotIp(config.robot_ip || "");
    setRobotApiUrl(config.robot_api_url || "");
  };

  const onSelectSlot = async (slotId: number) => {
    setBusy(true);
    try {
      await api(`/api/slots/${slotId}/select`, { method: "POST" });
      setSelectedSlot(slotId);
      await Promise.all([reloadSlots(), reloadItems(slotId)]);
      setMessage(`Slot ${slotId} selected`);
      scanInputRef.current?.focus();
    } catch (error) {
      setMessage((error as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const onScanSubmit = async (event: FormEvent) => {
    event.preventDefault();
    if (!selectedSlot) {
      setMessage("Select slot first");
      return;
    }

    if (!scanRaw.trim()) {
      return;
    }

    setBusy(true);
    try {
      const result = await api<{ item_id: string; station_code: string }>(`/api/slots/${selectedSlot}/scan`, {
        method: "POST",
        body: JSON.stringify({ qr_raw: scanRaw.trim() }),
      });
      setScanRaw("");
      await Promise.all([reloadSlots(), reloadItems(selectedSlot)]);
      setMessage(`Added ${result.item_id} (${result.station_code})`);
      scanInputRef.current?.focus();
    } catch (error) {
      setMessage((error as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const onDelete = async (scanId: number) => {
    if (!selectedSlot) {
      return;
    }
    setBusy(true);
    try {
      await api(`/api/slots/${selectedSlot}/items/${scanId}`, { method: "DELETE" });
      await Promise.all([reloadSlots(), reloadItems(selectedSlot)]);
      setMessage("Removed item");
    } catch (error) {
      setMessage((error as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const onStartMission = async () => {
    if (!selectedSlot) {
      return;
    }
    setBusy(true);
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
    }
  };

  const onReopen = async () => {
    if (!selectedSlot) {
      return;
    }
    setBusy(true);
    try {
      await api(`/api/slots/${selectedSlot}/reopen`, { method: "POST" });
      await Promise.all([reloadSlots(), reloadItems(selectedSlot)]);
      setMessage(`Slot ${selectedSlot} reopened`);
      scanInputRef.current?.focus();
    } catch (error) {
      setMessage((error as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const onOpenSelectedSlot = async () => {
    if (!selectedSlot) {
      setMessage("Select slot first");
      return;
    }

    setBusy(true);
    try {
      const result = await api<RelayOpenResult>(`/api/slots/${selectedSlot}/open`, { method: "POST" });
      setSelectedSlot(result.slot_id);
      await Promise.all([reloadSlots(), reloadItems(result.slot_id)]);
      setMessage(`Slot ${result.slot_id} opened (${result.relay_result})`);
      scanInputRef.current?.focus();
    } catch (error) {
      setMessage((error as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const onOpenEmptySlot = async () => {
    setBusy(true);
    try {
      const result = await api<RelayOpenResult>(`/api/slots/open-empty`, { method: "POST" });
      setSelectedSlot(result.slot_id);
      await Promise.all([reloadSlots(), reloadItems(result.slot_id)]);
      setMessage(`Opened empty slot ${result.slot_id} (${result.relay_result})`);
      scanInputRef.current?.focus();
    } catch (error) {
      setMessage((error as Error).message);
    } finally {
      setBusy(false);
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
      setShowRobotConfig(false);
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
    if (selectedSlot) {
      reloadItems(selectedSlot).catch((error) => setMessage((error as Error).message));
      scanInputRef.current?.focus();
    } else {
      setItems([]);
    }
  }, [selectedSlot]);

  return (
    <div className="app">
      <header>
        <div className="header-main">
          <div>
            <h1>Med Slot Control</h1>
            <p>Choose slot first, scan bottle one-by-one, then press Start Mission.</p>
          </div>
          <button className="header-config-button" onClick={() => setShowRobotConfig((prev) => !prev)} disabled={busy || configBusy}>
            Config Robot IP/API
          </button>
        </div>

        {showRobotConfig && (
          <div className="robot-config-panel">
            <h3>Robot Configuration</h3>
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
              <button onClick={onSaveRobotConfig} disabled={configBusy}>Save Config</button>
              <button onClick={() => setShowRobotConfig(false)} disabled={configBusy}>Close</button>
            </div>
          </div>
        )}
      </header>

      <section className="work-area">
        <div className="slots">
          {slots.map((slot) => (
            <button
              key={slot.id}
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
          <div className="panel-left scanner-card">
            <h2>Scanner Input</h2>
            <div className="actions top-actions">
              <button onClick={onOpenEmptySlot} disabled={busy}>
                Open Empty Slot
              </button>
              <button onClick={onOpenSelectedSlot} disabled={!selectedSlot || busy}>
                Open Selected Slot
              </button>
            </div>
            <form onSubmit={onScanSubmit}>
              <input
                ref={scanInputRef}
                value={scanRaw}
                onChange={(event) => setScanRaw(event.target.value)}
                placeholder="Focus here and scan QR by USB scanner"
                disabled={!selectedSlot || busy}
              />
              <button type="submit" disabled={!selectedSlot || busy}>Scan Into Slot</button>
            </form>

            <div className="actions">
              <button onClick={onStartMission} disabled={!selectedSlot || busy || items.length === 0}>
                Start Mission
              </button>
              <button onClick={onReopen} disabled={!selectedSlot || busy}>
                Reopen Slot
              </button>
            </div>
            <p className="status">{message}</p>
          </div>

          <div className="panel-right items-card">
            <h2>Current Slot Items {selectedData ? `(Slot ${selectedData.id})` : ""}</h2>
            <ul>
              {items.map((item) => (
                <li key={item.id}>
                  <div>
                    <strong>{item.item_id}</strong> {item.drug_code} HN:{item.hn} Bed:{item.bed_no || "-"}
                  </div>
                  <button disabled={busy} onClick={() => onDelete(item.id)}>
                    Remove
                  </button>
                </li>
              ))}
            </ul>
            {items.length === 0 && <p>No items in selected slot.</p>}
          </div>
        </div>
      </section>

      <section className="history-panel">
        <div className="history-header">
          <h2>History And Export</h2>
          <div className="actions">
            <button disabled={busy} onClick={() => reloadHistory().catch((error) => setMessage((error as Error).message))}>
              Refresh History
            </button>
            <a className="link-button" href={`${API_BASE}/api/history/export/scans.csv`} target="_blank" rel="noreferrer">
              Export Scans CSV
            </a>
            <a className="link-button" href={`${API_BASE}/api/history/export/missions.csv`} target="_blank" rel="noreferrer">
              Export Missions CSV
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
        </div>
      </section>
    </div>
  );
}
