import React from 'react';
import { createPortal } from 'react-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { Server, X, Globe, Tag as TagIcon, History } from 'lucide-react';
import { formatDynamicLocalTime } from '../../utils/dateFormatter';
import { formatType, formatIdentifier, formatName } from '../../utils/ui-utils';
import { EmptyState } from '../../components/ui/EmptyState';

const colorizeJson = (jsonObj) => {
  if (!jsonObj) return '';
  
  // Clone to avoid mutating the original state
  const cleanObj = { ...jsonObj };
  // Automatically parse stringified tags so they format as a proper nested JSON tree
  if (typeof cleanObj.tags === 'string') {
    try { cleanObj.tags = JSON.parse(cleanObj.tags); } catch(e) {}
  }

  const jsonStr = JSON.stringify(cleanObj, null, 2);
  
  return jsonStr.split('\n').map((line, i) => {
    // Basic regex for JSON syntax highlighting
    let coloredLine = line;
    // Keys (strings before colon)
    coloredLine = coloredLine.replace(/"([^"]+)":/g, '<span class="text-sky-300">"$1"</span>:');
    // String values
    coloredLine = coloredLine.replace(/: "([^"]*)"/g, ': <span class="text-zinc-100">"$1"</span>');
    // Numbers
    coloredLine = coloredLine.replace(/: (-?\d+\.?\d*)/g, ': <span class="text-emerald-300">$1</span>');
    // Booleans
    coloredLine = coloredLine.replace(/: (true|false|null)/g, ': <span class="text-purple-400 font-medium">$1</span>');

    return (
      <div key={i} className="table-row">
        <span className="table-cell text-zinc-600 select-none pr-4 text-right border-r border-zinc-800">{i + 1}</span>
        <span className="table-cell pl-4 break-words whitespace-pre-wrap" dangerouslySetInnerHTML={{ __html: coloredLine }} />
      </div>
    );
  });
};

export function ResourceDetailModal({ selectedResource, setSelectedResource }) {
  const [activeTab, setActiveTab] = React.useState('overview');

  React.useEffect(() => {
    if (selectedResource) setActiveTab('overview');
  }, [selectedResource]);

  return createPortal(
    <AnimatePresence>
      {selectedResource && (
        <motion.div 
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.15 }}
          className="fixed inset-0 z-[9999] flex items-center justify-center w-screen h-screen bg-black/70 backdrop-blur-sm"
        >
          <motion.div 
            initial={{ opacity: 0, scale: 0.98, y: 8 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.98, y: 8 }}
            transition={{ type: "spring", damping: 25, stiffness: 300 }}
            className="bg-[#131315] border border-[#26262b] rounded-xl w-full max-w-[480px] shadow-2xl overflow-hidden flex flex-col h-[600px] max-h-[85vh]"
          >
        <div className="px-4 py-3 bg-[#131315] flex items-center justify-between shrink-0">
          <div>
            <h2 className="text-[13px] font-bold text-zinc-100 flex items-center gap-2">
              <Server className="h-3.5 w-3.5 text-blue-400" />
              {formatName(selectedResource.name, selectedResource.native_id, selectedResource.provider) || formatIdentifier(selectedResource.native_id, selectedResource.provider)}
            </h2>
            <p className="text-[11px] text-zinc-500 mt-1 uppercase tracking-wider font-semibold">
              {formatType(selectedResource.resource_type, selectedResource.provider)}
            </p>
          </div>
          <motion.button 
            whileHover={{ scale: 1.05, backgroundColor: '#26262b' }}
            whileTap={{ scale: 0.95 }}
            onClick={() => setSelectedResource(null)} 
            className="p-1.5 text-zinc-500 rounded-md transition-colors"
          >
            <X className="h-4 w-4" />
          </motion.button>
        </div>

        <div className="px-4 pb-3 border-b border-[#26262b] bg-[#131315] shrink-0">
          <div className="flex items-center gap-1 bg-[#0a0a0f] p-1 rounded-lg w-fit border border-[#26262b]">
            <button 
              onClick={() => setActiveTab('overview')} 
              className={`px-3 py-1 text-[11px] font-bold rounded-md transition-colors relative z-10 ${activeTab === 'overview' ? 'text-white' : 'text-zinc-500 hover:text-zinc-300'}`}
            >
              {activeTab === 'overview' && <motion.div layoutId="detailTab" className="absolute inset-0 bg-[#26262b] rounded-md z-[-1]" />}
              Overview
            </button>
            <button 
              onClick={() => setActiveTab('json')} 
              className={`px-3 py-1 text-[11px] font-bold rounded-md transition-colors relative z-10 ${activeTab === 'json' ? 'text-white' : 'text-zinc-500 hover:text-zinc-300'}`}
            >
              {activeTab === 'json' && <motion.div layoutId="detailTab" className="absolute inset-0 bg-[#26262b] rounded-md z-[-1]" />}
              Raw JSON
            </button>
          </div>
        </div>

        <div className="p-4 overflow-y-auto bg-[#0a0a0f] flex-1 min-h-0">
          {activeTab === 'overview' ? (
            <div className="space-y-4">
              
              <div className="bg-[#161b22] p-3 rounded-xl border border-[#26262b] shadow-sm">
                <label className="text-[10px] uppercase tracking-wider text-zinc-500 font-bold mb-1 block">Resource Identifier (ARN)</label>
                <div className="font-mono text-[11px] text-zinc-300 break-all select-all">
                  {selectedResource.native_id}
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div className="bg-[#161b22] p-3 rounded-xl border border-[#26262b] shadow-sm">
                  <label className="text-[10px] uppercase tracking-wider text-zinc-500 font-bold mb-1 block">Region</label>
                  <p className="text-[12px] font-bold text-zinc-200 flex items-center gap-1.5">
                    <Globe className="h-3.5 w-3.5 text-zinc-500" /> {selectedResource.region}
                  </p>
                </div>
                <div className="bg-[#161b22] p-3 rounded-xl border border-[#26262b] shadow-sm">
                  <label className="text-[10px] uppercase tracking-wider text-zinc-500 font-bold mb-1 block">Billable Status</label>
                  <p className="text-[12px] font-bold text-zinc-200 flex items-center gap-2">
                    <span className={`inline-block w-2 h-2 rounded-full ${selectedResource.billable ? 'bg-zinc-200' : 'bg-zinc-600'}`} />
                    {selectedResource.billable ? 'Billable' : 'Non-Billable'}
                  </p>
                </div>
                <div className="bg-[#161b22] p-3 rounded-xl border border-[#26262b] shadow-sm">
                  <label className="text-[10px] uppercase tracking-wider text-zinc-500 font-bold mb-1 block">First Seen</label>
                  <p className="text-[12px] font-bold text-zinc-300">
                    {formatDynamicLocalTime(selectedResource.first_seen_date)}
                  </p>
                </div>
                {selectedResource.deleted_at && (
                  <div className="bg-[#161b22] p-3 rounded-xl border border-[#26262b] shadow-sm">
                    <label className="text-[10px] uppercase tracking-wider text-zinc-500 font-bold mb-1 flex items-center gap-1.5"><History className="h-3 w-3" /> Deleted At</label>
                    <p className="text-[12px] font-bold text-red-400">
                      {formatDynamicLocalTime(selectedResource.deleted_at)}
                    </p>
                  </div>
                )}
              </div>

              <div>
                <div className="flex items-center gap-2 mb-2">
                  <TagIcon className="h-3.5 w-3.5 text-zinc-500" />
                  <h3 className="text-[11px] font-bold uppercase tracking-wider text-zinc-400">{(selectedResource.provider || 'cloud')} Tags</h3>
                </div>
                {(() => {
                  try {
                    const tags = typeof selectedResource.tags === 'string' ? JSON.parse(selectedResource.tags) : (selectedResource.tags || {});
                    const tagKeys = Object.keys(tags);
                    if (tagKeys.length === 0) return <EmptyState icon={TagIcon} message="No tags found on this resource." height="h-[100px]" />;
                    return (
                      <div className="grid grid-cols-2 gap-3">
                        {tagKeys.map(k => (
                          <div key={k} className="bg-[#161b22] border border-[#26262b] rounded-lg flex overflow-hidden shadow-sm">
                            <div className="px-3 py-2 bg-[#1c2128] border-r border-[#26262b] text-[10px] font-bold text-zinc-400 w-[40%] truncate" title={k}>
                              {k}
                            </div>
                            <div className="px-3 py-2 text-[11px] text-zinc-300 truncate font-mono w-[60%]" title={tags[k]}>
                              {tags[k]}
                            </div>
                          </div>
                        ))}
                      </div>
                    );
                  } catch (e) {
                    return <div className="text-xs text-zinc-500">Could not parse tags.</div>;
                  }
                })()}
              </div>
            </div>
          ) : (
            <div className="border border-[#26262b] rounded-lg shadow-sm bg-[#0a0a0f]">
              <div className="p-4 m-0 text-[11px] font-mono table w-full">
                {colorizeJson(selectedResource)}
              </div>
            </div>
          )}
        </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>,
    document.body
  );
}
