import { BrowserRouter, Routes, Route, NavLink, useLocation } from 'react-router-dom'
import { LayoutDashboard, ListChecks, Shield, AlertTriangle, Search, Bell, CreditCard } from 'lucide-react'
import Dashboard from './components/Dashboard'
import ReviewQueue from './components/ReviewQueue'
import Transactions from './components/Transactions'
import LiveCheckout from './components/LiveCheckout'
import './App.css'

const pageTitles = {
  '/': 'Dashboard',
  '/queue': 'Review Queue',
  '/transactions': 'Transactions',
  '/checkout': 'Live Checkout',
}

function TopBar() {
  const location = useLocation()
  const title = pageTitles[location.pathname] || 'Dashboard'

  return (
    <div className="top-bar">
      <div className="top-bar-left">
        <span className="top-bar-breadcrumb">
          Guardian Ledger <span style={{ margin: '0 6px', color: 'var(--text-muted)' }}>/</span> <span>{title}</span>
        </span>
      </div>
      <div className="top-bar-right">
        <div className="top-bar-search">
          <Search size={14} />
          <span>Search…</span>
          <kbd>⌘K</kbd>
        </div>
        <button className="icon-btn" aria-label="Notifications">
          <Bell size={16} />
        </button>
        <div className="avatar" title="User">GL</div>
      </div>
    </div>
  )
}

function App() {
  return (
    <BrowserRouter>
      <div className="app-layout">
        <aside className="sidebar">
          <div className="sidebar-brand">
            <Shield className="brand-icon" size={24} />
            <h1>Guardian Ledger</h1>
          </div>
          <nav className="sidebar-nav">
            <NavLink to="/" end className={({isActive}) => `nav-link ${isActive ? 'active' : ''}`}>
              <LayoutDashboard size={18} />
              <span>Dashboard</span>
            </NavLink>
            <NavLink to="/queue" className={({isActive}) => `nav-link ${isActive ? 'active' : ''}`}>
              <AlertTriangle size={18} />
              <span>Review Queue</span>
            </NavLink>
            <NavLink to="/transactions" className={({isActive}) => `nav-link ${isActive ? 'active' : ''}`}>
              <ListChecks size={18} />
              <span>Transactions</span>
            </NavLink>
            <NavLink to="/checkout" className={({isActive}) => `nav-link ${isActive ? 'active' : ''}`}>
              <CreditCard size={18} />
              <span>Live Checkout</span>
            </NavLink>
          </nav>
          <div className="sidebar-footer">
            <span className="status-dot"></span>
            <span>System Online</span>
            <span style={{ marginLeft: 'auto', fontSize: '11px', opacity: 0.5 }}>v1.0</span>
          </div>
        </aside>
        <main className="main-content">
          <TopBar />
          <div className="page-content">
            <Routes>
              <Route path="/" element={<Dashboard />} />
              <Route path="/queue" element={<ReviewQueue />} />
              <Route path="/transactions" element={<Transactions />} />
              <Route path="/checkout" element={<LiveCheckout />} />
            </Routes>
          </div>
        </main>
      </div>
    </BrowserRouter>
  )
}
export default App
