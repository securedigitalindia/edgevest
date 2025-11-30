import React from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import BottomNavigation from './components/BottomNavigation';
import Trades from './components/routes/Trades';
import Portfolio from './components/routes/Portfolio';

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
    <Router>
      <div className="App">
        <Routes>
          <Route path="/" element={<Navigate to="/portfolio" replace />} />
          <Route path="/portfolio" element={<Portfolio />} />
          <Route path="/trades" element={<Trades />} />
          <Route path="/profile" element={<Profile />} />
        </Routes>
        <BottomNavigation />
      </div>
    </Router>
  );
}

export default App;
