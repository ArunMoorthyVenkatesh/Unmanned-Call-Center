import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';

const API_BASE_URL = 'http://localhost:8000';
const API_KEY = 'nUutfYzyfwDyQ99r-7eYkQULAQLpk95zKkhlp-ISmpM';

const axiosHeaders = {
  'X-API-Key': API_KEY,
  'Content-Type': 'application/json',
};

const styles = {
  container: {
    fontFamily: 'Arial, sans-serif',
    padding: '24px',
    maxWidth: '1100px',
    margin: '0 auto',
  },
  heading: {
    fontSize: '24px',
    fontWeight: 'bold',
    marginBottom: '20px',
    color: '#1a1a2e',
  },
  summaryRow: {
    display: 'flex',
    gap: '16px',
    marginBottom: '24px',
    flexWrap: 'wrap',
  },
  card: (color) => ({
    flex: '1 1 180px',
    backgroundColor: color,
    color: '#fff',
    borderRadius: '10px',
    padding: '18px 20px',
    textAlign: 'center',
    boxShadow: '0 2px 6px rgba(0,0,0,0.15)',
  }),
  cardNumber: {
    fontSize: '36px',
    fontWeight: 'bold',
    margin: '4px 0',
  },
  cardLabel: {
    fontSize: '14px',
    opacity: 0.9,
  },
  tableWrapper: {
    overflowX: 'auto',
    borderRadius: '8px',
    boxShadow: '0 2px 8px rgba(0,0,0,0.1)',
  },
  table: {
    width: '100%',
    borderCollapse: 'collapse',
    backgroundColor: '#fff',
  },
  th: {
    backgroundColor: '#2c3e50',
    color: '#fff',
    padding: '12px 14px',
    textAlign: 'left',
    fontSize: '13px',
    fontWeight: '600',
    whiteSpace: 'nowrap',
  },
  td: {
    padding: '11px 14px',
    borderBottom: '1px solid #e8e8e8',
    fontSize: '13px',
    color: '#333',
    verticalAlign: 'middle',
  },
  trEven: {
    backgroundColor: '#f9f9f9',
  },
  badge: (status) => {
    const colors = {
      confirmed: { background: '#dbeafe', color: '#1d4ed8' },
      completed: { background: '#dcfce7', color: '#15803d' },
      cancelled: { background: '#fee2e2', color: '#b91c1c' },
      'no-show': { background: '#fef3c7', color: '#92400e' },
    };
    const c = colors[status] || { background: '#e5e7eb', color: '#374151' };
    return {
      display: 'inline-block',
      padding: '3px 10px',
      borderRadius: '12px',
      fontSize: '12px',
      fontWeight: '600',
      backgroundColor: c.background,
      color: c.color,
    };
  },
  actionBtn: (color) => ({
    marginRight: '6px',
    padding: '5px 12px',
    fontSize: '12px',
    fontWeight: '600',
    border: 'none',
    borderRadius: '5px',
    cursor: 'pointer',
    backgroundColor: color,
    color: '#fff',
    transition: 'opacity 0.2s',
  }),
  refreshRow: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: '14px',
  },
  refreshBtn: {
    padding: '8px 16px',
    fontSize: '13px',
    fontWeight: '600',
    border: 'none',
    borderRadius: '6px',
    cursor: 'pointer',
    backgroundColor: '#2c3e50',
    color: '#fff',
  },
  infoText: {
    fontSize: '12px',
    color: '#888',
  },
  loading: {
    textAlign: 'center',
    padding: '40px',
    color: '#555',
    fontSize: '16px',
  },
  errorText: {
    color: '#b91c1c',
    backgroundColor: '#fee2e2',
    padding: '12px',
    borderRadius: '6px',
    marginBottom: '12px',
  },
  noData: {
    textAlign: 'center',
    padding: '40px',
    color: '#888',
    fontSize: '14px',
  },
};

export default function AppointmentDashboard() {
  const [appointments, setAppointments] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');
  const [lastRefresh, setLastRefresh] = useState(null);

  const fetchAppointments = useCallback(async () => {
    setIsLoading(true);
    setError('');
    try {
      const response = await axios.get(`${API_BASE_URL}/appointments`, {
        headers: axiosHeaders,
      });
      setAppointments(response.data.appointments || []);
      setLastRefresh(new Date());
    } catch (err) {
      const msg = err.response?.data?.message || err.message || 'Failed to fetch appointments.';
      setError(msg);
    } finally {
      setIsLoading(false);
    }
  }, []);

  // Initial load
  useEffect(() => {
    fetchAppointments();
  }, [fetchAppointments]);

  // Auto-refresh every 30 seconds
  useEffect(() => {
    const interval = setInterval(() => {
      fetchAppointments();
    }, 30000);
    return () => clearInterval(interval);
  }, [fetchAppointments]);

  const updateStatus = async (id, status) => {
    try {
      await axios.put(
        `${API_BASE_URL}/appointments/${id}/status`,
        { status },
        { headers: axiosHeaders }
      );
      setAppointments((prev) =>
        prev.map((appt) => (appt.id === id ? { ...appt, status } : appt))
      );
    } catch (err) {
      const msg = err.response?.data?.detail || err.message || 'Failed to update status.';
      alert(`Error: ${msg}`);
    }
  };

  const counts = appointments.reduce(
    (acc, a) => {
      acc.total++;
      if (a.status === 'confirmed') acc.confirmed++;
      else if (a.status === 'completed') acc.completed++;
      else if (a.status === 'cancelled') acc.cancelled++;
      return acc;
    },
    { total: 0, confirmed: 0, completed: 0, cancelled: 0 }
  );

  const summaryCards = [
    { label: 'Total', value: counts.total, color: '#2c3e50' },
    { label: 'Confirmed', value: counts.confirmed, color: '#1d4ed8' },
    { label: 'Completed', value: counts.completed, color: '#15803d' },
    { label: 'Cancelled', value: counts.cancelled, color: '#b91c1c' },
  ];

  return (
    <div style={styles.container}>
      <h2 style={styles.heading}>Service Appointment Dashboard</h2>

      {/* Summary Cards */}
      <div style={styles.summaryRow}>
        {summaryCards.map((card) => (
          <div key={card.label} style={styles.card(card.color)}>
            <div style={styles.cardNumber}>{card.value}</div>
            <div style={styles.cardLabel}>{card.label}</div>
          </div>
        ))}
      </div>

      {/* Refresh controls */}
      <div style={styles.refreshRow}>
        <span style={styles.infoText}>
          {lastRefresh
            ? `Last updated: ${lastRefresh.toLocaleTimeString()} (auto-refreshes every 30s)`
            : 'Loading...'}
        </span>
        <button style={styles.refreshBtn} onClick={fetchAppointments} disabled={isLoading}>
          {isLoading ? 'Refreshing...' : 'Refresh Now'}
        </button>
      </div>

      {error && <div style={styles.errorText}>{error}</div>}

      {isLoading && appointments.length === 0 ? (
        <div style={styles.loading}>Loading appointments...</div>
      ) : (
        <div style={styles.tableWrapper}>
          <table style={styles.table}>
            <thead>
              <tr>
                {['Ref', 'Name', 'Phone', 'Email', 'Vehicle', 'Service', 'Date', 'Time', 'Status', 'Actions'].map(
                  (col) => (
                    <th key={col} style={styles.th}>
                      {col}
                    </th>
                  )
                )}
              </tr>
            </thead>
            <tbody>
              {appointments.length === 0 ? (
                <tr>
                  <td colSpan={10} style={styles.noData}>
                    No appointments found. Appointments booked via phone will appear here.
                  </td>
                </tr>
              ) : (
                appointments.map((appt, idx) => (
                  <tr key={appt.appointment_id} style={idx % 2 === 1 ? styles.trEven : {}}>
                    <td style={styles.td} title={appt.appointment_id}>{appt.appointment_id?.slice(0, 8) || '-'}</td>
                    <td style={styles.td}>{appt.name || '-'}</td>
                    <td style={styles.td}>{appt.phone || '-'}</td>
                    <td style={styles.td}>{appt.email || '-'}</td>
                    <td style={styles.td}>{appt.vehicle || '-'}</td>
                    <td style={styles.td}>{appt.service_type || '-'}</td>
                    <td style={styles.td}>{appt.appointment_date || '-'}</td>
                    <td style={styles.td}>{appt.appointment_time || '-'}</td>
                    <td style={styles.td}>
                      <span style={styles.badge(appt.status)}>{appt.status}</span>
                    </td>
                    <td style={styles.td}>
                      {appt.status !== 'completed' && (
                        <button
                          style={styles.actionBtn('#15803d')}
                          onClick={() => updateStatus(appt.appointment_id, 'completed')}
                          title="Mark as completed"
                        >
                          Complete
                        </button>
                      )}
                      {appt.status !== 'cancelled' && (
                        <button
                          style={styles.actionBtn('#b91c1c')}
                          onClick={() => updateStatus(appt.appointment_id, 'cancelled')}
                          title="Cancel appointment (reminders will be cancelled)"
                        >
                          Cancel
                        </button>
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
