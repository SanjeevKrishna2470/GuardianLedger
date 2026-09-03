// Centralized API configuration
// Uses VITE_API_URL if defined; defaults to the deployed backend on Render
export const API_BASE = import.meta.env.VITE_API_URL || 'https://guardianledger.onrender.com';
