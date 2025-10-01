import { useState, useEffect, useCallback } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import tradeService from '../services/tradeService';

export const useTrade = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const [segments, setSegments] = useState([]);
  const [allStrategies, setAllStrategies] = useState([]);
  const [strategies, setStrategies] = useState([]);
  const [marketData, setMarketData] = useState(null);
  const [selectedSegment, setSelectedSegment] = useState(null);
  const [selectedStrategy, setSelectedStrategy] = useState(null);
  const [tradeStatus, setTradeStatus] = useState('active');
  const [activeFilters, setActiveFilters] = useState({
    strategyType: [],
    holdingPeriod: [],
    riskLevel: []
  });
  const [showPopup, setShowPopup] = useState(true);
  const [livePrices, setLivePrices] = useState({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // Fetch trading segments
  const fetchSegments = useCallback(async () => {
    try {
      setLoading(true);
      const data = await tradeService.getTradingSegments();
      setSegments(data);
      setError(null);
    } catch (err) {
      setError(err.message);
      console.error('Error fetching segments:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  // Helper function to determine holding period category
  const getHoldingPeriodCategory = (holdingPeriod) => {
    if (!holdingPeriod) return 'mid';
    const period = holdingPeriod.toLowerCase();
    if (period.includes('7-30') || period.includes('short')) return 'short';
    if (period.includes('90+') || period.includes('long')) return 'long';
    return 'mid';
  };

  // Apply all filters to strategies
  const applyFilters = useCallback((strategiesToFilter, status, filters) => {
    let filtered = strategiesToFilter.filter(strategy => strategy.status === status);

    // Apply strategy type filter (F&O only)
    if (filters.strategyType.length > 0 && selectedSegment === 'fno') {
      filtered = filtered.filter(strategy => 
        filters.strategyType.includes(strategy.strategyType)
      );
    }

    // Apply risk level filter
    if (filters.riskLevel.length > 0) {
      filtered = filtered.filter(strategy => 
        filters.riskLevel.includes(strategy.riskLevel)
      );
    }

    // Apply holding period filter
    if (filters.holdingPeriod.length > 0) {
      filtered = filtered.filter(strategy => {
        const category = getHoldingPeriodCategory(strategy.holdingPeriod);
        return filters.holdingPeriod.includes(category);
      });
    }

    return filtered;
  }, [selectedSegment]);

  // Fetch strategies for selected segment (load all, filter locally)
  const fetchStrategies = useCallback(async (segment) => {
    try {
      setLoading(true);
      
      // Load ALL strategies for the segment (both active and closed)
      const data = await tradeService.getStrategiesBySegment(segment);
      setAllStrategies(data);
      
      // Apply filters locally for fast switching
      const filteredData = applyFilters(data, tradeStatus, activeFilters);
      setStrategies(filteredData);
      setError(null);
    } catch (err) {
      setError(err.message);
      console.error('Error fetching strategies:', err);
    } finally {
      setLoading(false);
    }
  }, [tradeStatus, activeFilters, applyFilters]);

  // Filter strategies by status and other filters (local filtering for fast switching)
  const filterStrategiesByStatus = useCallback((status) => {
    setTradeStatus(status);
    
    // Fast local filtering - no API calls needed
    const filteredData = applyFilters(allStrategies, status, activeFilters);
    setStrategies(filteredData);
  }, [allStrategies, activeFilters, applyFilters]);

  // Update filters and reapply
  const updateFilters = useCallback((filterType, filterValues) => {
    const newFilters = {
      ...activeFilters,
      [filterType]: filterValues
    };
    setActiveFilters(newFilters);
    
    // Reapply filters to current strategies
    const filteredData = applyFilters(allStrategies, tradeStatus, newFilters);
    setStrategies(filteredData);
  }, [activeFilters, allStrategies, tradeStatus, applyFilters]);

  // Clear all filters
  const clearAllFilters = useCallback(() => {
    const clearedFilters = {
      strategyType: [],
      holdingPeriod: [],
      riskLevel: []
    };
    setActiveFilters(clearedFilters);
    
    // Reapply with cleared filters
    const filteredData = applyFilters(allStrategies, tradeStatus, clearedFilters);
    setStrategies(filteredData);
  }, [allStrategies, tradeStatus, applyFilters]);

  // Fetch market data
  const fetchMarketData = useCallback(async () => {
    try {
      const data = await tradeService.getMarketData();
      setMarketData(data);
    } catch (err) {
      console.error('Error fetching market data:', err);
    }
  }, []);

  // Fetch live price for a symbol
  const fetchLivePrice = useCallback(async (symbol) => {
    try {
      const priceData = await tradeService.getLivePrice(symbol);
      setLivePrices(prev => ({
        ...prev,
        [symbol]: priceData
      }));
    } catch (err) {
      console.error('Error fetching live price:', err);
    }
  }, []);

  // Execute trade
  const executeTrade = async (tradeData) => {
    try {
      setLoading(true);
      const result = await tradeService.executeTrade(tradeData);
      setError(null);
      return result;
    } catch (err) {
      setError(err.message);
      throw err;
    } finally {
      setLoading(false);
    }
  };

  // Get risk analysis
  const getRiskAnalysis = async (strategyId) => {
    try {
      const analysis = await tradeService.getRiskAnalysis(strategyId);
      return analysis;
    } catch (err) {
      console.error('Error fetching risk analysis:', err);
      throw err;
    }
  };

  // Handle segment change
  const handleSegmentChange = useCallback((segment) => {
    const segmentId = typeof segment === 'object' ? segment.id : segment;
    setSelectedSegment(segmentId);
    setSelectedStrategy(null);
    fetchStrategies(segmentId);
  }, [fetchStrategies]);

  // Get URL parameters
  const getUrlParams = useCallback(() => {
    const searchParams = new URLSearchParams(location.search);
    return {
      tradeId: searchParams.get('tradeId'),
      segment: searchParams.get('segment'),
      status: searchParams.get('status'),
      openModal: searchParams.get('openModal') === 'true',
      showPopup: searchParams.get('showPopup') !== 'false' // Default to true unless explicitly false
    };
  }, [location.search]);

  // Update URL with current state
  const updateUrl = useCallback((params) => {
    const searchParams = new URLSearchParams(location.search);
    
    Object.entries(params).forEach(([key, value]) => {
      if (value) {
        searchParams.set(key, value);
      } else {
        searchParams.delete(key);
      }
    });

    const newUrl = `${location.pathname}${searchParams.toString() ? '?' + searchParams.toString() : ''}`;
    navigate(newUrl, { replace: true });
  }, [location.pathname, location.search, navigate]);

  // Navigate to specific trade
  const navigateToTrade = useCallback((tradeId, options = {}) => {
    const params = {
      tradeId,
      ...(options.segment && { segment: options.segment }),
      ...(options.status && { status: options.status }),
      ...(options.openModal && { openModal: 'true' }),
      ...(options.showPopup !== undefined && { showPopup: options.showPopup.toString() })
    };
    updateUrl(params);
  }, [updateUrl]);

  // Generate trade URL with popup control
  const generateTradeUrl = useCallback((tradeId, showPopup = true) => {
    const baseUrl = window.location.origin + window.location.pathname;
    const params = new URLSearchParams();
    
    if (tradeId) params.set('tradeId', tradeId);
    if (selectedSegment) params.set('segment', selectedSegment);
    if (tradeStatus) params.set('status', tradeStatus);
    if (!showPopup) params.set('showPopup', 'false');
    
    return `${baseUrl}?${params.toString()}`;
  }, [selectedSegment, tradeStatus]);

  // Handle strategy selection with URL update
  const handleStrategySelect = useCallback((strategy) => {
    setSelectedStrategy(strategy);
    
    // Update URL with selected strategy
    if (strategy) {
      updateUrl({ tradeId: strategy.id });
    } else {
      updateUrl({ tradeId: null });
    }
    
    // Fetch live price for the strategy symbol
    if (strategy?.symbol) {
      fetchLivePrice(strategy.symbol);
    }
  }, [fetchLivePrice, updateUrl]);

  // Auto-select trade from URL using efficient API call
  const selectTradeFromUrl = useCallback(async () => {
    const urlParams = getUrlParams();
    
    if (urlParams.tradeId) {
      try {
        // Use the efficient getStrategyDetails API to find the trade
        const targetTrade = await tradeService.getStrategyDetails(urlParams.tradeId);
        
        if (targetTrade) {
          // Set the trade as selected
          setSelectedStrategy(targetTrade);
          
          // Switch to the correct segment based on the trade's segment
          if (targetTrade.segment && targetTrade.segment !== selectedSegment) {
            setSelectedSegment(targetTrade.segment);
            await fetchStrategies(targetTrade.segment); // Load with proper filtering
          }
          
          // Switch to the correct status based on the trade's status
          if (targetTrade.status && targetTrade.status !== tradeStatus) {
            setTradeStatus(targetTrade.status);
            const filteredData = applyFilters(allStrategies, targetTrade.status, activeFilters);
            setStrategies(filteredData);
          }
          
          // Scroll to the trade after a short delay
          setTimeout(() => {
            const tradeElement = document.getElementById(`trade-${urlParams.tradeId}`);
            if (tradeElement) {
              tradeElement.scrollIntoView({ 
                behavior: 'smooth', 
                block: 'center',
                inline: 'nearest'
              });
              
              // Add highlight effect
              tradeElement.classList.add('ring-2', 'ring-blue-500', 'ring-opacity-50');
              setTimeout(() => {
                tradeElement.classList.remove('ring-2', 'ring-blue-500', 'ring-opacity-50');
              }, 3000);
            }
          }, 500);
        }
      } catch (error) {
        console.error('Error fetching trade details:', error);
        setError(`Trade not found: ${urlParams.tradeId}`);
      }
    }
  }, [getUrlParams, selectedSegment, tradeStatus, allStrategies, activeFilters, applyFilters, fetchStrategies]);

  // Refresh data
  const refreshData = useCallback(() => {
    fetchSegments();
    fetchStrategies(selectedSegment);
    fetchMarketData();
  }, [fetchSegments, fetchStrategies, fetchMarketData, selectedSegment]);

  // Initialize data
  useEffect(() => {
    fetchSegments();
    fetchMarketData();
  }, [fetchSegments, fetchMarketData]);

  // Auto-select segment from URL or default to equity
  useEffect(() => {
    if (segments.length > 0 && !selectedSegment) {
      const urlParams = getUrlParams();
      
      // Check if URL has a segment parameter
      if (urlParams.segment) {
        const urlSegment = segments.find(segment => segment.id === urlParams.segment);
        if (urlSegment) {
          setSelectedSegment(urlParams.segment);
          fetchStrategies(urlParams.segment);
          return;
        }
      }
      
      // Default to equity if no URL segment specified
      const equitySegment = segments.find(segment => segment.id === 'equity');
      if (equitySegment) {
        setSelectedSegment('equity');
        fetchStrategies('equity');
      }
    }
  }, [segments, selectedSegment, fetchStrategies, getUrlParams]);

  // Load strategies when segment changes
  useEffect(() => {
    if (selectedSegment) {
      fetchStrategies(selectedSegment);
    }
  }, [selectedSegment, fetchStrategies]);

  // Set up live price updates
  useEffect(() => {
    const interval = setInterval(() => {
      strategies.forEach(strategy => {
        if (strategy.symbol) {
          fetchLivePrice(strategy.symbol);
        }
      });
    }, 5000); // Update every 5 seconds

    return () => clearInterval(interval);
  }, [strategies, fetchLivePrice]);

  // Initialize status from URL parameters (only on initial load)
  useEffect(() => {
    const urlParams = getUrlParams();
    if (urlParams.status && urlParams.status !== tradeStatus) {
      // Only update if URL has a different status than current
      filterStrategiesByStatus(urlParams.status);
    }
  }, [getUrlParams, tradeStatus, filterStrategiesByStatus]);

  // Initialize showPopup from URL parameters
  useEffect(() => {
    const urlParams = getUrlParams();
    setShowPopup(urlParams.showPopup);
  }, [getUrlParams]);

  // Handle URL-based trade selection
  useEffect(() => {
    selectTradeFromUrl();
  }, [selectTradeFromUrl]);


  // Update URL when segment changes (only if different from URL)
  useEffect(() => {
    if (selectedSegment) {
      const urlParams = getUrlParams();
      if (urlParams.segment !== selectedSegment) {
        updateUrl({ segment: selectedSegment });
      }
    }
  }, [selectedSegment, updateUrl, getUrlParams]);

  return {
    // Data
    segments,
    strategies,
    marketData,
    selectedSegment,
    selectedStrategy,
    livePrices,
    loading,
    error,
    showPopup,
    
    // Actions
    handleSegmentChange,
    handleStrategySelect,
    executeTrade,
    getRiskAnalysis,
    refreshData,
    filterStrategiesByStatus,
    
    // Filtering
    activeFilters,
    updateFilters,
    clearAllFilters,
    
    // Navigation
    navigateToTrade,
    generateTradeUrl,
    getUrlParams,
    
    // Utilities
    setSelectedSegment,
    setSelectedStrategy,
    tradeStatus,
  };
};
