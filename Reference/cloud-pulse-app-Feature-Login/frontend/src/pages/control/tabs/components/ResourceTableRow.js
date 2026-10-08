import React from 'react';
import { ChevronDown, ChevronRight, Clock, Eye, EyeOff } from 'lucide-react';
import { ResourceIcon } from '../../../../components/ui/ResourceIcon';

export const ResourceTableRow = React.memo(({
  r,
  isGroupView,
  toggleRow,
  setDetailResource,
  getStatusStyle,
  setModalState,
  isSettingsMode = false,
  handleToggle = null
}) => {
  let tags = {};
  try {
    if (r.tags_json) tags = typeof r.tags_json === 'string' ? JSON.parse(r.tags_json) : r.tags_json;
  } catch (e) { }

  const isAsgManaged = !!tags['aws:autoscaling:groupName'];
  const asgName = tags['aws:autoscaling:groupName'];
  const isScaleToZero = r.control_type === 'SCALE_TO_ZERO';

  return (
    <>
      <td className="p-4 truncate" style={{ paddingLeft: r._level ? `${r._level * 24 + 16}px` : '16px' }}>
        <div className="flex items-center gap-3">
          {isGroupView && r._isExpandable ? (
            <button onClick={(e) => { e.stopPropagation(); toggleRow(r.resource_id); }} className="p-0.5 hover:bg-zinc-800 rounded text-zinc-400">
              {r._isExpanded ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
            </button>
          ) : (
            isGroupView && <div className="w-5" />
          )}
          <div className="p-1.5 rounded bg-zinc-800/50 shrink-0">
            <ResourceIcon serviceType={r.service_type} className="w-3.5 h-3.5 text-zinc-400" />
          </div>
          <div className="min-w-0">
            <div
              className="text-[13px] font-semibold text-zinc-200 truncate cursor-pointer hover:text-blue-400 hover:underline transition-colors"
              onClick={() => setDetailResource(r)}
            >
              {r.name}
            </div>
            {r.resource_id && r.resource_id !== r.name && (
              <div className="text-[10px] text-zinc-500 font-mono mt-0.5 truncate">
                {r.resource_id}
              </div>
            )}
          </div>
        </div>
      </td>
      <td className="p-4 text-[13px] text-zinc-400 font-medium uppercase">{r.service_type}</td>
      <td className="p-4 text-[13px] text-zinc-400 font-medium whitespace-nowrap">{r.region}</td>
      <td className="p-4 flex flex-col items-start gap-1 justify-center min-h-[50px]">
        <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${getStatusStyle(r.status)}`}>
          {r.status}
        </span>
        {isAsgManaged && (
          <span
            className="px-2 py-0.5 rounded text-[10px] font-bold bg-zinc-800 text-zinc-400 border border-zinc-700 cursor-help"
            title={`Power actions for this instance are controlled by Auto Scaling Group: ${asgName}`}
          >
            ASG Managed
          </span>
        )}
      </td>
      <td className="p-4 text-[13px] text-zinc-400">
        {isSettingsMode ? (
          <span className="text-zinc-500 italic text-xs">Settings Managed</span>
        ) : r.schedule?.is_automation_enabled ? (
          <div className="flex items-center gap-1.5 text-blue-400 font-medium">
            <Clock className="h-3 w-3 shrink-0" />
            <span className="font-mono">{r.schedule.start_time} - {r.schedule.stop_time}</span>
          </div>
        ) : (
          <span className="text-zinc-500 italic text-xs">Manual</span>
        )}
      </td>
      <td className="p-4 text-right">
        <div className="flex justify-end gap-2">
          {isSettingsMode ? (
            <button
              onClick={() => handleToggle(r)}
              className={`inline-flex items-center gap-1.5 px-3 py-1.5 text-[11px] font-semibold rounded-md transition-colors ${r.is_visible
                  ? 'bg-zinc-800 text-zinc-300 hover:text-white border border-zinc-700 hover:bg-zinc-700'
                  : 'bg-zinc-900 text-zinc-500 border border-zinc-800 hover:bg-zinc-800 hover:text-zinc-400'
                }`}
            >
              {r.is_visible ? (
                <><Eye className="h-3 w-3" /> Visible</>
              ) : (
                <><EyeOff className="h-3 w-3" /> Hidden</>
              )}
            </button>
          ) : !(!r.parent_resource_id && ['EKS', 'ECS', 'BEANSTALK'].includes((r.service_type || '').toUpperCase())) ? (
            <>
              <button
                onClick={() => setModalState({ isOpen: true, mode: 'schedule', resource: r })}
                className="px-2.5 py-1 text-[11px] font-medium bg-zinc-800 text-zinc-300 hover:text-white rounded border border-zinc-700 hover:bg-zinc-700 transition-colors"
              >
                Schedule
              </button>
              {['RUNNING', 'AVAILABLE'].includes((r.status || '').toUpperCase()) ? (
                <button
                  onClick={() => setModalState({ isOpen: true, mode: 'stop', resource: r })}
                  disabled={isAsgManaged || ['STARTING', 'PENDING', 'STOPPING', 'TERMINATING'].includes((r.status || '').toUpperCase())}
                  title={isAsgManaged ? `Controlled by ASG: ${asgName}` : ''}
                  className={`px-2.5 py-1 text-[11px] font-bold rounded transition-colors whitespace-nowrap ${(isAsgManaged || ['STARTING', 'PENDING', 'STOPPING', 'TERMINATING'].includes((r.status || '').toUpperCase()))
                    ? 'bg-zinc-800 text-zinc-600 border border-zinc-800 cursor-not-allowed'
                    : 'bg-red-600/10 text-red-500 hover:bg-red-600/20 border border-red-600/20'
                    }`}
                >
                  {isScaleToZero ? 'SCALE TO ZERO' : 'STOP'}
                </button>
              ) : (
                <button
                  onClick={() => setModalState({ isOpen: true, mode: 'start', resource: r })}
                  disabled={isAsgManaged || ['STARTING', 'PENDING', 'STOPPING', 'TERMINATING'].includes((r.status || '').toUpperCase())}
                  title={isAsgManaged ? `Controlled by ASG: ${asgName}` : ''}
                  className={`px-2.5 py-1 text-[11px] font-bold rounded transition-colors whitespace-nowrap ${(isAsgManaged || ['STARTING', 'PENDING', 'STOPPING', 'TERMINATING'].includes((r.status || '').toUpperCase()))
                    ? 'bg-zinc-800 text-zinc-600 border border-zinc-800 cursor-not-allowed'
                    : 'bg-green-600/10 text-green-500 hover:bg-green-600/20 border border-green-600/20'
                    }`}
                >
                  START
                </button>
              )}
            </>
          ) : (
            <span
              className="px-2.5 py-1 text-[10px] font-medium text-zinc-500 bg-zinc-900/50 border border-zinc-800 rounded cursor-help whitespace-nowrap"
              title="This is a structural parent container. Expand this row to schedule or control its underlying compute resources."
            >
              Expand to {r.service_type === 'BEANSTALK' ? 'Control Application' : r.service_type === 'ASG' ? 'View Instances' : 'Control Cluster'}
            </span>
          )}
        </div>
      </td>
    </>
  );
});
