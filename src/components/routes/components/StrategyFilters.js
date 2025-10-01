import React, { useState } from 'react';
import { Filter, Clock, TrendingUp, Shield } from 'lucide-react';

const StrategyFilters = ({ 
  selectedSegment, 
  activeFilters, 
  onFilterChange,
  onToggleChange,
  activeStatus 
}) => {
  const [showFilters, setShowFilters] = useState(false);

  // Filter options based on segment
  const getFilterOptions = () => {
    const riskLevels = [
      { id: 'VERY_LOW', label: 'VERY LOW', icon: '🟢' },
      { id: 'LOW', label: 'LOW', icon: '🟢' },
      { id: 'MID', label: 'MID', icon: '🟡' },
      { id: 'HIGH', label: 'HIGH', icon: '🟠' },
      { id: 'VERY_HIGH', label: 'VERY HIGH', icon: '🔴' }
    ];

    if (selectedSegment === 'fno') {
      return {
        strategyType: [
          { id: 'Options', label: 'OPTIONS', icon: '📊' },
          { id: 'Futures', label: 'FUTURES', icon: '📈' },
          { id: 'Hybrid', label: 'HYBRID', icon: '⚡' }
        ],
        holdingPeriod: [
          { id: 'short', label: 'SHORT TERM', icon: '⚡', description: '7-30 days' },
          { id: 'mid', label: 'MID TERM', icon: '📅', description: '30-90 days' },
          { id: 'long', label: 'LONG TERM', icon: '📆', description: '90+ days' }
        ],
        riskLevel: riskLevels
      };
    } else if (selectedSegment === 'equity') {
      return {
        holdingPeriod: [
          { id: 'short', label: 'SHORT TERM', icon: '⚡', description: '7-30 days' },
          { id: 'mid', label: 'MID TERM', icon: '📅', description: '30-90 days' },
          { id: 'long', label: 'LONG TERM', icon: '📆', description: '90+ days' }
        ],
        riskLevel: riskLevels
      };
    }
    return { strategyType: [], holdingPeriod: [], riskLevel: [] };
  };

  const filterOptions = getFilterOptions();

  const handleFilterToggle = (filterType, filterId) => {
    const currentFilters = activeFilters[filterType] || [];
    const newFilters = currentFilters.includes(filterId)
      ? currentFilters.filter(id => id !== filterId)
      : [...currentFilters, filterId];
    
    onFilterChange(filterType, newFilters);
  };


  const hasActiveFilters = () => {
    return (activeFilters.strategyType?.length > 0) || (activeFilters.holdingPeriod?.length > 0) || (activeFilters.riskLevel?.length > 0);
  };

  return (
    <div className="bg-white border-b border-gray-200">
      {/* Filter Toggle Bar */}
      <div className="max-w-7xl mx-auto px-6 py-3">
        <div className="flex items-center justify-between">
          {/* Left: Active Status Toggle - Swiggy Style */}
          <div className="flex items-center gap-2">
            <span className="text-sm text-gray-600">Status:</span>
            <div className="bg-gray-100 rounded-lg p-1 flex">
              <button
                onClick={() => onToggleChange('active')}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-all ${
                  activeStatus === 'active'
                    ? 'bg-green-500 text-white shadow-sm'
                    : 'text-gray-600 hover:text-green-600'
                }`}
              >
                <div className={`w-2 h-2 rounded-full ${activeStatus === 'active' ? 'bg-white' : 'bg-green-500'}`}></div>
                ACTIVE
              </button>
              <button
                onClick={() => onToggleChange('closed')}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-all ${
                  activeStatus === 'closed'
                    ? 'bg-red-500 text-white shadow-sm'
                    : 'text-gray-600 hover:text-red-600'
                }`}
              >
                <div className={`w-2 h-2 rounded-full ${activeStatus === 'closed' ? 'bg-white' : 'bg-red-500'}`}></div>
                CLOSED
              </button>
            </div>
          </div>

          {/* Right: Filter Toggle Button */}
          <div className="flex items-center gap-3">
            <button
              onClick={() => setShowFilters(!showFilters)}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all ${
                showFilters || hasActiveFilters()
                  ? 'bg-blue-100 text-blue-700 border border-blue-200'
                  : 'bg-gray-100 text-gray-600 border border-gray-200 hover:bg-gray-200'
              }`}
            >
              <Filter size={16} />
              {hasActiveFilters() && (
                <span className="bg-blue-600 text-white text-xs rounded-full w-5 h-5 flex items-center justify-center">
                  {(activeFilters.strategyType?.length || 0) + (activeFilters.holdingPeriod?.length || 0) + (activeFilters.riskLevel?.length || 0)}
                </span>
              )}
            </button>
          </div>
        </div>
      </div>

      {/* Filter Options Panel */}
      {showFilters && (
        <div className="border-t border-gray-100 bg-gray-50">
          <div className="max-w-7xl mx-auto px-6 py-4">
            <div className="space-y-4">
              {/* Strategy Type Filters (F&O only) */}
              {filterOptions.strategyType?.length > 0 && (
                <div>
                  <h4 className="text-sm font-semibold text-gray-700 mb-3 flex items-center gap-2">
                    <TrendingUp size={14} />
                    Strategy Type
                  </h4>
                  <div className="flex flex-wrap gap-1.5">
                    {filterOptions.strategyType.map((option) => (
                      <button
                        key={option.id}
                        onClick={() => handleFilterToggle('strategyType', option.id)}
                        className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-xs font-medium transition-all border ${
                          activeFilters.strategyType?.includes(option.id)
                            ? 'bg-blue-100 text-blue-700 border-blue-200'
                            : 'bg-white text-gray-600 border-gray-200 hover:border-blue-200 hover:text-blue-600'
                        }`}
                      >
                        <span className="text-sm">{option.icon}</span>
                        {option.label}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {/* Risk Level Filters */}
              {filterOptions.riskLevel?.length > 0 && (
                <div>
                  <h4 className="text-sm font-semibold text-gray-700 mb-3 flex items-center gap-2">
                    <Shield size={14} />
                    Risk Level
                  </h4>
                  <div className="flex flex-wrap gap-1.5">
                    {filterOptions.riskLevel.map((option) => (
                      <button
                        key={option.id}
                        onClick={() => handleFilterToggle('riskLevel', option.id)}
                        className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-xs font-medium transition-all border ${
                          activeFilters.riskLevel?.includes(option.id)
                            ? 'bg-red-100 text-red-700 border-red-200'
                            : 'bg-white text-gray-600 border-gray-200 hover:border-red-200 hover:text-red-600'
                        }`}
                      >
                        <span className="text-sm">{option.icon}</span>
                        {option.label}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {/* Holding Period Filters */}
              {filterOptions.holdingPeriod?.length > 0 && (
                <div>
                  <h4 className="text-sm font-semibold text-gray-700 mb-3 flex items-center gap-2">
                    <Clock size={14} />
                    Holding Period
                  </h4>
                  <div className="flex flex-wrap gap-1.5">
                    {filterOptions.holdingPeriod.map((option) => (
                      <button
                        key={option.id}
                        onClick={() => handleFilterToggle('holdingPeriod', option.id)}
                        className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-xs font-medium transition-all border ${
                          activeFilters.holdingPeriod?.includes(option.id)
                            ? 'bg-green-100 text-green-700 border-green-200'
                            : 'bg-white text-gray-600 border-gray-200 hover:border-green-200 hover:text-green-600'
                        }`}
                      >
                        <span className="text-sm">{option.icon}</span>
                        <div className="text-left">
                          <div>{option.label}</div>
                          <div className="text-xs text-gray-500">{option.description}</div>
                        </div>
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default StrategyFilters;
