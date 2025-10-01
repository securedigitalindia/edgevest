import React from 'react';
import { Play, Square } from 'lucide-react';

const StatusToggle = ({ activeStatus, onStatusChange }) => {
  return (
    <div className="flex items-center justify-center">
      <div className="flex gap-2">
        <button
          onClick={() => onStatusChange('active')}
          className={`relative px-4 py-2 rounded-full font-medium text-xs transition-all duration-300 flex items-center gap-1.5 ${
            activeStatus === 'active'
              ? 'bg-gradient-to-r from-green-600 to-green-700 text-white shadow-lg shadow-green-200 transform scale-105'
              : 'bg-white text-gray-600 hover:text-green-600 hover:shadow-md border border-gray-200 hover:border-green-200'
          }`}
        >
          <Play size={12} />
          Active
          {activeStatus === 'active' && (
            <div className="absolute inset-0 bg-gradient-to-r from-green-400 to-green-500 rounded-full opacity-20 animate-pulse"></div>
          )}
        </button>
        <button
          onClick={() => onStatusChange('closed')}
          className={`relative px-4 py-2 rounded-full font-medium text-xs transition-all duration-300 flex items-center gap-1.5 ${
            activeStatus === 'closed'
              ? 'bg-gradient-to-r from-red-600 to-red-700 text-white shadow-lg shadow-red-200 transform scale-105'
              : 'bg-white text-gray-600 hover:text-red-600 hover:shadow-md border border-gray-200 hover:border-red-200'
          }`}
        >
          <Square size={12} />
          Closed
          {activeStatus === 'closed' && (
            <div className="absolute inset-0 bg-gradient-to-r from-red-400 to-red-500 rounded-full opacity-20 animate-pulse"></div>
          )}
        </button>
      </div>
    </div>
  );
};

export default StatusToggle;
