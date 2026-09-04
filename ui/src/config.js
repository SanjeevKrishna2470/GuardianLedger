// Centralized API configuration
// Uses VITE_API_URL if defined; defaults to the deployed backend on Render
export const API_BASE = import.meta.env.VITE_API_URL || 'https://guardianledger.onrender.com';

export const fetchAuth = async (url, options = {}) => {
  const token = localStorage.getItem('gl_token');
  const headers = { ...options.headers };
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }
  
  const res = await fetch(url, { ...options, headers });
  if (res.status === 401) {
    localStorage.removeItem('gl_token');
    window.location.reload();
  }
  return res;
};
