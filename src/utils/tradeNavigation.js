/**
 * Utility functions for trade navigation and deep linking
 */

/**
 * Generate a direct link to a specific trade
 * @param {string} tradeId - The ID of the trade
 * @param {Object} options - Additional options
 * @param {string} options.segment - The segment (equity, fno)
 * @param {string} options.status - The status (active, closed)
 * @param {boolean} options.openModal - Whether to open the trade details modal
 * @param {string} options.baseUrl - Base URL (defaults to current origin)
 * @returns {string} - The complete URL
 */
export const generateTradeLink = (tradeId, options = {}) => {
  const {
    segment,
    status,
    openModal = false,
    baseUrl = window.location.origin
  } = options;

  const params = new URLSearchParams();
  params.set('tradeId', tradeId);
  
  if (segment) params.set('segment', segment);
  if (status) params.set('status', status);
  if (openModal) params.set('openModal', 'true');

  return `${baseUrl}/trades?${params.toString()}`;
};

/**
 * Generate a shareable link for a trade
 * @param {Object} trade - The trade object
 * @param {Object} options - Additional options
 * @returns {string} - The shareable URL
 */
export const generateShareableLink = (trade, options = {}) => {
  return generateTradeLink(trade.id, {
    segment: trade.segment,
    status: trade.status,
    ...options
  });
};

/**
 * Copy trade link to clipboard
 * @param {string} tradeId - The ID of the trade
 * @param {Object} options - Additional options
 * @returns {Promise<boolean>} - Whether the copy was successful
 */
export const copyTradeLink = async (tradeId, options = {}) => {
  try {
    const link = generateTradeLink(tradeId, options);
    await navigator.clipboard.writeText(link);
    return true;
  } catch (error) {
    console.error('Failed to copy trade link:', error);
    return false;
  }
};

/**
 * Parse URL parameters to extract trade navigation info
 * @param {string} search - The search string from URL
 * @returns {Object} - Parsed parameters
 */
export const parseTradeUrlParams = (search) => {
  const params = new URLSearchParams(search);
  return {
    tradeId: params.get('tradeId'),
    segment: params.get('segment'),
    status: params.get('status'),
    openModal: params.get('openModal') === 'true'
  };
};

/**
 * Generate a QR code data URL for a trade link
 * @param {string} tradeId - The ID of the trade
 * @param {Object} options - Additional options
 * @returns {string} - QR code data URL
 */
export const generateTradeQRCode = async (tradeId, options = {}) => {
  try {
    // You would typically use a QR code library like 'qrcode'
    // For now, we'll return a placeholder
    const link = generateTradeLink(tradeId, options);
    return `https://api.qrserver.com/v1/create-qr-code/?size=200x200&data=${encodeURIComponent(link)}`;
  } catch (error) {
    console.error('Failed to generate QR code:', error);
    return null;
  }
};

/**
 * Check if a trade link is valid
 * @param {string} tradeId - The ID of the trade
 * @param {Array} availableTrades - List of available trades
 * @returns {boolean} - Whether the trade exists
 */
export const isValidTradeLink = (tradeId, availableTrades) => {
  return availableTrades.some(trade => trade.id === tradeId);
};

/**
 * Generate notification message for new trade
 * @param {Object} trade - The new trade object
 * @returns {string} - Notification message
 */
export const generateNewTradeNotification = (trade) => {
  const link = generateTradeLink(trade.id, {
    segment: trade.segment,
    status: trade.status
  });
  
  return {
    title: `New ${trade.strategyType || trade.segment} Trade Available`,
    message: `${trade.strategy} - ${trade.symbol}`,
    link,
    tradeId: trade.id
  };
};
