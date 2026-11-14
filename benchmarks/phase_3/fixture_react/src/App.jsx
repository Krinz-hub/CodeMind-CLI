import React, { useState } from 'react';
import Header from './components/Header';
import Dashboard from './components/Dashboard';
import './styles/main.css';

export default function App() {
  const [activeSession, setActiveSession] = useState('cm-dev-session-01');
  const [tasks, setTasks] = useState([
    { id: '1', title: 'Inspect repository architecture', status: 'completed' },
    { id: '2', title: 'Verify test suite coverage', status: 'in_progress' },
  ]);

  return (
    <div className="app-container">
      <Header sessionName={activeSession} />
      <main className="main-content">
        <Dashboard tasks={tasks} />
      </main>
    </div>
  );
}
