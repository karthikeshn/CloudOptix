
export const formatDynamicLocalTime = (dateString, format = 'full') => {
  if (!dateString) return 'Unknown';
  
  let dString = String(dateString);
  
  // Remove the literal ' IST' if it exists so Date can parse it properly
  dString = dString.replace(' IST', '+05:30');

  // If the backend returns naive string datetimes intended to be IST
  // we append +05:30 or Z so the browser parses it correctly before converting to local.
  if (!dString.includes('+') && !dString.includes('Z')) {
    if (dString.includes('T')) {
      dString += 'Z';
    } else {
      dString += '+05:30';
    }
  }
  
  const date = new Date(dString);
  if (isNaN(date.getTime())) {
    // Fallback if parsing fails, just return the raw string
    return dateString;
  }

  if (format === 'timeOnly') {
    return date.toLocaleTimeString(undefined, { 
      hour: '2-digit', minute: '2-digit', hour12: false 
    });
  }

  if (format === 'short') {
    return date.toLocaleString(undefined, {
      weekday: 'short', hour: '2-digit', hour12: false 
    });
  }
  
  if (format === 'dateOnly') {
    return date.toLocaleDateString(undefined, { 
      month: 'short', day: 'numeric' 
    });
  }

  // default 'full'
  return date.toLocaleString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false
  });
};
