import React from 'react';

const SegmentSelector = ({ segments, selectedSegment, onSegmentChange }) => {
  return (
    <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-4">
      <h2 className="text-lg font-semibold text-gray-900 mb-4">Trading Segments</h2>
      
      {/* Horizontal Scrollable Segments */}
      <div className="flex space-x-3 overflow-x-auto pb-2">
        {segments.map((segment) => (
          <button
            key={segment.id}
            onClick={() => onSegmentChange(segment.id)}
            className={`flex-shrink-0 p-4 rounded-lg border-2 transition-all duration-200 min-w-[140px] ${
              selectedSegment === segment.id
                ? 'border-primary-500 bg-primary-50 shadow-md'
                : 'border-gray-200 bg-white hover:border-gray-300 hover:shadow-sm'
            }`}
          >
            <div className="text-center">
              <div className="text-3xl mb-2">{segment.icon}</div>
              <h3 className="font-semibold text-gray-900 text-sm">{segment.name}</h3>
              <p className="text-xs text-gray-600 mt-1">{segment.description}</p>
            </div>
          </button>
        ))}
      </div>
    </div>
  );
};

export default SegmentSelector;
