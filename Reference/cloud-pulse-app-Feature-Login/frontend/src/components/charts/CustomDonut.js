import React from 'react';
import { PieChart, Pie, Cell, ResponsiveContainer, Sector } from 'recharts';
import { formatType } from '../../utils/ui-utils';

const renderActiveShape = (props) => {
  const { cx, cy, innerRadius, outerRadius, startAngle, endAngle, fill } = props;
  return (
    <g>
      <Sector cx={cx} cy={cy} innerRadius={innerRadius} outerRadius={outerRadius + 6} startAngle={startAngle} endAngle={endAngle} fill={fill} />
    </g>
  );
};

export function CustomDonut({ data, colors, onSliceClick, isAnimationActive = true, height = 140, innerRadius = 35, outerRadius = 55 }) {
  const [activeIndex, setActiveIndex] = React.useState(-1);
  const activeItem = activeIndex >= 0 ? data[activeIndex] : null;

  return (
    <div className="relative">
      {activeItem && (
        <div className="absolute -top-3 right-0 text-right z-10 pointer-events-none animate-in fade-in duration-200">
          <div className="text-[11px] font-bold truncate max-w-[150px]" style={{ color: colors[activeIndex % colors.length] }}>
            {formatType(activeItem.name)}
          </div>
        </div>
      )}
       
      {/* Center Total / Hover Value */}
      <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
        <span className="text-[13px] font-bold text-white mt-2">
          {activeItem ? activeItem.value : data.reduce((acc, curr) => acc + curr.value, 0)}
        </span>
        <span className="text-[9px] uppercase tracking-widest font-bold text-zinc-500">
          Total
        </span>
      </div>
      <ResponsiveContainer width="100%" height={height}>
        <PieChart>
          <Pie
            data={data}
            cx="50%" cy="50%" innerRadius={innerRadius} outerRadius={outerRadius}
            dataKey="value" paddingAngle={2} strokeWidth={0}
            activeIndex={activeIndex}
            activeShape={renderActiveShape}
            onMouseEnter={(_, index) => setActiveIndex(index)}
            onMouseLeave={() => setActiveIndex(-1)}
            onClick={(entry) => onSliceClick && onSliceClick(entry.name)}
            isAnimationActive={isAnimationActive}
            animationDuration={1200}
            cursor="pointer"
          >
            {data.map((_, i) => <Cell key={i} fill={colors[i % colors.length]} />)}
          </Pie>
        </PieChart>
      </ResponsiveContainer>
    </div>
  );
}
