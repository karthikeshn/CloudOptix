import React, { useState, useEffect } from 'react';
import { ArrowUp } from 'lucide-react';

export const ScrollToTopButton = () => {
  const [visible, setVisible] = useState(false);
  
  useEffect(() => {
    const handleScroll = (e) => {
      const t = e.target;
      // Check if the scroll event is from the main page or a Virtuoso list
      if (t && t.scrollTop !== undefined) {
        if (t.id === 'main-scroll-container' || (t.getAttribute && t.getAttribute('data-virtuoso-scroller') === 'true')) {
          if (t.scrollTop > 300) {
            setVisible(true);
          } else if (t.scrollTop <= 50) {
            setVisible(false);
          }
        }
      }
    };

    // Use capture phase (true) to intercept all scroll events on the page
    window.addEventListener('scroll', handleScroll, true);

    // Initial check just in case
    const mainEl = document.getElementById('main-scroll-container');
    if (mainEl && mainEl.scrollTop > 300) setVisible(true);

    return () => window.removeEventListener('scroll', handleScroll, true);
  }, []);

  if (!visible) return null;

  return (
    <button 
      onClick={() => {
        const el = document.getElementById('main-scroll-container');
        if (el) el.scrollTo({ top: 0, behavior: 'auto' });
        
        // Also scroll TableVirtuoso containers to top (used in Resources/Deleted tabs)
        const virtuosoScrollers = document.querySelectorAll('[data-virtuoso-scroller]');
        virtuosoScrollers.forEach(t => t.scrollTo({ top: 0, behavior: 'auto' }));
      }}
      className="fixed bottom-6 right-4 p-2 rounded-full bg-blue-600 text-white shadow-lg shadow-blue-500/20 hover:bg-blue-500 transition-all z-50 flex items-center justify-center opacity-80 hover:opacity-100"
      title="Scroll to Top"
    >
      <ArrowUp className="h-4 w-4" />
    </button>
  );
};
