import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';

const API_BASE_URL = 'http://localhost:8000';
const API_KEY = 'nUutfYzyfwDyQ99r-7eYkQULAQLpk95zKkhlp-ISmpM';

const axiosHeaders = {
  'X-API-Key': API_KEY,
  'Content-Type': 'application/json',
};

const S = {
  wrap: {
    fontFamily: '-apple-system, BlinkMacSystemFont, "Inter", "SF Pro Display", "Segoe UI", sans-serif',
    padding: '28px 28px 32px',
    WebkitFontSmoothing: 'antialiased',
  },
  topRow: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: '24px',
    flexWrap: 'wrap',
    gap: '12px',
  },
  heading: {
    fontSize: '20px',
    fontWeight: '700',
    color: 'var(--text)',
    letterSpacing: '-0.4px',
  },
  sub: {
    fontSize: '12px',
    color: 'var(--text-sub)',
    marginTop: '2px',
  },
  refreshBtn: {
    padding: '8px 18px',
    fontSize: '12px',
    fontWeight: '600',
    border: '1px solid var(--border)',
    borderRadius: '9px',
    cursor: 'pointer',
    background: 'transparent',
    color: 'var(--text-sub)',
    transition: 'all 0.2s',
    letterSpacing: '0.1px',
  },
  statsRow: {
    display: 'flex',
    gap: '12px',
    marginBottom: '24px',
    flexWrap: 'wrap',
  },
  statCard: (accent) => ({
    flex: '1 1 140px',
    background: 'var(--surface2-s)',
    border: `1px solid ${accent}33`,
    borderRadius: '14px',
    padding: '16px 18px',
    display: 'flex',
    flexDirection: 'column',
    gap: '4px',
    boxShadow: `0 0 20px ${accent}0a`,
  }),
  statNum: (accent) => ({
    fontSize: '34px',
    fontWeight: '700',
    color: accent,
    lineHeight: 1,
    letterSpacing: '-1px',
  }),
  statLabel: {
    fontSize: '12px',
    color: 'var(--text-sub)',
    fontWeight: '500',
    textTransform: 'uppercase',
    letterSpacing: '0.5px',
  },
  tableOuter: {
    overflowX: 'auto',
    border: '1px solid var(--border)',
    borderRadius: '14px',
  },
  table: {
    width: '100%',
    borderCollapse: 'collapse',
    fontSize: '13px',
  },
  thead: {
    background: 'rgba(0,0,0,0.25)',
  },
  th: {
    padding: '11px 14px',
    textAlign: 'left',
    fontSize: '11px',
    fontWeight: '600',
    color: 'var(--text-sub)',
    textTransform: 'uppercase',
    letterSpacing: '0.6px',
    whiteSpace: 'nowrap',
    borderBottom: '1px solid var(--border)',
  },
  td: {
    padding: '12px 14px',
    color: 'var(--text)',
    borderBottom: '1px solid var(--border)',
    verticalAlign: 'middle',
    whiteSpace: 'nowrap',
  },
  tdMuted: {
    color: 'var(--text-sub)',
  },
  badge: (status) => {
    const map = {
      confirmed: { bg: 'rgba(0,200,192,0.12)', fg: '#00c8c0', border: 'rgba(0,200,192,0.25)' },
      completed: { bg: 'rgba(45,214,126,0.12)', fg: '#2dd67e', border: 'rgba(45,214,126,0.25)' },
      cancelled: { bg: 'rgba(255,74,94,0.12)',  fg: '#ff4a5e', border: 'rgba(255,74,94,0.25)' },
      'no-show': { bg: 'rgba(251,191,36,0.12)', fg: '#fbbf24', border: 'rgba(251,191,36,0.25)' },
    };
    const c = map[status] || { bg: 'rgba(255,255,255,0.06)', fg: 'var(--text-sub)', border: 'var(--border)' };
    return {
      display: 'inline-block',
      padding: '3px 10px',
      borderRadius: '20px',
      fontSize: '11.5px',
      fontWeight: '600',
      backgroundColor: c.bg,
      color: c.fg,
      border: `1px solid ${c.border}`,
      letterSpacing: '0.2px',
    };
  },
  actionBtn: (accent, bg) => ({
    marginRight: '6px',
    padding: '5px 12px',
    fontSize: '11.5px',
    fontWeight: '600',
    border: `1px solid ${accent}44`,
    borderRadius: '7px',
    cursor: 'pointer',
    background: bg,
    color: accent,
    transition: 'all 0.18s',
    letterSpacing: '0.1px',
  }),
  empty: {
    textAlign: 'center',
    padding: '48px 20px',
    color: 'var(--text-sub)',
    fontSize: '13.5px',
  },
  loadState: {
    textAlign: 'center',
    padding: '40px',
    color: 'var(--text-sub)',
    fontSize: '14px',
  },
  errBox: {
    background: 'rgba(255,74,94,0.08)',
    border: '1px solid rgba(255,74,94,0.25)',
    color: '#ff8a99',
    padding: '10px 14px',
    borderRadius: '10px',
    fontSize: '13px',
    marginBottom: '16px',
  },
};

export default function AppointmentDashboard() {
  const [appointments, setAppointments] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError]           = useState('');
  const [lastRefresh, setLastRefresh] = useState(null);

  const fetchAppointments = useCallback(async () => {
    setIsLoading(true);
    setError('');
    try {
      const res = await axios.get(`${API_BASE_URL}/appointments`, { headers: axiosHeaders });
      setAppointments(res.data.appointments || []);
      setLastRefresh(new Date());
    } catch (err) {
      setError(err.response?.data?.message || err.message || 'Failed to fetch appointments.');
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => { fetchAppointments(); }, [fetchAppointments]);

  useEffect(() => {
    const id = setInterval(fetchAppointments, 30000);
    return () => clearInterval(id);
  }, [fetchAppointments]);

  const updateStatus = async (id, status) => {
    try {
      await axios.put(`${API_BASE_URL}/appointments/${id}/status`, { status }, { headers: axiosHeaders });
      setAppointments(prev => prev.map(a => a.appointment_id === id ? { ...a, status } : a));
    } catch (err) {
      alert(`Error: ${err.response?.data?.detail || err.message}`);
    }
  };

  const counts = appointments.reduce(
    (acc, a) => { acc.total++; acc[a.status] = (acc[a.status] || 0) + 1; return acc; },
    { total: 0, confirmed: 0, completed: 0, cancelled: 0 }
  );

  const stats = [
    { label: 'Total',     value: counts.total,     accent: '#8899aa' },
    { label: 'Confirmed', value: counts.confirmed,  accent: '#00c8c0' },
    { label: 'Completed', value: counts.completed,  accent: '#2dd67e' },
    { label: 'Cancelled', value: counts.cancelled,  accent: '#ff4a5e' },
  ];

  const cols = ['Ref', 'Name', 'Phone', 'Vehicle', 'Service', 'Date', 'Time', 'Status', 'Actions'];

  return (
    <div style={S.wrap}>
      {/* Header */}
      <div style={S.topRow}>
        <div>
          <div style={S.heading}>Appointments</div>
          <div style={S.sub}>
            {lastRefresh ? `Updated ${lastRefresh.toLocaleTimeString()} · auto-refresh 30s` : 'Loading…'}
          </div>
        </div>
        <button
          style={S.refreshBtn}
          onClick={fetchAppointments}
          disabled={isLoading}
          onMouseEnter={e => { e.target.style.borderColor = 'var(--teal)'; e.target.style.color = 'var(--teal)'; }}
          onMouseLeave={e => { e.target.style.borderColor = 'var(--border)'; e.target.style.color = 'var(--text-sub)'; }}
        >
          {isLoading ? 'Refreshing…' : 'Refresh'}
        </button>
      </div>

      {/* Stats */}
      <div style={S.statsRow}>
        {stats.map(s => (
          <div key={s.label} style={S.statCard(s.accent)}>
            <div style={S.statNum(s.accent)}>{s.value}</div>
            <div style={S.statLabel}>{s.label}</div>
          </div>
        ))}
      </div>

      {error && <div style={S.errBox}>{error}</div>}

      {/* Table */}
      {isLoading && appointments.length === 0 ? (
        <div style={S.loadState}>Loading appointments…</div>
      ) : (
        <div style={S.tableOuter}>
          <table style={S.table}>
            <thead style={S.thead}>
              <tr>
                {cols.map(c => <th key={c} style={S.th}>{c}</th>)}
              </tr>
            </thead>
            <tbody>
              {appointments.length === 0 ? (
                <tr>
                  <td colSpan={cols.length} style={S.empty}>
                    No appointments yet. Bookings made via phone or chat will appear here.
                  </td>
                </tr>
              ) : (
                appointments.map(appt => (
                  <tr
                    key={appt.appointment_id}
                    onMouseEnter={e => { e.currentTarget.style.background = 'rgba(255,255,255,0.03)'; }}
                    onMouseLeave={e => { e.currentTarget.style.background = 'transparent'; }}
                    style={{ transition: 'background 0.15s' }}
                  >
                    <td style={{ ...S.td, ...S.tdMuted, fontFamily: 'monospace', fontSize: '11.5px' }}
                        title={appt.appointment_id}>
                      {appt.appointment_id?.slice(0, 8) || '-'}
                    </td>
                    <td style={S.td}>{appt.name || '-'}</td>
                    <td style={{ ...S.td, ...S.tdMuted }}>{appt.phone || '-'}</td>
                    <td style={S.td}>{appt.vehicle || '-'}</td>
                    <td style={S.td}>{appt.service_type || '-'}</td>
                    <td style={{ ...S.td, ...S.tdMuted }}>{appt.appointment_date || '-'}</td>
                    <td style={{ ...S.td, ...S.tdMuted }}>{appt.appointment_time || '-'}</td>
                    <td style={S.td}>
                      <span style={S.badge(appt.status)}>{appt.status}</span>
                    </td>
                    <td style={S.td}>
                      {appt.status !== 'completed' && (
                        <button
                          style={S.actionBtn('#2dd67e', 'rgba(45,214,126,0.08)')}
                          onClick={() => updateStatus(appt.appointment_id, 'completed')}
                          onMouseEnter={e => { e.target.style.background = 'rgba(45,214,126,0.16)'; }}
                          onMouseLeave={e => { e.target.style.background = 'rgba(45,214,126,0.08)'; }}
                        >Complete</button>
                      )}
                      {appt.status !== 'cancelled' && (
                        <button
                          style={S.actionBtn('#ff4a5e', 'rgba(255,74,94,0.08)')}
                          onClick={() => updateStatus(appt.appointment_id, 'cancelled')}
                          onMouseEnter={e => { e.target.style.background = 'rgba(255,74,94,0.16)'; }}
                          onMouseLeave={e => { e.target.style.background = 'rgba(255,74,94,0.08)'; }}
                        >Cancel</button>
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
