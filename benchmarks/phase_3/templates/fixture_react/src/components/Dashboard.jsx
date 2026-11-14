import React from 'react';

export default function Dashboard({ tasks }) {
  const completedCount = tasks.filter(t => t.status === 'completed').length;

  return (
    <div className="dashboard-grid">
      <div className="metric-card">
        <h3>Tasks Completed</h3>
        <p className="metric-number">{completedCount} / {tasks.length}</p>
      </div>
      <div className="task-list">
        <h3>Active Plan</h3>
        <ul>
          {tasks.map(t => (
            <li key={t.id} className={`task-item ${t.status}`}>
              <span className="task-title">{t.title}</span>
              <span className="task-badge">{t.status}</span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
