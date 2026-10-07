import React from 'react';

export default function TopbarHud() {
  return (
    <div className="topbar-hud-wrapper">
      <svg
        viewBox="0 0 1000 70"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        className="topbar-hud-svg"
      >
        <defs>
          <linearGradient id="hudGlow" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor="#00e5ff" stopOpacity="0.2" />
            <stop offset="50%" stopColor="#00e5ff" stopOpacity="0.9" />
            <stop offset="100%" stopColor="#00e5ff" stopOpacity="0.2" />
          </linearGradient>
          <linearGradient id="cyanFade" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor="#00e5ff" stopOpacity="0" />
            <stop offset="50%" stopColor="#00e5ff" stopOpacity="0.5" />
            <stop offset="100%" stopColor="#00e5ff" stopOpacity="0" />
          </linearGradient>
        </defs>

        {/* Lignes de structure HUD */}
        <path d="M 0 10 L 250 10 L 270 30 L 730 30 L 750 10 L 1000 10" stroke="#00e5ff" strokeWidth="1.5" strokeOpacity="0.4" fill="none" />
        <path d="M 100 20 L 240 20 L 255 35 L 745 35 L 760 20 L 900 20" stroke="url(#cyanFade)" strokeWidth="1" fill="none" />

        {/* Biais et repères d'angles */}
        <path d="M 270 30 L 285 45 L 715 45 L 730 30" stroke="#00e5ff" strokeWidth="2" strokeOpacity="0.8" fill="none" />
        
        {/* Ligne principale brillante du bas */}
        <line x1="0" y1="65" x2="1000" y2="65" stroke="url(#hudGlow)" strokeWidth="2" />
        <line x1="450" y1="65" x2="550" y2="65" stroke="#00e5ff" strokeWidth="4" />

        {/* Blocs technologiques répétitifs */}
        <g opacity="0.7">
          <rect x="20" y="25" width="4" height="15" fill="#00e5ff" />
          <rect x="28" y="25" width="4" height="15" fill="#00e5ff" />
          <rect x="36" y="25" width="4" height="15" fill="#00e5ff" />
          
          <rect x="960" y="25" width="4" height="15" fill="#00e5ff" />
          <rect x="968" y="25" width="4" height="15" fill="#00e5ff" />
          <rect x="976" y="25" width="4" height="15" fill="#00e5ff" />
        </g>

        {/* Repères centraux */}
        <polygon points="500,20 493,10 507,10" fill="#00e5ff" opacity="0.9" />
        <circle cx="500" cy="45" r="3" fill="#00ff9d" />
        <line x1="470" y1="45" x2="490" y2="45" stroke="#00e5ff" strokeWidth="1" />
        <line x1="510" y1="45" x2="530" y2="45" stroke="#00e5ff" strokeWidth="1" />

        {/* Réticules latéraux */}
        <circle cx="200" cy="20" r="2" fill="#00e5ff" />
        <circle cx="800" cy="20" r="2" fill="#00e5ff" />
      </svg>
    </div>
  );
}