import React from 'react';
import { Play, Square } from 'lucide-react';

const StatusToggle = ({ activeStatus, onStatusChange }) => {
  return (
    <div className="px-4 pb-4">
      <div className="flex items-center justify-center">
        <div className="bg-gray-100 rounded-lg p-1 flex">
          <button
            onClick={() => onStatusChange('active')}
            className={`flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium transition-all ${
              activeStatus === 'active'
                ? 'bg-white text-green-700 shadow-sm'
                : 'text-gray-600 hover:text-gray-900'
            }`}
          >
            <Play size={16} />
            Active Trades
          </button>
          <button
            onClick={() => onStatusChange('closed')}
            className={`flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium transition-all ${
              activeStatus === 'closed'
                ? 'bg-white text-red-700 shadow-sm'
                : 'text-gray-600 hover:text-gray-900'
            }`}
          >
            <Square size={16} />
            Closed Trades
          </button>
        </div>
      </div>
    </div>
  );
};

export default StatusToggle;
