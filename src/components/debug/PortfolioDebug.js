import React, { useState, useEffect } from 'react';

const PortfolioDebug = () => {
  const [localStorageData, setLocalStorageData] = useState(null);
  const [isVisible, setIsVisible] = useState(false);

  useEffect(() => {
    const checkLocalStorage = () => {
      const portfolio = localStorage.getItem('userPortfolio');
      const capital = localStorage.getItem('totalCapital');
      setLocalStorageData({
        portfolio: portfolio ? JSON.parse(portfolio) : null,
        capital: capital ? parseFloat(capital) : null,
        rawPortfolio: portfolio,
        rawCapital: capital
      });
    };

    checkLocalStorage();
    
    // Listen for changes
    const handleStorageChange = () => {
      checkLocalStorage();
    };

    window.addEventListener('storage', handleStorageChange);
    window.addEventListener('portfolioUpdated', handleStorageChange);

    return () => {
      window.removeEventListener('storage', handleStorageChange);
      window.removeEventListener('portfolioUpdated', handleStorageChange);
    };
  }, []);

  if (!isVisible) {
    return (
      <button
        onClick={() => setIsVisible(true)}
        className="fixed bottom-4 right-4 bg-red-600 text-white px-3 py-2 rounded-lg text-sm z-50"
      >
        Debug Portfolio
      </button>
    );
  }

  return (
    <div className="fixed bottom-4 right-4 bg-white border border-gray-300 rounded-lg p-4 max-w-md max-h-96 overflow-y-auto shadow-lg z-50">
      <div className="flex justify-between items-center mb-2">
        <h3 className="font-semibold text-gray-900">Portfolio Debug</h3>
        <button
          onClick={() => setIsVisible(false)}
          className="text-gray-500 hover:text-gray-700"
        >
          ✕
        </button>
      </div>
      
      <div className="space-y-2 text-sm">
        <div>
          <strong>Portfolio Count:</strong> {localStorageData?.portfolio?.length || 0}
        </div>
        
        <div>
          <strong>Total Capital:</strong> {localStorageData?.capital ? `₹${localStorageData.capital.toLocaleString()}` : 'Not set'}
        </div>
        
        <div>
          <strong>Raw Portfolio Data:</strong>
          <pre className="bg-gray-100 p-2 rounded text-xs overflow-x-auto">
            {localStorageData?.rawPortfolio || 'null'}
          </pre>
        </div>
        
        <div>
          <strong>Parsed Portfolio:</strong>
          <pre className="bg-gray-100 p-2 rounded text-xs overflow-x-auto">
            {JSON.stringify(localStorageData?.portfolio, null, 2)}
          </pre>
        </div>
        
        <button
          onClick={() => {
            localStorage.removeItem('userPortfolio');
            localStorage.removeItem('totalCapital');
            setLocalStorageData({
              portfolio: null,
              capital: null,
              rawPortfolio: null,
              rawCapital: null
            });
          }}
          className="w-full bg-red-600 text-white px-2 py-1 rounded text-xs"
        >
          Clear All Data
        </button>
      </div>
    </div>
  );
};

export default PortfolioDebug;
