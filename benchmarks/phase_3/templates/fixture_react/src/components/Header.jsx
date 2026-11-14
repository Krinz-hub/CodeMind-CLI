import React from 'react';

export default function Header({ sessionName }) {
  return (
    <header className="header-bar">
      <div className="brand-logo">▟●▙ CodeMind Companion</div>
      <div className="session-indicator">Session: {sessionName}</div>
    </header>
  );
}
