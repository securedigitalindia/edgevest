import React from 'react';
import { TrendingUp, Target } from 'lucide-react';

const SegmentSelector = ({ segments, selectedSegment, onSegmentChange }) => {
  const getSegmentIcon = (segmentId) => {
    const icons = {
      'equity': TrendingUp,
      'fno': Target
    };
    return icons[segmentId] || TrendingUp;
  };

  const getSegmentGradient = (segmentId, isSelected) => {
    const gradients = {
      'equity': isSelected 
        ? 'from-green-500 to-emerald-600' 
        : 'from-green-50 to-emerald-50',
      'fno': isSelected 
        ? 'from-purple-500 to-violet-600' 
        : 'from-purple-50 to-violet-50'
    };
    return gradients[segmentId] || 'from-gray-50 to-gray-100';
  };

  const getSegmentTextColor = (segmentId, isSelected) => {
    const colors = {
      'equity': isSelected ? 'text-white' : 'text-green-700',
      'fno': isSelected ? 'text-white' : 'text-purple-700'
    };
    return colors[segmentId] || 'text-gray-700';
  };

  const getSegmentIconColor = (segmentId, isSelected) => {
    const colors = {
      'equity': isSelected ? '#ffffff' : '#10b981',
      'fno': isSelected ? '#ffffff' : '#8b5cf6'
    };
    return colors[segmentId] || '#6b7280';
  };

  return (
    <div className="px-4 pb-6">
      {/* Header */}
      <div className="mb-4">
        <h2 className="text-lg font-bold text-gray-900">Trading Segments</h2>
      </div>

      {/* Segment Cards */}
      <div className="grid grid-cols-2 gap-3">
        {segments.map((segment) => {
          const isSelected = selectedSegment?.id === segment.id;
          const IconComponent = getSegmentIcon(segment.id);
          const gradient = getSegmentGradient(segment.id, isSelected);
          const textColor = getSegmentTextColor(segment.id, isSelected);
          const iconColor = getSegmentIconColor(segment.id, isSelected);

          return (
            <button
              key={segment.id}
              onClick={() => onSegmentChange(segment)}
              className={`
                relative p-4 rounded-2xl border-2 transition-all duration-200 transform hover:scale-105
                ${isSelected 
                  ? 'border-transparent shadow-lg' 
                  : 'border-gray-200 hover:border-gray-300 shadow-sm hover:shadow-md'
                }
                bg-gradient-to-br ${gradient}
              `}
            >
              {/* Selection Indicator */}
              {isSelected && (
                <div className="absolute -top-1 -right-1 w-6 h-6 bg-white rounded-full flex items-center justify-center shadow-md">
                  <div className="w-3 h-3 bg-current rounded-full" style={{ backgroundColor: iconColor }}></div>
                </div>
              )}

              {/* Icon */}
              <div className="flex items-center justify-center mb-3">
                <div className={`
                  w-12 h-12 rounded-xl flex items-center justify-center
                  ${isSelected ? 'bg-white bg-opacity-20' : 'bg-white bg-opacity-50'}
                `}>
                  <IconComponent size={24} color={iconColor} />
                </div>
              </div>

              {/* Content */}
              <div className="text-center">
                <h3 className={`font-bold text-sm ${textColor}`}>
                  {segment.name}
                </h3>
              </div>

              {/* Active Indicator */}
              {isSelected && (
                <div className="absolute bottom-0 left-0 right-0 h-1 bg-white bg-opacity-30 rounded-b-2xl"></div>
              )}
            </button>
          );
        })}
      </div>

    </div>
  );
};

export default SegmentSelector;