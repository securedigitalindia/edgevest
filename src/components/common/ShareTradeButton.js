import React, { useState } from 'react';
import { Share2, Copy, Check, ExternalLink, MessageCircle, Mail, Twitter, Facebook, Linkedin } from 'lucide-react';

const ShareTradeButton = ({ trade, generateTradeUrl, className = '' }) => {
  const [copied, setCopied] = useState(false);
  const [showShareOptions, setShowShareOptions] = useState(false);

  const generateLink = (showPopup = true) => {
    if (generateTradeUrl) {
      return generateTradeUrl(trade.id, showPopup);
    }
    // Fallback to manual URL generation
    const params = new URLSearchParams();
    params.set('tradeId', trade.id);
    if (trade.segment) params.set('segment', trade.segment);
    if (trade.status) params.set('status', trade.status);
    if (!showPopup) params.set('showPopup', 'false');
    return `${window.location.origin}${window.location.pathname}?${params.toString()}`;
  };

  const handleCopyLink = async (showPopup = true) => {
    try {
      const link = generateLink(showPopup);
      await navigator.clipboard.writeText(link);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (error) {
      console.error('Failed to copy link:', error);
      // Fallback for older browsers
      const textArea = document.createElement('textarea');
      textArea.value = generateLink(showPopup);
      document.body.appendChild(textArea);
      textArea.select();
      document.execCommand('copy');
      document.body.removeChild(textArea);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const handleNativeShare = async () => {
    const link = generateLink(true);
    
    if (navigator.share) {
      try {
        await navigator.share({
          title: `${trade.strategy} - ${trade.symbol}`,
          text: `Check out this ${trade.segment.toUpperCase()} trade: ${trade.name}`,
          url: link
        });
      } catch (error) {
        if (error.name !== 'AbortError') {
          console.error('Error sharing:', error);
          handleCopyLink(true);
        }
      }
    } else {
      handleCopyLink(true);
    }
  };

  const handleSocialShare = (platform) => {
    const link = generateLink(true);
    const text = `Check out this ${trade.segment.toUpperCase()} trade: ${trade.strategy} - ${trade.symbol}`;
    
    let shareUrl = '';
    
    switch (platform) {
      case 'twitter':
        shareUrl = `https://twitter.com/intent/tweet?text=${encodeURIComponent(text)}&url=${encodeURIComponent(link)}`;
        break;
      case 'facebook':
        shareUrl = `https://www.facebook.com/sharer/sharer.php?u=${encodeURIComponent(link)}`;
        break;
      case 'linkedin':
        shareUrl = `https://www.linkedin.com/sharing/share-offsite/?url=${encodeURIComponent(link)}`;
        break;
      case 'whatsapp':
        shareUrl = `https://wa.me/?text=${encodeURIComponent(text + ' ' + link)}`;
        break;
      case 'telegram':
        shareUrl = `https://t.me/share/url?url=${encodeURIComponent(link)}&text=${encodeURIComponent(text)}`;
        break;
      case 'email':
        shareUrl = `mailto:?subject=${encodeURIComponent(trade.strategy + ' - ' + trade.symbol)}&body=${encodeURIComponent(text + '\n\n' + link)}`;
        break;
      default:
        return;
    }
    
    window.open(shareUrl, '_blank', 'width=600,height=400');
  };

  return (
    <div className={`relative ${className}`}>
      <button
        onClick={() => setShowShareOptions(!showShareOptions)}
        className="flex items-center gap-1 px-3 py-2 text-gray-600 border border-gray-300 rounded-lg hover:bg-blue-50 hover:text-blue-600 hover:border-blue-300 transition-all"
      >
        <Share2 size={12} />
        <span className="text-xs font-medium">Share</span>
      </button>

      {showShareOptions && (
        <div className="absolute top-full right-0 mt-2 w-64 bg-white rounded-xl shadow-xl border border-gray-200 z-20">
          <div className="p-3">
            {/* Header */}
            <div className="mb-3 pb-2 border-b border-gray-100">
              <h3 className="text-sm font-semibold text-gray-800">Share Trade</h3>
              <p className="text-xs text-gray-500">{trade.strategy} - {trade.symbol}</p>
            </div>

            {/* Copy Link Options */}
            <div className="space-y-1 mb-3">
              <button
                onClick={() => handleCopyLink(true)}
                className="w-full flex items-center gap-2 px-3 py-2 text-sm text-gray-700 hover:bg-gray-50 rounded-lg transition-colors"
              >
                {copied ? (
                  <>
                    <Check size={14} className="text-green-600" />
                    <span className="text-green-600">Copied with Popup!</span>
                  </>
                ) : (
                  <>
                    <Copy size={14} />
                    <span>Copy Link (with popup)</span>
                  </>
                )}
              </button>
              
              <button
                onClick={() => handleCopyLink(false)}
                className="w-full flex items-center gap-2 px-3 py-2 text-sm text-gray-700 hover:bg-gray-50 rounded-lg transition-colors"
              >
                <Copy size={14} />
                <span>Copy Link (no popup)</span>
              </button>
            </div>

            <div className="border-t border-gray-100 my-2"></div>

            {/* Native Share */}
            {navigator.share && (
              <>
                <button
                  onClick={handleNativeShare}
                  className="w-full flex items-center gap-2 px-3 py-2 text-sm text-gray-700 hover:bg-gray-50 rounded-lg transition-colors mb-2"
                >
                  <Share2 size={14} />
                  <span>Share via Apps</span>
                </button>
                <div className="border-t border-gray-100 my-2"></div>
              </>
            )}

            {/* Social Media */}
            <div className="mb-3">
              <p className="text-xs text-gray-500 mb-2">Share on Social Media</p>
              <div className="grid grid-cols-2 gap-1">
                <button
                  onClick={() => handleSocialShare('twitter')}
                  className="flex items-center gap-2 px-2 py-1.5 text-xs text-gray-700 hover:bg-blue-50 hover:text-blue-600 rounded-md transition-colors"
                >
                  <Twitter size={12} className="text-blue-400" />
                  <span>Twitter</span>
                </button>
                <button
                  onClick={() => handleSocialShare('facebook')}
                  className="flex items-center gap-2 px-2 py-1.5 text-xs text-gray-700 hover:bg-blue-50 hover:text-blue-600 rounded-md transition-colors"
                >
                  <Facebook size={12} className="text-blue-600" />
                  <span>Facebook</span>
                </button>
                <button
                  onClick={() => handleSocialShare('linkedin')}
                  className="flex items-center gap-2 px-2 py-1.5 text-xs text-gray-700 hover:bg-blue-50 hover:text-blue-600 rounded-md transition-colors"
                >
                  <Linkedin size={12} className="text-blue-700" />
                  <span>LinkedIn</span>
                </button>
                <button
                  onClick={() => handleSocialShare('whatsapp')}
                  className="flex items-center gap-2 px-2 py-1.5 text-xs text-gray-700 hover:bg-green-50 hover:text-green-600 rounded-md transition-colors"
                >
                  <MessageCircle size={12} className="text-green-500" />
                  <span>WhatsApp</span>
                </button>
              </div>
            </div>

            <div className="border-t border-gray-100 my-2"></div>

            {/* Other Options */}
            <div className="space-y-1">
              <button
                onClick={() => handleSocialShare('email')}
                className="w-full flex items-center gap-2 px-3 py-2 text-sm text-gray-700 hover:bg-gray-50 rounded-lg transition-colors"
              >
                <Mail size={14} />
                <span>Send via Email</span>
              </button>
              
              <a
                href={generateLink(true)}
                target="_blank"
                rel="noopener noreferrer"
                className="w-full flex items-center gap-2 px-3 py-2 text-sm text-gray-700 hover:bg-gray-50 rounded-lg transition-colors"
              >
                <ExternalLink size={14} />
                <span>Open in New Tab</span>
              </a>
            </div>
          </div>
        </div>
      )}

      {/* Click outside to close */}
      {showShareOptions && (
        <div
          className="fixed inset-0 z-10"
          onClick={() => setShowShareOptions(false)}
        />
      )}
    </div>
  );
};

export default ShareTradeButton;
