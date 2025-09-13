import React from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { AppProvider } from './context/AppContext';
import BottomNavigation from './components/BottomNavigation';
import Dashboard from './components/routes/Dashboard';
import Trades from './components/routes/Trades';

const Portfolio = () => (
  <div className="min-h-screen bg-gray-50 flex items-center justify-center pb-20">
    <div className="text-center">
      <h2 className="text-2xl font-bold text-gray-900 mb-2">Portfolio</h2>
      <p className="text-gray-600">Coming soon...</p>
    </div>
  </div>
);

const Analysis = () => (
  <div className="min-h-screen bg-gray-50 flex items-center justify-center pb-20">
    <div className="text-center">
      <h2 className="text-2xl font-bold text-gray-900 mb-2">Analysis</h2>
      <p className="text-gray-600">Coming soon...</p>
    </div>
  </div>
);

const Profile = () => (
  <div className="min-h-screen bg-gray-50 flex items-center justify-center pb-20">
    <div className="text-center">
      <h2 className="text-2xl font-bold text-gray-900 mb-2">Profile</h2>
      <p className="text-gray-600">Coming soon...</p>
    </div>
  </div>
);

function App() {
  return (
    <AppProvider>
      <Router>
        <div className="App">
          <Routes>
            <Route path="/" element={<Navigate to="/dashboard" replace />} />
            <Route path="/dashboard" element={<Dashboard />} />
            <Route path="/trades" element={<Trades />} />
            <Route path="/portfolio" element={<Portfolio />} />
            <Route path="/analysis" element={<Analysis />} />
            <Route path="/profile" element={<Profile />} />
          </Routes>
          <BottomNavigation />
        </div>
      </Router>
    </AppProvider>
  );
}

export default App;
