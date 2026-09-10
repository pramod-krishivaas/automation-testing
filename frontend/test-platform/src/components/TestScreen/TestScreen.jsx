import React, { useState, useEffect, useRef } from 'react';
import useWebSocket, { ReadyState } from 'react-use-websocket';
import Header from "../Header/Header";
// import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'; // disabled: MetricsChart
import { Play, Terminal, Activity, CheckCircle, Circle, AlertCircle, /* Cpu, */ Maximize2, Minimize2, Layers, FolderOpen, Tag } from 'lucide-react';
import UIScreenshotIssues from '../UIScreenshotIssues/UIScreenshotIssues';
import IssuePanel from '../IssuePanel/IssuePanel';
import NetworkConfigPanel from '../NetworkConfig/NetworkConfig'
import catalogService from '../../services/catalogService';
import testCaseService from '../../services/testCaseService';
import '../../App.css';

const WS_URL = 'ws://localhost:8000/ws/test-status';
const API_URL = 'http://localhost:8000';

// LEGACY fallback only. Since the unified app's four roles share one package_name,
// the authoritative UI→variant key is now the Application's `variant` field (see
// resolvedVariantId below). This map is consulted only for older DB rows that were
// created before the variant column existed. New rows should set `variant` directly.
const PACKAGE_VARIANT_MAP = {
    "com.agribride.krishivaas.farmer_app": "regular_farmer",
    "com.agribride.krishivaas.client_app": "regular_client",
    "com.agribride.krishivaas.farmer_state_app": "state_farmer",
    "com.agribride.krishivaas.client_state_app": "state_client",
};

// Login is identical for all four apps, so every app's "Login" module maps to this
// single shared test. It reads the selected app (via --target-role), logs in, and
// switches to that app. Lives outside the per-app folders (common_test_cases).
const COMMON_LOGIN = 'tests/test_cases/common_test_cases/test_login_pytest.py';

// Test types selectable in the UI. Sent to the backend as `test_types`; drives both
// folder-based collection (tests/test_suites/<type>/) and the DB test_types filter.
// Labels MUST match TEST_TYPE_FOLDERS keys in tests/test_type_config.py and the DB tags.
const AVAILABLE_TEST_TYPES = ['Smoke', 'Regression', 'End-to-End', 'Sanity'];

// ── SINGLE SOURCE OF TRUTH: app_variant → test_type → module → suite path ──────
// Selecting an app + a test type runs exactly the module suites listed under that
// (app, type). The path is a function of ALL THREE — the same module can point at a
// different suite per type — which mirrors the on-disk layout tests/test_suites/
// <type>/<app>/. `Login` is the one shared suite (COMMON_LOGIN) and is listed under
// every type of every app so it always runs. Add a module by dropping its real
// suite path under the right type; only paths that exist on disk actually execute
// (the backend skips missing ones), so unbuilt modules can be stubbed here safely.
// Keys of `test_type` MUST match AVAILABLE_TEST_TYPES / TEST_TYPE_FOLDERS.
const APP_TEST_CONFIG = {
    regular_farmer: {
        id: "regular_farmer",
        label: "Krishivaas Farmer (Regular)",
        test_type: {
            "Smoke":      { Login: COMMON_LOGIN },
            "Regression": { Login: COMMON_LOGIN },
            "End-to-End": { Login: COMMON_LOGIN },
            "Sanity":     { Login: COMMON_LOGIN },
        },
    },
    regular_client: {
        id: "regular_client",
        label: "Krishivaas Client (Regular)",
        test_type: {
            "Smoke":      { Login: COMMON_LOGIN },
            "Regression": { Login: COMMON_LOGIN },
            "End-to-End": { 
                Login: COMMON_LOGIN, 
                Onboarding: "tests/test_suites/end_to_end/state_client/test_onboarding_pytest.py" 
            },
            "Sanity":     { Login: COMMON_LOGIN },
        },
    },
    state_farmer: {
        id: "state_farmer",
        label: "Krishivaas Telangana Farmer",
        test_type: {
            "Smoke":      { Login: COMMON_LOGIN },
            "Regression": { Login: COMMON_LOGIN },
            "End-to-End": { Login: COMMON_LOGIN },
            "Sanity":     { Login: COMMON_LOGIN },
        },
    },
    state_client: {
        id: "state_client",
        label: "Krishivaas Telangana Client",
        test_type: {
            "Smoke":      { Login: COMMON_LOGIN },
            "Regression": { Login: COMMON_LOGIN },
            "End-to-End": {
                Login:      COMMON_LOGIN,
                Onboarding: "tests/test_suites/end_to_end/state_client/test_onboarding_pytest.py",
            },
            "Sanity":     { Login: COMMON_LOGIN },
        },
    },
};

// Build the module list for an app from APP_TEST_CONFIG, scoped to the selected test
// types (or ALL of the app's types when none are selected). Each module carries the
// concrete suite paths it will run — deduped, tagged with the type(s) that include
// them — so the run payload and the "ready to run" panel derive straight from here.
const modulesFromConfig = (cfg, selectedTypes) => {
    if (!cfg) return [];
    const typeMap = cfg.test_type || {};
    const scope = (selectedTypes && selectedTypes.length)
        ? selectedTypes.filter((t) => typeMap[t])
        : Object.keys(typeMap);
    const acc = new Map();                     // moduleName -> Map(path -> Set(types))
    scope.forEach((type) => {
        Object.entries(typeMap[type] || {}).forEach(([moduleName, path]) => {
            if (!path) return;
            if (!acc.has(moduleName)) acc.set(moduleName, new Map());
            const byPath = acc.get(moduleName);
            if (!byPath.has(path)) byPath.set(path, new Set());
            byPath.get(path).add(type);
        });
    });
    return Array.from(acc.entries()).map(([name, byPath]) => ({
        name,
        runTargets: Array.from(byPath.entries()).map(([path, types]) => ({ path, types: Array.from(types) })),
        status: 'pending',
        isSelected: true,
    }));
};

/* ─── ModuleFlow ─────────────────────────────────────────────────────────── */
const ModuleFlow = ({ modules, isRunning, onToggleModule }) => (
    <div className="dashboard-card">
        <h3 className="card-title">
            <Activity size={20} className="icon-blue" /> Module Flow Status
        </h3>
        <div className="module-list">
            {modules.map((mod, idx) => {
                const mismatched = mod.matched === false;
                let statusClass = mismatched ? "status-mismatch" : "status-pending";
                let icon = <Circle size={16} />;
                if (!mismatched && mod.status === 'completed') { statusClass = "status-success"; icon = <CheckCircle size={16} />; }
                else if (!mismatched && mod.status === 'running') { statusClass = "status-running"; icon = <Activity size={16} className="icon-pulse" />; }
                else if (!mismatched && mod.status === 'failed') { statusClass = "status-failed"; icon = <AlertCircle size={16} />; }

                const clickable = !isRunning && !mismatched;
                return (
                    <div key={idx}
                        className={`module-item ${statusClass} ${clickable ? "clickable-module" : ""}`}
                        onClick={() => clickable && onToggleModule(idx)}
                        style={{ cursor: clickable ? 'pointer' : 'default' }}>
                        {mismatched ? (
                            <AlertCircle size={16} className="text-gray-500" style={{ flexShrink: 0 }} />
                        ) : !isRunning ? (
                            <input type="checkbox" checked={!!mod.isSelected}
                                onClick={e => e.stopPropagation()}
                                onChange={() => onToggleModule(idx)}
                                className="mr-2 cursor-pointer" style={{ marginRight: '0px' }} />
                        ) : (
                            mod.isSelected ? icon : <Circle size={16} className="text-gray-500" />
                        )}
                        <span className={`module-name ${!mismatched && !mod.isSelected && !isRunning ? 'opacity-50' : ''}`}>
                            {mod.name}
                        </span>
                        {mismatched && (
                            <span className="status-label" style={{ color: 'var(--text-muted)', fontStyle: 'italic' }}>
                                {mod.path ? 'Not in test catalog' : 'No automation available'}
                            </span>
                        )}
                        {!mismatched && mod.status === 'running' && <span className="status-label">Testing...</span>}
                        {!mismatched && mod.status === 'completed' && <span className="status-label" style={{ color: '#22c55e' }}>Completed</span>}
                        {!mismatched && mod.status === 'failed' && <span className="status-label" style={{ color: '#ef4444' }}>Failed</span>}
                    </div>
                );
            })}
        </div>
    </div>
);

/* ─── ReadyTestCases — the concrete test_* functions that will run ────────────
 * Config-driven and informational: for each SELECTED module it lists the actual
 * test_* functions discovered in the suite file(s) that module resolves to under
 * the selected test type(s) (via GET /api/automation-tests). Because every app's
 * config includes Login → COMMON_LOGIN, the shared login cases show for ALL apps.
 * ─────────────────────────────────────────────────────────────────────────── */
const ReadyTestCases = ({ modules }) => {
    const [sourceByPath, setSourceByPath] = useState({});
    const [loading, setLoading] = useState(false);

    const selected = modules.filter((m) => m.isSelected);
    // Every distinct suite path the selected modules will run (a module can span
    // several types, but the same file is only discovered once).
    const paths = Array.from(new Set(
        selected.flatMap((m) => (m.runTargets || []).map((rt) => rt.path))
    ));
    const key = paths.join(',');

    useEffect(() => {
        if (!paths.length) { setSourceByPath({}); return; }
        setLoading(true);
        Promise.all(
            paths.map((p) =>
                catalogService.discoverAutomationTests(p)
                    .then((items) => [p, items || []])
                    .catch(() => [p, []])
            )
        ).then((entries) => {
            setSourceByPath(Object.fromEntries(entries));
            setLoading(false);
        });
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [key]);

    if (!selected.length) return null;

    return (
        <div className="dashboard-card">
            <h3 className="card-title">
                <CheckCircle size={20} className="icon-blue" /> Test Cases Ready to Run
            </h3>
            {loading ? (
                <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>Loading test cases...</div>
            ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.9rem' }}>
                    {selected.map((m) => (
                        <div key={m.name}>
                            <div style={{ fontSize: '0.72rem', fontWeight: 700, color: 'var(--text-secondary)', marginBottom: '4px' }}>
                                {m.name}
                            </div>
                            {(m.runTargets || []).map((rt) => {
                                const fns = sourceByPath[rt.path] || [];
                                return (
                                    <div key={rt.path} style={{ marginBottom: '6px' }}>
                                        <div style={{ fontSize: '0.66rem', color: 'var(--text-muted)', fontFamily: 'monospace', marginBottom: '3px' }}>
                                            {rt.path} <span style={{ fontStyle: 'italic' }}>· {rt.types.join(', ')}</span>
                                        </div>
                                        {fns.length === 0 ? (
                                            <div style={{ fontSize: '0.74rem', color: 'var(--text-muted)', fontStyle: 'italic' }}>
                                                No <code>test_*</code> functions found (suite not built yet).
                                            </div>
                                        ) : (
                                            <div style={{ display: 'flex', flexDirection: 'column', gap: '5px' }}>
                                                {fns
                                                    .slice()
                                                    .sort((a, b) => (a.function_name || '').localeCompare(b.function_name || ''))
                                                    .map((s) => (
                                                        <div key={s.function_name} style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '0.78rem', flexWrap: 'wrap' }}>
                                                            <span style={{ color: 'var(--text-primary)', flex: 1, minWidth: '120px' }}>{s.title || s.function_name}</span>
                                                            <span style={{ fontFamily: 'monospace', color: '#7C3AED', fontSize: '0.72rem', flexShrink: 0 }}
                                                                title={s.line ? `Source function (line ${s.line})` : 'Source function'}>
                                                                def {s.function_name}()
                                                            </span>
                                                        </div>
                                                    ))}
                                            </div>
                                        )}
                                    </div>
                                );
                            })}
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
};

/* ─── TestTypeCases — maps selected test types to the tests they'll run ────────
 * For each selected test type, shows BOTH sides of the type membership model:
 *   • FOLDER tests — physically under tests/test_suites/<type>/ (folder = authority,
 *     collected wholesale, no DB tag), via GET /api/test-type-tests.
 *   • DB-TAGGED tests — catalogued test cases whose test_types include this type,
 *     for the selected app, via GET /api/test-cases?test_type=…&application_id=…
 * Purely informational — mirrors what the backend collects for --test-type.
 * ─────────────────────────────────────────────────────────────────────────── */
const TYPE_FOLDER_NAME = { 'Smoke': 'smoke', 'Regression': 'regression', 'End-to-End': 'end_to_end', 'Sanity': 'sanity' };

const TestTypeCases = ({ selectedTestTypes, applicationId, appVariantId }) => {
    const [byType, setByType] = useState({});
    const [loading, setLoading] = useState(false);
    const key = selectedTestTypes.join(',') + '|' + (applicationId || '') + '|' + (appVariantId || '');

    useEffect(() => {
        if (!selectedTestTypes.length) { setByType({}); return; }
        setLoading(true);
        Promise.all(selectedTestTypes.map(async (t) => {
            const [folderAll, tagged] = await Promise.all([
                catalogService.discoverTypeFolderTests(t).catch(() => []),
                testCaseService.listTestCases({ test_type: t, application_id: applicationId || undefined, page_size: 100 })
                    .then((r) => r.items || []).catch(() => []),
            ]);
            // test_suites/<type>/ holds a subfolder per app; keep only the SELECTED
            // app_variant's tests (plus shared `common`/unlabelled ones that run for
            // every app), so this panel matches the app chosen above.
            const folder = (folderAll || []).filter(
                (f) => !appVariantId || f.app === appVariantId || f.app === 'common' || !f.app
            );
            return [t, { folder, tagged }];
        })).then((entries) => { setByType(Object.fromEntries(entries)); setLoading(false); });
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [key]);

    if (!selectedTestTypes.length) return null;

    const rowStyle = { display: 'flex', alignItems: 'center', gap: '8px', fontSize: '0.78rem', flexWrap: 'wrap' };
    const badge = (bg, color, label) => (
        <span style={{ fontSize: '0.6rem', fontWeight: 700, padding: '2px 7px', borderRadius: '999px', flexShrink: 0, background: bg, color }}>{label}</span>
    );

    return (
        <div className="dashboard-card">
            <h3 className="card-title">
                <Layers size={20} className="icon-blue" /> Test Cases by Type
            </h3>
            {loading ? (
                <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>Loading test cases...</div>
            ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.9rem' }}>
                    {selectedTestTypes.map((t) => {
                        const data = byType[t] || { folder: [], tagged: [] };
                        const total = data.folder.length + data.tagged.length;
                        return (
                            <div key={t}>
                                <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '6px' }}>
                                    <span style={{ fontSize: '0.72rem', fontWeight: 700, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>{t}</span>
                                    <span style={{ fontSize: '0.62rem', color: 'var(--text-muted)' }}>{total} test{total !== 1 ? 's' : ''}</span>
                                </div>
                                {total === 0 ? (
                                    <div style={{ fontSize: '0.76rem', color: 'var(--text-muted)', fontStyle: 'italic' }}>
                                        No tests in <code>tests/test_suites/{TYPE_FOLDER_NAME[t] || t}/</code> and none DB-tagged “{t}” for this app.
                                    </div>
                                ) : (
                                    <div style={{ display: 'flex', flexDirection: 'column', gap: '5px' }}>
                                        {data.folder.map((f, i) => (
                                            <div key={`f${i}`} style={rowStyle}>
                                                <FolderOpen size={13} style={{ color: 'var(--accent-purple)', flexShrink: 0 }} />
                                                <span style={{ fontFamily: 'monospace', color: 'var(--accent-purple)', fontSize: '0.72rem', flexShrink: 0 }}
                                                    title={`${f.file}${f.line ? ` (line ${f.line})` : ''}`}>def {f.function_name}()</span>
                                                <span style={{ color: 'var(--text-secondary)', flex: 1, minWidth: '90px' }}>{f.title || '—'}</span>
                                                <span style={{ fontSize: '0.62rem', color: 'var(--text-muted)' }}>{f.app || '—'}</span>
                                                {badge('rgba(124,58,237,0.14)', 'var(--accent-purple)', 'Folder')}
                                            </div>
                                        ))}
                                        {data.tagged.map((tc) => (
                                            <div key={`d${tc.testcase_id}`} style={rowStyle}>
                                                <Tag size={13} style={{ color: '#2563EB', flexShrink: 0 }} />
                                                <span style={{ fontFamily: 'monospace', color: '#2563EB', fontWeight: 600, fontSize: '0.72rem', flexShrink: 0 }}
                                                    title="DB testcase_key">{tc.testcase_key}</span>
                                                <span style={{ color: 'var(--text-primary)', flex: 1, minWidth: '90px' }}>{tc.title}</span>
                                                {badge('rgba(37,99,235,0.12)', '#2563EB', 'DB tag')}
                                            </div>
                                        ))}
                                    </div>
                                )}
                            </div>
                        );
                    })}
                    <span style={{ color: 'var(--text-muted)', fontSize: '0.68rem' }}>
                        Folder tests always run for the type; DB-tagged tests run when their module is also selected above.
                    </span>
                </div>
            )}
        </div>
    );
};

/* ─── MetricsChart ───────────────────────────────────────────────────────── */
/* Temporarily disabled — live profiler metrics are not yet wired to a
   backend data source. Re-enable once the /ws/metrics endpoint is ready.
const MetricsChart = ({ data }) => (
    <div className="dashboard-card chart-card">
        <h3 className="card-title">
            <Cpu size={20} className="icon-purple" /> Live Profiler Metrics
        </h3>
        <div className="chart-container">
            <ResponsiveContainer width="100%" height="100%">
                <LineChart data={data}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                    <XAxis dataKey="time" hide />
                    <YAxis yAxisId="left" stroke="#94a3b8" label={{ value: 'CPU %', angle: -90, position: 'insideLeft' }} domain={[0, 100]} />
                    <YAxis yAxisId="right" orientation="right" stroke="#94a3b8" label={{ value: 'MB', angle: 90, position: 'insideRight' }} />
                    <Tooltip contentStyle={{ backgroundColor: '#1e293b', borderColor: '#334155', color: '#e2e8f0' }} itemStyle={{ color: '#e2e8f0' }} />
                    <Line yAxisId="left" type="monotone" dataKey="cpu" stroke="#38bdf8" strokeWidth={2} dot={false} animationDuration={300} />
                    <Line yAxisId="right" type="monotone" dataKey="memory" stroke="#c084fc" strokeWidth={2} dot={false} animationDuration={300} />
                </LineChart>
            </ResponsiveContainer>
        </div>
    </div>
);
*/

const staticApiLogs = [
    { time: "10:00:01.234", type: "info", message: "GET /api/v1/health-check - 200 OK (12ms)" },
    { time: "10:00:02.100", type: "info", message: "POST /api/v1/auth/login - 200 OK (45ms)" },
    { time: "10:00:05.400", type: "error", message: "GET /api/v1/users/profile - 401 Unauthorized (8ms)" },
    { time: "10:00:08.220", type: "warn", message: "Rate limit threshold approaching for IP 192.168.1.105" },
    { time: "10:00:15.000", type: "info", message: "GET /api/v1/dashboard/metrics - 200 OK (110ms)" },
];

/* ─── LogConsole ─────────────────────────────────────────────────────────── */
const LogConsole = ({ logs, statusMode = 'idle' }) => {
    const endRef = useRef(null);
    const [searchTerm, setSearchTerm] = useState('');
    const [isFullScreen, setIsFullScreen] = useState(false);
    const [activeTab, setActiveTab] = useState('test');
    const [apiLogs, setApiLogs] = useState([]);

    const normalizedSearch = searchTerm.toLowerCase().trim();

    const matchesSearch = (log) => {
        if (!normalizedSearch) return false;
        return (
            log.message.toLowerCase().includes(normalizedSearch) ||
            log.type.toLowerCase().includes(normalizedSearch) ||
            String(log.time).toLowerCase().includes(normalizedSearch)
        );
    };

    /* Status bar — animated stripe while running, solid colour on result */
    const getBarStyle = () => {
        const base = { height: '3px', flexGrow: 1, margin: '0 12px', borderRadius: '2px', transition: 'all 0.3s ease' };
        if (statusMode === 'running')  return { ...base, background: 'linear-gradient(90deg,#bfdbfe 0%,#2563EB 50%,#bfdbfe 100%)', backgroundSize: '200% 100%', animation: 'gradientLoad 2s linear infinite' };
        if (statusMode === 'failure')  return { ...base, background: '#DC2626', animation: 'blinkRed 1.5s infinite' };
        if (statusMode === 'success')  return { ...base, background: '#059669', animation: 'blinkGreen 1.5s infinite' };
        return { ...base, background: 'var(--border-color)' };
    };

    const currentLogs = activeTab === 'test' ? logs : apiLogs;

    /* Auto-scroll to bottom on new logs */
    useEffect(() => {
        if (endRef.current) endRef.current.scrollIntoView({ behavior: 'smooth' });
    }, [currentLogs.length]);

    useEffect(() => {
        if (activeTab !== 'api') return;
        const interval = setInterval(async () => {
            try {
                const res  = await fetch('http://localhost:8000/api-testing/logs');
                const data = await res.json();
                setApiLogs(data.map(log => ({
                    time:    log.timestamp,
                    type:    log.status >= 400 ? 'error' : 'info',
                    message: `${log.method} ${log.endpoint} - ${log.status} (${log.response_time_ms} ms)`,
                })).reverse());
            } catch { /* ignore */ }
        }, 2000);
        return () => clearInterval(interval);
    }, [activeTab]);

    return (
        <div className={`log-console ${isFullScreen ? 'full-screen' : ''}`}>

            {/* ── Header row ── */}
            <div className="console-header-row">
                <h3 className="console-header">
                    <Terminal size={13} /> LIVE LOGS
                </h3>
                <div style={getBarStyle()} />
                <div className="log-search">
                    <input
                        type="text"
                        placeholder={`Search logs…`}
                        value={searchTerm}
                        onChange={e => setSearchTerm(e.target.value)}
                        className="text-input"
                        style={{ width: '160px', padding: '4px 8px', fontSize: '0.72rem' }}
                    />
                </div>
                <button
                    onClick={() => setIsFullScreen(f => !f)}
                    title={isFullScreen ? 'Exit Full Screen' : 'Full Screen'}
                    style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)', display: 'flex', alignItems: 'center', padding: '3px', marginLeft: '4px' }}
                >
                    {isFullScreen ? <Minimize2 size={16} /> : <Maximize2 size={16} />}
                </button>
            </div>

            {/* ── Tab row ── */}
            <div className="log-tabs">
                <button className={`log-tab-btn ${activeTab === 'test' ? 'active' : ''}`} onClick={() => setActiveTab('test')}>Test Logs</button>
                <button className={`log-tab-btn ${activeTab === 'api'  ? 'active' : ''}`} onClick={() => setActiveTab('api')}>API Logs</button>
            </div>

            {/* ── Log lines ── */}
            <div className="console-body">
                {currentLogs.length === 0 && (
                    <div style={{ color: 'var(--text-muted)', fontSize: '0.75rem', padding: '1.5rem', textAlign: 'center' }}>
                        No logs yet — start a test run to see output here.
                    </div>
                )}
                {currentLogs.map((log, i) => (
                    <div key={i} className={`log-line ${log.type.toLowerCase()} ${matchesSearch(log) ? 'log-line-highlight' : ''}`}>
                        <span className="timestamp">[{log.time}]</span>
                        <span className="message">{log.message}</span>
                    </div>
                ))}
                <div ref={endRef} />
            </div>
        </div>
    );
};

/* ─── TestScreen ─────────────────────────────────────────────────────────── */
/**
 * Props:
 *   onHistoryUpdate(entry) — injected by App.jsx (JiraHistoryContext).
 *     Called by IssuePanel when user clicks Create → entry.type="created"
 *     Called by IssuePanel when user clicks Remove → entry.type="removed"
 *     JiraHistory screen reads these entries to populate Assigned/Unassigned tabs.
 */
function TestScreen({ onHistoryUpdate }) {

    const loadState = (key, fallback) => {
        try { const s = sessionStorage.getItem(key); return s ? JSON.parse(s) : fallback; }
        catch { return fallback; }
    };

    const [apkUrl, setApkUrl] = useState(() => loadState('apkUrl', ''));
    const [isRunning, setIsRunning] = useState(() => loadState('isRunning', false));
    const [isDownloading, setIsDownloading] = useState(false);
    const [showUiIssuesScreen, setShowUiIssuesScreen] = useState(false);
    const [uiAnalysisStatus, setUiAnalysisStatus] = useState('idle');
    const [uiAnalysisError, setUiAnalysisError] = useState('');
    const [uiAnalysisResults, setUiAnalysisResults] = useState([]);
    const [logs, setLogs] = useState(() => loadState('logs', []));
    const [metrics, setMetrics] = useState([]);
    const [appIcon, setAppIcon] = useState(null);
    const [appTitle, setAppTitle] = useState('');
    const [isDeviceConnected, setIsDeviceConnected] = useState(false);
    const [appiumStatus, setAppiumStatus] = useState('stopped');
    const [showStopPopup, setShowStopPopup] = useState(false);
    // Holds a DB application_id, resolved to an automation variant id (regular_farmer
    // etc.) via the app's `variant` field, then to its APP_TEST_CONFIG node.
    const [selectedAppKey, setSelectedAppKey] = useState(() => loadState('selectedAppKey', ''));
    const [existingApks, setExistingApks] = useState([]);
    const [selectedApk, setSelectedApk] = useState(() => loadState('selectedApk', ''));
    const [loginPhone, setLoginPhone] = useState(() => loadState('loginPhone', ''));
    const [loginMpin, setLoginMpin] = useState(() => loadState('loginMpin', ''));
    const [selectedTestTypes, setSelectedTestTypes] = useState(() => loadState('selectedTestTypes', []));
    const [hasOpenedReport, setHasOpenedReport] = useState(false);
    const [networkConfig, setNetworkConfig] = useState(null);
    const [showNewTestButton, setShowNewTestButton] = useState(false);

    const [dbApplications, setDbApplications] = useState([]);

    const [modules, setModules] = useState(() => {
        const saved = sessionStorage.getItem('modules');
        return saved ? JSON.parse(saved) : [];
    });

    // Persist state
    useEffect(() => {
        sessionStorage.setItem('apkUrl', JSON.stringify(apkUrl));
        sessionStorage.setItem('isRunning', JSON.stringify(isRunning));
        sessionStorage.setItem('selectedAppKey', JSON.stringify(selectedAppKey));
        sessionStorage.setItem('modules', JSON.stringify(modules));
        sessionStorage.setItem('selectedApk', JSON.stringify(selectedApk));
        sessionStorage.setItem('loginPhone', JSON.stringify(loginPhone));
        sessionStorage.setItem('loginMpin', JSON.stringify(loginMpin));
        sessionStorage.setItem('selectedTestTypes', JSON.stringify(selectedTestTypes));
        sessionStorage.setItem('logs', JSON.stringify(logs.slice(-200)));
    }, [apkUrl, isRunning, selectedAppKey, modules, selectedApk, loginPhone, loginMpin, selectedTestTypes, logs]);

    const getConsoleStatus = () => {
        if (isRunning) return 'running';
        const active = modules.filter(m => m.isSelected);
        if (!active.length) return 'idle';
        if (active.some(m => m.status === 'failed')) return 'failure';
        const hasCompleted = active.some(m => m.status === 'completed' || m.status === 'passed');
        const hasRunning = active.some(m => m.status === 'running');
        if (hasCompleted && !hasRunning) return 'success';
        return 'idle';
    };

    // Fetch DB applications once, auto-select the first one if nothing (or a
    // stale/deleted app) is currently selected.
    useEffect(() => {
        catalogService.listApplications()
            .then((res) => {
                const items = res.items || [];
                setDbApplications(items);
                setSelectedAppKey((prev) => {
                    if (prev && items.some((a) => String(a.application_id) === String(prev))) return String(prev);
                    // Keep the key a string (matches HTML <select> values, whose IDs are numeric now).
                    return items[0]?.application_id != null ? String(items[0].application_id) : '';
                });
            })
            .catch(() => setDbApplications([]));
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    const selectedDbApp = dbApplications.find((a) => String(a.application_id) === String(selectedAppKey)) || null;

    // Resolve the automation variant from the app's explicit `variant` field.
    // The unified app's four roles (regular_farmer / regular_client / state_farmer
    // / state_client) all share ONE package_name, so package_name can no longer
    // tell them apart — `variant` is the authoritative key. Fall back to the legacy
    // package map only for older rows that predate the variant column.
    const resolvedVariantId = selectedDbApp?.variant
        || (selectedDbApp?.package_name ? PACKAGE_VARIANT_MAP[selectedDbApp.package_name] : null);
    // The nested app→test_type→module→path config (APP_TEST_CONFIG) is the single
    // source of truth for what runs. Resolve the app's config node by variant id.
    const resolvedConfig = resolvedVariantId ? (APP_TEST_CONFIG[resolvedVariantId] || null) : null;

    // Modules for the selected app, scoped to the selected test types (all of the
    // app's types when none are chosen). Each carries the concrete suite paths it runs.
    const configModules = React.useMemo(
        () => modulesFromConfig(resolvedConfig, selectedTestTypes),
        [resolvedConfig, selectedTestTypes]
    );

    // Rebuild `modules` whenever the app or the selected test types change. Preserve
    // the user's per-module checkbox by name across type toggles; new modules default
    // to selected.
    useEffect(() => {
        setModules((prev) => {
            const wasSelected = new Map(prev.map((m) => [m.name, m.isSelected]));
            return configModules.map((m) => ({
                ...m,
                isSelected: wasSelected.has(m.name) ? wasSelected.get(m.name) : true,
            }));
        });
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [configModules]);

    const toggleModuleSelection = (index) => {
        if (isRunning) return;
        setModules(prev => prev.map((m, i) => i === index ? { ...m, isSelected: !m.isSelected } : m));
    };

    const { lastJsonMessage, sendMessage, readyState } = useWebSocket(WS_URL, {
        shouldReconnect: () => true,
        onMessage: (event) => {
            try { handleIncomingData(JSON.parse(event.data)); } catch { }
        }
    });

    const handleIncomingData = (data) => {
        // IssuePanel handles JIRA_PAYLOAD via its own WebSocket — skip here
        if (data.type === 'JIRA_PAYLOAD') return;

        if (data.type === 'LOG') {
            const { message = '', status } = data.payload || {};

            if (status === 'PROGRESS') {
                setLogs(prev => {
                    if (prev.length > 0 && prev[prev.length - 1].type === 'PROGRESS') {
                        const n = [...prev];
                        n[n.length - 1] = { time: new Date().toLocaleTimeString(), message, type: status };
                        return n;
                    }
                    return [...prev, { time: new Date().toLocaleTimeString(), message, type: status }];
                });
                return;
            }

            setLogs(prev => [...prev, { time: new Date().toLocaleTimeString(), message, type: status || 'INFO' }]);

            if (message && (
                message.includes("Allure HTML report generated") ||
                message.includes("Skipping report generation") ||
                message.includes("Test execution interrupted") ||
                message.includes("Test process terminated")
            )) setIsRunning(false);

        } else if (data.type === 'MODULE') {
            const { module, status, message } = data.payload || {};
            if (module && status) {
                setModules(prev => {
                    const updated = prev.map(m =>
                        m.name.toLowerCase() === module.toLowerCase() ? { ...m, status } : m
                    );
                    if (!updated.some(m => m.status === 'running') && !updated.some(m => m.status === 'pending' && m.isSelected)) {
                        setIsRunning(false);
                    }
                    return updated;
                });
                if (message) setLogs(prev => [...prev, { time: new Date().toLocaleTimeString(), message: `[${module}] ${message}`, type: status.toUpperCase() }]);
            }
        } else if (data.type === 'RUN_COMPLETE') {
            setIsRunning(false);
            setShowNewTestButton(true);
        }
    };

    const handleRunTest = async () => {
        if (appiumStatus !== 'running') { alert("Appium Server is not running. Start it first."); return; }
        if (!apkUrl && !selectedApk) { alert("Please enter a Google Drive URL or select an existing APK!"); return; }
        if (!resolvedConfig) { alert("No test config registered for this application (check its variant in Apps & Modules)."); return; }
        // Expand every selected module into the concrete suite paths it runs (across
        // the selected types), deduped by path. Config paths already encode the type
        // (tests/test_suites/<type>/…), so pytest gets exact files — no server-side
        // folder collection or type-filtering needed.
        const seenPaths = new Set();
        const testsToRun = modules
            .filter((m) => m.isSelected)
            .flatMap((m) => (m.runTargets || []).map((rt) => ({ name: m.name, path: rt.path })))
            .filter((t) => t.path && !seenPaths.has(t.path) && seenPaths.add(t.path));
        if (!testsToRun.length) {
            alert("No runnable suites for this app + test-type selection. Pick a module (and a test type that includes one)."); return;
        }

        setHasOpenedReport(false);
        setModules(prev => prev.map(m => ({ ...m, status: 'pending' })));
        setIsRunning(true);
        setShowNewTestButton(false);
        setIsDownloading(!!apkUrl);
        setLogs([]);

        handleIncomingData({ type: 'LOG', payload: { message: `Initializing ${selectedDbApp?.application_name || resolvedConfig.label} test with ${testsToRun.length} suite(s)...`, status: 'INFO' } });

        try {
            const runId = crypto.randomUUID();

            // Save network config against this run_id BEFORE starting tests
            // if (networkConfig?.enabled) {
            //     try {
            //         await fetch(`${API_URL}/network-simulate/apply`, {
            //             method: 'POST',
            //             headers: { 'Content-Type': 'application/json' },
            //             body: JSON.stringify({ ...networkConfig, run_id: runId }),
            //         });

            //         // ✅ Log confirmation to the console
            //         handleIncomingData({
            //             type: 'LOG',
            //             payload: {
            //                 message: `📡 Network Simulation Applied → ${networkConfig.networkType} | ${networkConfig.download}Mbps ↓ | ${networkConfig.upload}Mbps ↑ | ${networkConfig.latency}ms latency | ${networkConfig.packetLoss}% loss`,
            //                 status: 'INFO'
            //             }
            //         });

            //     } catch (err) {
            //         console.warn("Network config apply failed:", err);
            //         handleIncomingData({
            //             type: 'LOG',
            //             payload: { message: `⚠️ Network config apply failed: ${err.message}`, status: 'FAILED' }
            //         });
            //     }
            // }

            const payload = {
                tests_to_run: testsToRun,
                app_type: resolvedConfig.id,
                run_id: runId,
                login_phone: loginPhone.trim() || null,
                login_mpin: loginMpin.trim() || null,
                // Config is the single source of truth: the selected test types already
                // resolved to explicit suite paths above, so we don't send test_types
                // (which would trigger server-side folder collection + DB type-filtering).
                test_types: null,
            };
            const endpoint = selectedApk ? '/test/start-test-existing' : '/test/start-test';
            const body = selectedApk ? { ...payload, apk_name: selectedApk } : { ...payload, url: apkUrl };

            const response = await fetch(`${API_URL}${endpoint}`, {
                method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
            });
            const data = await response.json();

            if (!response.ok) {
                const detail = data?.detail || 'Failed to start test';
                handleIncomingData({ type: 'LOG', payload: { message: `❌ Server error: ${detail}`, status: 'FAILED' } });
                throw new Error(detail);
            }

            if (data.app_icon) setAppIcon(data.app_icon);
            if (data.app_name) setAppTitle(data.app_name);
            handleIncomingData({ type: 'LOG', payload: { message: `Backend accepted job. APK Path: ${data.apk_path}`, status: 'SUCCESS' } });

        } catch (error) {
            console.error("Error starting test:", error);
            handleIncomingData({ type: 'LOG', payload: { message: `Error: ${error.message}`, status: 'FAILED' } });
            setIsRunning(false);
        } finally {
            setIsDownloading(false);
        }
    };

    const handleStopTest = async () => {
        try { 
            await fetch(`${API_URL}/test/stop-test`, { 
                method: 'POST' 
            });
         } catch { }

        setIsRunning(false); 
        setIsDownloading(false);
        setShowNewTestButton(true);
        handleIncomingData({ type: 'LOG', payload: { message: 'Test stopped by user.', status: 'FAILED' } });
        setShowStopPopup(true);
    };

    const handleGenerateReport = async () => {
        setShowStopPopup(false);
        try { await fetch(`${API_URL}/test/generate-report`, { method: 'POST' }); } catch { }
        handleIncomingData({ type: 'LOG', payload: { message: 'Generating partial report...', status: 'INFO' } });
    };
    const handleReset = async () => {

        setShowNewTestButton(false);

        // Clear UI states
        setIsRunning(false);
        setIsDownloading(false);

        // Clear APK selections
        setApkUrl('');
        setSelectedApk('');

        // Clear app details
        setAppIcon(null);
        setAppTitle('');

        // Clear logs completely
        setLogs([]);

        // Reset module statuses (fresh from config, all selected)
        setModules(configModules.map((m) => ({ ...m })));

        // Clear session storage
        [
            'apkUrl',
            'selectedApk',
            'logs',
            'modules',
            'isRunning',
            'jiraIssues'
        ].forEach(k => sessionStorage.removeItem(k));

        // Re-fetch fresh statuses
        await checkAppiumStatus();

        handleIncomingData({
            type: 'LOG',
            payload: {
                message: 'Ready for new test execution.',
                status: 'INFO'
            }
        });
    };
    const analyzeUiScreenshots = async () => {
        setUiAnalysisStatus('loading'); setUiAnalysisError('');
        try {
            const res = await fetch(`${API_URL}/llm/ui-screenshots/analyze`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
            const data = await res.json().catch(() => ({}));
            if (!res.ok) throw new Error(data?.detail || 'UI analysis failed');
            setUiAnalysisResults(data.results || []); setUiAnalysisStatus('ready');
        } catch (e) { setUiAnalysisStatus('error'); setUiAnalysisError(e?.message || 'Unknown error'); }
    };

    const checkAppiumStatus = async () => {
        try { const r = await fetch(`${API_URL}/test/appium/status`); setAppiumStatus((await r.json()).status); }
        catch { setAppiumStatus('stopped'); }
    };

    const toggleAppium = async () => {
        try {
            await fetch(`${API_URL}/test/appium/${appiumStatus === 'running' ? 'stop' : 'start'}`, { method: 'POST' });
            setLogs(prev => [
                ...prev,
                {
                    time: new Date().toLocaleTimeString(),
                    message: `Appium server ${appiumStatus === 'running' ? 'stopping' : 'starting'}...`,
                    type: 'SYSTEM'
                }
            ]);
            setTimeout(checkAppiumStatus, 1000);
        } catch { }
    };

    useEffect(() => {
        const checkDevice = async () => {
            try { const r = await fetch(`${API_URL}/test/device-status`); setIsDeviceConnected(!!(await r.json()).connected); }
            catch { setIsDeviceConnected(false); }
        };
        const loadApks = async () => {
            try { const r = await fetch(`${API_URL}/test/apk-list`); setExistingApks((await r.json()).apks || []); } catch { }
        };
        loadApks(); checkDevice(); checkAppiumStatus();
        // Clear stale jiraIssues from old version (IssuePanel now manages its own)
        sessionStorage.removeItem('jiraIssues');
        const id = setInterval(() => { checkDevice(); checkAppiumStatus(); }, 5000);
        return () => clearInterval(id);
    }, []);

    /* ── Render ─────────────────────────────────────────────────────────────── */
    return (
        <div>

            <Header
                appIcon={appIcon} appTitle={appTitle}
                isDeviceConnected={isDeviceConnected} readyState={readyState}
                appiumStatus={appiumStatus}
                uiIssuesOpen={showUiIssuesScreen} uiIssuesLoading={uiAnalysisStatus === "loading"}
                onToggleUiIssues={() => setShowUiIssuesScreen(v => !v)}
            />

            {showUiIssuesScreen && (
                <div className="ui-issues-overlay" role="dialog" aria-modal="true">
                    <div className="ui-issues-overlay-inner">
                        <UIScreenshotIssues
                            status={uiAnalysisStatus} error={uiAnalysisError}
                            results={uiAnalysisResults} onAnalyzeClick={analyzeUiScreenshots}
                            onClose={() => setShowUiIssuesScreen(false)} />
                    </div>
                </div>
            )}

            {showStopPopup && (
                <div style={{ position: 'fixed', inset: 0, background: 'rgba(15,23,42,0.25)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000 }}>
                    <div className="dashboard-card" style={{ width: '400px', padding: '24px', boxShadow: '0 20px 48px rgba(15,23,42,0.18)' }}>
                        <h3 style={{ margin: '0 0 8px', color: 'var(--text-primary)', fontSize: '1rem', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '8px' }}>
                            <AlertCircle size={18} color="#D97706" /> Test Stopped
                        </h3>
                        <p style={{ color: 'var(--text-secondary)', margin: '0 0 20px', fontSize: '0.85rem', lineHeight: '1.6' }}>
                            Tests were stopped manually. Would you like to generate a partial Allure report from the results collected so far?
                        </p>
                        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
                            <button onClick={() => setShowStopPopup(false)}
                                style={{ padding: '7px 16px', borderRadius: '6px', cursor: 'pointer', background: 'transparent', border: '1px solid #E2E8F0', color: 'var(--text-secondary)', fontSize: '0.8rem', fontWeight: 600, fontFamily: 'inherit' }}>
                                No, Close
                            </button>
                            <button onClick={handleGenerateReport}
                                style={{ padding: '7px 18px', borderRadius: '6px', cursor: 'pointer', background: '#2563EB', border: 'none', color: '#fff', fontSize: '0.8rem', fontWeight: 600, fontFamily: 'inherit' }}>
                                Yes, Generate Report
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {/* ── Two-panel layout: left = controls, right = logs+issues ── */}
            <div className="dashboard-grid">

                {/* ── LEFT PANEL: Appium controls + Module Flow + Network Config ── */}
                <div className="dashboard-left-panel">

                    {/* Controls card */}
                    <div className="dashboard-card">
                        {/* Appium server row */}
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', paddingBottom: '12px', marginBottom: '12px', borderBottom: '1px solid #E2E8F0' }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '7px' }}>
                                <div style={{ width: '9px', height: '9px', borderRadius: '50%', backgroundColor: appiumStatus === 'running' ? '#059669' : '#DC2626', boxShadow: appiumStatus === 'running' ? '0 0 0 3px rgba(5,150,105,.15)' : 'none', flexShrink: 0 }} />
                                <span style={{ fontSize: '0.72rem', fontWeight: 700, color: 'var(--text-secondary)', letterSpacing: '0.03em' }}>APPIUM SERVER</span>
                                <span style={{ fontSize: '0.68rem', fontWeight: 600, color: appiumStatus === 'running' ? '#059669' : '#94A3B8', background: appiumStatus === 'running' ? '#ECFDF5' : '#F1F5F9', borderRadius: '4px', padding: '1px 6px' }}>
                                    {appiumStatus === 'running' ? 'Running' : 'Stopped'}
                                </span>
                            </div>
                            <button
                                onClick={toggleAppium}
                                style={{ padding: '5px 12px', borderRadius: '6px', border: appiumStatus === 'running' ? '1px solid #FECACA' : '1px solid #BFDBFE', backgroundColor: appiumStatus === 'running' ? '#FEF2F2' : '#EFF6FF', color: appiumStatus === 'running' ? '#DC2626' : '#2563EB', cursor: 'pointer', fontWeight: 700, fontSize: '0.72rem', fontFamily: 'inherit', transition: 'all 0.15s' }}>
                                {appiumStatus === 'running' ? 'Stop' : 'Start'}
                            </button>
                        </div>
                        <div className="input-group mb-4">
                            <label className="input-label">Select Application</label>
                            <div className="select-wrapper">
                                <select className="text-input" value={selectedAppKey} onChange={e => setSelectedAppKey(e.target.value)} disabled={isRunning}>
                                    {dbApplications.map((app) => (
                                        <option key={app.application_id} value={app.application_id}>{app.application_name}</option>
                                    ))}
                                </select>
                            </div>
                        </div>
                        <div className="input-group mb-4" style={{ display: 'flex', gap: '10px' }}>
                            <div style={{ flex: 2 }}>
                                <label className="input-label">Login Mobile Number</label>
                                <input type="tel" inputMode="numeric" placeholder="e.g. 1234567890" value={loginPhone}
                                    onChange={e => setLoginPhone(e.target.value.replace(/[^0-9]/g, ''))}
                                    className="text-input" disabled={isRunning} maxLength={15} />
                            </div>
                            <div style={{ flex: 1 }}>
                                <label className="input-label">MPIN</label>
                                <input type="text" inputMode="numeric" placeholder="1234" value={loginMpin}
                                    onChange={e => setLoginMpin(e.target.value.replace(/[^0-9]/g, ''))}
                                    className="text-input" disabled={isRunning} maxLength={6} />
                            </div>
                        </div>
                        <div className="input-group mb-4">
                            <label className="input-label">Test Types</label>
                            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', marginTop: '4px' }}>
                                {AVAILABLE_TEST_TYPES.map((tt) => {
                                    const active = selectedTestTypes.includes(tt);
                                    return (
                                        <button
                                            key={tt}
                                            type="button"
                                            disabled={isRunning}
                                            onClick={() => setSelectedTestTypes(prev =>
                                                prev.includes(tt) ? prev.filter(x => x !== tt) : [...prev, tt]
                                            )}
                                            style={{
                                                display: 'flex', alignItems: 'center', gap: '6px',
                                                padding: '5px 11px', borderRadius: '999px',
                                                cursor: isRunning ? 'not-allowed' : 'pointer',
                                                fontSize: '0.75rem', fontWeight: 600, fontFamily: 'inherit',
                                                border: active ? '1px solid var(--accent-blue)' : '1px solid var(--border-color)',
                                                background: active ? 'var(--accent-blue-light)' : 'transparent',
                                                color: active ? 'var(--accent-blue)' : 'var(--text-secondary)',
                                                transition: 'all 0.15s',
                                            }}>
                                            <input type="checkbox" checked={active} readOnly tabIndex={-1}
                                                style={{ pointerEvents: 'none', margin: 0 }} />
                                            {tt}
                                        </button>
                                    );
                                })}
                            </div>
                            <span style={{ color: 'var(--text-muted)', fontSize: '0.7rem', marginTop: '4px', display: 'block' }}>
                                Picks which module suites run for this app. None selected = every type the app defines. Login always runs.
                            </span>
                        </div>
                        <div className="input-group">
                            <label className="input-label">APK Source (Drive URL)</label>
                            <input type="text" placeholder="https://drive.google.com/..." value={apkUrl}
                                onChange={e => { setApkUrl(e.target.value); if (e.target.value) setSelectedApk(''); }}
                                className="text-input" disabled={isRunning || !!selectedApk} />
                        </div>
                        <div className="input-group mt-2">
                            <label className="input-label">OR Select Existing APK</label>
                            <select className="text-input" value={selectedApk}
                                onChange={e => { setSelectedApk(e.target.value); if (e.target.value) setApkUrl(''); }}
                                disabled={isRunning || !!apkUrl}>
                                <option value="">-- Select from Server --</option>
                                {existingApks.map(name => <option key={name} value={name}>{name}</option>)}
                            </select>
                        </div>
                        <div className="action-row mt-4">
                            <button onClick={handleRunTest} disabled={isRunning} className={`run-button ${isRunning ? 'disabled' : ''}`}>
                                <Play size={18} fill="currentColor" />
                                {isDownloading ? 'Downloading...' : isRunning ? 'Running Tests...' : 'Start Automation'}
                            </button>
                            {isRunning && (
                                <button onClick={handleStopTest} className="run-button stop-button ml-2">Stop</button>
                            )}
                            {showNewTestButton && (
                                <button onClick={handleReset} className="run-button ml-2"
                                    style={{ backgroundColor: 'var(--bg-input)', color: 'var(--text-secondary)', border: '1px solid var(--border-color)', boxShadow: 'none' }}>
                                    Start New Test
                                </button>
                            )}
                        </div>
                    </div>

                    {/* Module Flow status */}
                    <div className="grid-item-flo">
                        <ModuleFlow modules={modules} isRunning={isRunning} onToggleModule={toggleModuleSelection} />
                    </div>

                    {/* Test cases catalogued for the selected + matched modules */}
                    <div className="grid-item-flo">
                        <ReadyTestCases modules={modules} />
                        <TestTypeCases selectedTestTypes={selectedTestTypes} applicationId={selectedAppKey} appVariantId={resolvedVariantId} />
                    </div>

                    {/* Network Config */}
                    <NetworkConfigPanel setNetworkConfig={setNetworkConfig} />

                </div>{/* /dashboard-left-panel */}

                {/* ── RIGHT PANEL: Live Logs + Issue Panel side by side ── */}
                <div className="dashboard-right-panel">
                    {/* Log console — grows to fill all remaining width */}
                    <div style={{ flex: '1 1 auto', minWidth: 0, overflow: 'hidden' }}>
                        <LogConsole logs={logs} statusMode={getConsoleStatus()} />
                    </div>
                    {/* Issue panel — fixed 340px, never overflows */}
                    <div style={{ flex: '0 0 340px', width: '340px', display: 'flex', flexDirection: 'column' }}>
                        <IssuePanel
                            modules={modules}
                            onHistoryUpdate={onHistoryUpdate}
                        />
                    </div>
                </div>{/* /dashboard-right-panel */}

            </div>{/* /dashboard-grid */}
        </div>
    );
}

export default TestScreen;